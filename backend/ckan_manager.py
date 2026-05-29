import os
import re
import json
import asyncio
import logging
from typing import Optional
from pathlib import Path
from backend.config import get_path, settings

logger = logging.getLogger("ML.CKAN")

CKAN_EXE = get_path(settings.CKAN_EXE)
LOCAL_KSP_DIR = get_path("data", "ksp_local")
LOCAL_GAMEDATA = os.path.join(LOCAL_KSP_DIR, "GameData")
INSTANCE_NAME = "ML_LOCAL"


class CkanManager:
    def __init__(self):
        self._ckan_path = CKAN_EXE
        self._gamedir = ""

    def _cleanup_lock(self):
        lock_path = os.path.join(self.gamedir, "CKAN", "registry.locked")
        if os.path.exists(lock_path):
            try:
                os.remove(lock_path)
                logger.info(f"已清理 CKAN 注册表锁文件: {lock_path}")
            except Exception as e:
                logger.warning(f"清理 CKAN 锁文件失败: {e}")

    @property
    def available(self) -> bool:
        return os.path.exists(self._ckan_path)

    @property
    def gamedir(self) -> str:
        if self._gamedir:
            return self._gamedir
        user_path = settings.KSP_GAMEDATA_PATH
        if user_path:
            abs_path = get_path(user_path) if not os.path.isabs(user_path) else user_path
            parent = os.path.dirname(abs_path)
            if os.path.isdir(parent):
                self._gamedir = parent
                return self._gamedir
            if os.path.isdir(abs_path):
                self._gamedir = abs_path
                return self._gamedir
        os.makedirs(LOCAL_GAMEDATA, exist_ok=True)
        self._gamedir = str(LOCAL_KSP_DIR)
        return self._gamedir

    async def _ensure_instance(self):
        if not self.available:
            return
        gd = self.gamedir
        try:
            os.makedirs(os.path.join(gd, "GameData"), exist_ok=True)
            proc = await asyncio.create_subprocess_exec(
                self._ckan_path, "instance", "fake",
                INSTANCE_NAME, gd, "1.12.3",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
        except Exception:
            pass

    async def _run_ckan(self, args: list[str], timeout: int = 120) -> tuple[int, str, str]:
        self._cleanup_lock()
        for attempt in range(2):
            cmd = [self._ckan_path] + args
            gd = self.gamedir
            if gd:
                cmd += ["--gamedir", gd]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
                out = self._decode(stdout)
                err = self._decode(stderr)
                if proc.returncode != 0 and ("locked" in err.lower() or "kraken" in err.lower()):
                    self._cleanup_lock()
                    continue
                return proc.returncode, out, err
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                if attempt == 0:
                    self._cleanup_lock()
                    continue
                return -1, "", "命令超时"
        return -1, "", "注册表锁定"

    def _decode(self, data: bytes) -> str:
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            try:
                return data.decode("gbk")
            except UnicodeDecodeError:
                return data.decode("utf-8", errors="replace")

    async def search(self, query: str, page: int = 1, page_size: int = 50) -> dict:
        if not self.available:
            return {"mods": [], "total": 0, "page": page, "page_size": page_size}
        await self._ensure_instance()
        args = ["search", "--detail"]
        if query:
            args.append(query)
        ret, stdout, stderr = await self._run_ckan(args)
        if ret != 0:
            logger.warning(f"CKAN 搜索失败: {stderr}")
            return {"mods": [], "total": 0, "page": page, "page_size": page_size}
        all_mods = self._parse_search_output(stdout)
        total = len(all_mods)
        start = (page - 1) * page_size
        end = start + page_size
        return {
            "mods": all_mods[start:end],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def browse_all(self, page: int = 1, page_size: int = 50) -> dict:
        if not self.available:
            return {"mods": [], "total": 0, "page": page, "page_size": page_size}
        await self._ensure_instance()
        ret, stdout, stderr = await self._run_ckan(["available", "--detail"], timeout=120)
        if ret != 0:
            logger.warning(f"CKAN 浏览全部失败: {stderr}")
            return {"mods": [], "total": 0, "page": page, "page_size": page_size}
        all_mods = self._parse_search_output(stdout)
        total = len(all_mods)
        start = (page - 1) * page_size
        end = start + page_size
        return {
            "mods": all_mods[start:end],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def _parse_search_output(self, text: str) -> list[dict]:
        mods = []
        line_pattern = re.compile(r"^\*\s+(.+?)\s+\((.+?)\)\s*-\s*(.+)", re.MULTILINE)
        for m in line_pattern.finditer(text):
            identifier = m.group(1).strip()
            version = m.group(2).strip()
            rest = m.group(3).strip()
            author = ""
            abstract = ""
            display_name = rest
            by_match = re.search(r"\s+by\s+", rest)
            if by_match:
                display_name = rest[:by_match.start()].strip()
                after_by = rest[by_match.end():].strip()
                sep_idx = after_by.find(" - ")
                if sep_idx != -1:
                    author = after_by[:sep_idx].strip()
                    abstract = after_by[sep_idx + 3:].strip()
                else:
                    author = after_by
            else:
                sep_idx = rest.find(" - ")
                if sep_idx != -1:
                    display_name = rest[:sep_idx].strip()
                    abstract = rest[sep_idx + 3:].strip()
            mods.append({
                "name": identifier,
                "display_name": display_name,
                "identifier": identifier,
                "abstract": abstract,
                "version": version,
                "author": author,
                "download_url": "",
                "ksp_version": "",
                "installed": False,
            })
        return mods

    async def list_installed(self) -> list[dict]:
        if not self.available:
            return []
        await self._ensure_instance()
        ret, stdout, stderr = await self._run_ckan(["list", "installed", "--export", "ckan"])
        if ret != 0:
            return []
        try:
            raw = json.loads(stdout)
        except json.JSONDecodeError:
            return []
        mods = []
        if isinstance(raw, dict):
            depends = raw.get("depends", [])
            for dep in depends:
                mod_id = dep.get("name", "") if isinstance(dep, dict) else str(dep)
                if mod_id:
                    mods.append({"name": mod_id, "identifier": mod_id, "version": "", "abstract": "", "installed": True})
        if isinstance(raw, list):
            for item in raw:
                mods.append({
                    "name": item.get("name", item.get("identifier", "")),
                    "identifier": item.get("identifier", ""),
                    "version": str(item.get("version", "")),
                    "abstract": item.get("abstract", ""),
                    "installed": True,
                })
        return mods

    async def install(self, identifier: str) -> str:
        if not self.available:
            raise RuntimeError("CKAN 不可用，请检查 CKAN.exe 路径")
        await self._ensure_instance()
        ret, stdout, stderr = await self._run_ckan(["install", identifier], timeout=300)
        if ret != 0:
            raise RuntimeError(f"安装失败: {stderr or stdout}")
        return stdout

    async def uninstall(self, identifier: str) -> str:
        if not self.available:
            raise RuntimeError("CKAN 不可用")
        await self._ensure_instance()
        ret, stdout, stderr = await self._run_ckan(["remove", identifier], timeout=60)
        if ret != 0:
            raise RuntimeError(f"卸载失败: {stderr or stdout}")
        return stdout

    async def refresh(self) -> bool:
        if not self.available:
            return False
        await self._ensure_instance()
        ret, stdout, stderr = await self._run_ckan(["update"], timeout=120)
        return ret == 0

    async def show(self, identifier: str) -> dict:
        if not self.available:
            raise RuntimeError("CKAN 不可用")
        await self._ensure_instance()
        ret, stdout, stderr = await self._run_ckan(["show", identifier], timeout=30)
        if ret != 0:
            raise RuntimeError(f"获取详情失败: {stderr or stdout}")
        return self._parse_show_output(stdout)

    def _parse_show_output(self, text: str) -> dict:
        result = {"name": "", "identifier": "", "abstract": "", "description": "",
                   "version": "", "author": "", "license": "", "homepage": "",
                   "repository": "", "tags": [], "depends": [], "conflicts": [],
                   "recommends": [], "suggests": []}
        current_section = ""
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            lower = stripped.lower()
            if lower.startswith("module info"):
                current_section = "info"; continue
            elif lower.startswith("depends"):
                current_section = "depends"; continue
            elif lower.startswith("conflicts"):
                current_section = "conflicts"; continue
            elif lower.startswith("recommends"):
                current_section = "recommends"; continue
            elif lower.startswith("suggests"):
                current_section = "suggests"; continue
            elif lower.startswith("resources"):
                current_section = "resources"; continue

            if current_section == "info" and ":" in stripped:
                key, _, val = stripped.partition(":")
                key = key.strip().lower()
                val = val.strip()
                if key in ("version", "license"):
                    result[key] = val
                elif key == "authors":
                    result["author"] = val
                elif key == "tags":
                    result["tags"] = [t.strip() for t in val.split(",") if t.strip()]
            elif current_section == "depends" and stripped.startswith("- "):
                result["depends"].append(stripped[2:])
            elif current_section == "conflicts" and stripped.startswith("- "):
                result["conflicts"].append(stripped[2:])
            elif current_section == "recommends" and stripped.startswith("- "):
                result["recommends"].append(stripped[2:])
            elif current_section == "suggests" and stripped.startswith("- "):
                result["suggests"].append(stripped[2:])
            elif current_section == "resources" and ":" in stripped:
                key, _, val = stripped.partition(":")
                key = key.strip().lower()
                val = val.strip()
                if key == "home page":
                    result["homepage"] = val
                elif key == "repository":
                    result["repository"] = val

        if not result["author"]:
            for line in text.splitlines():
                s = line.strip()
                if s.startswith("Authors:"):
                    result["author"] = s[8:].strip()
                elif s.startswith("Home page:"):
                    result["homepage"] = s[10:].strip()
                elif s.startswith("Repository:"):
                    result["repository"] = s[11:].strip()
        return result

    async def _run_ckan_simple(self, args: list[str], timeout: int = 30) -> tuple[int, str]:
        cmd = [self._ckan_path] + args + ["--gamedir", self.gamedir]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return proc.returncode, self._decode(stdout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return -1, ""

    async def list_repos(self) -> list[dict]:
        if not self.available:
            return []
        await self._ensure_instance()
        self._cleanup_lock()
        ret, out = await self._run_ckan_simple(["repo", "list"])
        repos = []
        for line in out.splitlines():
            line = line.strip()
            if not line or line.startswith("Repository") or line.startswith("---") or line.startswith("Priority"):
                continue
            if "δ��������" in line or "异常" in line or "ERR" in line.upper():
                continue
            parts = line.split()
            if len(parts) >= 2:
                repos.append({"name": parts[0].strip(), "url": parts[-1].strip(), "priority": 0})
        if not repos and "locked" in out.lower() or "kraken" in out.lower():
            logger.warning("CKAN 注册表被锁定，返回空列表")
        return repos

    async def available_repos(self) -> list[str]:
        if not self.available:
            return []
        await self._ensure_instance()
        ret, out = await self._run_ckan_simple(["repo", "available"])
        return [l.strip() for l in out.splitlines() if l.strip() and not l.startswith("Available")]

    async def add_repo(self, url: str, name: str = "") -> str:
        if not self.available:
            raise RuntimeError("CKAN 不可用")
        await self._ensure_instance()
        args = ["repo", "add", url]
        if name:
            args.append(name)
        ret, out = await self._run_ckan_simple(args)
        if ret != 0:
            raise RuntimeError(f"添加仓库失败: {out}")
        return out

    async def remove_repo(self, name: str) -> str:
        if not self.available:
            raise RuntimeError("CKAN 不可用")
        await self._ensure_instance()
        ret, out = await self._run_ckan_simple(["repo", "forget", name])
        if ret != 0:
            raise RuntimeError(f"删除仓库失败: {out}")
        return out

    async def set_default_repo(self, name: str) -> str:
        if not self.available:
            raise RuntimeError("CKAN 不可用")
        await self._ensure_instance()
        ret, out = await self._run_ckan_simple(["repo", "default", name])
        if ret != 0:
            raise RuntimeError(f"设置默认仓库失败: {out}")
        return out


ckan_manager = CkanManager()
