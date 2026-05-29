import os
import re
import asyncio
import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional
from backend.config import get_path, settings
from backend.database import get_db
from backend.models import ConfigField, ConfigValidationResult, FullConfigValidation

logger = logging.getLogger("ML.ConfigEditor")

XSI = 'http://www.w3.org/2001/XMLSchema-instance'
XSD = 'http://www.w3.org/2001/XMLSchema'
XMLNS_ATTR = f'xmlns:xsi="{XSI}" xmlns:xsd="{XSD}"'

# ============================================================================
# XML file definitions: (field_name, default_value, comment_or_None)
# ============================================================================

_XML_FILES_DEF = {
    "GeneralSettings.xml": {
        "root": "GeneralSettingsDefinition",
        "fields": [
            ("ServerName", "KSP LMP Server", "Name of the server. Max 30 char"),
            ("Description", "", "Description of the server. Max 200 char"),
            ("CountryCode", "", None),
            ("WebsiteText", "LMP", None),
            ("Website", "lunamultiplayer.com", None),
            ("Password", "", "Password to connect. Leave it empty to have a public server"),
            ("AdminPassword", "", "Admin password to do admin commands"),
            ("ServerMotd", "Welcome!", None),
            ("PrintMotdInChat", "false", None),
            ("MaxPlayers", "8", None),
            ("MaxUsernameLength", "15", None),
            ("AutoDekessler", "30", None),
            ("AutoNuke", "0", None),
            ("Cheats", "true", None),
            ("AllowSackKerbals", "false", None),
            ("ConsoleIdentifier", "Server", None),
            ("GameDifficulty", "Normal", None),
            ("GameMode", "Sandbox", None),
            ("ModControl", "true", None),
            ("NumberOfAsteroids", "5", None),
            ("NumberOfComets", "5", None),
            ("TerrainQuality", "High", None),
            ("SafetyBubbleDistance", "100", None),
            ("MaxVesselParts", "200", None),
        ],
    },
    "ConnectionSettings.xml": {
        "root": "ConnectionSettingsDefinition",
        "fields": [
            ("ListenAddress", "[::]", None),
            ("Port", "8800", None),
            ("HearbeatMsInterval", "5000", None),
            ("ConnectionMsTimeout", "30000", None),
            ("Upnp", "true", None),
            ("UpnpMsTimeout", "5000", None),
            ("MaximumTransmissionUnit", "1408", None),
            ("AutoExpandMtu", "false", None),
        ],
    },
    "GameplaySettings.xml": {
        "root": "GameplaySettingsDefinition",
        "fields": [
            ("CanRevert", "true", None),
            ("MissingCrewsRespawn", "true", None),
            ("RespawnTime", "2", None),
            ("AutoHireCrews", "false", None),
            ("BypassEntryPurchaseAfterResearch", "true", None),
            ("IndestructibleFacilities", "false", None),
            ("AllowStockVessels", "false", None),
            ("AllowOtherLaunchSites", "true", None),
            ("ReentryHeatScale", "1", None),
            ("ResourceAbundance", "1", None),
            ("CommNetwork", "true", None),
            ("StartingFunds", "25000", None),
            ("StartingScience", "0", None),
            ("StartingReputation", "0", None),
            ("ScienceGainMultiplier", "1", None),
            ("FundsGainMultiplier", "1", None),
            ("RepGainMultiplier", "1", None),
            ("FundsLossMultiplier", "1", None),
            ("RepLossMultiplier", "1", None),
            ("RepLossDeclined", "1", None),
            ("KerbalExp", "true", None),
            ("ImmediateLevelUp", "false", None),
            ("AllowNegativeCurrency", "false", None),
        ],
    },
    "WarpSettings.xml": {
        "root": "WarpSettingsDefinition",
        "fields": [
            ("WarpMode", "SUBSPACE", None),
        ],
    },
    "IntervalSettings.xml": {
        "root": "IntervalSettingsDefinition",
        "fields": [
            ("VesselUpdatesMsInterval", "100", None),
            ("SecondaryVesselUpdatesMsInterval", "500", None),
            ("SendReceiveThreadTickMs", "10", None),
            ("MainTimeTick", "30", None),
            ("BackupIntervalMs", "300000", None),
            ("GcMinutesInterval", "60", None),
        ],
    },
    "CraftSettings.xml": {
        "root": "CraftSettingsDefinition",
        "fields": [
            ("MinCraftLibraryRequestIntervalMs", "5000", None),
            ("MaxCraftsPerUser", "30", None),
            ("MaxCraftFolders", "5", None),
        ],
    },
    "DebugSettings.xml": {
        "root": "DebugSettingsDefinition",
        "fields": [
            ("SimulatedLossChance", "0", None),
            ("SimulatedDuplicatesChance", "0", None),
            ("MaxSimulatedRandomLatencyMs", "0", None),
            ("MinSimulatedLatencyMs", "0", None),
            ("CustomMasterServer", "", None),
        ],
    },
    "DedicatedServerSettings.xml": {
        "root": "DedicatedServerSettingsDefinition",
        "fields": [
            ("UseRainbowEffect", "false", None),
            ("Red", "255", None),
            ("Green", "255", None),
            ("Blue", "255", None),
        ],
    },
    "LogSettings.xml": {
        "root": "LogSettingsDefinition",
        "fields": [
            ("LogLevel", "Debug", None),
            ("ExpireLogs", "0", None),
            ("UseUtcTimeInLog", "false", None),
        ],
    },
    "MasterServerSettings.xml": {
        "root": "MasterServerSettingsDefinition",
        "fields": [
            ("RegisterWithMasterServer", "true", None),
            ("MasterServerRegistrationMsInterval", "5000", None),
        ],
    },
    "ScreenshotSettings.xml": {
        "root": "ScreenshotSettingsDefinition",
        "fields": [
            ("MinScreenshotIntervalMs", "30000", None),
            ("MaxScreenshotWidth", "1280", None),
            ("MaxScreenshotHeight", "720", None),
            ("MaxScreenshotsPerUser", "100", None),
            ("MaxScreenshotsFolders", "5", None),
        ],
    },
    "WebsiteSettings.xml": {
        "root": "WebsiteSettingsDefinition",
        "fields": [
            ("EnableWebsite", "false", None),
            ("ListenAddress", "[::]", None),
            ("Port", "8900", None),
            ("RefreshIntervalMs", "2000", None),
        ],
    },
}

