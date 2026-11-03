import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('vendor_wifi_abi', Path(__file__).resolve().parents[1] / 'scripts/verify_vendor_wifi_abi.py')
abi = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(abi)


class VendorAbiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.symvers = Path(self.temp.name) / 'Module.symvers'
        self.reference = {'model': 'OP13', 'os_version': 'OOS16', 'kernel': '6.6.118',
                          'symbols': {'wiphy_register': '0x73c9f04c'}}

    def test_matching_builtin_crc_passes(self):
        self.symvers.write_text('0x73c9f04c\twiphy_register\tvmlinux\tEXPORT_SYMBOL\n')
        self.assertEqual(abi.check(self.reference, self.symvers), [])

    def test_changed_crc_and_missing_export_fail(self):
        self.symvers.write_text('0x00000000\twiphy_register\tvmlinux\tEXPORT_SYMBOL\n')
        self.assertIn('factory=0x73c9f04c', abi.check(self.reference, self.symvers)[0])
        self.symvers.write_text('')
        self.assertIn('missing', abi.check(self.reference, self.symvers)[0])

    def test_module_fallback_fails(self):
        self.symvers.write_text('0x73c9f04c\twiphy_register\tnet/wireless/cfg80211\tEXPORT_SYMBOL\n')
        self.assertIn('not built-in', abi.check(self.reference, self.symvers)[0])

    def test_reference_is_scoped_to_exact_model_os_and_kernel(self):
        self.assertTrue(abi.matches(self.reference, 'OP13', 'OOS16', 'android15-6.6.118'))
        self.assertFalse(abi.matches(self.reference, 'OP13', 'OOS16', 'android15-6.6.89'))
        self.assertFalse(abi.matches(self.reference, 'OP13', 'OOS15', '6.6.118'))
        self.assertFalse(abi.matches(self.reference, 'OP13T', 'OOS16', '6.6.118'))

    def test_cli_refuses_packaging_but_saves_mismatch_report(self):
        self.symvers.write_text('')
        report = Path(self.temp.name) / 'vendor-abi.txt'
        result = subprocess.run([sys.executable, SPEC.origin, '--model', 'OP13', '--os-version', 'OOS16',
                                 '--kernel', 'android15-6.6.118', '--symvers', str(self.symvers),
                                 '--report', str(report)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('refusing to package', result.stderr)
        self.assertIn('wiphy_register: missing', report.read_text())

    def test_factory_reference_matches_all_50_builtin_exports(self):
        reference = json.loads((abi.REFERENCES / 'op13-oos16-6.6.118.json').read_text())
        self.assertEqual(len(reference['symbols']), 50)
        self.symvers.write_text(''.join(f'{crc}\t{name}\tvmlinux\tEXPORT_SYMBOL\n'
                                       for name, crc in reference['symbols'].items()))
        self.assertEqual(abi.check(reference, self.symvers), [])

    def test_missing_reference_refuses_packaging_instead_of_using_another_os(self):
        for os_version, kernel in [('COS17', '6.6.123'), ('OOS16', '6.6.89'), ('COS18', '6.6.118')]:
            with self.subTest(os_version=os_version, kernel=kernel):
                report = Path(self.temp.name) / 'unknown-abi.txt'
                result = subprocess.run([sys.executable, SPEC.origin, '--model', 'OP13',
                                         '--os-version', os_version, '--kernel', kernel,
                                         '--symvers', str(self.symvers), '--report', str(report)],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 1)
                self.assertIn('no matching factory wireless ABI reference', report.read_text())
                self.assertNotIn('PASS:', result.stdout)

    def test_cos17_crc_report_keeps_the_experimental_reference_scope(self):
        reference = abi.selected_references('OP13', 'COS17', '6.6.118')[0]
        self.assertEqual(reference['factory_wlan_imports'], 'unverified')
        self.symvers.write_text(''.join(f'{crc}\t{name}\tvmlinux\tEXPORT_SYMBOL\n'
                                       for name, crc in reference['symbols'].items()))
        report = Path(self.temp.name) / 'cos17-abi.txt'
        result = subprocess.run([sys.executable, SPEC.origin, '--model', 'OP13',
                                 '--os-version', 'COS17', '--kernel', '6.6.118',
                                 '--symvers', str(self.symvers), '--report', str(report)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('PASS: 50', result.stdout)
        self.assertIn('not independently audited', result.stdout)
        self.assertNotIn('match factory module requirements', result.stdout)
