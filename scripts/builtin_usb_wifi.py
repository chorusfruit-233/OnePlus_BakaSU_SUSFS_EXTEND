#!/usr/bin/env python3
"""Resolve each kernel's USB WLAN drivers and embed their available firmware.

apply -> kernel olddefconfig -> firmware -> kernel olddefconfig -> verify
The C Kconfig output remains authoritative; firmware is staged only for actual
built-ins. Absent or incompatible candidates are reported independently.
"""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess

import kconfiglib as kc
import usb_wifi_firmware as fw
import verify_vendor_wifi_abi as vendor_abi

ROOT = Path(__file__).resolve().parents[1]
SETTING = re.compile(r'^(CONFIG_\w+)=.*$|^# (CONFIG_\w+) is not set$')
# Architecture/compiler capabilities and unrelated buses are never enabled just
# to pass a WLAN dependency. Already enabled dependencies can be promoted m->y.
IMMUTABLE = {'COMPILE_TEST', 'EXPERT', 'BROKEN', 'PCI', 'MMC', 'ACPI', 'X86',
             'X86_32', 'X86_64', 'ARM', 'ARM64', '64BIT', 'OF', 'UML', 'SMP',
             'MODULES', 'CPU_BIG_ENDIAN', 'CPU_LITTLE_ENDIAN'}
DEPENDENCY_PATHS = ('drivers/net/wireless/', 'drivers/staging/rtl',
                    'drivers/staging/vt', 'drivers/staging/wlan',
                    'net/wireless/', 'net/mac80211/', 'crypto/')


class LinuxKconfig(kc.Kconfig):
    """Match native Linux syntax that Kconfiglib 14.1 does not accept.

    Kconfiglib 14.1 predates Linux's removal of the 'option' prefix. Both
    spellings have identical semantics; kernel source files stay untouched.
    Linux also terminates an unclosed quoted source path at newline with a
    warning. Some MediaTek camera Kconfigs rely on this behavior.
    """
    def __init__(self, *args, **kwargs):
        self.compatibility_notes = []
        super().__init__(*args, **kwargs)

    def _tokenize(self, line):
        if re.fullmatch(r'\s*modules\s*(?:#[^\n]*)?\s*', line):
            line = re.sub(r'\bmodules\b', 'option modules', line, count=1)
        match = re.fullmatch(r'''(\s*(?:source|rsource|osource|orsource)\s+)(["'])([^"'\\\r\n]+)(\r?\n)?''', line)
        if match:
            self.compatibility_notes.append(
                f'{self.filename}:{self.linenr}: unclosed source quote terminated at end of line (native Linux semantics)')
            line = ''.join(match.group(index) for index in (1, 2, 3, 2)) + (match[4] or '')
        return super()._tokenize(line)


def read_config(config):
    values = {}
    for line in Path(config).read_text().splitlines():
        match = SETTING.fullmatch(line)
        if not match:
            continue
        key = (match[1] or match[2]).removeprefix('CONFIG_')
        values[key] = line.split('=', 1)[1] if match[1] else 'n'
    return values


def update_config(config, values):
    """Change only planned assignments; retain vendor-specific config lines."""
    retained, seen = [], set()
    def assignment(name):
        return f'CONFIG_{name}={values[name]}' if values[name] != 'n' else f'# CONFIG_{name} is not set'
    for line in Path(config).read_text().splitlines():
        match = SETTING.fullmatch(line)
        name = (match[1] or match[2]).removeprefix('CONFIG_') if match else None
        if name not in values:
            retained.append(line)
        elif name not in seen:
            retained.append(assignment(name))
            seen.add(name)
    retained.extend(assignment(name) for name in sorted(values.keys() - seen))
    Path(config).write_text('\n'.join(retained) + '\n')


def kernel_version(source):
    makefile = Path(source) / 'Makefile'
    if not makefile.is_file():
        return 'unknown'
    fields = dict(re.findall(r'^(VERSION|PATCHLEVEL|SUBLEVEL|EXTRAVERSION)\s*=\s*(.*?)\s*$',
                             makefile.read_text(), re.M))
    return '.'.join(fields.get(name, '0') for name in ('VERSION', 'PATCHLEVEL', 'SUBLEVEL')) + fields.get('EXTRAVERSION', '')