XML_FILENAMES = list(_XML_FILES_DEF.keys())


def _xml_escape(text: str) -> str:
    text = str(text)
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    text = text.replace('"', "&quot;")
    text = text.replace("'", "&apos;")
    return text


# ============================================================================
# SETTINGS_KNOWLEDGE_BASE
# ============================================================================

SETTINGS_KNOWLEDGE_BASE = {
    "port": {
        "type": "int",
        "label": "服务器端口",
        "category": "network",
        "description": "LMP 服务器监听的端口号。客户端将通过此端口连接到服务器。",
        "tooltip": "决定了客户端连接时使用的端口。\n\n是什么：服务器监听连接的网络端口\n为什么：端口被占用或防火墙未放行会导致玩家无法连接\n怎么做：建议默认8800，如有冲突可改为8801-8899。确保防火墙放行此端口。",
        "min_value": 1024,
        "max_value": 65535,
        "required": True,
        "error_message": "无效端口，请输入 1024-65535 之间的数字",
        "xml_file": "ConnectionSettings.xml",
        "xml_field": "Port",
    },
    "ip": {
        "type": "string",
        "label": "监听 IP 地址",
        "category": "network",
        "description": "服务器绑定的本地 IP 地址。",
        "tooltip": "是什么：服务器监听的网络接口地址\n为什么：设为 0.0.0.0 表示接受所有来源连接；设为 127.0.0.1 将仅接受本机连接\n怎么做：公网服务器设 0.0.0.0，使用 EasyTier 内网穿透时设为虚拟IP",
        "required": True,
        "warning_if_empty": True,
        "warning_message": "建议设置为 0.0.0.0 以接受所有连接，或设为 EasyTier 分配的虚拟 IP。",
        "xml_file": "ConnectionSettings.xml",
        "xml_field": "ListenAddress",
    },
    "maxPlayers": {
        "type": "int",
        "label": "最大玩家数",
        "category": "game",
        "description": "同时允许在线的最大玩家数量。",
        "tooltip": "是什么：服务器的玩家容量上限\n为什么：过多玩家会增加带宽和CPU压力，家庭宽带上限值不宜过高\n怎么做：家庭宽带建议 4-8 人，服务器建议 16-32 人",
        "min_value": 1,
        "max_value": 255,
        "required": True,
        "error_message": "请输入 1-255 之间的数字",
        "xml_file": "GeneralSettings.xml",
        "xml_field": "MaxPlayers",
    },
    "name": {
        "type": "string",
        "label": "服务器名称",
        "category": "game",
        "description": "在服务器列表中显示的服务器的名称。",
        "tooltip": "是什么：你的服务器在LMP客户端列表中的显示名称\n为什么：好的名称能吸引玩家加入\n怎么做：中文名也是支持的，也可以用颜色代码如 <color=#00ff00>服务器名</color>",
        "required": True,
        "warning_if_empty": True,
        "warning_message": "服务器名称不能为空，否则玩家将无法识别你的服务器。",
        "xml_file": "GeneralSettings.xml",
        "xml_field": "ServerName",
    },
    "motd": {
        "type": "string",
        "label": "欢迎语 (MOTD)",
        "category": "game",
        "description": "玩家进入服务器后看到的欢迎消息。",
        "tooltip": "是什么：Message Of The Day 的缩写，服务器每日消息\n为什么：可以向新玩家展示规则、公告或欢迎信息\n怎么做：支持多行消息，用\\n换行。保持友善和简洁。",
        "xml_file": "GeneralSettings.xml",
        "xml_field": "ServerMotd",
    },
    "password": {
        "type": "string",
        "label": "服务器密码",
        "category": "network",
        "description": "玩家连接服务器时需要的密码。留空表示无密码。",
        "tooltip": "是什么：服务器访问密码\n为什么：防止不认识的玩家加入\n怎么做：建议使用 4-16 位字母数字组合。⚠️ 密码通过明文传输，请勿使用重要密码。",
        "xml_file": "GeneralSettings.xml",
        "xml_field": "Password",
    },
    "updateInterval": {
        "type": "int",
        "label": "更新间隔 (毫秒)",
        "category": "sync",
        "description": "服务器每多少毫秒刷新一次飞船位置信息。",
        "tooltip": "是什么：服务器向客户端推送更新的频率\n为什么：数值越小飞船飞行越丝滑，但带宽和CPU占用越高\n怎么做：家庭宽带建议 80-120ms，专业服务器可降到 30-50ms。低于 20ms 容易导致性能问题。",
        "min_value": 10,
        "max_value": 1000,
        "required": True,
        "error_message": "请输入 10-1000 之间的数字",
        "xml_file": "ConnectionSettings.xml",
        "xml_field": "HearbeatMsInterval",
    },
    "autoDekessler": {
        "type": "bool",
        "label": "自动清理太空垃圾",
        "category": "game",
        "description": "是否自动清除太空垃圾。",
        "tooltip": "是什么：自动删除标记为'太空垃圾'的飞船\n为什么：Kerbal玩家经常产生大量太空垃圾,自动清理可以保持服务器性能\n怎么做：推荐开启,设置合理的保留时间避免误删有价值物品",
        "xml_file": "GeneralSettings.xml",
        "xml_field": "AutoDekessler",
    },
    "dekesslerMinTime": {
        "type": "int",
        "label": "垃圾清理最小保留时间 (分钟)",
        "category": "game",
        "description": "飞船成为太空垃圾后,至少保留多少分钟才允许被自动清理。",
        "tooltip": "是什么：太空垃圾在被自动清理前必须存在的最短时间\n为什么：防止玩家不小心丢弃的物品被立即清理,给玩家反悔的机会\n怎么做：建议设置 30-60 分钟",
        "min_value": 1,
        "xml_file": "GeneralSettings.xml",
        "xml_field": "AutoDekessler",
    },
    "modControlMode": {
        "type": "select",
        "label": "模组控制模式",
        "category": "mod",
        "description": "LMP 的模组控制策略。",
        "tooltip": "是什么：控制服务端如何管理玩家的模组\n为什么：防止玩家使用作弊模组或与服务器不兼容的模组\n怎么做：\n- DISABLED (禁用): 不检查模组\n- BLACKLIST (黑名单): 禁用列表中的模组\n- WHITELIST (白名单): 只允许列表中的模组",
        "options": ["DISABLED", "BLACKLIST", "WHITELIST"],
        "required": True,
        "warning_if_whitelist_empty": True,
        "warning_message": "警告：已启用白名单模式但未添加任何必需 Mod，这将导致所有玩家无法进入！请在'模组商店'中添加至少一个模组到白名单。",
        "xml_file": "GeneralSettings.xml",
        "xml_field": "ModControl",
    },
    "totalSaveGameBans": {
        "type": "int",
        "label": "存档总数上限（Bans 模式）",
        "category": "game",
        "description": "以Bans模式运行时允许的总存档数上限。",
        "tooltip": "是什么：限制服务器上每种飞船类型允许的最大存档数量\n为什么：防止资源无限复制导致服务器过载\n怎么做：一般设置为 10-20 即可",
        "min_value": 1,
        "xml_file": None,
        "xml_field": None,
    },
    "registerPrivateIp": {
        "type": "bool",
        "label": "注册内网 IP",
        "category": "network",
        "description": "是否将内网IP也注册到主服务器列表。",
        "tooltip": "是什么：是否向LMP主服务器同时上报内网IP\n为什么：局域网玩家可以直接通过内网IP连接，延迟更低\n怎么做：局域网服务器建议开启，公网服务器可关闭",
        "xml_file": None,
        "xml_field": None,
    },
    "heartbeatMs": {
        "type": "int",
        "label": "心跳间隔 (毫秒)",
        "category": "sync",
        "description": "服务器向 LMP 主服务器发送心跳的间隔。",
        "tooltip": "是什么：服务器定期向LMP官方列表发送'我还活着'信号\n为什么：保持心跳可以让你的服务器显示在公开列表中\n怎么做：建议默认值5000ms，过长可能导致服务器被标记为离线",
        "min_value": 100,
        "max_value": 60000,
        "error_message": "请输入 100-60000 之间的数字",
        "xml_file": "ConnectionSettings.xml",
        "xml_field": "HearbeatMsInterval",
    },
    "spectateTimeout": {
        "type": "int",
        "label": "观察者超时 (秒)",
        "category": "game",
        "description": "玩家处于观察模式时，多久无操作后踢出。",
        "tooltip": "是什么：观察者模式下的超时踢出时间\n为什么：防止玩家占用服务器资源却不参与游戏\n怎么做：一般设置为 600-1800 秒（10-30分钟）",
        "min_value": 0,
        "xml_file": None,
        "xml_field": None,
    },
    "numberOfAsteroids": {
        "type": "int",
        "label": "小行星数量",
        "category": "game",
        "description": "服务器生成的小行星总数。",
        "tooltip": "是什么：Kerbin轨道上生成的未知物体总数\n为什么：小行星会影响性能和存档大小\n怎么做：一般保持默认 100 即可，高配置服务器可适当增加",
        "min_value": 0,
        "xml_file": "GeneralSettings.xml",
        "xml_field": "NumberOfAsteroids",
    },
    "cheats": {
        "type": "bool",
        "label": "允许作弊",
        "category": "game",
        "description": "是否允许玩家使用作弊菜单。",
        "tooltip": "是什么：是否开放游戏内置的Debug/Cheat菜单给玩家\n为什么：开放作弊会严重破坏联机平衡\n怎么做：联机服强烈建议关闭 (False)",
        "xml_file": "GeneralSettings.xml",
        "xml_field": "Cheats",
    },
    "saveInterval": {
        "type": "int",
        "label": "存档间隔 (毫秒)",
        "category": "sync",
        "description": "服务器自动保存的间隔时间。",
        "tooltip": "是什么：服务器自动存盘到硬盘的频率\n为什么：间隔太小会增加磁盘IO，间隔太大可能在崩溃时丢失更多进度\n怎么做：建议 300000 (5分钟) 到 600000 (10分钟)",
        "min_value": 60000,
        "max_value": 3600000,
        "error_message": "请输入 60000-3600000 之间的数字（1分钟到1小时）",
        "xml_file": "IntervalSettings.xml",
        "xml_field": "BackupIntervalMs",
    },
    "warpMode": {
        "type": "select",
        "label": "时间加速模式",
        "category": "game",
        "description": "联机时间加速的控制模式。",
        "tooltip": "是什么：控制多人游戏中时间加速的行为\n为什么：在KSP中时间加速是核心机制,联机时需协调所有玩家\n怎么做：\n- NONE: 完全禁用加速\n- SUBSPACE: 每个玩家独立加速\n- MCW_FORCE: 强制全服同步加速",
        "options": ["NONE", "SUBSPACE", "MCW_FORCE"],
        "xml_file": "WarpSettings.xml",
        "xml_field": "WarpMode",
    },
    "gameMode": {
        "type": "select",
        "label": "游戏模式",
        "category": "game",
        "description": "服务器的游戏模式。",
        "tooltip": "是什么：决定了资源消耗和科技树的规则\n为什么：不同模式难度差异巨大，影响玩家体验\n怎么做：\n- Sandbox: 沙盒模式(无限资源)\n- Career: 生涯模式(资源管理)\n- Science: 科学模式",
        "options": ["Sandbox", "Career", "Science"],
        "xml_file": "GeneralSettings.xml",
        "xml_field": "GameMode",
    },
    "allowStockVessels": {
        "type": "bool",
        "label": "允许原版飞船",
        "category": "game",
        "description": "是否允许使用游戏自带的预设飞船。",
        "tooltip": "是什么：是否允许载入KSP自带的Stock飞船\n为什么：这些飞船太大可能导致服务器延迟\n怎么做：联机服通常建议关闭以减少垃圾数据",
        "xml_file": "GameplaySettings.xml",
        "xml_field": "AllowStockVessels",
    },
}

