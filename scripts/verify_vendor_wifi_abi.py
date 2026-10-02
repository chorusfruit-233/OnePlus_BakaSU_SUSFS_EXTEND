#!/usr/bin/env python3
"""Check built cfg80211 symbol CRCs against a matching factory WLAN module."""
import argparse
import json
from pathlib import Path
import re

REFERENCES = Path(__file__).resolve().parents[1] / 'profiles/vendor-wifi-abi'


def check(reference, symvers):
    actual = {}
    for line in symvers.read_text().splitlines():
        parts = line.split()
        if len(parts) >= 3:
            actual[parts[1]] = (int(parts[0], 16), parts[2])
    errors = []
    for name, expected in reference['symbols'].items():
        entry = actual.get(name)
        if entry is None:
            errors.append(f'{name}: missing from {symvers.name}')
        elif entry[1] != 'vmlinux':
            errors.append(f'{name}: not built-in ({entry[1]})')
        elif entry[0] != int(expected, 16):
            errors.append(f'{name}: built=0x{entry[0]:08x}, factory={expected}')
    return errors


def matches(reference, model, os_version, kernel):
    return (reference['model'] == model and reference['os_version'] == os_version
            and bool(re.search(r'(?:^|-)' + re.escape(reference['kernel']) + r'(?:$|-)', kernel)))


def selected_references(model, os_version, kernel):
    references = [json.loads(path.read_text()) for path in sorted(REFERENCES.glob('*.json'))]
    return [ref for ref in references if matches(ref, model, os_version, kernel)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', required=True)
    parser.add_argument('--os-version', required=True)
    parser.add_argument('--kernel', required=True)
    parser.add_argument('--symvers', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    selected = selected_references(args.model, args.os_version, args.kernel)
    lines = ['Factory WLAN module ABI check', f'Model: {args.model}', f'Kernel: {args.kernel}']
    failures = []
    if not selected:
        lines.append('No matching factory symbol reference; only wireless configuration guards verified separately.')
    for reference in selected:
        lines.append('Factory system: ' + reference['system'])
        try:
            errors = check(reference, args.symvers)
        except (OSError, ValueError) as error:
            errors = [str(error)]
        failures.extend(errors)
        lines.extend(errors or [f"PASS: {len(reference['symbols'])} built-in cfg80211 symbol CRCs match factory WLAN module"])
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text('\n'.join(lines) + '\n')
    print('\n'.join(lines))
    if failures:
        parser.exit(1, 'Factory WLAN ABI mismatch; refusing to package this kernel\n')


if __name__ == '__main__':
    main()
