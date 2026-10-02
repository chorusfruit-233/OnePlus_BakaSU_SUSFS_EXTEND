#!/usr/bin/env python3
"""Validate the single maintained OnePlus 13 OOS16 build target."""
import argparse
import json
from pathlib import Path

TARGET_CONFIG = 'configs/oos16/OP13.json'
TARGET_MANIFEST = 'manifests/oos16/oneplus_13_w.xml'
TARGET = {
    'model': 'OP13',
    'soc': 'sun',
    'branch': 'wild/sm8750',
    'manifest': 'oneplus_13_w.xml',
    'os_version': 'OOS16',
    'android_version': 'android15',
    'kernel_version': '6.6',
}


def validate(config):
    if not isinstance(config, dict) or any(config.get(key) != value for key, value in TARGET.items()):
        raise ValueError('Only OP13 OOS16 / oneplus_13_w.xml / android15-6.6 is maintained')
    return config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        if args.config:
            validate(json.loads(args.config.read_text()))
        else:
            config = validate(json.loads((args.root / TARGET_CONFIG).read_text()))
            if not (args.root / TARGET_MANIFEST).is_file():
                raise ValueError('Missing maintained manifest: ' + TARGET_MANIFEST)
            print(json.dumps([config]))
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
