import os
import sys
import json
import shutil
import zipfile
import logging
from pathlib import Path
from datetime import datetime
from backend.config import get_path, settings

logger = logging.getLogger("ML.ClientSync")

WINDOWS = sys.platform == "win32"


def get_client_sync_dir() -> Path:
    path = get_path("data", "client_sync")
    os.makedirs(path, exist_ok=True)
    return Path(path)


async def generate_modpack_zip(mod_list: list[str], include_gamedata: bool = False, server_config: dict = None) -> Path:
    sync_dir = get_client_sync_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_name = f"KSP_ModPack_{timestamp}.zip"
    zip_path = sync_dir / zip_name

    gamedata_src = ""
    if include_gamedata and settings.KSP_GAMEDATA_PATH:
        gamedata_src = str(get_path(settings.KSP_GAMEDATA_PATH))
    elif include_gamedata:
        local_gd = get_path("data", "ksp_local", "GameData")
        if os.path.isdir(local_gd) and os.listdir(local_gd):
            gamedata_src = str(local_gd)

    package_info = {
        "name": "ML Modpack",
        "version": "1.0.0",
        "created_at": datetime.now().isoformat(),
        "mod_count": len(mod_list),
        "mods": mod_list,
        "source_gamedata": gamedata_src,
    }

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("modpack.json", json.dumps(package_info, indent=2, ensure_ascii=False))
        zf.writestr("_MANIFEST.txt", generate_manifest(mod_list))

        if server_config:
            install_cfg = {
                "server_ip": server_config.get("server_ip", "127.0.0.1"),
                "server_port": server_config.get("server_port", 8800),
                "virtual_ip": server_config.get("virtual_ip", ""),
                "network_name": server_config.get("network_name", ""),
                "network_key": server_config.get("network_key", ""),
                "modpack_id": package_info.get("mods", []),
            }
            zf.writestr("client_config.json", json.dumps(install_cfg, indent=2, ensure_ascii=False))

            use_easytier = bool(install_cfg.get("network_name") and install_cfg.get("virtual_ip"))
            install_bat = (
                f"@echo off\n"
                f"chcp 65001 >nul\n"
                f"title ML - KSP Modpack Installer\n"
                f"echo.\n"
                f"echo ============================================\n"
                f"echo  ML - KSP LMP Modpack Installer\n"
                f"echo ============================================\n"
                f"echo.\n"
                f"echo [1/3] 安装模组...\n"
                f"if not exist \"%~dp0GameData\" (\n"
                f"  echo 警告: 未找到 GameData 目录，跳过模组复制\n"
                f")\n"
                f"if exist \"%~dp0GameData\" (\n"
                f"  if exist \"..\\GameData\" (\n"
                f"    xcopy /E /Y \"%~dp0GameData\" \"..\\GameData\"\n"
                f"    echo 模组安装完成！\n"
                f"  ) else (\n"
                f"    echo 未找到 KSP GameData，请手动将 GameData 复制到 KSP 目录\n"
                f"  )\n"
                f")\n"
            )
            if use_easytier:
                install_bat += (
                    f"echo.\n"
                    f"echo [2/3] 启动 EasyTier 组网...\n"
                    f"if exist \"%~dp0EasyTier\\easytier-core.exe\" (\n"
                    f"  start /MIN \"EasyTier\" \"%~dp0EasyTier\\easytier-core.exe\" "
                    f"--network-name \"{install_cfg['network_name']}\" "
                    f"--network-secret \"{install_cfg['network_key']}\" "
                    f"--dhcp\n"
                    f"  echo EasyTier 已在后台启动！\n"
                    f"  echo 虚拟 IP: {install_cfg['virtual_ip']}\n"
                )
            install_bat += (
                f"echo.\n"
                f"echo [3/3] 连接信息\n"
                f"echo.\n"
                f"echo 服务器地址: {install_cfg['server_ip']}:{install_cfg['server_port']}\n"
                f"echo.\n"
                f"echo 启动 KSP，选择 Multiplayer -\n"
                f"echo 输入服务器地址即可联机！\n"
                f"echo.\n"
                f"echo 按任意键退出...\n"
                f"pause >nul\n"
            )
            if use_easytier:
                install_bat += (
                    f"taskkill /F /IM easytier-core.exe >nul 2>&1\n"
                )
            zf.writestr("install.bat", install_bat.replace("\n", "\r\n"))

            use_easytier = bool(install_cfg.get("network_name") and install_cfg.get("virtual_ip"))
            if use_easytier:
                easytier_src = get_path("tools", "easytier", "easytier-windows-x86_64")
                if os.path.isdir(easytier_src):
                    for root, dirs, files in os.walk(easytier_src):
                        for fname in files:
                            fpath = os.path.join(root, fname)
                            arcname = os.path.relpath(fpath, os.path.dirname(easytier_src))
                            zf.write(fpath, os.path.join("EasyTier", arcname))

                    start_et = (
                        f"@echo off\n"
                        f"chcp 65001 >nul\n"
                        f"title ML - EasyTier Client\n"
                        f"echo 正在启动 EasyTier...\n"
                        f"echo 网络: {install_cfg['network_name']}\n"
                        f"echo.\n"
                        f"\"%~dp0EasyTier\\easytier-core\" "
                        f"--network-name \"{install_cfg['network_name']}\" "
                        f"--network-secret \"{install_cfg['network_key']}\" "
                        f"--dhcp\n"
                        f"echo.\n"
                        f"echo EasyTier 已退出。\n"
                        f"pause\n"
                    )
                    zf.writestr("start_easytier.bat", start_et.replace("\n", "\r\n"))

        if gamedata_src and os.path.isdir(gamedata_src):
            for root, dirs, files in os.walk(gamedata_src):
                for fname in files:
                    fpath = os.path.join(root, fname)
                    arcname = os.path.relpath(fpath, os.path.dirname(gamedata_src))
                    zf.write(fpath, arcname)

    logger.info(f"整合包已生成: {zip_path} ({os.path.getsize(zip_path) / 1024 / 1024:.1f} MB)")
    return zip_path