@contextmanager
def kernel_environment(source):
    """Supply the environment normally exported by the kernel Makefile."""
    original = dict(os.environ)
    previous_directory = Path.cwd()
    source = Path(source).resolve()
    architecture = os.environ.get('ARCH', 'arm64')
    defaults = {'srctree': str(source), 'ARCH': architecture,
                'SRCARCH': os.environ.get('SRCARCH', architecture),
                'CC': os.environ.get('CC', 'clang'), 'LD': os.environ.get('LD', 'ld.lld'),
                'RUSTC': os.environ.get('RUSTC', 'rustc'),
                'HOSTCC': os.environ.get('HOSTCC', 'gcc'),
                'KERNELVERSION': kernel_version(source)}
    try:
        os.environ.update(defaults)
        os.chdir(source)
        if 'CC_VERSION_TEXT' not in os.environ:
            output = subprocess.check_output(shlex.split(defaults['CC']) + ['--version'],
                                             stderr=subprocess.STDOUT, text=True)
            os.environ['CC_VERSION_TEXT'] = output.splitlines()[0]
        if 'CLANG_FLAGS' not in os.environ and 'clang' in os.environ['CC_VERSION_TEXT'].lower():
            target = os.environ.get('CROSS_COMPILE', 'aarch64-linux-gnu-').rstrip('-')
            if architecture == 'arm64':
                assembler = '-fno-integrated-as' if os.environ.get('LLVM_IAS') == '0' else '-fintegrated-as'
                os.environ['CLANG_FLAGS'] = '--target=' + target + ' ' + assembler
        yield
    finally:
        os.chdir(previous_directory)
        os.environ.clear()
        os.environ.update(original)


def load_kconfig(source, config):
    config = Path(config).resolve()
    with kernel_environment(source):
        kconf = LinuxKconfig(os.environ.get('KBUILD_KCONFIG', 'Kconfig'), warn=False,
                          suppress_traceback=True)
        kconf.load_config(str(config))
    return kconf


