#!/usr/bin/env python3
"""Validate the explicitly maintained OnePlus 13 OOS16 / COS17 targets."""
import argparse
import json
from pathlib import Path

COMMON = {
    "model": "OP13",
    "soc": "sun",
    "branch": "wild/sm8750",
    "manifest": "oneplus_13_w.xml",
    "android_version": "android15",
    "kernel_version": "6.6",
}
TARGETS = {
    "oos16": {**COMMON, "os_version": "OOS16"},
    "cos17": {**COMMON, "os_version": "COS17"},
}
# Backwards-compatible aliases for older tooling; the default remains OOS16.
TARGET = TARGETS["oos16"]
TARGET_CONFIG = "configs/oos16/OP13.json"
TARGET_MANIFEST = "manifests/oos16/oneplus_13_w.xml"


def config_path(target):
    return f"configs/{target}/OP13.json"


def manifest_path(target):
    return f"manifests/{target}/oneplus_13_w.xml"


def validate(config, target=None):
    if not isinstance(config, dict):
        raise ValueError("OP13 build configuration must be a JSON object")
    key = target or next((name for name, item in TARGETS.items()
                          if config.get("os_version") == item["os_version"]), None)
    if key not in TARGETS or any(config.get(name) != value
                                for name, value in TARGETS[key].items()):
        raise ValueError("Only OP13 OOS16 or COS17 on android15-6.6 is maintained")
    return config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=TARGETS, default="oos16")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        if args.config:
            config = json.loads(args.config.read_text())
            validate(config)
        else:
            config = validate(json.loads((args.root / config_path(args.target)).read_text()), args.target)
            if not (args.root / manifest_path(args.target)).is_file():
                raise ValueError("Missing maintained manifest: " + manifest_path(args.target))
            print(json.dumps([config]))
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    main()
