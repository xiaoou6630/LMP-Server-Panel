import os
import sys
import json
import logging
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "ML - KSP LMP Multiplayer Launcher"
    APP_VERSION: str = "1.0.0"
    HOST: str = "127.0.0.1"
    PORT: int = 8080
    LOG_LEVEL: str = "INFO"
    DATA_DIR: str = "data"
    LOGS_DIR: str = "logs"
    TOOLS_DIR: str = "tools"
    LMP_SERVER_EXE: str = "tools/lmp_server/LMPServer/Server.exe"
    CKAN_EXE: str = "tools/ckan/ckan.exe"
    KSP_GAMEDATA_PATH: str = ""
    AUTO_RESTART_ON_CRASH: bool = True
    MAX_RESTART_ATTEMPTS: int = 5
    ENABLE_SYSTEM_TRAY: bool = True

    class Config:
        env_prefix = "ML_"
        env_file = ".env"


def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent.parent


def get_app_dir():
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).parent.parent


BASE_DIR = get_base_dir()
APP_DIR = get_app_dir()


def get_path(*parts):
    return os.path.join(BASE_DIR, *parts)


def get_app_path(*parts):
    return os.path.join(APP_DIR, *parts)


def setup_logging(log_level: str = "INFO", log_dir: str | None = None):
    if log_dir is None:
        log_dir = get_path("logs")
    os.makedirs(log_dir, exist_ok=True)

    log_format = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    file_handler = logging.FileHandler(
        os.path.join(log_dir, "ml_server.log"), encoding="utf-8"
    )
    file_handler.setFormatter(log_format)
    file_handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(log_format)
    console_handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    return root_logger


settings = Settings()