class DriverPlanner:
    """Promote scoped, positive dependencies; roll back failed candidates."""
    def __init__(self, kconf, profile, abi_config=None):
        self.kconf = kconf
        self.profile = profile
        self.entries = [dict(driver) if isinstance(driver, dict) else {'symbol': driver}
                        for driver in profile['drivers']]
        self.allowed = set(profile['required']) | set(profile.get('helpers', []))
        self.allowed.update(driver['symbol'] for driver in self.entries)
        for driver in self.entries:
            self.allowed.update(driver.get('helpers', []))
        self.baseline = {sym.name: sym.str_value for sym in kconf.unique_defined_syms}
        self.abi_preserved = {name: self.baseline[name] for name in profile.get('preserve_abi', [])
                              if name in self.baseline}
        for name, value in (abi_config or {}).items():
            if name not in self.abi_preserved or value not in ('n', 'y'):
                raise ValueError(f'unsupported factory wireless ABI option CONFIG_{name}={value}')
            self.abi_preserved[name] = value
        self.preserved = {name for driver in self.entries for name in driver.get('preserve_disabled', [])
                          if self.baseline.get(name) == 'n'}
        self.selected = []

    def _snapshot(self):
        return ([(sym, sym.user_value) for sym in self.kconf.unique_defined_syms],
                [(choice, choice.user_value, choice.user_selection) for choice in self.kconf.unique_choices])

    @staticmethod
    def _restore(snapshot):
        symbols, choices = snapshot
        for symbol, value in symbols:
            if symbol.user_value != value:
                symbol.unset_value() if value is None else symbol.set_value(value)
        for choice, value, selection in choices:
            choice.unset_value() if value is None else choice.set_value(value)
            if selection is not None:
                selection.set_value(2)

    def _can_change(self, symbol):
        if (symbol.name in IMMUTABLE or symbol.name in self.preserved or symbol.name in self.abi_preserved
                or symbol.is_constant or not symbol.nodes):
            return False
        return (symbol.name in self.allowed or self.baseline.get(symbol.name) in ('m', 'y')
                or any(node.filename.startswith(DEPENDENCY_PATHS) for node in symbol.nodes))

    def _preserved_ok(self):
        return (all(self.kconf.syms[name].tri_value == 0 for name in self.preserved)
                and not self._abi_changes())

    def _abi_changes(self):
        return [f'CONFIG_{name}={value}->{self.kconf.syms[name].str_value}'
                for name, value in self.abi_preserved.items() if self.kconf.syms[name].str_value != value]

    def _satisfy(self, expression, stack):
        if kc.expr_value(expression) == 2:
            return True
        if isinstance(expression, kc.Symbol):
            return self._enable(expression, stack)
        if isinstance(expression, kc.Choice):
            return False
        operation = expression[0]
        if operation == kc.AND:
            return self._satisfy(expression[1], stack) and self._satisfy(expression[2], stack)
        if operation == kc.OR:
            branches = sorted(expression[1:], key=kc.expr_value, reverse=True)
            for branch in branches:
                snapshot = self._snapshot()
                if self._satisfy(branch, stack):
                    return True
                self._restore(snapshot)
            return False
        # A negated dependency is not permission to disable platform options.
        # Driver-specific, documented conflicts are handled before resolution.
        if operation == kc.EQUAL:
            left, right = expression[1:]
            if isinstance(right, kc.Symbol) and right is self.kconf.y:
                return self._satisfy(left, stack)
            if isinstance(left, kc.Symbol) and left is self.kconf.y:
                return self._satisfy(right, stack)
        return False

    def _enable(self, symbol, stack=()):
        if symbol.tri_value == 2:
            return True
        if symbol in stack or symbol.type not in (kc.BOOL, kc.TRISTATE) or not self._can_change(symbol):
            return False
        nested = stack + (symbol,)
        if not self._satisfy(symbol.direct_dep, nested):
            return False
        # Hidden symbols take values from select/default, never from user writes.
        if not any(node.prompt for node in symbol.nodes):
            for value, condition in symbol.defaults:
                snapshot = self._snapshot()
                if self._satisfy(condition, nested) and self._satisfy(value, nested) and symbol.tri_value == 2:
                    return True
                self._restore(snapshot)
            return symbol.tri_value == 2
        for node in symbol.nodes:
            if node.prompt and self._satisfy(node.prompt[1], nested) and 2 in symbol.assignable:
                symbol.set_value(2)
                return symbol.tri_value == 2
        return False

    def _selected_dependencies(self):
        """select bypasses dependencies in Kconfig; make those dependencies valid."""
        for _ in range(32):
            pending = []
            for symbol in self.kconf.unique_defined_syms:
                if symbol.tri_value != 2 or (self.baseline.get(symbol.name) == 'y' and symbol.name not in self.allowed):
                    continue
                for target, condition in symbol.selects:
                    if kc.expr_value(condition) == 2 and kc.expr_value(target.direct_dep) != 2:
                        pending.append(target)
            if not pending:
                return True
            before = [(sym.name, sym.str_value) for sym in pending]
            for target in pending:
                if not self._satisfy(target.direct_dep, (target,)):
                    return False
            if before == [(sym.name, sym.str_value) for sym in pending] and any(kc.expr_value(sym.direct_dep) != 2 for sym in pending):
                return False
        return False

    def resolve(self, model='', version=''):
        for name in self.preserved:
            self.kconf.syms[name].set_value(0)
        missing = [name for name in self.profile['required']
                   if name not in self.kconf.syms or not self.kconf.syms[name].nodes]
        if missing:
            raise ValueError('kernel lacks required USB WiFi symbols: ' + ', '.join(missing))
        for name in self.profile['required']:
            if not self._enable(self.kconf.syms[name]):
                raise ValueError(f'cannot build required USB WiFi core CONFIG_{name}=y')
        # Vendor modules can enable ABI options hidden by a disabled GKI core.
        # Apply the measured factory values only after enabling that core.
        for name, value in self.abi_preserved.items():
            symbol = self.kconf.syms[name]
            if symbol.str_value != value:
                symbol.set_value(value)
            if symbol.str_value != value:
                raise ValueError(f'cannot preserve wireless ABI CONFIG_{name}={value}')
        results = []
        for driver in self.entries:
            name = driver['symbol']
            symbol = self.kconf.syms.get(name)
            if symbol is None or not symbol.nodes:
                results.append({'symbol': name, 'status': 'absent', 'reason': 'not in this kernel Kconfig'})
                continue
            snapshot = self._snapshot()
            for conflict in driver.get('conflicts', []):
                item = self.kconf.syms.get(conflict)
                if item and item.name not in IMMUTABLE and self._can_change(item):
                    item.set_value(0)
            successful = self._enable(symbol)
            helper_results = []
            if successful:
                successful = self._selected_dependencies() and symbol.tri_value == 2 and self._preserved_ok()
            if successful:
                for helper in driver.get('helpers', []):
                    item = self.kconf.syms.get(helper)
                    if item is None or not item.nodes:
                        helper_results.append({'symbol': helper, 'status': 'absent'})
                        continue
                    helper_snapshot = self._snapshot()
                    if (self._enable(item) and self._selected_dependencies() and symbol.tri_value == 2
                            and self._preserved_ok()
                            and all(self.kconf.syms[entry['symbol']].tri_value == 2 for entry in self.selected)):
                        helper_results.append({'symbol': helper, 'status': 'builtin'})
                    else:
                        abi_changes = self._abi_changes()
                        self._restore(helper_snapshot)
                        helper_results.append({'symbol': helper, 'status': 'blocked',
                                               'reason': ('would change stock wireless ABI: ' + ', '.join(abi_changes))
                                                         if abi_changes else kc.expr_str(item.direct_dep)})
            if successful and self._preserved_ok() and all(self.kconf.syms[entry['symbol']].tri_value == 2 for entry in self.selected):
                self.selected.append(driver)
                results.append({'symbol': name, 'status': 'builtin', 'reason': '', 'helpers': helper_results})
            else:
                abi_changes = self._abi_changes()
                self._restore(snapshot)
                results.append({'symbol': name, 'status': 'blocked',
                                'reason': ('would change stock wireless ABI: ' + ', '.join(abi_changes)) if abi_changes else
                                          'cannot satisfy built-in dependencies: ' + kc.expr_str(symbol.direct_dep),
                                'value': symbol.str_value})
        for record, driver in zip(results, self.entries):
            if driver.get('notes'):
                record['notes'] = driver['notes']
        if not self.selected:
            raise ValueError('no USB WiFi driver can be built into this kernel')
        values = {}
        for symbol in self.kconf.unique_defined_syms:
            if symbol.str_value != self.baseline.get(symbol.name):
                values[symbol.name] = json.dumps(symbol.str_value, ensure_ascii=False) if symbol.type == kc.STRING else symbol.str_value
        # Request the core and chosen leaf symbols explicitly, even if a default
        # already enabled them in Kconfiglib's view of the source configuration.
        for name in self.profile['required'] + [entry['symbol'] for entry in self.selected]:
            values[name] = 'y'
        for name in self.preserved:
            values[name] = 'n'
        values.update(self.abi_preserved)
        return {'schema': 2, 'model': model, 'kernel': version,
                'required': self.profile['required'], 'drivers': results,
                'selected': self.selected, 'assignments': values,
                'kconfig_compatibility': self.kconf.compatibility_notes,
                'abi_preserved': self.abi_preserved,
                'preserved_disabled': sorted(self.preserved)}


