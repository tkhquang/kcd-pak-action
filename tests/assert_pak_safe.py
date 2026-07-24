#!/usr/bin/env python3
"""Assert that .pak/.zip files are CryPak-safe.

A file is CryPak-safe when it is a structurally valid ZIP and none of its local or central headers
carry a forbidden modification-time extra field: NTFS time (0x000A) or extended timestamp / "UT"
(0x5455). Benign extra fields such as ZIP64 (0x0001) are reported but do not fail the check. With
--method, also assert every entry uses the given compression method (0 = Store, 8 = Deflate).

Usage:
    assert_pak_safe.py [--method N] FILE [FILE ...]
"""
from __future__ import annotations

import argparse
import mmap
import struct
import sys
import zipfile

# ZIP extra-field ids that CryPak rejects; any other id (e.g. 0x0001 ZIP64) is allowed.
FORBIDDEN_FIELD_IDS = {0x000A: "NTFS-time", 0x5455: "UT-ext-timestamp"}


def forbidden_bytes_in_extra(extra: bytes) -> int:
    """Sum the byte lengths of forbidden extra fields within one header's extra area."""
    total = 0
    offset = 0
    while offset + 4 <= len(extra):
        field_id, field_len = struct.unpack_from("<HH", extra, offset)
        if field_id in FORBIDDEN_FIELD_IDS:
            total += field_len
        offset += 4 + field_len
    return total


def scan(path: str) -> tuple[int, set[int]] | None:
    """Return (forbidden extra-field bytes, compression methods), or None if not a valid ZIP."""
    if not zipfile.is_zipfile(path):
        return None
    forbidden = 0
    methods: set[int] = set()
    with open(path, "rb") as handle, mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as data:
        index, size = 0, len(data)
        while index < size:
            signature = data[index:index + 4]
            if signature == b"PK\x03\x04":
                fields = struct.unpack_from("<HHHHHIIIHH", data, index + 4)
                method, comp_size, name_len, extra_len = fields[2], fields[6], fields[8], fields[9]
                methods.add(method)
                extra = data[index + 30 + name_len:index + 30 + name_len + extra_len]
                forbidden += forbidden_bytes_in_extra(extra)
                index += 30 + name_len + extra_len + comp_size
            elif signature == b"PK\x01\x02":
                name_len, extra_len, comment_len = struct.unpack_from("<HHH", data, index + 28)
                extra = data[index + 46 + name_len:index + 46 + name_len + extra_len]
                forbidden += forbidden_bytes_in_extra(extra)
                index += 46 + name_len + extra_len + comment_len
            elif signature == b"PK\x05\x06":
                break
            else:
                index += 1
    return forbidden, methods


def main() -> None:
    parser = argparse.ArgumentParser(description="Assert .pak files are CryPak-safe.")
    parser.add_argument("files", nargs="+")
    parser.add_argument("--method", type=int, help="Require every entry to use this method (0 or 8).")
    arguments = parser.parse_args()

    failed = False
    for path in arguments.files:
        result = scan(path)
        if result is None:
            print(f"BAD {path}: not a valid ZIP archive")
            failed = True
            continue
        forbidden, methods = result
        method_ok = arguments.method is None or methods <= {arguments.method}
        safe = forbidden == 0 and method_ok
        print(f"{'ok ' if safe else 'BAD'} {path}: forbidden-ts-bytes={forbidden} methods={sorted(methods)}")
        failed = failed or not safe
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
