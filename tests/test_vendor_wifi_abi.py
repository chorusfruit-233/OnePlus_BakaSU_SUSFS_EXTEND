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
