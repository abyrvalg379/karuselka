"""Build KARUSELKA: generate legacy from extension + zips into out/v<version>.

The legacy package gets a generated bl_info header. The LAMPOCHKA v2.4.1
regression (legacy shipped without bl_info) must never repeat, so this
script is the only supported way to build the zips.

Usage: python build.py
"""

import re
import shutil
import sys
import zipfile
from pathlib import Path

WORK = Path(__file__).resolve().parent
EXT = WORK / "extension"
LEGACY = WORK / "legacy" / "karuselka"
OUT = WORK.parent / "out"

BL_INFO = '''bl_info = {
    "name": "KARUSELKA",
    "author": "Maksim Kovalev",
    "version": (%VERSION%),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar (N) > KARUSELKA",
    "description": "Fast camera turntable rig: orbit camera + linear keyframes + animation render",
    "doc_url": "https://github.com/abyrvalg379/karuselka",
    "license": "GPL-3.0-or-later",
    "category": "Animation",
}
'''


def main():
    manifest = (EXT / "blender_manifest.toml").read_text(encoding="utf-8")
    # ^-anchored: otherwise schema_version matches first
    ver = re.search(r'^version = "(\d+)\.(\d+)\.(\d+)"', manifest, re.MULTILINE)
    if not ver:
        sys.exit("build.py: no version line in blender_manifest.toml")
    v = tuple(int(g) for g in ver.groups())
    version = ".".join(str(x) for x in v)

    body = (EXT / "__init__.py").read_text(encoding="utf-8")
    header = BL_INFO.replace("%VERSION%", "{}, {}, {}".format(v[0], v[1], v[2]))
    LEGACY.mkdir(parents=True, exist_ok=True)
    (LEGACY / "__init__.py").write_text(header + "\n" + body, encoding="utf-8")

    dest = OUT / f"v{version}"
    dest.mkdir(parents=True, exist_ok=True)

    ext_zip = dest / "karuselka_extension.zip"
    with zipfile.ZipFile(ext_zip, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(EXT / "__init__.py", "__init__.py")
        z.write(EXT / "blender_manifest.toml", "blender_manifest.toml")

    leg_zip = dest / "karuselka_legacy.zip"
    with zipfile.ZipFile(leg_zip, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(LEGACY / "__init__.py", "karuselka/__init__.py")

    for name in ("README.md", "README_ru.md", "LICENSE"):
        src = WORK / name
        if src.exists():
            shutil.copy2(src, dest / name)

    print(f"v{version}:")
    print(f"  {ext_zip}")
    print(f"  {leg_zip}")


if __name__ == "__main__":
    main()