SETTING_CATEGORIES = {
    "network": "网络设置",
    "game": "游戏设置",
    "sync": "同步设置",
    "mod": "Mod 控制",
    "lua": "Lua 脚本",
}

CATEGORY_ORDER = ["network", "game", "sync", "mod", "lua"]

# Build reverse mapping: (xml_file, xml_field) -> config_key
# For duplicate xml_field mappings (e.g. updateInterval/heartbeatMs both→HearbeatMsInterval),
# the last one in the dict wins. Special-case handling in load_config covers the rest.
_XML_TO_KEY = {}
for _key, _kb in SETTINGS_KNOWLEDGE_BASE.items():
    _xf = _kb.get("xml_file")
    _xfi = _kb.get("xml_field")
    if _xf and _xfi:
        _XML_TO_KEY[(_xf, _xfi)] = _key

# Map (xml_file, xml_field) -> [config_keys] for fields that map to multiple keys
_MULTI_MAP = {
    ("ConnectionSettings.xml", "HearbeatMsInterval"): ["updateInterval", "heartbeatMs"],
    ("GeneralSettings.xml", "AutoDekessler"): ["autoDekessler", "dekesslerMinTime"],
}


def get_config_dir() -> str:
    """Get the LMP Config directory based on the actual LMP server exe path."""
    lmp_exe = get_path(settings.LMP_SERVER_EXE)
    lmp_dir = os.path.dirname(lmp_exe)
    config_dir = os.path.join(lmp_dir, "Config")
    if not os.path.isdir(config_dir):
        # Fallback to default path
        config_dir = get_path("tools", "lmp_server", "LMPServer", "Config")
    return config_dir


