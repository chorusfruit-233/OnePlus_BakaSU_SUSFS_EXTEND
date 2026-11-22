#!/usr/bin/env python3
"""Generate or validate the OnePlus 13 ColorOS 17 build matrix."""
import argparse
import json
from pathlib import Path

TARGET = {
    "model": "OP13",
    "soc": "sun",
    "branch": "wild/sm8750",
    "manifest": "oneplus_13_w.xml",
    "android_version": "android15",
    "kernel_version": "6.6",
    "os_version": "COS17",
}
TARGET_CONFIG = "configs/cos17/OP13.json"
TARGET_MANIFEST = "manifests/cos17/oneplus_13_w.xml"


def validate(config):
    if not isinstance(config, dict):
        raise ValueError("OP13 build configuration must be a JSON object")
    if any(config.get(key) != value for key, value in TARGET.items()):
        raise ValueError("Only OP13 COS17 on android15-6.6 is maintained")
    return config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--target", choices=["cos17"])
    selection.add_argument("--all", action="store_true", help="Emit the single maintained target")
    selection.add_argument("--config", type=Path)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        config = validate(json.loads((args.config or args.root / TARGET_CONFIG).read_text()))
        if not args.config:
            if not (args.root / TARGET_MANIFEST).is_file():
                raise ValueError("Missing maintained manifest: " + TARGET_MANIFEST)
            print(json.dumps([config]))
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    main()
