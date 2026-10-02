import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import builtin_usb_wifi as wifi


class BuiltinWifiTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.config = self.root / '.config'
        self.plan_path = self.root / 'usb-wifi/plan.json'
        self.report = self.root / 'report.txt'
        self.metadata = self.plan_path.parent
        self.staging = self.root / 'firmware'
        self.profile = {'required': ['NET', 'USB', 'CFG80211', 'MAC80211', 'FW_LOADER'],
                        'helpers': ['WIRELESS', 'CRYPTO', 'RFKILL'],
                        'drivers': [{'symbol': 'GOOD_USB', 'sources': ['drivers/net/wireless/good.c'], 'firmware': ['good.bin']},
                                    {'symbol': 'MODULE_ONLY_USB', 'sources': []},
                                    {'symbol': 'MISSING_USB', 'sources': []}]}
        self.kconfig = self.root / 'Kconfig'
        self.kconfig.write_text('''
config MODULES
    bool "modules"
    default y
    option modules
config NET
    bool "network"
config USB
    tristate "usb"
config WIRELESS
    bool "wireless"
    depends on NET
config CRYPTO
    tristate "crypto"
config CFG80211
    tristate "cfg80211"
    depends on WIRELESS
    select CRYPTO
config MAC80211
    tristate "mac80211"
    depends on CFG80211
config RFKILL
    tristate "rfkill"
config FW_LOADER
    tristate "firmware"
config GOOD_USB
    tristate "USB WLAN"
    depends on USB && MAC80211 && (RFKILL || !RFKILL)
config MODULE_ONLY_USB
    tristate "only modules"
    depends on USB && m
config EXTRA_FIRMWARE
    string "firmware files"
    depends on FW_LOADER
config EXTRA_FIRMWARE_DIR
    string "firmware dir"
    depends on EXTRA_FIRMWARE != ""
config KSU
    bool "KSU"
config VENDOR_WLAN
    tristate "vendor WLAN"
config LOCALVERSION
    string "version"
''')
        self.config.write_text('CONFIG_MODULES=y\nCONFIG_USB=m\nCONFIG_RFKILL=m\n' +
                               'CONFIG_KSU=y\nCONFIG_VENDOR_WLAN=m\nCONFIG_LOCALVERSION="-custom"\n'
                               'CONFIG_UNKNOWN_VENDOR_FEATURE=y\n')

    def apply(self):
        return wifi.apply_plan(self.root, self.config, self.profile, self.plan_path, 'test-device', '6.6-test')

    def test_resolves_nested_menu_dependencies_and_keeps_vendor_settings(self):
        plan = self.apply()
        values = wifi.read_config(self.config)
        for symbol in self.profile['required'] + ['GOOD_USB', 'WIRELESS', 'CRYPTO', 'RFKILL']:
            self.assertEqual(values[symbol], 'y', symbol)
        self.assertEqual(values['KSU'], 'y')
        self.assertEqual(values['VENDOR_WLAN'], 'm')
        self.assertEqual(values['LOCALVERSION'], '"-custom"')
        self.assertEqual(values['UNKNOWN_VENDOR_FEATURE'], 'y')
        self.assertEqual([item['symbol'] for item in plan['selected']], ['GOOD_USB'])
        statuses = {entry['symbol']: entry['status'] for entry in plan['drivers']}
        self.assertEqual(statuses['MODULE_ONLY_USB'], 'blocked')
        self.assertEqual(statuses['MISSING_USB'], 'absent')
        result = self.config.read_text()
        self.apply()
        self.assertEqual(self.config.read_text(), result)

    def test_does_not_enable_other_architectures_or_compile_test(self):
        with self.kconfig.open('a') as handle:
            handle.write('''
config X86
    bool "x86"
config COMPILE_TEST
    bool "compile testing"
config WRONG_ARCH_USB
    tristate "wrong architecture"
    depends on X86 || COMPILE_TEST
''')
        self.profile['drivers'].insert(0, {'symbol': 'WRONG_ARCH_USB'})
        plan = self.apply()
        self.assertEqual(plan['drivers'][0]['status'], 'blocked')
        values = wifi.read_config(self.config)
        self.assertNotEqual(values.get('X86'), 'y')
        self.assertNotEqual(values.get('COMPILE_TEST'), 'y')
        self.assertEqual(values['GOOD_USB'], 'y')

    def test_rolls_back_failed_candidate_dependencies(self):
        with self.kconfig.open('a') as handle:
            handle.write('''
config OPTIONAL_WIFI_HELPER
    bool "optional"
config FAILED_USB
    tristate "failed"
    depends on OPTIONAL_WIFI_HELPER && m
''')
        self.profile['helpers'].append('OPTIONAL_WIFI_HELPER')
        self.profile['drivers'].insert(0, {'symbol': 'FAILED_USB'})
        self.apply()
        self.assertNotEqual(wifi.read_config(self.config).get('OPTIONAL_WIFI_HELPER'), 'y')

    def test_selected_hidden_dependency_is_resolved(self):
        with self.kconfig.open('a') as handle:
            handle.write('''
config WIFI_CIPHER
    bool "cipher"
config WIFI_CORE
    tristate
    depends on WIFI_CIPHER
config SECOND_USB
    tristate "second driver"
    depends on USB
    select WIFI_CORE
''')
        self.profile['helpers'].append('WIFI_CIPHER')
        self.profile['drivers'].append({'symbol': 'SECOND_USB'})
        self.apply()
        values = wifi.read_config(self.config)
        self.assertEqual(values['SECOND_USB'], 'y')
        self.assertEqual(values['WIFI_CIPHER'], 'y')
        self.assertEqual(values['WIFI_CORE'], 'y')

    def test_no_viable_driver_and_missing_core_fail(self):
        self.profile['drivers'] = [{'symbol': 'MODULE_ONLY_USB'}]
        with self.assertRaisesRegex(ValueError, 'no USB WiFi driver'):
            self.apply()
        self.profile['required'].append('MISSING_CORE')
        with self.assertRaisesRegex(ValueError, 'lacks required'):
            self.apply()

    def add_legacy_abi_fixture(self):
        with self.kconfig.open('a') as handle:
            handle.write('''
config CFG80211_WEXT
    bool "legacy compatibility"
config CFG80211_WEXT_EXPORT
    bool
    select CFG80211_WEXT
config LEGACY_USB
    tristate "legacy USB"
    depends on USB
    select CFG80211_WEXT_EXPORT
''')
        self.profile['preserve_abi'] = ['CFG80211_WEXT', 'CFG80211_WEXT_EXPORT']

    def test_driver_select_cannot_change_stock_abi(self):
        self.add_legacy_abi_fixture()
        self.profile['drivers'].insert(0, {'symbol': 'LEGACY_USB'})
        plan = self.apply()
        self.assertEqual(plan['drivers'][0]['status'], 'blocked')
        self.assertIn('stock wireless ABI', plan['drivers'][0]['reason'])
        values = wifi.read_config(self.config)
        self.assertEqual(values['CFG80211_WEXT'], 'n')
        self.assertEqual(values['CFG80211_WEXT_EXPORT'], 'n')
        self.assertEqual(values['GOOD_USB'], 'y')
        self.assertEqual(plan['abi_preserved']['CFG80211_WEXT'], 'n')

    def test_legacy_driver_is_kept_when_stock_abi_already_enables_wext(self):
        self.add_legacy_abi_fixture()
        with self.kconfig.open('a') as handle:
            handle.write('''
config STOCK_LEGACY_SUPPORT
    bool "stock legacy support"
    select CFG80211_WEXT_EXPORT
''')
        with self.config.open('a') as handle:
            handle.write('CONFIG_STOCK_LEGACY_SUPPORT=y\n')
        self.profile['drivers'].append({'symbol': 'LEGACY_USB'})
        plan = self.apply()
        self.assertEqual(plan['drivers'][-1]['status'], 'builtin')
        self.assertEqual(plan['abi_preserved']['CFG80211_WEXT'], 'y')

    def test_optional_helper_that_changes_abi_is_rolled_back(self):
        self.add_legacy_abi_fixture()
        self.profile['drivers'][0]['helpers'] = ['LEGACY_USB']
        plan = self.apply()
        self.assertEqual(plan['drivers'][0]['status'], 'builtin')
        self.assertEqual(plan['drivers'][0]['helpers'][0]['status'], 'blocked')
        self.assertEqual(wifi.read_config(self.config)['CFG80211_WEXT'], 'n')

    def test_native_config_abi_drift_stops_firmware_and_final_verification(self):
        self.add_legacy_abi_fixture()
        self.apply()
        self.prepare()
        wifi.update_config(self.config, {'CFG80211_WEXT': 'y'})
        with self.assertRaisesRegex(ValueError, 'stock wireless ABI'):
            self.prepare()
        with self.assertRaisesRegex(ValueError, 'stock wireless ABI'):
            wifi.verify(self.root, self.config, self.plan_path, self.metadata, self.report)

    def firmware_manifest(self, source, drivers, staging, metadata, **kwargs):
        data = b'firmware-test-data'
        target = Path(staging) / 'good.bin'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return {'source': {'repository': 'https://example.test/firmware', 'revision': 'a' * 40},
                'files': [{'name': 'good.bin', 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'drivers': ['GOOD_USB']}],
                'names': ['good.bin'], 'status': 'complete', 'licenses': [],
                'missing': [], 'unresolved': [], 'no_firmware_drivers': []}

    def prepare(self):
        with patch.object(wifi.fw, 'stage_firmware', side_effect=self.firmware_manifest):
            return wifi.prepare_firmware(self.root, self.config, self.plan_path, self.staging, self.metadata)

    def test_embeds_firmware_and_preserves_preexisting_extra_firmware(self):
        self.apply()
        old_root = self.root / 'vendor-firmware'
        old_root.mkdir()
        (old_root / 'vendor.bin').write_bytes(b'vendor')
        wifi.update_config(self.config, {'EXTRA_FIRMWARE': '"vendor.bin"', 'EXTRA_FIRMWARE_DIR': json.dumps(str(old_root))})
        manifest = self.prepare()
        self.assertEqual(manifest['names'], ['good.bin', 'vendor.bin'])
        values = wifi.read_config(self.config)
        self.assertEqual(values['EXTRA_FIRMWARE'], '"good.bin vendor.bin"')
        self.assertEqual(json.loads(values['EXTRA_FIRMWARE_DIR']), str(self.staging.resolve()))
        self.assertEqual((self.staging / 'vendor.bin').read_bytes(), b'vendor')
        wifi.verify(self.root, self.config, self.plan_path, self.metadata, self.report)
        self.assertIn('test-device', self.report.read_text())
        self.assertIn('6.6-test', self.report.read_text())

    def test_dropped_candidate_is_not_given_firmware(self):
        self.apply()
        with self.kconfig.open('a') as handle:
            handle.write('\nconfig ANOTHER_USB\n    tristate "another"\n    depends on USB\n')
        self.profile['drivers'].append({'symbol': 'ANOTHER_USB'})
        self.apply()
        wifi.update_config(self.config, {'ANOTHER_USB': 'n'})
        captured = []
        def stage(source, drivers, staging, metadata, **kwargs):
            captured.extend(item['symbol'] for item in drivers)
            return self.firmware_manifest(source, drivers, staging, metadata, **kwargs)
        with patch.object(wifi.fw, 'stage_firmware', side_effect=stage):
            wifi.prepare_firmware(self.root, self.config, self.plan_path, self.staging, self.metadata)
        self.assertEqual(captured, ['GOOD_USB'])
        plan = json.loads(self.plan_path.read_text())
        self.assertEqual(plan['drivers'][-1]['status'], 'blocked')

    def test_verify_rejects_modular_driver_missing_firmware_and_config_drift(self):
        self.apply()
        self.prepare()
        original = self.config.read_text()
        for values in ({'GOOD_USB': 'm'}, {'EXTRA_FIRMWARE': '""'}, {'EXTRA_FIRMWARE_DIR': '"/wrong"'}):
            with self.subTest(values=values):
                self.config.write_text(original)
                wifi.update_config(self.config, values)
                with self.assertRaises(ValueError):
                    wifi.verify(self.root, self.config, self.plan_path, self.metadata, self.report)
        self.config.write_text(original)
        (self.staging / 'good.bin').write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError, 'checksum changed'):
            wifi.verify(self.root, self.config, self.plan_path, self.metadata, self.report)

    def test_kernel_environment_is_restored(self):
        original = dict(os.environ)
        original_cwd = Path.cwd()
        self.apply()
        self.assertEqual(dict(os.environ), original)
        self.assertEqual(Path.cwd(), original_cwd)

    def test_modern_linux_modules_property_has_legacy_semantics(self):
        original = self.kconfig.read_text()
        self.kconfig.write_text(original.replace('option modules', 'modules # modern kernel syntax'))
        plan = self.apply()
        self.assertEqual([driver['symbol'] for driver in plan['selected']], ['GOOD_USB'])
        self.assertEqual(plan['drivers'][1]['status'], 'blocked')

    def test_vendor_unclosed_source_quote_matches_native_linux(self):
        for quote in ('"', "'"):
            with self.subTest(quote=quote):
                included = self.root / 'camera/Kconfig'
                included.parent.mkdir(exist_ok=True)
                included.write_text('config VENDOR_CAMERA\n    bool "camera"\n    default y\n')
                original = self.kconfig.read_text()
                self.kconfig.write_text(original + f'\nsource {quote}camera/Kconfig\n')
                config_before = self.kconfig.read_text()
                plan = self.apply()
                self.assertEqual(self.kconfig.read_text(), config_before)
                self.assertEqual(wifi.load_kconfig(self.root, self.config).syms['VENDOR_CAMERA'].str_value, 'y')
                self.assertEqual(len(plan['kconfig_compatibility']), 1)
                self.assertIn('unclosed source quote', plan['kconfig_compatibility'][0])
                self.kconfig.write_text(original)

    def test_other_unclosed_strings_still_fail(self):
        with self.kconfig.open('a') as handle:
            handle.write('\nconfig BAD_STRING\n    string "unfinished prompt\n')
        with self.assertRaisesRegex(SystemExit, 'unterminated string'):
            self.apply()

    def test_unclosed_source_does_not_skip_missing_include(self):
        with self.kconfig.open('a') as handle:
            handle.write('\nsource "missing/Kconfig\n')
        with self.assertRaisesRegex(SystemExit, 'missing/Kconfig.*not found'):
            self.apply()

    def test_new_usb_family_preserves_disabled_other_transports(self):
        with self.kconfig.open('a') as handle:
            handle.write('''
config FULLMAC
    tristate "fullmac"
config FULLMAC_SDIO
    bool "SDIO"
    depends on FULLMAC
    default y
config FULLMAC_USB
    bool "USB fullmac"
    depends on FULLMAC && USB
''')
        self.profile['drivers'].append({'symbol': 'FULLMAC_USB', 'helpers': ['FULLMAC'],
                                        'preserve_disabled': ['FULLMAC_SDIO']})
        self.apply()
        values = wifi.read_config(self.config)
        self.assertEqual(values['FULLMAC_USB'], 'y')
        self.assertEqual(values['FULLMAC_SDIO'], 'n')
        wifi.update_config(self.config, {'FULLMAC': 'y', 'FULLMAC_SDIO': 'y'})
        self.apply()
        self.assertEqual(wifi.read_config(self.config)['FULLMAC_SDIO'], 'y')

    def test_failed_optional_helper_rolls_back_without_losing_driver(self):
        with self.kconfig.open('a') as handle:
            handle.write('''
config HELPER_DEP
    bool "helper dependency"
config UNSUPPORTED_FEATURE
    tristate "unsupported feature"
    depends on HELPER_DEP && m
''')
        self.profile['helpers'].append('HELPER_DEP')
        self.profile['drivers'][0]['helpers'] = ['UNSUPPORTED_FEATURE']
        self.profile['drivers'][0]['notes'] = 'Experimental hardware support.'
        plan = self.apply()
        self.assertEqual(wifi.read_config(self.config)['GOOD_USB'], 'y')
        self.assertNotEqual(wifi.read_config(self.config).get('HELPER_DEP'), 'y')
        self.assertEqual(plan['drivers'][0]['helpers'][0]['status'], 'blocked')
        self.assertEqual(plan['drivers'][0]['notes'], 'Experimental hardware support.')

    def test_verify_checks_firmware_bytes_and_request_name_in_image(self):
        self.apply()
        self.prepare()
        data = (self.staging / 'good.bin').read_bytes()
        image = self.root / 'Image'
        image.write_bytes(b'kernel-header' + data + b'good.bin\0')
        wifi.verify(self.root, self.config, self.plan_path, self.metadata, self.report, image)
        self.assertIn('Compiled Image firmware contents: verified', self.report.read_text())
        for contents in (b'kernel-header' + data, b'kernel-headergood.bin\0', b''):
            image.write_bytes(contents)
            with self.assertRaises(ValueError):
                wifi.verify(self.root, self.config, self.plan_path, self.metadata, self.report, image)

    def test_select_cannot_bypass_preserved_transport_and_helper_is_rolled_back(self):
        with self.kconfig.open('a') as handle:
            handle.write('''
config OTHER_BUS
    bool "other transport"
config WIFI_HELPER
    bool "helper"
    select OTHER_BUS
''')
        self.profile['drivers'][0].update(helpers=['WIFI_HELPER'], preserve_disabled=['OTHER_BUS'])
        plan = self.apply()
        self.assertEqual(plan['drivers'][0]['status'], 'builtin')
        self.assertEqual(plan['drivers'][0]['helpers'][0]['status'], 'blocked')
        self.assertEqual(wifi.read_config(self.config)['OTHER_BUS'], 'n')
        self.prepare()
        wifi.update_config(self.config, {'OTHER_BUS': 'y'})
        with self.assertRaisesRegex(ValueError, 'unexpectedly enabled'):
            wifi.verify(self.root, self.config, self.plan_path, self.metadata, self.report)

    def test_optional_helper_coverage_uses_final_kernel_values(self):
        with self.kconfig.open('a') as handle:
            handle.write('\nconfig EXTRA_USB_IDS\n    bool "extra USB IDs"\n')
        self.profile['drivers'][0]['helpers'] = ['EXTRA_USB_IDS']
        self.apply()
        wifi.update_config(self.config, {'EXTRA_USB_IDS': 'n'})
        self.prepare()
        wifi.verify(self.root, self.config, self.plan_path, self.metadata, self.report)
        self.assertIn('CONFIG_EXTRA_USB_IDS: blocked', self.report.read_text())
        self.assertNotIn('CONFIG_EXTRA_USB_IDS: builtin', self.report.read_text())

    def test_missing_softmac_core_does_not_prevent_fullmac_driver(self):
        self.kconfig.write_text(self.kconfig.read_text().replace('config MAC80211\n', 'config UNUSED_MAC80211\n'))
        with self.kconfig.open('a') as handle:
            handle.write('\nconfig FULLMAC_USB\n    tristate "fullmac USB"\n    depends on USB && CFG80211\n')
        self.profile['required'].remove('MAC80211')
        self.profile['drivers'].append({'symbol': 'FULLMAC_USB'})
        plan = self.apply()
        self.assertEqual([driver['symbol'] for driver in plan['selected']], ['FULLMAC_USB'])

    def test_existing_relative_firmware_symlink_is_preserved(self):
        self.apply()
        old_root = self.root / 'vendor'
        old_root.mkdir()
        (old_root / 'actual.bin').write_bytes(b'vendor-data')
        (old_root / 'alias.bin').symlink_to('actual.bin')
        wifi.update_config(self.config, {'EXTRA_FIRMWARE': '"alias.bin"', 'EXTRA_FIRMWARE_DIR': json.dumps(str(old_root))})
        self.prepare()
        self.assertEqual((self.staging / 'alias.bin').read_bytes(), b'vendor-data')

    def test_unicode_firmware_directory_is_written_as_valid_kconfig_string(self):
        self.apply()
        self.staging = self.root / '固件'
        self.prepare()
        self.assertIn('固件', self.config.read_text())
        wifi.verify(self.root, self.config, self.plan_path, self.metadata, self.report)

    def test_regulatory_database_requirements_follow_final_config(self):
        self.apply()
        path = self.root / 'net/wireless/reg.c'
        path.parent.mkdir(parents=True)
        path.write_text('/* regulatory.db */\n')
        wifi.update_config(self.config, {'CFG80211_REQUIRE_SIGNED_REGDB': 'y',
                                        'CFG80211_USE_KERNEL_REGDB_KEYS': 'y'})
        captured = []
        def stage(source, drivers, staging, metadata, **kwargs):
            captured.extend(drivers)
            return self.firmware_manifest(source, drivers, staging, metadata, **kwargs)
        with patch.object(wifi.fw, 'stage_firmware', side_effect=stage):
            wifi.prepare_firmware(self.root, self.config, self.plan_path, self.staging, self.metadata)
        self.assertEqual(captured[-1]['symbol'], 'CFG80211')
        self.assertEqual(captured[-1]['firmware'], ['regulatory.db', 'regulatory.db.p7s'])
        self.assertTrue(captured[-1]['regdb_use_kernel_keys'])


if __name__ == '__main__':
    unittest.main()
