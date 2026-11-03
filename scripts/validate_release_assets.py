#!/usr/bin/env python3
"""Validate downloaded OP13 release assets before creating a release tag."""
import argparse
import json
from pathlib import Path
import zipfile


def validate(directory, expected):
    matrix = json.loads((directory / "matrix.json").read_text())
    if expected < 1 or not isinstance(matrix, list) or len(matrix) != expected:
        raise ValueError("Release matrix count does not match the expected device count")
    archives = sorted(directory.glob("AK3_*_USBWiFi.zip"))
    if len(archives) != expected:
        raise ValueError(f"Expected {expected} kernel ZIPs, found {len(archives)}")
    prefixes = [f"AK3_{item['model']}_{item['os_version']}_" for item in matrix]
    if len(set(prefixes)) != expected:
        raise ValueError("Release matrix contains duplicate targets")
    for prefix in prefixes:
        if sum(path.name.startswith(prefix) for path in archives) != 1:
            raise ValueError("Missing or duplicated release asset for " + prefix)
    for archive in archives:
        with zipfile.ZipFile(archive) as package:
            for name in ("Image", "anykernel.sh"):
                if name not in package.namelist() or package.getinfo(name).file_size == 0:
                    raise ValueError(f"{archive.name} is missing {name}; check artifact extraction")
            bad = package.testzip()
            if bad:
                raise ValueError(f"{archive.name} has a corrupt entry: {bad}")
    return archives


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--expected", type=int, required=True)
    args = parser.parse_args()
    try:
        archives = validate(args.directory, args.expected)
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile, RuntimeError) as error:
        parser.exit(1, "::error::Invalid release assets: " + str(error) + "\n")
    print(f"Validated {len(archives)} complete kernel release ZIP(s)")


if __name__ == "__main__":
    main()
