#!/usr/bin/env python3
"""Enable in-tree USB WiFi as built-ins, then audit Kconfig's resolved output.

Run apply after gki_defconfig, run the kernel's olddefconfig with its normal
build environment, then run verify before compiling Image. No ABI files or
precompiled modules from the former LKM project are used.
"""
import argparse
import json
import os
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
DECLARATION = re.compile(r'^\s*(?:menuconfig|config)\s+(\w+)\s*$', re.M)
SETTING = re.compile(r'^(CONFIG_\w+)=.*$|^# (CONFIG_\w+) is not set$')


def declared_symbols(source):
    symbols = set()
    for directory, dirs, files in os.walk(source):
        dirs[:] = [name for name in dirs if name not in
                   ('.git', 'out', 'tools', 'Documentation', '.cache')]
        for name in files:
            if name == 'Kconfig' or name.startswith('Kconfig.'):
                symbols.update(DECLARATION.findall(
                    (Path(directory) / name).read_text(errors='replace')))
    return symbols


def plan(source, profile):
    declared = declared_symbols(source)
    missing = set(profile['required']) - declared
    if missing:
        raise ValueError('kernel lacks required USB WiFi symbols: ' + ', '.join(sorted(missing)))
    drivers = sorted(set(profile['drivers']) & declared)
    if not drivers:
        raise ValueError('no supported USB WiFi drivers found in this kernel tree')
    helpers = set(profile['helpers'])
    # Do not enable an otherwise unused family core on older kernel trees.
    for helper, prefix in (('RTL_CARDS', 'RTL8192CU'), ('RT2X00', 'RT'),
                           ('ATH6KL', 'ATH6KL_'), ('P54_COMMON', 'P54_'),
                           ('RTW88', 'RTW88_'), ('RTW89', 'RTW89_')):
        members = [name for name in drivers if name.startswith(prefix)]
        if helper == 'RT2X00':
            members = [name for name in members if name in ('RT2500USB', 'RT73USB', 'RT2800USB')]
        if not members:
            helpers.discard(helper)
    requested = sorted((set(profile['required']) | helpers | set(drivers)) & declared)
    absent = sorted(set(profile['drivers']) - declared)
    return requested, drivers, absent


def apply(config, requested):
    wanted = {'CONFIG_' + symbol for symbol in requested}
    retained = []
    for line in config.read_text().splitlines():
        match = SETTING.fullmatch(line)
        if not match or (match[1] or match[2]) not in wanted:
            retained.append(line)
    config.write_text('\n'.join(retained + [name + '=y' for name in sorted(wanted)]) + '\n')


def verify(config, requested, drivers, absent, report):
    values = {}
    for line in config.read_text().splitlines():
        if line.startswith('CONFIG_') and '=' in line:
            name, value = line.split('=', 1)
            values[name.removeprefix('CONFIG_')] = value
    # Reject silently dropped drivers, modular dependencies and unmet menus.
    # Declared symbols are not proof that olddefconfig enabled them.
    blocked = {name: values.get(name, 'n') for name in requested
               if values.get(name) != 'y'}
    lines = ['USB WiFi built-in configuration (after olddefconfig)', '',
             *[f'CONFIG_{name}={values.get(name, "n")}' for name in requested], '',
             'Drivers absent from this source tree (not backported):',
             *absent, '']
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text('\n'.join(lines))
    if blocked:
        detail = ', '.join(f'CONFIG_{name}={value}' for name, value in blocked.items())
        raise ValueError('olddefconfig did not retain required built-ins: ' + detail)
    print(f'USB WiFi: verified {len(drivers)} built-in drivers; report: {report}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('apply', 'verify'))
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--profile', type=Path, default=ROOT / 'profiles/usb-wifi.json')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    try:
        profile = json.loads(args.profile.read_text())
        requested, drivers, absent = plan(args.source, profile)
        if args.mode == 'apply':
            apply(args.config, requested)
            print('USB WiFi: requesting built-ins: ' + ', '.join(drivers))
            print('USB WiFi: absent in source, skipped: ' + ', '.join(absent))
        else:
            if args.report is None:
                parser.error('--report is required for verify')
            verify(args.config, requested, drivers, absent, args.report)
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f'USB WiFi configuration error: {error}\n')


if __name__ == '__main__':
    main()
