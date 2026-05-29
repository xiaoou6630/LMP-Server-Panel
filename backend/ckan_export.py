import json
import os
from datetime import datetime
from typing import List, Dict

IDENTIFIER_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9-]+$"
MIN_SPEC_VERSION = "v1.6"

RULE_TO_CKAN = {
    "Allow": "recommends",
    "Force": "depends",
    "Deny": "conflicts",
}


def build_ckan_metapackage(metadata: dict, mods: List[dict]) -> dict:
    identifier = metadata.get("identifier", "my-ksp-modpack")
    name = metadata.get("name", identifier)
    abstract = metadata.get("abstract", f"Modpack: {name}")
    author = metadata.get("author", os.environ.get("USERNAME", "ML User"))
    license_val = metadata.get("license", "MIT")
    version = metadata.get("version", datetime.utcnow().strftime("%Y.%m.%d.%H.%M.%S"))

    if isinstance(author, str):
        author = [a.strip() for a in author.split(",") if a.strip()]
    if isinstance(license_val, str):
        license_val = [l.strip() for l in license_val.split(",") if l.strip()]

    ckan = {
        "spec_version": metadata.get("spec_version", MIN_SPEC_VERSION),
        "identifier": identifier,
        "name": name,
        "abstract": abstract,
        "author": author,
        "license": license_val,
        "version": version,
        "kind": "metapackage",
    }

    depends = []
    recommends = []
    conflicts = []

    for mod in mods:
        mod_id = mod.get("identifier", "")
        mod_rule = mod.get("rule", "Allow")
        mod_version = mod.get("version", "")
        rel = {"name": mod_id}
        if mod_version:
            rel["version"] = mod_version
        ckan_type = RULE_TO_CKAN.get(mod_rule, "recommends")
        if ckan_type == "depends":
            depends.append(rel)
        elif ckan_type == "conflicts":
            conflicts.append(rel)
        else:
            recommends.append(rel)

    if depends:
        ckan["depends"] = depends
    if recommends:
        ckan["recommends"] = recommends
    if conflicts:
        ckan["conflicts"] = conflicts

    return ckan


def export_to_ckan_json(metadata: dict, mods: List[dict]) -> str:
    ckan = build_ckan_metapackage(metadata, mods)
    return json.dumps(ckan, indent=2, ensure_ascii=False)


def export_to_ckan_file(metadata: dict, mods: List[dict], output_dir: str) -> str:
    ckan = build_ckan_metapackage(metadata, mods)
    identifier = ckan.get("identifier", "modpack")
    version = ckan.get("version", "1.0.0")
    filename = f"{identifier}-{version}.ckan"
    filepath = os.path.join(output_dir, filename)
    os.makedirs(output_dir, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(ckan, f, indent=2, ensure_ascii=False)
    return filepath