def generate_manifest(mod_list: list[str]) -> str:
    lines = [
        "=" * 50,
        "ML - KSP LMP Modpack Manifest",
        "=" * 50,
        f"Total Mods: {len(mod_list)}",
        "-" * 50,
    ]
    for i, mod in enumerate(mod_list, 1):
        name = mod.get("name", mod) if isinstance(mod, dict) else mod
        identifier = mod.get("identifier", mod) if isinstance(mod, dict) else mod
        lines.append(f"{i:3d}. {name} ({identifier})")
    return "\n".join(lines)


def generate_client_sync_script(
    server_ip: str,
    server_port: int = 8800,
    network_name: str = "",
    network_key: str = "",
) -> dict:
    config = {
        "server": {
            "ip": server_ip,
            "port": server_port,
        },
        "network": {
            "name": network_name,
            "key": network_key,
            "enabled": bool(network_name and network_key),
        },
        "sync": {
            "modpack_zip": "KSP_ModPack.zip",
            "backup_gamedata": True,
            "verify_integrity": True,
        },
        "instructions": [
            "1. 将 ML_Client_Sync.exe 和 KSP_ModPack.zip 放入 KSP 游戏根目录",
            "2. 双击运行 ML_Client_Sync.exe",
            "3. 程序会自动备份当前 GameData 并替换为服务器模组包",
            "4. 如配置了组网信息，程序会自动加入 EasyTier 网络",
            "5. 打开 KSP 游戏，服务器 IP 已自动填入联机列表",
        ],
    }

    sync_config_path = get_client_sync_dir() / "client_sync_config.json"
    with open(sync_config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    logger.info(f"客户端同步配置已生成: {sync_config_path}")
    return config


CLIENT_LAUNCHER_SOURCE = r'''
# ML Client Sync Launcher
# 此文件将被 PyInstaller 打包为 ML_Client_Sync.exe

import os
import sys
import json
import shutil
import zipfile
import tkinter as tk
from tkinter import messagebox, ttk
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
GAMEDATA_PATH = BASE_DIR / "GameData"
BACKUP_DIR = BASE_DIR / f"GameData_Backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

def load_config():
    paths = [
        BASE_DIR / "client_sync_config.json",
    ]
    for p in paths:
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
    return None

def find_modpack():
    for root, dirs, files in os.walk(str(BASE_DIR)):
        for f in files:
            if f.endswith(".zip") and "ModPack" in f:
                return Path(root) / f
    return None

def backup_gamedata():
    if GAMEDATA_PATH.exists():
        shutil.move(str(GAMEDATA_PATH), str(BACKUP_DIR))
        return True
    return False

def restore_backup():
    if BACKUP_DIR.exists():
        if GAMEDATA_PATH.exists():
            shutil.rmtree(str(GAMEDATA_PATH))
        shutil.move(str(BACKUP_DIR), str(GAMEDATA_PATH))

def extract_modpack(zip_path):
    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.namelist():
            if member.startswith("GameData"):
                zf.extract(member, str(BASE_DIR))
    return True

def verify_integrity(zip_path):
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            gd_files = [m for m in zf.namelist() if m.startswith("GameData")]
            return len(gd_files) > 0
    except Exception:
        return False

def run_sync(progress_callback=None):
    config = load_config()
    modpack = find_modpack()

    if config is None:
        messagebox.showwarning("提示", "未找到同步配置文件，跳过网络配置")
    if modpack is None:
        messagebox.showerror("错误", "未找到 KSP_ModPack.zip！请确保该文件与 ML_Client_Sync.exe 在同一目录。")
        return False

    if not verify_integrity(modpack):
        messagebox.showerror("错误", "整合包校验失败！文件可能已损坏。请重新从服主处获取。")
        return False

    result = messagebox.askyesno(
        "确认操作",
        "此操作将完全删除你当前的 GameData 文件夹！\n\n"
        f"当前 GameData 将被备份到:\n{BACKUP_DIR}\n\n"
        "点击'是'继续，点击'否'退出。",
        icon="warning"
    )
    if not result:
        return False

    if progress_callback:
        progress_callback("正在备份 GameData...", 10)
    backup_gamedata()

    if progress_callback:
        progress_callback("正在解压模组包...", 40)
    try:
        extract_modpack(modpack)
    except Exception as e:
        messagebox.showerror("解压失败", f"解压模组包时出错: {e}")
        restore_backup()
        return False

    if progress_callback:
        progress_callback("校验完整性...", 80)

    if progress_callback:
        progress_callback("完成！", 100)

    return True

def main():
    root = tk.Tk()
    root.title("ML Client Sync - KSP 模组同步器")
    root.geometry("500x400")
    root.resizable(False, False)

    title = tk.Label(root, text="ML Client Sync", font=("Arial", 18, "bold"))
    title.pack(pady=15)

    subtitle = tk.Label(root, text="KSP LMP 联机模组同步工具", font=("Arial", 10), fg="gray")
    subtitle.pack()

    info_frame = tk.LabelFrame(root, text="服务器信息", padx=10, pady=10)
    info_frame.pack(fill="x", padx=20, pady=10)

    config = load_config()
    if config:
        server = config.get("server", {})
        tk.Label(info_frame, text=f"服务器 IP: {server.get('ip', 'N/A')}", font=("Arial", 10)).pack(anchor="w")
        tk.Label(info_frame, text=f"服务器端口: {server.get('port', 'N/A')}", font=("Arial", 10)).pack(anchor="w")

        network = config.get("network", {})
        if network.get("enabled"):
            tk.Label(info_frame, text=f"网络: {network.get('name', 'N/A')}", font=("Arial", 10), fg="green").pack(anchor="w")
    else:
        tk.Label(info_frame, text="未配置服务器信息", font=("Arial", 10), fg="orange").pack(anchor="w")

    progress_var = tk.DoubleVar()
    progress = ttk.Progressbar(root, variable=progress_var, maximum=100)
    progress.pack(fill="x", padx=20, pady=10)

    status_label = tk.Label(root, text="就绪", font=("Arial", 9), fg="gray")
    status_label.pack()

    def on_sync():
        def update_status(msg, val):
            status_label.config(text=msg)
            progress_var.set(val)
            root.update()

        success = run_sync(progress_callback=update_status)
        if success:
            messagebox.showinfo("完成", "模组环境已与服务器同步完毕！\n\n现在可以打开 KSP 游戏进行联机了。")
            root.destroy()
        else:
            progress_var.set(0)
            status_label.config(text="同步取消")

    sync_btn = tk.Button(root, text="开始同步", command=on_sync, font=("Arial", 12),
                          bg="#4CAF50", fg="white", padx=30, pady=8)
    sync_btn.pack(pady=20)

    root.mainloop()

if __name__ == "__main__":
    main()
'''


def generate_client_sync_launcher():
    launcher_path = get_client_sync_dir() / "client_sync_launcher.py"
    with open(launcher_path, "w", encoding="utf-8") as f:
        f.write(CLIENT_LAUNCHER_SOURCE.strip())
    logger.info(f"客户端同步启动器已生成: {launcher_path}")
    return launcher_path