def apply_plan(source, config, profile, plan_path, model='', version='', os_version=''):
    version = version or kernel_version(source)
    references = vendor_abi.selected_references(model, os_version, version)
    abi_config = {}
    for reference in references:
        for name, value in reference.get('config', {}).items():
            if name in abi_config and abi_config[name] != value:
                raise ValueError(f'conflicting factory wireless ABI references for CONFIG_{name}')
            abi_config[name] = value
    plan = DriverPlanner(load_kconfig(source, config), profile, abi_config).resolve(model, version)
    plan['abi_reference'] = [reference['system'] for reference in references]
    update_config(config, plan['assignments'])
    write_json(plan_path, plan)
    for note in plan['kconfig_compatibility']:
        print('USB WiFi Kconfig compatibility: ' + note)
    print(f'USB WiFi: {len(plan["selected"])} driver candidates configured as built-ins for {plan["model"] or "this kernel"}')
    return plan


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def _config_string(value):
    return json.loads(value) if value and value.startswith('"') else (value or '')


def reconcile_helpers(plan, values):
    for driver in plan['drivers']:
        for helper in driver.get('helpers', []):
            actual = values.get(helper['symbol'], 'n')
            if helper['status'] == 'builtin' and actual != 'y':
                helper.update(status='blocked', reason='kernel resolved CONFIG_' + helper['symbol'] + '=' + actual)
            elif helper['status'] == 'blocked' and actual == 'y':
                helper.update(status='builtin')
                helper.pop('reason', None)