def _get_all_config_dirs() -> list[str]:
    """Get ALL config directories that need to be updated.

    Returns both the development config dir and the release config dir
    (if they are different), so that LMP reads the same config regardless
    of how it's started.
    """
    dirs = []
    
    # Primary config dir (based on current run mode)
    primary_dir = get_config_dir()
    dirs.append(primary_dir)
    
    # Release config dir (always update this too, in case user switches modes)
    release_config_dir = get_path("release", "tools", "lmp_server", "LMPServer", "Config")
    
    # Only add if it exists AND is different from primary
    if os.path.isdir(release_config_dir) and os.path.normpath(release_config_dir) != os.path.normpath(primary_dir):
        dirs.append(release_config_dir)
    
    # Development config dir (update if running from release mode)
    dev_config_dir = get_path("tools", "lmp_server", "LMPServer", "Config")
    if os.path.isdir(dev_config_dir) and os.path.normpath(dev_config_dir) != os.path.normpath(primary_dir) and os.path.normpath(dev_config_dir) != os.path.normpath(release_config_dir):
        dirs.append(dev_config_dir)
    
    return dirs


def get_settings_file_path() -> str:
    return get_config_dir()


def _config_path(filename: str) -> str:
    return os.path.join(get_config_dir(), filename)


# ============================================================================
# XML reading / writing with LMP-compatible format
# ============================================================================

