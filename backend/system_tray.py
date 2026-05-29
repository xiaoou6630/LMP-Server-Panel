import os
import sys
import logging
import threading
from pathlib import Path
from PIL import Image, ImageDraw
import pystray
from backend.config import settings, get_path

logger = logging.getLogger("ML.Tray")

WINDOWS = sys.platform == "win32"
_web_url = f"http://{settings.HOST}:{settings.PORT}"


def _create_icon_image(size: tuple[int, int] = (32, 32)) -> Image.Image:
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    w, h = size

    draw.rounded_rectangle([0, 0, w - 1, h - 1], radius=4, fill=(25, 35, 55))
    draw.rounded_rectangle([6, 6, w - 7, h - 7], radius=3, fill=(60, 140, 220))

    small_sz = max(4, w // 8)
    for row in range(2):
        for col in range(2):
            x = w // 4 + col * (w // 4) - small_sz // 2
            y = h // 4 + row * (h // 4) - small_sz // 2
            draw.rounded_rectangle(
                [x, y, x + small_sz, y + small_sz],
                radius=1,
                fill=(180, 220, 255),
            )

    return img


def _on_open(icon, item):
    import webbrowser
    webbrowser.open(_web_url)


def _on_exit(icon, item):
    icon.stop()
    os._exit(0)


def _get_menu(icon):
    from pystray import Menu, MenuItem
    return Menu(
        MenuItem("打开面板", _on_open, default=True),
        MenuItem("退出", _on_exit),
    )


def run_tray():
    image = _create_icon_image()
    icon = pystray.Icon(
        name=settings.APP_NAME,
        icon=image,
        title=settings.APP_NAME,
        menu=_get_menu(None),
    )

    threading.Thread(target=icon.run, daemon=True).start()
    logger.info("系统托盘已启动")
