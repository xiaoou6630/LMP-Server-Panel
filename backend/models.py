from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime


class AdminUserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=32)
    password: str = Field(min_length=6, max_length=128)


class AdminUserLogin(BaseModel):
    username: str
    password: str


class WizardStep(BaseModel):
    completed: bool = False
    data: dict = {}


class ServerStatus(BaseModel):
    online: bool = False
    pid: Optional[int] = None
    uptime: float = 0
    cpu_percent: float = 0
    memory_mb: float = 0
    player_count: int = 0
    player_names: List[str] = Field(default_factory=list)
    last_start_time: Optional[datetime] = None


class ServerCommand(BaseModel):
    command: str = Field(min_length=1)


class ConsoleMessage(BaseModel):
    type: str = "console"
    line: str
    timestamp: str


class StatusMessage(BaseModel):
    type: str = "status"
    data: ServerStatus


class ModEntry(BaseModel):
    name: str
    identifier: str
    abstract: str = ""
    version: str = ""
    author: str = ""
    download_url: str = ""
    ksp_version: str = ""
    installed: bool = False


class ModSearchQuery(BaseModel):
    query: str = ""
    page: int = 1
    page_size: int = 50


class ModpackCreate(BaseModel):
    name: str
    description: str = ""
    mod_list: List[str] = Field(default_factory=list)


class ModpackExport(BaseModel):
    name: str
    identifier: str
    description: str
    version: str
    mod_list: List[str]


class ConfigField(BaseModel):
    key: str
    value: str
    type: str = "string"
    label: str
    description: str = ""
    tooltip: str = ""
    category: str = "general"
    options: List[str] = Field(default_factory=list)
    min_value: Optional[int] = None
    max_value: Optional[int] = None
    required: bool = False
    warning_if_empty: bool = False
    warning_message: str = ""
    error_message: str = ""
    validation_pattern: str = ""


class ConfigValidationResult(BaseModel):
    key: str
    valid: bool = True
    level: str = "ok"
    message: str = ""


class FullConfigValidation(BaseModel):
    results: List[ConfigValidationResult] = Field(default_factory=list)
    has_errors: bool = False
    has_warnings: bool = False


class NetworkStatus(BaseModel):
    connected: bool = False
    network_name: str = ""
    virtual_ip: str = ""
    status_text: str = "未配置"
    peers_count: int = 0


class NetworkConfigUpdate(BaseModel):
    network_name: str
    network_key: str
    force_reconnect: bool = False


class ClientSyncConfig(BaseModel):
    server_ip: str
    server_port: int = 8800
    network_name: str = ""
    network_key: str = ""
    modpack_available: bool = False


class SystemInfo(BaseModel):
    cpu_percent: float = 0
    memory_total_gb: float = 0
    memory_used_gb: float = 0
    disk_total_gb: float = 0
    disk_used_gb: float = 0