def _parse_xml_file(filepath: str) -> dict[str, str]:
    """Parse an LMP XML file and return {field_name: text_value}."""
    if not os.path.exists(filepath):
        return {}
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except UnicodeDecodeError:
        try:
            with open(filepath, 'r', encoding='utf-16') as f:
                content = f.read()
        except Exception:
            logger.warning(f"无法读取 XML 文件编码: {filepath}", exc_info=True)
            return {}
    except Exception:
        logger.warning(f"无法读取 XML 文件: {filepath}", exc_info=True)
        return {}

    result = {}
    # Match <TagName>value</TagName> pairs
    pattern = re.compile(r'<([A-Za-z_][A-Za-z0-9_]*)>(.*?)</\1>', re.DOTALL)
    for match in pattern.finditer(content):
        tag = match.group(1)
        val = match.group(2)
        result[tag] = val
    return result


def _write_lmp_xml(filepath: str, root_tag: str, fields_def: list,
                   current_values: dict[str, str]):
    """Modify an existing LMP XML file by replacing field values in-place.

    This preserves the exact format LMP uses (encoding, comments, whitespace, etc.)
    by only replacing the text content between XML tags.
    """
    if not os.path.exists(filepath):
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        lines = []
        lines.append('<?xml version="1.0" encoding="utf-16"?>')
        lines.append(f'<{root_tag} xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema">')
        for name, default, comment in fields_def:
            val = current_values.get(name, default)
            if val is None:
                val = ""
            val_str = _xml_escape(str(val))
            if comment:
                lines.append(f'  <!--{comment}-->')
            lines.append(f'  <{name}>{val_str}</{name}>')
        lines.append(f'</{root_tag}>')
        xml_str = '\r\n'.join(lines)
        with open(filepath, 'wb') as f:
            f.write(xml_str.encode('utf-8'))
        return

    # Read existing file as bytes (preserve exact encoding)
    with open(filepath, 'rb') as f:
        raw = f.read()

    # Try to decode as UTF-8 first, then UTF-16
    try:
        content = raw.decode('utf-8')
        encoding = 'utf-8'
    except UnicodeDecodeError:
        content = raw.decode('utf-16')
        encoding = 'utf-16'

    # Replace each field value using regex
    for name, default, _ in fields_def:
        if name in current_values:
            new_val = _xml_escape(str(current_values[name]))
        else:
            new_val = _xml_escape(str(default))
        # Match <FieldName>anything</FieldName> and replace the value
        pattern = re.compile(
            r'(<' + re.escape(name) + r'>).*?(</' + re.escape(name) + r'>)',
            re.DOTALL
        )
        content = pattern.sub(r'\g<1>' + new_val + r'\g<2>', content)

    # Write back with same encoding
    if encoding == 'utf-8':
        with open(filepath, 'wb') as f:
            f.write(content.encode('utf-8'))
    else:
        with open(filepath, 'wb') as f:
            f.write(content.encode('utf-16'))



# ============================================================================
# ensure_default_lmp_config
# ============================================================================

def ensure_default_lmp_config():
    """Create all 12 XML config files if they don't exist."""
    config_dir = get_config_dir()
    os.makedirs(config_dir, exist_ok=True)

    for filename, filedef in _XML_FILES_DEF.items():
        filepath = _config_path(filename)
        if os.path.exists(filepath):
            continue
        root_tag = filedef["root"]
        fields_def = filedef["fields"]
        defaults = {name: default for name, default, _ in fields_def}
        _write_lmp_xml(filepath, root_tag, fields_def, defaults)
        logger.info(f"已创建默认 XML 配置文件: {filename}")

    logger.info("LMP 默认 XML 配置检查完成")


