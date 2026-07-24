#!/usr/bin/env python3
"""Package a Kingdom Come: Deliverance (KCD1/KCD2) loose-file mod into game-ready .pak files.

Pure Python: no shell required, so it runs the same on Windows, macOS, and Linux. A KCD .pak is a
plain ZIP, but CryPak rejects the per-file modification-time metadata that GUI zip tools add, so
the actual packing is done by zip_pak.py (Python's zipfile writes none of those fields). See
README.md for the full rationale and the folder->pak mapping.

Usage: pak_kcd_mod.py MOD_SRC_DIR [OUT_DIR] [--compress deflate|store]
  MOD_SRC_DIR  Folder containing mod.manifest (plus Data/, Localization/, mod.cfg)
  OUT_DIR      Output root (default: dist)
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import zip_pak  # noqa: E402  (sibling module; path set above)

MANIFEST_NAME = "mod.manifest"
CONFIG_NAME = "mod.cfg"
MODID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
VERSION_PATTERN = re.compile(r"^[A-Za-z0-9._+-]*$")


def fail(message: str) -> None:
    raise SystemExit(f"error: {message}")


def read_manifest_tag(manifest_path: str, tag: str) -> str:
    """Return the first <tag>value</tag> from the manifest, or '' if absent (no XML dependency)."""
    text = open(manifest_path, encoding="utf-8", errors="replace").read()
    match = re.search(rf"<{tag}>([^<]*)</{tag}>", text)
    return match.group(1).strip() if match else ""


def is_within(child: str, parent: str) -> bool:
    """True if child is the same as, or nested inside, parent."""
    child_abs = os.path.abspath(child)
    parent_abs = os.path.abspath(parent)
    return child_abs == parent_abs or child_abs.startswith(parent_abs + os.sep)


def main() -> None:
    parser = argparse.ArgumentParser(description="Package a KCD loose-file mod into .pak files.")
    parser.add_argument("source", help="Mod source folder containing mod.manifest.")
    parser.add_argument("out_dir", nargs="?", default="dist", help="Output root (default: dist).")
    parser.add_argument("--compress", choices=("deflate", "store"),
                        default=os.environ.get("PAK_COMPRESS", "deflate"),
                        help="Compression for every zip (default: deflate, or $PAK_COMPRESS).")
    arguments = parser.parse_args()

    # Newlines in a path would forge extra records when written to $GITHUB_OUTPUT.
    for value in (arguments.source, arguments.out_dir):
        if "\n" in value or "\r" in value:
            fail("newlines are not allowed in path arguments")

    source = arguments.source
    if not os.path.isdir(source):
        fail(f"source dir not found: {source}")
    manifest_path = os.path.join(source, MANIFEST_NAME)
    if not os.path.isfile(manifest_path):
        fail(f"{manifest_path} not found")
    if os.path.islink(manifest_path):
        fail("mod.manifest must not be a symlink")
    source = os.path.realpath(source)

    mod_id = read_manifest_tag(manifest_path, "modid")
    mod_version = read_manifest_tag(manifest_path, "version")
    if not mod_id:
        fail("<modid> missing in mod.manifest")
    # modid and version become file/directory names and an rm-rf target, so accept only a safe slug
    # that starts with an alphanumeric. This blocks traversal and names like '.git' or '..'.
    if ".." in mod_id or not MODID_PATTERN.match(mod_id):
        fail(f"invalid <modid>: '{mod_id}'")
    if not VERSION_PATTERN.match(mod_version):
        fail(f"invalid <version>: '{mod_version}'")

    os.makedirs(arguments.out_dir, exist_ok=True)
    output_dir = os.path.realpath(arguments.out_dir)
    deploy_dir = os.path.join(output_dir, mod_id)

    # Refuse only the overlaps that are actually dangerous: deleting deploy_dir must not remove the
    # source, and the output must not sit inside a folder we pack (which would re-ingest it). Output
    # elsewhere under the source (e.g. the default ./dist beside Data/) is fine.
    packed_roots = (os.path.join(source, "Data"), os.path.join(source, "Localization"))
    if is_within(source, deploy_dir):
        fail("output directory contains the source tree")
    if any(is_within(deploy_dir, root) for root in packed_roots):
        fail("output directory is inside a packed folder (Data/ or Localization/)")

    if os.path.exists(deploy_dir):
        shutil.rmtree(deploy_dir)
    os.makedirs(deploy_dir)

    print(f"modid={mod_id} version={mod_version or '<none>'}")
    store = arguments.compress == "store"

    # Data/** (excluding Data/Levels/**) -> Data/<modid>.pak. The packer skips an empty result, so
    # a Data tree that holds only Levels produces no main pak.
    data_dir = os.path.join(source, "Data")
    if os.path.isdir(data_dir) and not os.path.islink(data_dir):
        zip_pak.pack(data_dir, os.path.join(deploy_dir, "Data", f"{mod_id}.pak"),
                     exclude="Levels", store=store)

    # Localization/<Lang>/** -> Localization/<Lang>.pak (symlinked language dirs are skipped).
    localization_dir = os.path.join(source, "Localization")
    if os.path.isdir(localization_dir) and not os.path.islink(localization_dir):
        for name in sorted(os.listdir(localization_dir)):
            language_dir = os.path.join(localization_dir, name)
            if os.path.isdir(language_dir) and not os.path.islink(language_dir):
                zip_pak.pack(language_dir, os.path.join(deploy_dir, "Localization", f"{name}.pak"),
                             store=store)

    # Data/Levels/<level>/** -> Data/Levels/<level>/<modid>.pak (symlinked level dirs are skipped).
    levels_dir = os.path.join(source, "Data", "Levels")
    if os.path.isdir(levels_dir) and not os.path.islink(levels_dir):
        for name in sorted(os.listdir(levels_dir)):
            level_dir = os.path.join(levels_dir, name)
            if os.path.isdir(level_dir) and not os.path.islink(level_dir):
                zip_pak.pack(level_dir, os.path.join(deploy_dir, "Data", "Levels", name, f"{mod_id}.pak"),
                             store=store)

    # mod.manifest and mod.cfg stay loose; a symlinked mod.cfg is skipped so it cannot pull an
    # out-of-tree file into the release.
    shutil.copyfile(manifest_path, os.path.join(deploy_dir, MANIFEST_NAME))
    config_path = os.path.join(source, CONFIG_NAME)
    if os.path.isfile(config_path) and not os.path.islink(config_path):
        shutil.copyfile(config_path, os.path.join(deploy_dir, CONFIG_NAME))

    # Release archive: <modid>-v<version>.zip containing the whole deploy folder.
    suffix = f"-v{mod_version}" if mod_version else ""
    archive_path = os.path.join(output_dir, f"{mod_id}{suffix}.zip")
    zip_pak.pack(deploy_dir, archive_path, base=output_dir, store=store, include_pak=True)
    print(f"release: {os.path.relpath(archive_path, output_dir)}")

    # Expose results to GitHub Actions (a no-op outside CI). Paths are already native on Windows,
    # and the values are validated and newline-free, so they cannot inject extra output records.
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as handle:
            handle.write(f"modid={mod_id}\n")
            handle.write(f"version={mod_version}\n")
            handle.write(f"archive={archive_path}\n")
            handle.write(f"mod-dir={deploy_dir}\n")

    print(f"done -> {deploy_dir}")


if __name__ == "__main__":
    main()
