import os
import sys
import json
import time
import hashlib
import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import (
    FastAPI,
    WebSocket,
    WebSocketDisconnect,
    HTTPException,
    Request,
    Response,
)
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import PlainTextResponse

from backend.config import settings, get_path, get_app_path, setup_logging, BASE_DIR
from backend.database import init_db, get_db, get_setting, set_setting
from backend.models import (
    AdminUserCreate,
    AdminUserLogin,
    WizardStep,
    ServerCommand,
    ServerStatus,
    ModSearchQuery,
    ModpackCreate,
    ConfigField,
    FullConfigValidation,
    SystemInfo,
)
from backend.server_manager import ServerManager
from backend.websocket_manager import ws_manager
from backend.config_editor import (
    get_config_fields,
    validate_config,
    save_config,
    load_config,
)
from backend.mod_list_manager import ModListManager
from backend.ckan_export import export_to_ckan_json

logger = logging.getLogger("ML.Main")

mod_list_manager = ModListManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(settings.LOG_LEVEL, get_path(settings.LOGS_DIR))
    logger.info(f"{settings.APP_NAME} v{settings.APP_VERSION} 启动中...")
    await init_db()
    logger.info("数据库初始化完成")

    _ensure_lmp_settings()
    await _ensure_auto_modpack()
    await _ensure_default_admin()

    server_manager.set_callbacks(
        on_log=_on_server_log,
        on_status_change=_on_server_status_change,
    )
    yield
    logger.info(f"{settings.APP_NAME} 正在关闭...")
    if server_manager.running:
        await server_manager.stop()
    logger.info(f"{settings.APP_NAME} 已关闭")


def _ensure_lmp_settings():
    from backend.config_editor import ensure_default_lmp_config
    ensure_default_lmp_config()


async def _ensure_auto_modpack():
    from backend.database import get_db

    async with get_db() as conn:
        cursor = await conn.execute(
            "SELECT * FROM modpack WHERE identifier='auto_server_modpack'"
        )
        if not await cursor.fetchone():
            await conn.execute(
                "INSERT INTO modpack (name, identifier, description, mod_list) VALUES (?, ?, ?, ?)",
                ("服务器默认模组包", "auto_server_modpack", "纯净服（无模组）", "[]"),
            )
            await conn.commit()
            logger.info("已创建默认模组包")


async def _ensure_default_admin():
    from backend.database import get_db

    async with get_db() as conn:
        cursor = await conn.execute("SELECT COUNT(*) as cnt FROM admin_user")
        row = await cursor.fetchone()
        if (row["cnt"] or 0) == 0:
            pw = _hash_password("admin123")
            await conn.execute(
                "INSERT INTO admin_user (username, password_hash) VALUES (?, ?)",
                ("admin", pw),
            )
            await conn.commit()
            logger.info("已创建默认管理员 (密码: admin123)")


server_manager = ServerManager()

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def _basic_auth_check(request: Request):
    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Basic "):
        return Response(
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="KSP Server Manager"'},
        )
    import base64

    try:
        cred = base64.b64decode(auth[6:]).decode()
        username, password = cred.split(":", 1)
    except Exception:
        return Response(
            status_code=401, headers={"WWW-Authenticate": 'Basic realm="KSP"'}
        )
    try:
        async with get_db() as conn:
            cursor = await conn.execute(
                "SELECT username, password_hash FROM admin_user WHERE username = ?",
                (username,),
            )
            row = await cursor.fetchone()
            if not row:
                return Response(
                    status_code=401, headers={"WWW-Authenticate": 'Basic realm="KSP"'}
                )
            if _hash_password(password) != row["password_hash"]:
                return Response(
                    status_code=401, headers={"WWW-Authenticate": 'Basic realm="KSP"'}
                )
    except Exception as e:
        logger.error(f"Basic Auth error: {e}")
    return None


def _on_server_log(log_type: str, line: str):
    ts = time.strftime("%H:%M:%S")
    import asyncio

    asyncio.create_task(ws_manager.broadcast_console(line, ts))


def _on_server_status_change():
    import asyncio

    asyncio.create_task(_broadcast_status())


async def _broadcast_status():
    status = await server_manager.get_status()
    await ws_manager.broadcast_status(status)


def _hash_password(password: str) -> str:
    return hashlib.sha256(f"ml_salt_{password}".encode()).hexdigest()


# ============================================================
# Auth & Wizard
# ============================================================