# ============================================================================
# load_config
# ============================================================================

async def load_config() -> dict[str, str]:
    """Load config from all XML files and database, return {config_key: value}."""
    ensure_default_lmp_config()

    values: dict[str, str] = {}

    for filename in XML_FILENAMES:
        filepath = _config_path(filename)
        xml_data = _parse_xml_file(filepath)

        for xml_field, xml_val in xml_data.items():
            pair = (filename, xml_field)

            # Check multi-mapping first
            if pair in _MULTI_MAP:
                for ck in _MULTI_MAP[pair]:
                    if ck in ("updateInterval", "heartbeatMs"):
                        values["updateInterval"] = xml_val
                        values["heartbeatMs"] = xml_val
                    elif ck == "autoDekessler":
                        try:
                            float_val = float(xml_val)
                            values["autoDekessler"] = "true" if float_val > 0 else "false"
                        except (ValueError, TypeError):
                            values["autoDekessler"] = "false"
                    elif ck == "dekesslerMinTime":
                        try:
                            float_val = float(xml_val)
                            values["dekesslerMinTime"] = str(
                                int(float_val)) if float_val > 0 else "30"
                        except (ValueError, TypeError):
                            values["dekesslerMinTime"] = "30"
                continue

            if pair not in _XML_TO_KEY:
                continue

            config_key = _XML_TO_KEY[pair]

            if config_key == "modControlMode":
                values["modControlMode"] = "DISABLED" if xml_val.lower() == "false" else "BLACKLIST"
            elif config_key == "ip":
                values["ip"] = xml_val
            elif config_key in ("updateInterval", "heartbeatMs"):
                values["updateInterval"] = xml_val
                values["heartbeatMs"] = xml_val
            else:
                values[config_key] = xml_val

    # Load DB-only values
    async with get_db() as conn:
        cursor = await conn.execute(
            "SELECT config_key, config_value FROM server_config WHERE config_key LIKE 'lmp_%'"
        )
        rows = await cursor.fetchall()
        for r in rows:
            db_key = r["config_key"].replace("lmp_", "", 1)
            if db_key not in values:
                values[db_key] = r["config_value"]

    # Ensure all keys from KB exist with at least empty string
    for key in SETTINGS_KNOWLEDGE_BASE:
        if key not in values:
            values[key] = ""

    return values


# ============================================================================
# save_config
# ============================================================================

def _resolve_write_value(key: str, kb: dict, values: dict[str, str],
                          existing: dict[str, str]) -> str | None:
    """Resolve the XML value to write for a given config key.
    Returns None if no value can be resolved.
    """
    val = values.get(key, "")
    xml_field = kb.get("xml_field", "")
    xml_file = kb.get("xml_file", "")

    if key == "autoDekessler":
        auto_val = values.get("autoDekessler", "")
        time_val = values.get("dekesslerMinTime", "")
        if auto_val in ("true", "True"):
            if time_val:
                return str(time_val)
            return existing.get("AutoDekessler", "30")
        elif auto_val in ("false", "False"):
            return "0"
        if time_val:
            return str(time_val)
        return existing.get("AutoDekessler", "30")

    if key == "dekesslerMinTime":
        # Handled by autoDekessler above; skip standalone write
        return None

    if key == "modControlMode":
        mode = val.upper() if val else ""
        return "false" if mode == "DISABLED" else "true"

    if key == "ip":
        return str(val) if val else existing.get("ListenAddress", "[::]")

    if key in ("updateInterval", "heartbeatMs"):
        # Both map to HearbeatMsInterval - use whichever has a value
        for k in ("updateInterval", "heartbeatMs"):
            if k in values and values[k]:
                return str(values[k])
        return existing.get("HearbeatMsInterval", "5000")

    return str(val) if val else None


async def save_config(values: dict[str, str]):
    """Save config values back to XML files and database.

    Updates BOTH the development (tools/) and release (release/tools/) config
    directories so that LMP reads the same config regardless of how it's started.
    """
    ensure_default_lmp_config()

    # Determine which XML files need updating
    dirty_files: set[str] = set()
    for key, kb in SETTINGS_KNOWLEDGE_BASE.items():
        if key not in values or values[key] == "":
            continue
        xml_file = kb.get("xml_file")
        if xml_file:
            dirty_files.add(xml_file)

    # Get both config directories (dev + release)
    config_dirs = _get_all_config_dirs()

    # For each dirty file, read existing values, overlay changes, write to ALL dirs
    for filename in dirty_files:
        filedef = _XML_FILES_DEF.get(filename)
        if not filedef:
            continue

        # Read existing values from the primary (first) config dir
        primary_path = os.path.join(config_dirs[0], filename)
        existing = _parse_xml_file(primary_path)
        defaults = {name: default for name, default, _ in filedef["fields"]}
        target = dict(defaults)
        target.update(existing)

        # Apply changes from our config keys that map to this file
        for key, kb in SETTINGS_KNOWLEDGE_BASE.items():
            if kb.get("xml_file") != filename:
                continue
            if key == "dekesslerMinTime":
                continue
            xml_field = kb.get("xml_field")
            if not xml_field:
                continue

            resolved = _resolve_write_value(key, kb, values, target)
            if resolved is not None:
                target[xml_field] = resolved

        # Write to ALL config directories
        for config_dir in config_dirs:
            filepath = os.path.join(config_dir, filename)
            _write_lmp_xml(filepath, filedef["root"], filedef["fields"], target)

    # Persist DB-only values
    for key, val in values.items():
        if key in SETTINGS_KNOWLEDGE_BASE:
            from backend.database import set_setting
            await set_setting(f"lmp_{key}", str(val))

    # Sync Settings.txt in ALL config directories
    _sync_settings_txt_all(values)

    logger.info(f"已保存 {len(values)} 个配置项到 XML 文件 (共 {len(config_dirs)} 个目录)")


