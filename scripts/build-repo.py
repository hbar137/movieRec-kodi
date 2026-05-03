#!/usr/bin/env python3
"""Build the Kodi repository tree for gh-pages.

Output layout (under --out):
    addons.xml
    addons.xml.md5
    <addon_id>/
        addon.xml
        <addon_id>-<version>.zip

Each zip contains a top-level <addon_id>/ folder so Kodi extracts it correctly.
"""
import argparse
import hashlib
import os
import shutil
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ADDON_DIRS = ["plugin.video.movierec", "repository.movierec"]
EXCLUDE_FILE_SUFFIXES = (".pyc",)
EXCLUDE_DIR_NAMES = {"__pycache__", ".git"}


def addon_meta(addon_dir: Path):
    tree = ET.parse(addon_dir / "addon.xml")
    root = tree.getroot()
    return root.attrib["id"], root.attrib["version"], root


def zip_addon(addon_dir: Path, out_path: Path, addon_id: str):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(addon_dir):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIR_NAMES]
            for f in files:
                if f.endswith(EXCLUDE_FILE_SUFFIXES):
                    continue
                src = Path(root) / f
                rel = src.relative_to(addon_dir)
                arc = Path(addon_id) / rel
                z.write(src, str(arc))


def build_index(roots, out_path: Path):
    index = ET.Element("addons")
    for r in roots:
        index.append(r)
    out_path.write_bytes(
        b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        + ET.tostring(index, encoding="utf-8")
    )


def md5_of(path: Path) -> str:
    h = hashlib.md5()
    h.update(path.read_bytes())
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=".", help="repo root")
    ap.add_argument("--out", default="_site", help="output dir for gh-pages")
    args = ap.parse_args()

    src = Path(args.src).resolve()
    out = Path(args.out).resolve()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    roots = []
    for ad in ADDON_DIRS:
        d = src / ad
        if not d.is_dir():
            print(f"WARN: missing {d}", file=sys.stderr)
            continue
        addon_id, version, root = addon_meta(d)
        zip_path = out / addon_id / f"{addon_id}-{version}.zip"
        zip_addon(d, zip_path, addon_id)
        # Mirror addon.xml alongside the zip (some Kodi builds use it).
        shutil.copy2(d / "addon.xml", out / addon_id / "addon.xml")
        roots.append(root)
        print(f"built {addon_id} {version}")

    index_path = out / "addons.xml"
    build_index(roots, index_path)
    (out / "addons.xml.md5").write_text(md5_of(index_path) + "\n")
    print(f"index → {index_path}")


if __name__ == "__main__":
    main()
