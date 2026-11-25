#!/usr/bin/env python3
"""Check built-in symbol CRCs against the matching factory module references."""
import argparse
from itertools import chain
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
    expected_groups = [reference['symbols'], *reference.get('module_imports', {}).values()]
    for name, expected in chain.from_iterable(group.items() for group in expected_groups):
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
    lines = ['Factory module ABI check', f'Model: {args.model}', f'Kernel: {args.kernel}']
    failures = []
    if not selected:
        lines.append('ERROR: no matching factory wireless ABI reference; refusing to package.')
        failures.append('no factory wireless ABI reference for requested model, OS and kernel')
    for reference in selected:
        lines.append('Factory system: ' + reference['system'])
        if reference.get('factory_wlan_imports') == 'unverified':
            lines.append('Experimental reference: stock cfg80211 exports and rfkill imports; '
                         'Qualcomm WLAN module imports are not independently audited')
        if 'factory_modules_audited' in reference:
            lines.append(f"Reference audited against {reference['factory_modules_audited']} original modules")
        try:
            errors = check(reference, args.symvers)
        except (OSError, ValueError) as error:
            errors = [str(error)]
        failures.extend(errors)
        if errors:
            lines.extend(errors)
            continue
        lines.append(f"PASS: {len(reference['symbols'])} built-in wireless symbol CRCs match stock cfg80211/rfkill reference")
        imports = reference.get('module_imports', {})
        if imports:
            count = sum(map(len, imports.values()))
            lines.append(f"PASS: {count} built-in symbol CRCs match factory imports from {', '.join(sorted(imports))}")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text('\n'.join(lines) + '\n')
    print('\n'.join(lines))
    if failures:
        parser.exit(1, 'Factory module ABI mismatch; refusing to package this kernel\n')


if __name__ == '__main__':
    main()
