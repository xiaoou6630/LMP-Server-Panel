import os
import sys
import asyncio
import logging
from pathlib import Path
from typing import Optional
from backend.config import get_path, settings
from backend.models import NetworkStatus

logger = logging.getLogger("ML.EasyTier")

WINDOWS = sys.platform == "win32"

EASYTIER_CORE = get_path(settings.EASYTIER_CORE_EXE)
EASYTIER_CLI = get_path(settings.EASYTIER_CLI_EXE)


class EasyTierManager:
    def __init__(self):
        self.process = None
        self._running = False
        self._network_name = ""
        self._network_key = ""
        self._virtual_ip = ""
        self._peers = ""
        self._external_node = ""
        self._listeners = ""

    @property
    def core_available(self) -> bool:
        return os.path.exists(EASYTIER_CORE)

    @property
    def cli_available(self) -> bool:
        return os.path.exists(EASYTIER_CLI)

    async def start(self, network_name: str, network_key: str,
                    peers: str = "", external_node: str = "", listeners: str = "",
                    ipv4: str = "", hostname: str = "", proxy_networks: str = "",
                    mapped_listeners: str = "") -> tuple[bool, str]:
        if not self.core_available:
            return False, f"找不到 easyTier-core: {EASYTIER_CORE}"

        if self._running:
            return False, "EasyTier 已在运行中"

        self._network_name = network_name
        self._network_key = network_key
        self._peers = peers
        self._external_node = external_node
        self._listeners = listeners

        args = [
            EASYTIER_CORE,
            "--network-name", network_name,
            "--network-secret", network_key,
            "--dhcp",
        ]
        if ipv4:
            args.extend(["--ipv4", ipv4])
        if hostname:
            args.extend(["--hostname", hostname])
        if peers:
            for p in peers.split(","):
                p = p.strip()
                if p:
                    args.extend(["--peers", p])
        if external_node:
            args.extend(["--external-node", external_node])
        if listeners:
            args.extend(["--listeners", listeners])
        if proxy_networks:
            for pn in proxy_networks.split(","):
                pn = pn.strip()
                if pn:
                    args.extend(["--proxy-networks", pn])
        if mapped_listeners:
            for ml in mapped_listeners.split(","):
                ml = ml.strip()
                if ml:
                    args.extend(["--mapped-listeners", ml])

        try:
            self.process = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        except Exception as e:
            logger.error(f"启动 EasyTier 失败: {e}")
            return False, f"启动失败: {e}"

        self._running = True
        logger.info(f"EasyTier 已启动 (网络: {network_name}, peers: {peers})")
        return True, f"EasyTier 已启动，网络: {network_name}"

    async def stop(self) -> tuple[bool, str]:
        if not self._running or self.process is None:
            return False, "EasyTier 未在运行"

        try:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=10)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()
        except Exception as e:
            logger.error(f"停止 EasyTier 失败: {e}")

        self._running = False
        self.process = None
        logger.info("EasyTier 已停止")
        return True, "EasyTier 已停止"

    async def get_status(self) -> NetworkStatus:
        if not self._running:
            return NetworkStatus(
                connected=False,
                network_name=self._network_name,
                virtual_ip=self._virtual_ip,
                status_text="未运行" if not self._network_name else "已停止",
            )

        peers = 0
        if self.cli_available:
            try:
                proc = await asyncio.create_subprocess_exec(
                    EASYTIER_CLI, "peer",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
                output = stdout.decode("utf-8", errors="replace")
                peers = max(0, output.count("peer") - 1)
            except Exception:
                pass

        return NetworkStatus(
            connected=True,
            network_name=self._network_name,
            virtual_ip=self._virtual_ip or "10.0.0.1",
            status_text=f"已连接 - {peers} 个对等节点",
            peers_count=peers,
        )

    async def get_virtual_ip(self) -> Optional[str]:
        if self.cli_available:
            try:
                proc = await asyncio.create_subprocess_exec(
                    EASYTIER_CLI, "route",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
                output = stdout.decode("utf-8", errors="replace")
                for line in output.splitlines():
                    if "10." in line or "172." in line or "192." in line:
                        self._virtual_ip = line.strip()
                        return self._virtual_ip
            except Exception:
                pass
        return None


easytier_manager = EasyTierManager()
