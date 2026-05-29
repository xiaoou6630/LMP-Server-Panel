import os
import json
import xml.etree.ElementTree as ET
import logging
from enum import Enum

logger = logging.getLogger("ML.ModList")

MOD_CONTROL_FILENAME = "LMPModControl.xml"


class ModRule(str, Enum):
    ALLOW = "Allow"
    DENY = "Deny"
    FORCE = "Force"


RULE_TO_CKAN = {
    ModRule.ALLOW: "recommends",
    ModRule.DENY: "conflicts",
    ModRule.FORCE: "depends",
}


class ModListManager:
    def __init__(self):
        self._lmp_config_dir = ""
        self._data = {"allow_non_listed": True, "items": {}}

    @property
    def config_dir(self) -> str:
        if self._lmp_config_dir:
            return self._lmp_config_dir
        from backend.config import get_path
        self._lmp_config_dir = get_path("tools", "lmp_server", "LMPServer", "Config")
        return self._lmp_config_dir

    @property
    def modfile_path(self) -> str:
        return os.path.join(self.config_dir, MOD_CONTROL_FILENAME)

    def load(self) -> dict:
        os.makedirs(self.config_dir, exist_ok=True)
        path = self.modfile_path
        if os.path.exists(path):
            try:
                tree = ET.parse(path)
                root = tree.getroot()
                anl = root.find("AllowNonListedPlugins")
                allow = True
                if anl is not None and anl.text is not None:
                    allow = anl.text.lower() == "true"

                result = {"allow_non_listed": allow, "items": {}}
                for tag, rule in [("MandatoryPlugins", ModRule.FORCE.value),
                                  ("OptionalPlugins", ModRule.ALLOW.value),
                                  ("ForbiddenPlugins", ModRule.DENY.value)]:
                    container = root.find(tag)
                    if container is not None:
                        for item in container:
                            fp_el = item.find("FilePath")
                            if fp_el is None or not fp_el.text:
                                continue
                            mod_id = fp_el.text.strip()
                            txt_el = item.find("Text")
                            link_el = item.find("Link")
                            sha_el = item.find("Sha")
                            result["items"][mod_id] = {
                                "name": txt_el.text if txt_el is not None and txt_el.text else mod_id,
                                "rule": rule,
                                "link": link_el.text if link_el is not None and link_el.text else "",
                                "sha": sha_el.text if sha_el is not None and sha_el.text else "",
                            }
                self._data = result
                logger.info(f"已加载模组名单: {len(result['items'])} 条规则")
                return result
            except Exception as e:
                logger.warning(f"解析 ModControl.xml 失败: {e}")

        self._data = {"allow_non_listed": True, "items": {}}
        self._save_to_file()
        return self._data

    def _save_to_file(self):
        os.makedirs(self.config_dir, exist_ok=True)
        root = ET.Element("ModControlStructure",
                          {"xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
                           "xmlns:xsd": "http://www.w3.org/2001/XMLSchema"})

        anl = ET.SubElement(root, "AllowNonListedPlugins")
        anl.text = str(self._data.get("allow_non_listed", True)).lower()

        for tag in ["RequiredExpansions", "AllowedParts", "AllowedResources"]:
            ET.SubElement(root, tag)

        mandatory = ET.SubElement(root, "MandatoryPlugins")
        optional = ET.SubElement(root, "OptionalPlugins")
        forbidden = ET.SubElement(root, "ForbiddenPlugins")
        ET.SubElement(root, "MandatoryParts")

        for mod_id, mod in self._data.get("items", {}).items():
            rule = mod.get("rule", ModRule.ALLOW.value)
            if rule == ModRule.FORCE.value:
                parent = mandatory
            elif rule == ModRule.DENY.value:
                df = ET.SubElement(forbidden, "ForbiddenDllFile")
                ET.SubElement(df, "Text").text = mod.get("name", mod_id)
                ET.SubElement(df, "FilePath").text = mod_id
                continue
            else:
                parent = optional
            dll = ET.SubElement(parent, "DllFile")
            ET.SubElement(dll, "Text").text = mod.get("name", mod_id)
            ET.SubElement(dll, "Link").text = mod.get("link", "")
            ET.SubElement(dll, "FilePath").text = mod_id
            ET.SubElement(dll, "Sha").text = mod.get("sha", "")

        import xml.dom.minidom
        ugly = ET.tostring(root, encoding="unicode")
        dom = xml.dom.minidom.parseString(ugly)
        path = self.modfile_path
        with open(path, "w", encoding="utf-8") as f:
            f.write(dom.toprettyxml(indent="  "))
        logger.info(f"已保存模组名单到: {path}")

    def list_items(self) -> list[dict]:
        self.load()
        return [{"id": mid, **mod} for mid, mod in self._data.get("items", {}).items()]

    def add_item(self, mod_id: str, name: str, rule: str = "Allow",
                 link: str = "", sha: str = "") -> bool:
        if rule not in [r.value for r in ModRule]:
            return False
        self.load()
        self._data["items"][mod_id] = {"name": name, "rule": rule, "link": link, "sha": sha}
        self._save_to_file()
        return True

    def remove_item(self, mod_id: str) -> bool:
        self.load()
        if mod_id in self._data.get("items", {}):
            del self._data["items"][mod_id]
            self._save_to_file()
            return True
        return False

    def update_rule(self, mod_id: str, new_rule: str) -> bool:
        if new_rule not in [r.value for r in ModRule]:
            return False
        self.load()
        if mod_id in self._data.get("items", {}):
            self._data["items"][mod_id]["rule"] = new_rule
            self._save_to_file()
            return True
        return False

    def get_allow_non_listed(self) -> bool:
        return self._data.get("allow_non_listed", True)

    def set_allow_non_listed(self, value: bool):
        self._data["allow_non_listed"] = value
        self._save_to_file()