@app.get("/api/status")
async def api_status():
    async with get_db() as conn:
        cursor = await conn.execute("SELECT COUNT(*) as cnt FROM admin_user")
        row = await cursor.fetchone()
        has_admin = row["cnt"] > 0

    status = await server_manager.get_status()

    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "has_admin": has_admin,
        "server": status,
        "websocket_clients": ws_manager.connection_count,
    }


@app.post("/api/wizard/setup-admin")
async def wizard_setup_admin(data: AdminUserCreate):
    async with get_db() as conn:
        cursor = await conn.execute("SELECT COUNT(*) as cnt FROM admin_user")
        row = await cursor.fetchone()
        if row["cnt"] > 0:
            raise HTTPException(400, "管理员已存在，无法重复创建")

        pw_hash = _hash_password(data.password)
        await conn.execute(
            "INSERT INTO admin_user (username, password_hash) VALUES (?, ?)",
            (data.username, pw_hash),
        )
        await conn.commit()
    logger.info(f"初始管理员 {data.username} 已创建")
    return {"success": True, "message": "管理员创建成功"}


@app.post("/api/wizard/login")
async def wizard_login(data: AdminUserLogin):
    async with get_db() as conn:
        cursor = await conn.execute(
            "SELECT * FROM admin_user WHERE username = ?", (data.username,)
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(401, "用户名或密码错误")
        if row["password_hash"] != _hash_password(data.password):
            raise HTTPException(401, "用户名或密码错误")
    return {"success": True, "username": data.username}


@app.post("/api/auth/login")
async def auth_password_login(data: dict):
    password = data.get("password", "")
    if not password:
        raise HTTPException(400, "密码不能为空")
    async with get_db() as conn:
        cursor = await conn.execute("SELECT * FROM admin_user LIMIT 1")
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(401, "密码错误")
        if row["password_hash"] != _hash_password(password):
            raise HTTPException(401, "密码错误")
    return {"success": True}


@app.get("/api/wizard/steps")
async def wizard_get_steps():
    async with get_db() as conn:
        cursor = await conn.execute("SELECT * FROM wizard_state ORDER BY id")
        rows = await cursor.fetchall()
        steps = []
        for r in rows:
            steps.append(
                {
                    "step": r["step"],
                    "completed": bool(r["completed"]),
                    "data": json.loads(r["data"]) if r["data"] else {},
                }
            )
    return {"steps": steps}


@app.post("/api/wizard/steps/{step}")
async def wizard_set_step(step: str, data: WizardStep):
    async with get_db() as conn:
        await conn.execute(
            """INSERT INTO wizard_state (step, completed, data)
               VALUES (?, ?, ?)
               ON CONFLICT(step) DO UPDATE SET
               completed=excluded.completed,
               data=excluded.data,
               updated_at=CURRENT_TIMESTAMP""",
            (step, 1 if data.completed else 0, json.dumps(data.data)),
        )
        await conn.commit()
    return {"success": True}


@app.post("/api/wizard/skip-wizard")
async def wizard_skip():
    async with get_db() as conn:
        await conn.execute("UPDATE wizard_state SET completed=1")
        await conn.commit()
    return {"success": True}


@app.get("/api/wizard/complete")
async def wizard_is_complete():
    async with get_db() as conn:
        cursor = await conn.execute(
            "SELECT COUNT(*) as total, SUM(completed) as done FROM wizard_state"
        )
        row = await cursor.fetchone()
        total = row["total"] or 0
        done = row["done"] or 0
    return {"complete": total > 0 and total == done}


# ============================================================
# Password Settings
# ============================================================


@app.post("/api/auth/set-username")
async def auth_set_username(data: dict):
    username = data.get("username", "")
    if not username or len(username) < 2:
        raise HTTPException(400, "用户名至少2位")
    async with get_db() as conn:
        cursor = await conn.execute("SELECT id FROM admin_user LIMIT 1")
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(400, "管理员不存在")
        await conn.execute(
            "UPDATE admin_user SET username = ? WHERE id = ?", (username, row["id"])
        )
        await conn.commit()
    return {"success": True}


@app.post("/api/auth/set-password")
async def auth_set_password(data: dict):
    password = data.get("password", "")
    if not password or len(password) < 4:
        raise HTTPException(400, "密码至少4位")
    async with get_db() as conn:
        cursor = await conn.execute("SELECT id FROM admin_user LIMIT 1")
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(400, "管理员不存在")
        pw_hash = _hash_password(password)
        await conn.execute(
            "UPDATE admin_user SET password_hash = ? WHERE id = ?", (pw_hash, row["id"])
        )
        await conn.commit()
    return {"success": True}


@app.post("/api/auth/set-level2")
async def auth_set_level2(data: dict):
    password = data.get("password", "")
    if not password or len(password) < 4:
        raise HTTPException(400, "密码至少4位")
    await set_setting("level2_password", _hash_password(password))
    logger.info("二级密码已更新")
    return {"success": True}


# ============================================================
# Server Management
# ============================================================


@app.get("/api/server/status")
async def server_status():
    status = await server_manager.get_status()
    import sys
    from backend.config import settings
    lmp_path = get_path(settings.LMP_SERVER_EXE)
    status["_diag"] = {
        "frozen": getattr(sys, "frozen", False),
        "base_dir": str(BASE_DIR),
        "lmp_path": lmp_path,
        "lmp_exists": os.path.exists(lmp_path),
        "cwd": os.getcwd(),
    }
    return status


@app.post("/api/server/start")
async def server_start():
    success, message = await server_manager.start()
    return {"success": success, "message": message}


@app.post("/api/server/stop")
async def server_stop():
    success, message = await server_manager.stop()
    return {"success": success, "message": message}


@app.post("/api/server/restart")
async def server_restart():
    success, message = await server_manager.restart()
    return {"success": success, "message": message}


@app.post("/api/server/force-restart")
async def server_force_restart():
    success, message = await server_manager.force_restart()
    return {"success": success, "message": message}


@app.post("/api/server/command")
async def server_send_command(data: ServerCommand):
    success, message = await server_manager.send_command(data.command)
    return {"success": success, "message": message}


@app.get("/api/server/logs")
async def server_logs(count: int = 200):
    logs = server_manager.get_recent_logs(count)
    return {"logs": logs}


@app.get("/api/server/auto-restart")
async def server_get_auto_restart():
    return {
        "enabled": server_manager._auto_restart,
        "max_attempts": server_manager._max_restart,
    }


@app.post("/api/server/auto-restart")
async def server_set_auto_restart(data: dict):
    server_manager.set_auto_restart(
        enabled=data.get("enabled", True),
        max_attempts=data.get("max_attempts", 5),
    )
    await set_setting("auto_restart", str(int(data.get("enabled", True))))
    await set_setting("max_restart_attempts", str(data.get("max_attempts", 5)))
    return {"success": True}


# ============================================================
# WebSocket
# ============================================================


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        status = await server_manager.get_status()
        await ws.send_json({"type": "status", "data": status})
        while True:
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await ws_manager.disconnect(ws)


# ============================================================
# Config Editor
# ============================================================


@app.get("/api/config/fields")
async def config_get_fields():
    fields = get_config_fields()
    current_values = await load_config()
    for f in fields:
        if f.key in current_values:
            f.value = current_values[f.key]
    return {"fields": [f.model_dump() for f in fields]}


@app.get("/api/config/values")
async def config_get_values():
    return {"values": await load_config()}


@app.post("/api/config/validate")
async def config_validate(data: dict):
    result = validate_config(data.get("values", {}))
    return result.model_dump()


@app.post("/api/config/save")
async def config_save(data: dict):
    values = data.get("values", {})
    existing = await load_config()
    for k, v in values.items():
        existing[k] = str(v)
    validation = validate_config(existing)
    if validation.has_errors:
        raise HTTPException(400, detail=validation.model_dump())
    await save_config(existing)
    logger.info("LMP 配置已更新")
    return {
        "success": True,
        "message": "配置已保存",
        "warnings": validation.has_warnings,
        "restart_hint": "配置已写入 XML 文件。LMP 仅在启动时读取配置，请重启服务器使更改生效。",
    }


@app.get("/api/config/file-path")
async def config_file_path():
    from backend.config_editor import get_settings_file_path

    return {"path": get_settings_file_path()}


# ============================================================
# Mod Store (CKAN) - Browse & Search only
# ============================================================


@app.get("/api/mods/search")
async def mods_search(query: str = "", page: int = 1, page_size: int = 50):
    try:
        from backend.ckan_manager import ckan_manager

        result = await ckan_manager.search(query, page, page_size)
        return result
    except ImportError:
        return {"mods": [], "total": 0, "page": page, "page_size": page_size}


@app.get("/api/mods/browse")
async def mods_browse(page: int = 1, page_size: int = 50):
    try:
        from backend.ckan_manager import ckan_manager

        result = await ckan_manager.browse_all(page, page_size)
        return result
    except ImportError:
        return {"mods": [], "total": 0, "page": page, "page_size": page_size}


@app.get("/api/mods/{identifier}/detail")
async def mods_detail(identifier: str):
    try:
        from backend.ckan_manager import ckan_manager

        detail = await ckan_manager.show(identifier)
        return detail
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    except ImportError:
        raise HTTPException(500, "CKAN 管理器未就绪")


# ============================================================
# Mod List Management (ModControl.xml)
# ============================================================


@app.get("/api/mods/list")
async def mods_list_get():
    mods = mod_list_manager.list_items()
    return {"allow_non_listed": mod_list_manager.get_allow_non_listed(), "mods": mods}


@app.post("/api/mods/list/add")
async def mods_list_add(data: dict):
    mod_id = data.get("identifier", data.get("mod_id", ""))
    name = data.get("name", mod_id)
    rule = data.get("rule", "Allow")
    link = data.get("link", "")
    sha = data.get("sha", "")
    if not mod_id:
        raise HTTPException(400, "缺少 identifier")
    mod_list_manager.add_item(mod_id, name, rule, link, sha)
    logger.info(f"模组名单添加: {mod_id} ({rule})")
    return {"success": True, "message": f"{mod_id} 已添加到 {rule} 名单"}


@app.delete("/api/mods/list/{mod_id}")
async def mods_list_remove(mod_id: str):
    mod_list_manager.remove_item(mod_id)
    logger.info(f"模组名单移除: {mod_id}")
    return {"success": True, "message": f"{mod_id} 已从名单移除"}


@app.put("/api/mods/list/{mod_id}")
async def mods_list_update(mod_id: str, data: dict):
    rule = data.get("rule", "Allow")
    mod_list_manager.update_rule(mod_id, rule)
    logger.info(f"模组名单更新: {mod_id} -> {rule}")
    return {"success": True, "message": f"{mod_id} 规则已更新为 {rule}"}


# ============================================================
# CKAN Export
# ============================================================


@app.post("/api/export-ckan")
async def export_ckan(data: dict):
    metadata = data.get("metadata", {})
    mods = data.get("mods", [])
    if not mods:
        raise HTTPException(400, "缺少 mods")
    for mod in mods:
        if not mod.get("identifier") and mod.get("id"):
            mod["identifier"] = mod.pop("id")
    ckan_json = export_to_ckan_json(metadata, mods)
    return {"success": True, "data": ckan_json}


# ============================================================
# CKAN Repos
# ============================================================


@app.get("/api/mods/repos")
async def mods_repos_list():
    try:
        from backend.ckan_manager import ckan_manager

        repos = await ckan_manager.list_repos()
        return {"repos": repos}
    except ImportError:
        return {"repos": []}


@app.post("/api/mods/repos")
async def mods_repos_add(data: dict):
    url = data.get("url", "")
    name = data.get("name", "")
    if not url:
        raise HTTPException(400, "缺少仓库 URL")
    try:
        from backend.ckan_manager import ckan_manager

        result = await ckan_manager.add_repo(url, name)
        return {"success": True, "message": f"仓库已添加: {name or url}"}
    except RuntimeError as e:
        raise HTTPException(400, str(e))


@app.delete("/api/mods/repos/{name}")
async def mods_repos_remove(name: str):
    if not name:
        raise HTTPException(400, "缺少仓库名称")
    try:
        from backend.ckan_manager import ckan_manager

        await ckan_manager.remove_repo(name)
        return {"success": True, "message": f"仓库已删除: {name}"}
    except RuntimeError as e:
        raise HTTPException(400, str(e))


@app.get("/api/mods/repos/available")
async def mods_repos_available():
    try:
        from backend.ckan_manager import ckan_manager

        repos = await ckan_manager.available_repos()
        return {"repos": repos}
    except ImportError:
        return {"repos": []}


@app.post("/api/mods/repos/default")
async def mods_repos_set_default(data: dict):
    name = data.get("name", "")
    if not name:
        raise HTTPException(400, "缺少仓库名称")
    try:
        from backend.ckan_manager import ckan_manager

        await ckan_manager.set_default_repo(name)
        return {"success": True, "message": f"默认仓库已设为: {name}"}
    except RuntimeError as e:
        raise HTTPException(400, str(e))


# ============================================================
# Modpack
# ============================================================


@app.get("/api/modpack")
async def modpack_get():
    async with get_db() as conn:
        cursor = await conn.execute("SELECT * FROM modpack ORDER BY updated_at DESC")
        rows = await cursor.fetchall()
        packs = []
        for r in rows:
            packs.append(
                {
                    "id": r["id"],
                    "name": r["name"],
                    "identifier": r["identifier"],
                    "version": r["version"],
                    "description": r["description"],
                    "mod_list": json.loads(r["mod_list"]) if r["mod_list"] else [],
                    "created_at": r["created_at"],
                    "updated_at": r["updated_at"],
                }
            )
    return {"modpacks": packs}


@app.post("/api/modpack")
async def modpack_create(data: ModpackCreate):
    from backend.ckan_manager import ckan_manager

    installed = await ckan_manager.list_installed() if ckan_manager else []
    mod_list = (
        data.mod_list if data.mod_list else [m.get("identifier", m) for m in installed]
    )

    identifier = data.name.lower().replace(" ", "_")
    async with get_db() as conn:
        await conn.execute(
            """INSERT INTO modpack (name, identifier, description, mod_list)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(identifier) DO UPDATE SET
               name=excluded.name,
               description=excluded.description,
               mod_list=excluded.mod_list,
               updated_at=CURRENT_TIMESTAMP""",
            (data.name, identifier, data.description, json.dumps(mod_list)),
        )
        await conn.commit()
    logger.info(f"模组包 {data.name} 已保存")
    return {"success": True, "identifier": identifier}


@app.post("/api/modpack/{identifier}/sync-whitelist")
async def modpack_sync_whitelist(identifier: str):
    async with get_db() as conn:
        cursor = await conn.execute(
            "SELECT mod_list FROM modpack WHERE identifier = ?", (identifier,)
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(404, "模组包不存在")
        mod_list = json.loads(row["mod_list"]) if row["mod_list"] else []

        await conn.execute("DELETE FROM mod_whitelist")
        for mod_name in mod_list:
            await conn.execute(
                "INSERT OR IGNORE INTO mod_whitelist (mod_name) VALUES (?)", (mod_name,)
            )
        await conn.commit()

    from backend.config_editor import sync_required_mods

    await sync_required_mods(mod_list)

    logger.info(f"白名单已同步，共 {len(mod_list)} 个模组")
    return {"success": True, "count": len(mod_list)}


@app.delete("/api/modpack/{identifier}")
async def modpack_delete(identifier: str):
    if identifier == "auto_server_modpack":
        raise HTTPException(400, "不能删除服务器默认模组包")
    async with get_db() as conn:
        cursor = await conn.execute(
            "SELECT * FROM modpack WHERE identifier = ?", (identifier,)
        )
        if not await cursor.fetchone():
            raise HTTPException(404, "模组包不存在")
        await conn.execute("DELETE FROM modpack WHERE identifier = ?", (identifier,))
        await conn.commit()
    return {"success": True, "message": "模组包已删除"}


@app.get("/api/modpack/{identifier}/export")
async def modpack_export(identifier: str):
    async with get_db() as conn:
        cursor = await conn.execute(
            "SELECT * FROM modpack WHERE identifier = ?", (identifier,)
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(404, "模组包不存在")

        return {
            "name": row["name"],
            "identifier": row["identifier"],
            "description": row["description"],
            "version": row["version"],
            "mod_list": json.loads(row["mod_list"]) if row["mod_list"] else [],
        }


# ============================================================
# KSP Detection
# ============================================================


@app.get("/api/settings/ksp-detect")
async def ksp_detect():
    import winreg

    candidates = []
    checked = set()

    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"SOFTWARE\Valve\Steam")
        steam_path = winreg.QueryValueEx(key, "SteamPath")[0]
        candidates.append(
            os.path.join(steam_path, "steamapps", "common", "Kerbal Space Program")
        )
    except Exception:
        pass

    for drive in [chr(d) + ":" for d in range(ord("C"), ord("F") + 1)]:
        for sub in [
            "Steam/steamapps/common/Kerbal Space Program",
            "SteamLibrary/steamapps/common/Kerbal Space Program",
            "Program Files (x86)/Steam/steamapps/common/Kerbal Space Program",
            "KSP",
            "KSP_win64",
        ]:
            candidates.append(os.path.join(drive, sub))

    found = []
    for p in candidates:
        p = os.path.normpath(p)
        if p.lower() in checked:
            continue
        checked.add(p.lower())
        gd = os.path.join(p, "GameData")
        if os.path.isdir(gd):
            found.append({"path": p, "gamedata": gd})

    current = settings.KSP_GAMEDATA_PATH or ""
    return {"found": found, "current": current}


@app.get("/api/settings/ksp-path")
async def ksp_path_get():
    path = settings.KSP_GAMEDATA_PATH or ""
    if path:
        abs_path = get_path(path) if not os.path.isabs(path) else path
        return {"path": path, "exists": os.path.isdir(os.path.join(abs_path, ".."))}
    return {"path": "", "exists": False}


@app.post("/api/settings/ksp-path")
async def ksp_path_set(data: dict):
    path = data.get("path", "")
    env_path = get_path(".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        with open(env_path, "w", encoding="utf-8") as f:
            found = False
            for line in lines:
                if line.strip().startswith("ML_KSP_GAMEDATA_PATH="):
                    f.write(f"ML_KSP_GAMEDATA_PATH={path}\n")
                    found = True
                else:
                    f.write(line)
            if not found:
                f.write(f"ML_KSP_GAMEDATA_PATH={path}\n")
    else:
        with open(env_path, "w", encoding="utf-8") as f:
            f.write(f"ML_KSP_GAMEDATA_PATH={path}\n")
    logger.info(f"KSP 目录已更新: {path}")
    return {"success": True, "message": "KSP 路径已保存，重启生效"}


# ============================================================
# System
# ============================================================


@app.get("/api/system/info")
async def system_info():
    import psutil

    cpu = psutil.cpu_percent(interval=0.5)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage(str(BASE_DIR))
    return SystemInfo(
        cpu_percent=cpu,
        memory_total_gb=round(mem.total / (1024**3), 2),
        memory_used_gb=round((mem.total - mem.available) / (1024**3), 2),
        disk_total_gb=round(disk.total / (1024**3), 2),
        disk_used_gb=round(disk.used / (1024**3), 2),
    ).model_dump()


# ============================================================
# API 404 handler
# ============================================================


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": "接口不存在"}, status_code=404)
    check = await _basic_auth_check(request)
    if check:
        return check
    index_path = get_app_path("frontend", "index.html")
    if os.path.exists(index_path):
        return FileResponse(
            index_path, headers={"Cache-Control": "no-store, no-cache, must-revalidate"}
        )
    return JSONResponse({"detail": "页面不存在"}, status_code=404)


# ============================================================
# Static files & SPA fallback
# ============================================================

frontend_dir = get_app_path("frontend")
if os.path.isdir(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")


@app.get("/")
async def index(request: Request):
    check = await _basic_auth_check(request)
    if check:
        return check
    index_path = get_app_path("frontend", "index.html")
    if os.path.exists(index_path):
        return FileResponse(
            index_path, headers={"Cache-Control": "no-store, no-cache, must-revalidate"}
        )
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "api": "/api/status",
    }


def run_system_tray():
    if not settings.ENABLE_SYSTEM_TRAY:
        return
    try:
        from backend.system_tray import run_tray

        run_tray()
    except Exception:
        pass


def run():
    import uvicorn
    import webbrowser
    import threading

    def start_uvicorn():
        for attempt in range(3):
            try:
                uvicorn.run(
                    "backend.main:app",
                    host=settings.HOST,
                    port=settings.PORT,
                    log_level=settings.LOG_LEVEL.lower(),
                    reload=False,
                )
                break
            except OSError as e:
                if attempt < 2:
                    import time

                    logger.warning(
                        f"端口 {settings.PORT} 被占用，等待 5 秒重试... ({e})"
                    )
                    time.sleep(5)
                else:
                    logger.error(f"端口 {settings.PORT} 仍然无法绑定，请检查端口占用")
                    raise

    t = threading.Thread(target=start_uvicorn, daemon=True)
    t.start()

    import time
    for i in range(20):
        time.sleep(0.5)
        try:
            import urllib.request
            urllib.request.urlopen(f"http://{settings.HOST}:{settings.PORT}/api/status", timeout=1)
            break
        except Exception:
            pass

    try:
        import ctypes
        ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
    except Exception:
        pass

    webbrowser.open(f"http://{settings.HOST}:{settings.PORT}")

    run_system_tray()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nML Server Manager 已退出")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host=settings.HOST,
        port=settings.PORT,
        log_level=settings.LOG_LEVEL.lower(),
        reload=True,
    )