def _sync_settings_txt(values: dict[str, str]):
    """Sync Settings.txt to match the current XML-based config.

    LMP reads XML files at startup, but Settings.txt is used by LMP clients
    for quick-connect. Keep them consistent.
    """
    lmp_exe = get_path(settings.LMP_SERVER_EXE)
    lmp_dir = os.path.dirname(lmp_exe)
    settings_txt_path = os.path.join(lmp_dir, "Settings.txt")
    _write_settings_txt(settings_txt_path, values)


def _sync_settings_txt_all(values: dict[str, str]):
    """Sync Settings.txt in ALL config directories."""
    config_dirs = _get_all_config_dirs()
    lmp_server_dirs = [os.path.dirname(d) for d in config_dirs]
    
    # Also sync the LMP exe directory (in case it's different)
    lmp_exe = get_path(settings.LMP_SERVER_EXE)
    lmp_dir = os.path.dirname(lmp_exe)
    if lmp_dir not in lmp_server_dirs:
        lmp_server_dirs.append(lmp_dir)
    
    for lmp_dir in lmp_server_dirs:
        settings_txt_path = os.path.join(lmp_dir, "Settings.txt")
        try:
            _write_settings_txt(settings_txt_path, values)
        except Exception as e:
            logger.warning(f"同步 Settings.txt 失败 ({settings_txt_path}): {e}")
    
    logger.info(f"已同步 Settings.txt (共 {len(lmp_server_dirs)} 个目录)")


