#!/usr/bin/env python3
"""Zip a directory's contents into a CryEngine/CryPak-compatible .pak (a plain ZIP).

KCD1/KCD2 paks are ordinary ZIP archives, but CryPak rejects the per-file modification-time
extra fields (NTFS 0x000A / extended-timestamp 0x5455) that GUI tools such as 7-Zip and WinRAR
add by default. Python's zipfile writes none of those fields, so the archives produced here load
in-game. Entries are sorted for a stable, platform-independent order.

Usage:
    zip_pak.py SOURCE OUTPUT [--base BASE] [--exclude REL] [--store] [--include-pak]
"""
from __future__ import annotations

import argparse
import os
import sys
import zipfile

# CPython's zipfile switches to ZIP64 near 2 GiB (below the 4 GiB uint32 max) and past 65535
# entries. CryPak predates ZIP64 and may reject such archives, so warn before that point.
MAX_ENTRIES = 65535
ZIP64_WARN_BYTES = 2_000_000_000


def _reraise(error: OSError) -> None:
    """os.walk error handler: turn a traversal error (e.g. permission denied) into a hard failure."""
    raise error


def is_unsafe_arcname(name: str) -> bool:
    """Reject names that traverse or are rooted under POSIX or Windows extraction rules."""
    if "\\" in name:                                  # backslash is a Windows separator / traversal
        return True
    if name.startswith("/") or os.path.isabs(name):   # rooted path
        return True
    if len(name) >= 2 and name[1] == ":":             # drive-qualified, e.g. C:...
        return True
    return ".." in name.split("/")                    # parent-directory component


def collect_entries(source_dir: str, base_dir: str, exclude: str, include_pak: bool) -> list[tuple[str, str]]:
    """Return sorted (absolute_path, archive_name) pairs for every file to pack."""
    exclude_prefix = exclude.rstrip("/") + "/" if exclude else ""
    entries: list[tuple[str, str]] = []
    for directory, _subdirs, filenames in os.walk(source_dir, onerror=_reraise):
        for filename in filenames:
            absolute_path = os.path.join(directory, filename)
            relative_to_source = os.path.relpath(absolute_path, source_dir).replace(os.sep, "/")
            if os.path.islink(absolute_path):
                # Do not follow links out of the source tree; keep this consistent with the shell.
                print(f"warning: skipping symlink: {relative_to_source}", file=sys.stderr)
                continue
            if not os.path.isfile(absolute_path):
                continue
            if not include_pak and relative_to_source.lower().endswith(".pak"):
                print(f"warning: skipping existing .pak file: {relative_to_source}", file=sys.stderr)
                continue
            if exclude and (relative_to_source == exclude or relative_to_source.startswith(exclude_prefix)):
                continue
            archive_name = os.path.relpath(absolute_path, base_dir).replace(os.sep, "/")
            if is_unsafe_arcname(archive_name):
                # Exclude (do not abort): keep the dangerous name out of the pak but still build it.
                print(f"warning: skipping file with an unsafe archive path: {archive_name}",
                      file=sys.stderr)
                continue
            entries.append((absolute_path, archive_name))
    # Case-insensitive first, then exact, so case-only collisions order deterministically everywhere.
    entries.sort(key=lambda pair: (pair[1].lower(), pair[1]))
    return entries


def warn_if_zip64_likely(entries: list[tuple[str, str]]) -> None:
    """Warn if the archive would likely need ZIP64, which older CryPak builds may not read."""
    total_size = 0
    for absolute_path, archive_name in entries:
        size = os.path.getsize(absolute_path)
        total_size += size
        if size > ZIP64_WARN_BYTES:
            print(f"warning: '{archive_name}' is ~{size / 1e9:.1f} GB; the pak likely needs ZIP64 "
                  "and may not load in KCD.", file=sys.stderr)
    if len(entries) > MAX_ENTRIES or total_size > ZIP64_WARN_BYTES:
        print(f"warning: {len(entries)} entries / {total_size} bytes may require ZIP64, which older "
              "CryPak builds may reject.", file=sys.stderr)


def write_archive(entries: list[tuple[str, str]], output_path: str, store: bool) -> None:
    """Write entries into a fresh ZIP at output_path (Store or Deflate)."""
    method = zipfile.ZIP_STORED if store else zipfile.ZIP_DEFLATED
    options = {} if store else {"compresslevel": 9}
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    if os.path.exists(output_path):
        os.remove(output_path)
    # strict_timestamps=False clamps pre-1980 / post-2107 mtimes instead of raising. It only affects
    # the DOS date field in the base header, never the extra fields, so paks stay CryPak-safe.
    with zipfile.ZipFile(output_path, "w", method, strict_timestamps=False, **options) as archive:
        for absolute_path, archive_name in entries:
            archive.write(absolute_path, archive_name)


def pack(source: str, output: str, base: str | None = None, exclude: str = "",
         store: bool = False, include_pak: bool = False) -> int:
    """Pack SOURCE into the ZIP at OUTPUT. Returns the entry count, or 0 if skipped as empty."""
    if not os.path.isdir(source):
        raise SystemExit(f"error: source directory not found: {source}")
    if os.path.islink(source):
        raise SystemExit(f"error: source directory is a symlink (not followed): {source}")
    source_abs = os.path.abspath(source)
    output_abs = os.path.abspath(output)
    if output_abs == source_abs or output_abs.startswith(source_abs + os.sep):
        raise SystemExit("error: OUTPUT must not be inside SOURCE (it would be re-ingested).")
    base_dir = base or source
    try:
        relative = os.path.relpath(source_abs, os.path.abspath(base_dir))
    except ValueError as error:  # different drive on Windows
        raise SystemExit(f"error: --base and SOURCE must be on the same drive: {error}")
    if relative.split(os.sep)[0] == "..":
        raise SystemExit(f"error: --base must be a parent directory of SOURCE (base={base_dir}).")
    entries = collect_entries(source, base_dir, exclude, include_pak)
    if not entries:
        print(f"  (skipped {os.path.basename(output)}: no files)")
        return 0
    warn_if_zip64_likely(entries)
    write_archive(entries, output, store)
    print(f"  + {os.path.basename(output)} ({len(entries)} files)")
    return len(entries)


def main() -> None:
    parser = argparse.ArgumentParser(description="Zip a directory into a CryPak-safe .pak/.zip.")
    parser.add_argument("source", help="Directory whose contents are packed.")
    parser.add_argument("output", help="Destination .pak/.zip path.")
    parser.add_argument("--base", help="Root that archive paths are relative to (default: SOURCE).")
    parser.add_argument("--exclude", default="", help="Relative subtree to skip, e.g. 'Levels'.")
    parser.add_argument("--store", action="store_true", help="Store with no compression.")
    parser.add_argument("--include-pak", action="store_true", help="Include existing .pak files.")
    arguments = parser.parse_args()
    pack(arguments.source, arguments.output, arguments.base, arguments.exclude,
         arguments.store, arguments.include_pak)


if __name__ == "__main__":
    main()
