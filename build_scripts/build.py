import os
import sys
import shutil
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.config import get_path, settings

ROOT = Path(__file__).parent.parent
BUILD_DIR = ROOT / "build"
DIST_DIR = ROOT / "dist"
RELEASE_DIR = ROOT / "release"


def find_upx():
    """查找 UPX 可执行文件"""
    paths = [
        ROOT / "upx" / "upx.exe",
        ROOT / "upx.exe",
        Path("upx") / "upx.exe",
        Path("upx.exe"),
        Path("e:/daima/block/upx/upx-4.2.2-win64/upx.exe"),
        Path("e:/daima/block/upx/upx-4.2.2-win64") / "upx.exe",
    ]
    if sys.platform == "win32":
        try:
            result = subprocess.run(["where", "upx"], capture_output=True, text=True)
            if result.returncode == 0:
                p = result.stdout.strip().split("\n")[0]
                if os.path.exists(p):
                    return p
        except Exception:
            pass
    else:
        try:
            result = subprocess.run(["which", "upx"], capture_output=True, text=True)
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
    for p in paths:
        if os.path.exists(str(p)):
            return str(p)
    return None


def build():
    print("=" * 60)
    print(f"  LMP Server Panel 打包脚本")
    print(f"  版本: {settings.APP_VERSION}")
    print("=" * 60)

    # 检查虚拟环境
    venv_python = ROOT / "venv" / "Scripts" / "python.exe"
    if not venv_python.exists():
        print(f"\n  [错误] 未找到虚拟环境: {venv_python}")
        print("  请先运行: python -m venv venv")
        print("  然后运行: venv\\Scripts\\pip install -r requirements.txt")
        sys.exit(1)

    # 使用 venv 中的 pip 安装 pyinstaller（如果未安装）
    pip_cmd = [str(ROOT / "venv" / "Scripts" / "pip.exe"), "install", "pyinstaller>=6.4.0"]
    print(f"\n正在检查 PyInstaller...")
    subprocess.run(pip_cmd, check=False, capture_output=True)

    upx_path = find_upx()
    if upx_path:
        print(f"  UPX 已找到: {upx_path}")
    else:
        print("\n  [提示] UPX 未找到，将跳过压缩。")
        print("  下载 UPX: https://upx.github.io/")
        print("  将 upx.exe 放到项目根目录即可自动使用。")

    release_dir = ROOT / "release"
    release_dir.mkdir(exist_ok=True)

    exe_name = "LMP_Server_Panel"

    tools_dir = ROOT / "tools"
    tools_status = {
        "LMP 服务端": (tools_dir / "lmp_server" / "LMPServer" / "Server.exe").exists(),
        "CKAN": (tools_dir / "ckan" / "ckan.exe").exists(),
    }
    print("\n工具检测:")
    for name, exist in tools_status.items():
        print(f"  [{'OK' if exist else 'MISSING'}] {name}")

    sep = ";" if sys.platform == "win32" else ":"

    datas = [
        f"--add-data={ROOT / 'frontend'}{sep}frontend",
    ]

    cmd = [str(ROOT / "venv" / "Scripts" / "pyinstaller.exe"),
           "--onefile",
           "--console",
           f"--name", exe_name,
           "--clean", "--noconfirm",
           f"--distpath", str(DIST_DIR),
           f"--workpath", str(BUILD_DIR / "pyinstaller_work"),
           f"--specpath", str(BUILD_DIR),
           ]

    icon = ROOT / "assets" / "icon.ico"
    if icon.exists():
        cmd.extend(["--icon", str(icon)])

    cmd.extend(datas)

    hidden_imports = [
        "asyncio", "logging", "json", "sqlite3", "xml", "xml.etree", "xml.dom",
        "fastapi", "uvicorn", "uvicorn.loops", "uvicorn.loops.auto",
        "uvicorn.protocols", "uvicorn.protocols.http", "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets", "uvicorn.protocols.websockets.auto",
        "websockets", "pydantic", "pydantic_settings",
        "psutil", "aiosqlite", "aiofiles",
        "pystray", "PIL", "PIL.Image", "PIL.ImageDraw",
        "backend", "backend.config", "backend.database", "backend.models",
        "backend.server_manager", "backend.websocket_manager",
        "backend.ckan_manager", "backend.config_editor", "backend.system_tray",
        "backend.mod_list_manager", "backend.ckan_export",
    ]
    for h in hidden_imports:
        cmd.extend(["--hidden-import", h])

    if upx_path:
        cmd.extend(["--upx-dir", str(Path(upx_path).parent)])

    cmd.append(str(ROOT / "run.py"))

    print(f"\n执行打包...")
    print(f"  命令: {' '.join(cmd)}\n")

    result = subprocess.run(cmd, cwd=str(ROOT))
    if result.returncode != 0:
        print("\n打包失败!")
        sys.exit(1)

    exe_path = DIST_DIR / f"{exe_name}.exe"
    if exe_path.exists():
        dest = release_dir / f"{exe_name}.exe"
        shutil.copy2(exe_path, dest)
        size_mb = dest.stat().st_size / (1024 * 1024)
        print(f"\n打包成功! {dest} ({size_mb:.1f} MB)")

        tools_src = ROOT / "tools"
        tools_dst = release_dir / "tools"
        if tools_src.exists():
            if tools_dst.exists():
                shutil.rmtree(tools_dst)
            shutil.copytree(tools_src, tools_dst)
            print(f"  已复制 tools/ 到 release/")

        readme = release_dir / "使用说明.txt"
        readme.write_text(
            "ML 服务器管理器 - KSP 多人联机服务端\n"
            "作者: xiaoou6630\n"
            "版本: " + settings.APP_VERSION + "\n"
            "=" * 50 + "\n\n"
            "快速开始:\n"
            "1. 双击 LMP_Server_Panel.exe 启动程序\n"
            "2. 浏览器打开 http://127.0.0.1:8080\n"
            "3. 首次使用请按提示设置管理员密码\n"
            "4. 在网页界面中点击「启动服务器」\n\n"
            "功能说明:\n"
            "- 配置编辑器: 修改服务器名称、端口、玩家数量等\n"
            "- 模组管理: 管理 CKAN 模组列表，支持黑白名单\n"
            "- 服务器控制: 启动/停止/重启 LMP 服务端\n"
            "- 实时日志: 在网页中查看服务器运行日志\n\n"
            "注意事项:\n"
            "- 修改配置后需重启服务器才能生效\n"
            "- LMP 服务端文件位于 tools/lmp_server/LMPServer/\n"
            "- 关闭服务器时请用 Ctrl+C 确保存档备份\n\n"
            "遇到问题? 请检查:\n"
            "1. 端口是否被其他程序占用\n"
            "2. 防火墙是否阻止了连接\n"
            "3. KSP 游戏路径是否设置正确\n",
            encoding="utf-8"
        )
        print(f"  README 已生成: {readme}")

        zip_name = release_dir / "LMP_Server_Panel.zip"
        print(f"\n正在打包 ZIP...")
        zip_root = ROOT / "LMP_Server_Panel"
        if zip_root.exists():
            shutil.rmtree(zip_root)
        zip_root.mkdir()
        shutil.copy2(dest, zip_root / f"{exe_name}.exe")
        shutil.copy2(readme, zip_root / "README.txt")
        tools_in_zip = zip_root / "tools"
        if tools_dst.exists():
            shutil.copytree(tools_dst, tools_in_zip)
        shutil.make_archive(str(release_dir / exe_name), 'zip', str(zip_root.parent), zip_root.name)
        shutil.rmtree(zip_root)
        zip_size = zip_name.stat().st_size / (1024 * 1024)
        print(f"  ZIP 已生成: {zip_name} ({zip_size:.1f} MB)")
    else:
        print(f"\n错误: 未找到生成的 exe 文件 {exe_path}")
        sys.exit(1)

    for d in [BUILD_DIR, DIST_DIR]:
        if d.exists():
            try:
                shutil.rmtree(d)
                print(f"  已清理: {d}")
            except Exception:
                pass

    print("\n完成! 输出目录: release/")


if __name__ == "__main__":
    build()