def _write_settings_txt(settings_txt_path: str, values: dict[str, str]):
    """Write a single Settings.txt file."""
    xml_map = {
        "port": ("ConnectionSettings.xml", "Port"),
        "ip": ("ConnectionSettings.xml", "ListenAddress"),
        "maxPlayers": ("GeneralSettings.xml", "MaxPlayers"),
        "name": ("GeneralSettings.xml", "ServerName"),
        "password": ("GeneralSettings.xml", "Password"),
        "motd": ("GeneralSettings.xml", "ServerMotd"),
        "updateInterval": ("ConnectionSettings.xml", "HearbeatMsInterval"),
        "autoDekessler": ("GeneralSettings.xml", "AutoDekessler"),
        "dekesslerMinTime": ("GeneralSettings.xml", "AutoDekessler"),
        "modControlMode": ("GeneralSettings.xml", "ModControl"),
        "totalSaveGameBans": (None, None),
        "registerPrivateIp": (None, None),
        "heartbeatMs": ("ConnectionSettings.xml", "HearbeatMsInterval"),
        "saveInterval": ("IntervalSettings.xml", "BackupIntervalMs"),
        "warpMode": ("WarpSettings.xml", "WarpMode"),
        "gameMode": ("GeneralSettings.xml", "GameMode"),
        "allowStockVessels": ("GameplaySettings.xml", "AllowStockVessels"),
        "cheats": ("GeneralSettings.xml", "Cheats"),
        "numberOfAsteroids": ("GeneralSettings.xml", "NumberOfAsteroids"),
        "spectateTimeout": (None, None),
    }

    resolved = {}
    for key, (xml_file, xml_field) in xml_map.items():
        val = values.get(key, "")
        if not val:
            continue

        if key == "autoDekessler":
            time_val = values.get("dekesslerMinTime", "")
            if val in ("true", "True"):
                resolved["autoDekessler"] = "true"
                resolved["dekesslerMinTime"] = time_val if time_val else "30"
            elif val in ("false", "False"):
                resolved["autoDekessler"] = "false"
                resolved["dekesslerMinTime"] = "0"
            else:
                resolved["autoDekessler"] = "true"
                resolved["dekesslerMinTime"] = str(int(float(val))) if val else "30"
        elif key == "dekesslerMinTime":
            pass
        elif key == "modControlMode":
            resolved["modControlMode"] = val.upper() if val else "DISABLED"
        elif key == "updateInterval" or key == "heartbeatMs":
            resolved["updateInterval"] = val
            resolved["heartbeatMs"] = val
        else:
            resolved[key] = val

    try:
        lines = []
        for key in [
            "port", "ip", "maxPlayers", "name", "password", "motd",
            "updateInterval", "autoDekessler", "dekesslerMinTime",
            "modControlMode", "dropSpamAccounts", "totalSaveGameBans",
            "registerPrivateIp", "heartbeatMs", "saveInterval",
            "warpMode", "gameMode", "allowStockVessels", "cheats",
            "numberOfAsteroids", "spectateTimeout",
        ]:
            if key in resolved:
                lines.append(f"{key}={resolved[key]}")
            elif key in values and values[key]:
                lines.append(f"{key}={values[key]}")

        if lines:
            with open(settings_txt_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            logger.info("已同步 Settings.txt")
    except Exception as e:
        logger.warning(f"同步 Settings.txt 失败: {e}", exc_info=True)


# ============================================================================
# get_config_fields
# ============================================================================

def get_config_fields() -> list[ConfigField]:
    fields = []
    for key, kb in SETTINGS_KNOWLEDGE_BASE.items():
        f = ConfigField(
            key=key,
            value="",
            type=kb["type"],
            label=kb["label"],
            description=kb["description"],
            tooltip=kb["tooltip"],
            category=kb["category"],
            options=kb.get("options", []),
            min_value=kb.get("min_value"),
            max_value=kb.get("max_value"),
            required=kb.get("required", False),
            warning_if_empty=kb.get("warning_if_empty", False),
            warning_message=kb.get("warning_message", ""),
            error_message=kb.get("error_message", ""),
        )
        fields.append(f)

    fields.sort(key=lambda f: (
        CATEGORY_ORDER.index(f.category) if f.category in CATEGORY_ORDER else 99,
        f.key,
    ))
    return fields


# ============================================================================
# validate_config
# ============================================================================

def validate_config(values: dict) -> FullConfigValidation:
    results = []
    has_errors = False
    has_warnings = False

    for key, kb in SETTINGS_KNOWLEDGE_BASE.items():
        val = values.get(key, "")
        val_str = str(val).strip() if val is not None else ""
        field_type = kb["type"]

        if field_type == "int":
            if val_str:
                try:
                    int_val = int(val_str)
                    min_v = kb.get("min_value")
                    max_v = kb.get("max_value")
                    if min_v is not None and int_val < min_v:
                        results.append(ConfigValidationResult(
                            key=key, valid=False, level="error",
                            message=kb.get("error_message", f"值不能小于 {min_v}")
                        ))
                        has_errors = True
                        continue
                    if max_v is not None and int_val > max_v:
                        results.append(ConfigValidationResult(
                            key=key, valid=False, level="error",
                            message=kb.get("error_message", f"值不能大于 {max_v}")
                        ))
                        has_errors = True
                        continue
                except ValueError:
                    results.append(ConfigValidationResult(
                        key=key, valid=False, level="error",
                        message=kb.get("error_message", "请输入有效数字")
                    ))
                    has_errors = True
                    continue
            elif kb.get("required"):
                results.append(ConfigValidationResult(
                    key=key, valid=False, level="error",
                    message="此项为必填"
                ))
                has_errors = True
                continue

        if field_type == "string" and kb.get("required") and not val_str:
            results.append(ConfigValidationResult(
                key=key, valid=False, level="error",
                message=kb.get("error_message", "此项为必填")
            ))
            has_errors = True
            continue

        if kb.get("warning_if_empty") and not val_str:
            results.append(ConfigValidationResult(
                key=key, valid=True, level="warning",
                message=kb.get("warning_message", "此值为空可能导致连接问题")
            ))
            has_warnings = True
            continue

        if key == "modControlMode" and val_str.upper() == "WHITELIST":
            whitelist_empty = values.get("_whitelist_empty", True)
            if whitelist_empty:
                results.append(ConfigValidationResult(
                    key=key, valid=True, level="warning",
                    message=kb.get("warning_message", "白名单模式下未添加模组")
                ))
                has_warnings = True
                continue

        results.append(ConfigValidationResult(
            key=key, valid=True, level="ok",
            message=""
        ))

    for key in values:
        if key.startswith("_"):
            continue
        if key not in SETTINGS_KNOWLEDGE_BASE:
            results.append(ConfigValidationResult(
                key=key, valid=True, level="ok", message=""
            ))

    return FullConfigValidation(
        results=results,
        has_errors=has_errors,
        has_warnings=has_warnings,
    )


# ============================================================================
# sync_required_mods
# ============================================================================

async def sync_required_mods(mod_list: list[str]):
    config_dir = get_config_dir()
    if not os.path.exists(config_dir):
        return

    filepath = _config_path("CraftSettings.xml")
    filedef = _XML_FILES_DEF.get("CraftSettings.xml")
    if not filedef:
        return

    existing = _parse_xml_file(filepath)
    defaults = {name: default for name, default, _ in filedef["fields"]}
    target = dict(defaults)
    target.update(existing)
    target["RequiredMods"] = ",".join(mod_list)

    _write_lmp_xml(filepath, filedef["root"], filedef["fields"], target)
    logger.info(f"已同步 {len(mod_list)} 个模组到 RequiredMods")