def abi_config_failures(plan, values):
    return [f'CONFIG_{name} changed stock wireless ABI ({expected}->{values.get(name, "n")})'
            for name, expected in plan.get('abi_preserved', {}).items()
            if values.get(name, 'n') != expected]


def prepare_firmware(source, config, plan_path, staging, metadata_dir, lock=None, cache_dir=None):
    plan = json.loads(Path(plan_path).read_text())
    values = read_config(config)
    abi_failures = abi_config_failures(plan, values)
    if abi_failures:
        raise ValueError('; '.join(abi_failures))
    for name in plan['required']:
        if values.get(name) != 'y':
            raise ValueError(f'olddefconfig dropped required core CONFIG_{name}=y')
    for name in plan.get('preserved_disabled', []):
        if values.get(name, 'n') != 'n':
            raise ValueError(f'olddefconfig enabled previously disabled non-USB transport CONFIG_{name}')
    selected = [entry for entry in plan['selected'] if values.get(entry['symbol']) == 'y']
    for record in plan['drivers']:
        if record['status'] == 'builtin' and values.get(record['symbol']) != 'y':
            record.update(status='blocked', reason='kernel olddefconfig resolved CONFIG_' + record['symbol'] + '=' + values.get(record['symbol'], 'n'))
    reconcile_helpers(plan, values)
    plan['selected'] = selected
    write_json(plan_path, plan)
    if not selected:
        raise ValueError('olddefconfig retained no built-in USB WiFi drivers')
    staging = Path(staging).resolve()
    metadata_dir = Path(metadata_dir).resolve()
    if any(character.isspace() for character in str(staging)):
        raise ValueError('EXTRA_FIRMWARE_DIR must not contain whitespace (kernel build limitation)')
    # Existing EXTRA_FIRMWARE must survive when replacing its root directory.
    old_names = _config_string(values.get('EXTRA_FIRMWARE', '""')).split()
    old_root = Path(_config_string(values.get('EXTRA_FIRMWARE_DIR', '"/lib/firmware"')))
    if not old_root.is_absolute():
        old_root = Path(source).resolve() / old_root
    existing = {}
    for name in old_names:
        fw.safe_name(name)
        original = old_root / name
        if not original.resolve().is_relative_to(old_root.resolve()):
            raise ValueError(f'existing EXTRA_FIRMWARE escapes its root: {name}')
        if not original.is_file():
            raise ValueError(f'existing EXTRA_FIRMWARE blob missing: {original}')
        existing[name] = original.read_bytes()
    firmware_drivers = list(selected)
    regulatory_source = Path(source) / 'net/wireless/reg.c'
    if values.get('CFG80211') == 'y' and regulatory_source.is_file() and 'regulatory.db' in regulatory_source.read_text(errors='replace'):
        database = ['regulatory.db']
        if values.get('CFG80211_REQUIRE_SIGNED_REGDB') == 'y':
            database.append('regulatory.db.p7s')
        firmware_drivers.append({'symbol': 'CFG80211', 'sources': ['net/wireless/reg.c'],
                                 'firmware': database, 'firmware_only': True,
                                 'regdb_use_kernel_keys': values.get('CFG80211_USE_KERNEL_REGDB_KEYS') == 'y',
                                 'regdb_extra_keydir': _config_string(values.get('CFG80211_EXTRA_REGDB_KEYDIR', '""'))})
    manifest = fw.stage_firmware(source, firmware_drivers, staging, metadata_dir,
                                 firmware_lock=lock, cache_dir=cache_dir, strict=False)
    for name, data in existing.items():
        target = fw.destination(staging, name)
        if target.exists() and target.read_bytes() != data:
            raise ValueError(f'USB firmware conflicts with existing EXTRA_FIRMWARE: {name}')
        if name not in manifest['names']:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            manifest['files'].append({'name': name, 'drivers': [], 'source_path': str(old_root / name),
                                      'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data),
                                      'origin': 'existing EXTRA_FIRMWARE', 'licenses': []})
            manifest['names'].append(name)
    manifest['names'] = sorted(set(manifest['names']))
    manifest['staging'] = str(staging)
    manifest['model'] = plan.get('model', '')
    manifest['kernel'] = plan.get('kernel', '')
    write_json(metadata_dir / 'manifest.json', manifest)
    kconf = load_kconfig(source, config)
    for symbol in ('EXTRA_FIRMWARE', 'EXTRA_FIRMWARE_DIR'):
        if symbol not in kconf.syms or not kconf.syms[symbol].nodes:
            raise ValueError(f'kernel has no CONFIG_{symbol} support')
    update_config(config, {'EXTRA_FIRMWARE': json.dumps(' '.join(manifest['names'])),
                           'EXTRA_FIRMWARE_DIR': json.dumps(str(staging), ensure_ascii=False)})
    print(f'USB WiFi: embedding {len(manifest["names"])} firmware blobs; coverage {manifest["status"]}')
    return manifest


