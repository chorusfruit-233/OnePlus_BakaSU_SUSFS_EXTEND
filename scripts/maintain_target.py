#!/usr/bin/env python3
"""Reapply the maintained build target after the legacy upstream sanitizer."""
import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from build_target import TARGET_CONFIG, TARGET_MANIFEST, TARGETS, validate
from build_target import config_path as target_config_path, manifest_path as target_manifest_path

UNAME = 'OP-BAKASU'
CONSTRAINTS = '''
Current maintained build requirements (supersede legacy target descriptions):
- Maintain only OnePlus 13 / android15-6.6, with stable OOS16 and experimental COS17 targets: configs/{oos16,cos17}/OP13.json and manifests/{oos16,cos17}/oneplus_13_w.xml.
- Keep OOS16 as the default; COS17 uses its own factory ABI reference and the existing 6.6.118 source baseline until official COS17 source is published.
- Keep uname OP-BAKASU and official Baka-SU/BakaSU integration; KernelSU remains an optional build choice.
- Preserve built-in USB WiFi drivers and firmware, vendor WiFi ABI checks, USB DWC3/OTG support, and USBWiFi artifact names.
- Preserve built-in Hybrid Mount VFS, its pinned source/checksum and verification; do not restore NoMount.
- Do not restore other devices, older OS targets, removed configurations or manifests.
'''


def target_files(root, target='oos16'):
    config_path = root / target_config_path(target)
    manifest_path = root / target_manifest_path(target)
    for path in (config_path, manifest_path):
        for parent in (path, *path.parents):
            if parent == root:
                break
            if parent.is_symlink():
                raise ValueError('Maintained target must not use symlinks: ' + str(path))
        if not path.is_file():
            raise ValueError('Missing maintained target: ' + str(path))
    config = validate(json.loads(config_path.read_text()), target)
    manifest = ET.parse(manifest_path).getroot()
    required = {'AnyKernel3', 'android_kernel_common_oneplus_sm8750',
                'android_kernel_modules_and_devicetree_oneplus_sm8750'}
    projects = {project.get('name') for project in manifest.findall('project')}
    if manifest.tag != 'manifest' or not required.issubset(projects):
        raise ValueError('Maintained manifest must contain the OnePlus 13 SM8750 sources and AnyKernel3')
    return config, config_path, manifest_path


def enforce(root, check=False):
    # Validate both targets before changing any file or deleting restored devices.
    targets = [target_files(root, target) for target in TARGETS]
    keep = {path for _, config_path, manifest_path in targets for path in (config_path, manifest_path)}
    extra = [path for directory in ('configs', 'manifests')
             for path in (root / directory).rglob('*')
             if (path.is_file() or path.is_symlink()) and path not in keep]
    if check:
        if any(config.get('uname') != UNAME for config, _, _ in targets):
            raise ValueError('Maintained target uname must be ' + UNAME)
        if extra:
            raise ValueError('Unmaintained targets remain: ' + ', '.join(str(p.relative_to(root)) for p in extra))
        return
    for config, config_path, _ in targets:
        if config.get('uname') != UNAME:
            config['uname'] = UNAME
            config_path.write_text(json.dumps(config, indent=2) + '\n')
    for path in extra:
        path.unlink()
    for directory in ('configs', 'manifests'):
        for path in sorted((root / directory).rglob('*'), key=lambda p: len(p.parts), reverse=True):
            if path.is_dir() and not path.is_symlink() and not any(path.iterdir()):
                path.rmdir()


def render_guidelines(text):
    # Adapt only the legacy instructions, never a user's request or comment text.
    text = text.replace('https://github.com/ReSukiSU/ReSukiSU', 'https://github.com/Baka-SU/BakaSU')
    text = text.replace('OP-RESUKISU', UNAME).replace('ReSukiSU', 'BakaSU')
    return text.rstrip() + '\n\n' + CONSTRAINTS.strip() + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--check', action='store_true', help='Validate without changing files')
    mode.add_argument('--guidelines', action='store_true', help='Print adapted legacy agent instructions')
    args = parser.parse_args()
    try:
        root = args.root.resolve()
        if args.guidelines:
            print(render_guidelines((root / '.github/opencode/guidelines.txt').read_text()), end='')
        else:
            enforce(root, check=args.check)
    except (OSError, ValueError, ET.ParseError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
