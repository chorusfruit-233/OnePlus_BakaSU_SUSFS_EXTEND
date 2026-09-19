import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('wifi', ROOT / 'scripts/builtin_usb_wifi.py')
wifi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wifi)


class BuiltinWifiTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.profile = json.loads((ROOT / 'profiles/usb-wifi.json').read_text())
        self.symbols = self.profile['required'] + self.profile['helpers'] + ['RTL8XXXU']
        self.kconfig = self.root / 'Kconfig'
        self.kconfig.write_text('\n'.join('config ' + name for name in self.symbols))
        self.config = self.root / '.config'
        self.config.write_text('CONFIG_CFG80211=m\n# CONFIG_RTL8XXXU is not set\n'
                               'CONFIG_KSU=y\nCONFIG_SUSFS=y\nCONFIG_LTO_CLANG_THIN=y\n'
                               'CONFIG_LOCALVERSION="-custom"\nCONFIG_VENDOR_WLAN=m\n')
        self.report = self.root / 'report.txt'

    def test_promotes_dependencies_without_changing_unrelated_config(self):
        requested, drivers, absent = wifi.plan(self.root, self.profile)
        wifi.apply(self.config, requested)
        result = self.config.read_text()
        self.assertIn('CONFIG_CFG80211=y\n', result)
        self.assertIn('CONFIG_RTL8XXXU=y\n', result)
        self.assertNotIn('CONFIG_CFG80211=m', result)
        for line in ('CONFIG_KSU=y', 'CONFIG_SUSFS=y', 'CONFIG_LTO_CLANG_THIN=y',
                     'CONFIG_LOCALVERSION="-custom"', 'CONFIG_VENDOR_WLAN=m'):
            self.assertIn(line + '\n', result)
        self.assertEqual(drivers, ['RTL8XXXU'])
        self.assertIn('MT7921U', absent)
        self.assertNotIn('RTW89', requested)
        wifi.apply(self.config, requested)
        self.assertEqual(self.config.read_text(), result)
        wifi.verify(self.config, requested, drivers, absent, self.report)

    def test_no_drivers_fails(self):
        self.kconfig.write_text('\n'.join('config ' + name for name in self.profile['required']))
        with self.assertRaisesRegex(ValueError, 'no supported'):
            wifi.plan(self.root, self.profile)

    def test_missing_core_fails(self):
        self.kconfig.write_text('config RTL8XXXU\n')
        with self.assertRaisesRegex(ValueError, 'required USB WiFi'):
            wifi.plan(self.root, self.profile)

    def test_dropped_driver_or_modular_dependency_fails_with_report(self):
        requested, drivers, absent = wifi.plan(self.root, self.profile)
        for symbol, value in [('RTL8XXXU', 'n'), ('MAC80211', 'm')]:
            with self.subTest(symbol=symbol):
                wifi.apply(self.config, requested)
                self.config.write_text(self.config.read_text().replace(
                    f'CONFIG_{symbol}=y', f'CONFIG_{symbol}={value}'))
                with self.assertRaisesRegex(ValueError, f'CONFIG_{symbol}={value}'):
                    wifi.verify(self.config, requested, drivers, absent, self.report)
                self.assertIn(f'CONFIG_{symbol}={value}', self.report.read_text())

    def test_nested_mixed_case_symbols_and_menuconfig(self):
        path = self.root / 'drivers/net/wireless/Kconfig.vendor'
        path.parent.mkdir(parents=True)
        path.write_text('menuconfig RT2X00\nconfig MT76x0U\nconfig RT2800USB\n')
        requested, drivers, _ = wifi.plan(self.root, self.profile)
        self.assertIn('MT76x0U', drivers)
        self.assertIn('RT2X00', requested)


if __name__ == '__main__':
    unittest.main()