def verify(source, config, plan_path, metadata_dir, report, image=None):
    plan = json.loads(Path(plan_path).read_text())
    manifest = json.loads((Path(metadata_dir) / 'manifest.json').read_text())
    values = read_config(config)
    reconcile_helpers(plan, values)
    write_json(plan_path, plan)
    failures = abi_config_failures(plan, values)
    for name in plan['required'] + [entry['symbol'] for entry in plan['selected']]:
        if values.get(name) != 'y':
            failures.append(f'CONFIG_{name}={values.get(name, "n")} (expected y)')
    for name in plan.get('preserved_disabled', []):
        if values.get(name, 'n') != 'n':
            failures.append(f'CONFIG_{name} was unexpectedly enabled (expected n)')
    names = _config_string(values.get('EXTRA_FIRMWARE', '""')).split()
    if sorted(names) != sorted(manifest['names']):
        failures.append('CONFIG_EXTRA_FIRMWARE differs from staged firmware manifest')
    if names and _config_string(values.get('EXTRA_FIRMWARE_DIR', '""')) != manifest['staging']:
        failures.append('CONFIG_EXTRA_FIRMWARE_DIR differs from staging root')
    for item in manifest['files']:
        blob = fw.destination(manifest['staging'], item['name'])
        if not blob.is_file() or hashlib.sha256(blob.read_bytes()).hexdigest() != item['sha256']:
            failures.append('firmware missing or checksum changed: ' + item['name'])
    for item in manifest.get('licenses', []):
        license_file = fw.destination(metadata_dir, 'licenses/' + item['name'])
        if not license_file.is_file() or hashlib.sha256(license_file.read_bytes()).hexdigest() != item['sha256']:
            failures.append('license text missing or checksum changed: ' + item['name'])
    if image is not None:
        image_bytes = Path(image).read_bytes()
        if not image_bytes:
            failures.append('compiled kernel Image is empty')
        for item in manifest['files']:
            blob = fw.destination(manifest['staging'], item['name'])
            if blob.is_file() and (blob.read_bytes() not in image_bytes or
                                   item['name'].encode() + b'\0' not in image_bytes):
                failures.append('firmware content or request name absent from Image: ' + item['name'])
    lines = ['USB WiFi built-in drivers and firmware',
             f'Model: {plan.get("model", "") or "unspecified"}',
             f'Kernel: {plan.get("kernel", "") or kernel_version(source)}',
             f'Built-in drivers: {len(plan["selected"])} / {len(plan["drivers"])} catalog candidates',
             f'Embedded firmware: {len(manifest["names"])} files, {sum(item["size"] for item in manifest["files"])} bytes',
             f'Firmware coverage: {manifest["status"]}',
             'Firmware source: ' + manifest['source']['repository'],
             'Firmware revision: ' + manifest['source']['revision'], '', 'Drivers:']
    if plan.get('kconfig_compatibility'):
        lines[-1:-1] = ['Kconfig compatibility:'] + plan['kconfig_compatibility'] + ['']
    if plan.get('abi_preserved'):
        lines[-1:-1] = ['Stock wireless ABI options preserved:'] + [
            f'CONFIG_{name}={value}' for name, value in plan['abi_preserved'].items()] + ['']
    if plan.get('abi_reference'):
        lines[-1:-1] = ['Factory wireless ABI reference: ' + ', '.join(plan['abi_reference']), '']
    for item in plan['drivers']:
        lines.append(f'CONFIG_{item["symbol"]}: {item["status"]}' + (f' — {item["reason"]}' if item['reason'] else ''))
        if item.get('notes'):
            lines.append('  Note: ' + item['notes'])
        for helper in item.get('helpers', []):
            lines.append(f'  CONFIG_{helper["symbol"]}: {helper["status"]}' + (f' — {helper["reason"]}' if helper.get('reason') else ''))
    lines += ['', 'Embedded firmware (SHA256):']
    lines.extend(f'{item["name"]} {item["sha256"]} ({item["size"]} bytes)' for item in manifest['files'])
    lines += ['', 'Drivers requiring no external firmware: ' + ', '.join(manifest['no_firmware_drivers']), '',
              'Missing firmware:']
    lines.extend(f'{item["name"]}: {item["reason"]} ({", ".join(item["drivers"])})' for item in manifest['missing'])
    lines += ['', 'Unresolved firmware references:']
    lines.extend(f'{item["driver"]}: {item["reference"]}' for item in manifest['unresolved'])
    lines += ['', 'Validation: ' + ('FAILED' if failures else 'passed')]
    if image is not None:
        lines.append('Compiled Image firmware contents: ' + ('FAILED' if failures else 'verified'))
    lines.extend(failures)
    report = Path(report)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text('\n'.join(lines) + '\n')
    if failures:
        raise ValueError('; '.join(failures))
    print(f'USB WiFi: verified {len(plan["selected"])} built-in drivers and {len(names)} firmware blobs')
    return plan, manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('apply', 'firmware', 'verify'))
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--profile', type=Path, default=ROOT / 'profiles/usb-wifi.json')
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--model', default='')
    parser.add_argument('--kernel', default='')
    parser.add_argument('--os-version', default='')
    parser.add_argument('--firmware-dir', type=Path)
    parser.add_argument('--metadata-dir', type=Path)
    parser.add_argument('--firmware-lock', type=Path)
    parser.add_argument('--cache-dir', type=Path)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--image', type=Path)
    args = parser.parse_args()
    try:
        if args.mode == 'apply':
            apply_plan(args.source, args.config, json.loads(args.profile.read_text()), args.plan,
                       args.model, args.kernel, args.os_version)
        elif args.mode == 'firmware':
            if args.firmware_dir is None or args.metadata_dir is None:
                parser.error('firmware requires --firmware-dir and --metadata-dir')
            prepare_firmware(args.source, args.config, args.plan, args.firmware_dir, args.metadata_dir,
                             args.firmware_lock, args.cache_dir)
        else:
            if args.metadata_dir is None or args.report is None:
                parser.error('verify requires --metadata-dir and --report')
            verify(args.source, args.config, args.plan, args.metadata_dir, args.report, args.image)
    except (OSError, ValueError, KeyError, kc.KconfigError, subprocess.SubprocessError) as error:
        parser.exit(1, f'USB WiFi configuration error: {error}\n')


if __name__ == '__main__':
    main()
