import os
import sys
import time
import signal
import asyncio
import logging
import threading
from pathlib import Path
from datetime import datetime
from backend.config import get_path, settings

logger = logging.getLogger("ML.ServerManager")

WINDOWS = sys.platform == "win32"


class ServerManager:
    def __init__(self):
        self.process = None
        self.pid: int | None = None
        self.start_time: float | None = None
        self._running = False
        self._stopping = False
        self._manual_start = False
        self._line_buffer: list[str] = []
        self._player_names: list[str] = []
        self._player_count: int = 0
        self._stdout_task: asyncio.Task | None = None
        self._monitor_task: asyncio.Task | None = None
        self._restart_attempts: int = 0
        self._max_restart = settings.MAX_RESTART_ATTEMPTS
        self._auto_restart = settings.AUTO_RESTART_ON_CRASH
        self._on_log: callable | None = None
        self._on_status_change: callable | None = None
        self._lmp_exe_path = get_path(settings.LMP_SERVER_EXE)

    @property
    def running(self) -> bool:
        return self._running and self.process is not None

    @property
    def player_names(self) -> list[str]:
        return list(self._player_names)

    def set_callbacks(self, on_log=None, on_status_change=None):
        self._on_log = on_log
        self._on_status_change = on_status_change

    def set_auto_restart(self, enabled: bool, max_attempts: int = 5):
        self._auto_restart = enabled
        self._max_restart = max_attempts

    async def start(self) -> tuple[bool, str]:
        if self._running:
            return False, "服务器已在运行中"

        exe_path = self._lmp_exe_path
        if not os.path.exists(exe_path):
            logger.error(f"LMP 路径不存在: {exe_path}")
            return False, f"找不到 LMP 服务端: {exe_path}"

        working_dir = os.path.dirname(exe_path)
        if not os.path.isdir(working_dir):
            return False, f"工作目录不存在: {working_dir}"

        logger.info(f"启动 LMP: {exe_path} (cwd={working_dir})")
        self._manual_start = True
        self._restart_attempts = 0
        self._stopping = False
        self._line_buffer = []

        try:
            kwargs = {
                "cwd": working_dir,
                "stdin": asyncio.subprocess.PIPE if not WINDOWS else None,
                "stdout": asyncio.subprocess.PIPE,
                "stderr": asyncio.subprocess.STDOUT,
            }
            if WINDOWS:
                self.process = await asyncio.create_subprocess_exec(
                    exe_path, **kwargs
                )
            else:
                self.process = await asyncio.create_subprocess_shell(
                    f'"{exe_path}"', **kwargs
                )
        except Exception as e:
            logger.error(f"启动 LMP 服务端失败: {e}")
            return False, f"启动失败: {str(e)}"

        self.pid = self.process.pid
        self.start_time = time.time()
        self._running = True
        self._emit_log("system", f"LMP 服务端已启动 (PID: {self.pid})")
        self._notify_status()
        self._stdout_task = asyncio.create_task(self._read_stdout())
        self._monitor_task = asyncio.create_task(self._monitor_process())
        logger.info(f"LMP 服务端启动成功, PID: {self.pid}")
        return True, f"服务器已启动 (PID: {self.pid})"

    async def stop(self) -> tuple[bool, str]:
        if not self._running or self.process is None:
            return False, "服务器未在运行"

        self._stopping = True
        self._emit_log("system", "正在停止 LMP 服务端...")

        try:
            if WINDOWS:
                self._send_command("/quit")
                try:
                    await asyncio.wait_for(self.process.wait(), timeout=10)
                except asyncio.TimeoutError:
                    self.process.terminate()
                    try:
                        await asyncio.wait_for(self.process.wait(), timeout=5)
                    except asyncio.TimeoutError:
                        self.process.kill()
                        await self.process.wait()
            else:
                self.process.terminate()
                try:
                    await asyncio.wait_for(self.process.wait(), timeout=15)
                except asyncio.TimeoutError:
                    self.process.kill()
                    await self.process.wait()
        except Exception as e:
            logger.error(f"停止 LMP 服务端时出错: {e}")

        await self._cleanup()
        return True, "服务器已停止"

    async def restart(self) -> tuple[bool, str]:
        await self.stop()
        await asyncio.sleep(1)
        return await self.start()

    async def force_restart(self) -> tuple[bool, str]:
        if self.process is not None:
            try:
                self.process.kill()
            except Exception:
                pass
        await self._cleanup()
        await asyncio.sleep(1)
        return await self.start()

    def _send_command(self, cmd: str):
        if self.process and self._running and not WINDOWS:
            try:
                stdin = self.process.stdin
                if stdin:
                    stdin.write((cmd + "\n").encode())
            except Exception:
                pass

    async def send_command(self, command: str) -> tuple[bool, str]:
        if not self._running or self.process is None:
            return False, "服务器未在运行"

        cmd = command.strip()
        self._emit_log("command", f"> {cmd}")

        if WINDOWS:
            return True, "命令已发送（Windows 模式下通过子进程管道暂不支持发送输入）"
        else:
            self._send_command(cmd)
            return True, "命令已发送"

    async def get_status(self) -> dict:
        import psutil
        status = {
            "online": self._running,
            "pid": self.pid,
            "uptime": time.time() - self.start_time if self.start_time else 0,
            "cpu_percent": 0.0,
            "memory_mb": 0.0,
            "player_count": self._player_count,
            "player_names": list(self._player_names),
            "last_start_time": (
                datetime.fromtimestamp(self.start_time).isoformat()
                if self.start_time else None
            ),
        }

        if self._running and self.pid:
            try:
                proc = psutil.Process(self.pid)
                status["cpu_percent"] = proc.cpu_percent(interval=0.1)
                mem = proc.memory_info()
                status["memory_mb"] = round(mem.rss / 1024 / 1024, 2)
            except (psutil.NoSuchProcess, Exception):
                pass

        return status

    async def _read_stdout(self):
        try:
            while self._running and self.process and self.process.stdout:
                line_bytes = await self.process.stdout.readline()
                if not line_bytes:
                    break
                line = line_bytes.decode("utf-8", errors="replace").rstrip()
                if line:
                    self._line_buffer.append(line)
                    if len(self._line_buffer) > 5000:
                        self._line_buffer = self._line_buffer[-5000:]
                    self._emit_log("stdout", line)
                    self._parse_log_for_players(line)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        except asyncio.CancelledError:
            pass

    def _parse_log_for_players(self, line: str):
        lower = line.lower()
        if "player " in lower and "connected" in lower:
            self._player_count += 1
            parts = line.split(" ")
            for i, p in enumerate(parts):
                if p.lower() == "player" and i + 1 < len(parts):
                    name = parts[i + 1].rstrip(".,;:!?")
                    if name not in self._player_names:
                        self._player_names.append(name)
                    break
            self._notify_status()
        elif "player " in lower and "disconnected" in lower:
            self._player_count = max(0, self._player_count - 1)
            parts = line.split(" ")
            for i, p in enumerate(parts):
                if p.lower() == "player" and i + 1 < len(parts):
                    name = parts[i + 1].rstrip(".,;:!?")
                    if name in self._player_names:
                        self._player_names.remove(name)
                    break
            self._notify_status()
        elif "handshake successful" in lower or "new client" in lower:
            self._player_count = len(self._player_names)
            self._notify_status()

    async def _monitor_process(self):
        while self._running and self.process:
            try:
                returncode = await asyncio.wait_for(
                    asyncio.shield(self.process.wait()), timeout=2.0
                )
                was_running = self._running
                elapsed = time.time() - self.start_time if self.start_time else 999
                self._running = False
                self._emit_log(
                    "system",
                    f"LMP 服务端进程已退出 (退出码: {returncode})"
                )
                self._notify_status()

                if self._auto_restart and not self._stopping:
                    if elapsed < 3:
                        self._emit_log("system", "进程快速退出，可能端口被占用，尝试清理旧进程...")
                        self._kill_stale_processes()
                        await asyncio.sleep(2)

                    self._restart_attempts += 1
                    if self._restart_attempts > self._max_restart:
                        self._emit_log("system", f"已达最大重启次数({self._max_restart})，停止自动重启")
                        self._restart_attempts = 0
                        break

                    delay = min(self._restart_attempts * 5, 30)
                    self._emit_log(
                        "system",
                        f"将在 {delay} 秒后自动重启 (第 {self._restart_attempts}/{self._max_restart} 次尝试)"
                    )
                    await asyncio.sleep(delay)
                    had_old = self.process
                    self.process = None
                    self.pid = None
                    success, msg = await self.start()
                    self._emit_log("system", f"自动重启: {msg}")
                    if success:
                        self._restart_attempts = 0
                break
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

    def _kill_stale_processes(self):
        try:
            import psutil
            for proc in psutil.process_iter(["pid", "name"]):
                try:
                    name = (proc.info.get("name") or "").lower()
                    if name in ("server.exe", "lunaserver.exe"):
                        self._emit_log("system", f"清理旧进程: {proc.info['name']} (PID: {proc.pid})")
                        proc.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except Exception:
            pass

    def _emit_log(self, log_type: str, line: str):
        if self._on_log:
            try:
                self._on_log(log_type, line)
            except Exception:
                pass

    def _notify_status(self):
        if self._on_status_change:
            try:
                self._on_status_change()
            except Exception:
                pass

    async def _cleanup(self):
        self._running = False
        self._stopping = False
        if self._stdout_task:
            self._stdout_task.cancel()
            self._stdout_task = None
        if self._monitor_task:
            self._monitor_task.cancel()
            self._monitor_task = None
        self.process = None
        self.pid = None
        self.start_time = None
        self._player_names = []
        self._player_count = 0
        self._notify_status()

    def get_recent_logs(self, count: int = 200) -> list[dict]:
        lines = self._line_buffer[-count:]
        return [{"line": line} for line in lines]
