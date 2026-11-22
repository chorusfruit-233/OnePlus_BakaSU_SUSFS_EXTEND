#!/usr/bin/env python3
"""Validate downloaded OP13 release assets before creating a release tag."""
import argparse
import json
from pathlib import Path
import zipfile

from build_target import validate as validate_target


def validate(directory, expected):
    matrix = json.loads((directory / "matrix.json").read_text())
    if expected != 1 or not isinstance(matrix, list) or len(matrix) != 1:
        raise ValueError("Expected exactly one OP13 ColorOS 17 release target")
    target = validate_target(matrix[0])
    archives = sorted(directory.glob("AK3_*_USBWiFi.zip"))
    if len(archives) != 1:
        raise ValueError(f"Expected one kernel ZIP, found {len(archives)}")
    prefix = f"AK3_{target['model']}_{target['os_version']}_{target['android_version']}-{target['kernel_version']}."
    if not archives[0].name.startswith(prefix):
        raise ValueError("Release asset does not match " + prefix)
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
