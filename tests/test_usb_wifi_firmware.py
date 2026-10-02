import base64
import hashlib
import importlib.util
import io
import json
import lzma
from pathlib import Path
import subprocess
import tempfile
import tarfile
import unittest
import urllib.error
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('usb_wifi_firmware', ROOT / 'scripts/usb_wifi_firmware.py')
firmware = importlib.util.module_from_spec(spec)
spec.loader.exec_module(firmware)


class FirmwareTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / 'kernel'
        self.source.mkdir()
        self.staging = self.root / 'staging'
        self.metadata = self.root / 'metadata'
        self.lock = {'repository': 'https://kernel.googlesource.com/firmware', 'revision': 'a' * 40}
        self.files = {}

    def driver(self, text, firmware_names=(), symbol='USB_TEST'):
        path = self.source / symbol / 'usb.c'
        path.parent.mkdir(exist_ok=True)
        path.write_text(text)
        return {'symbol': symbol, 'sources': [f'{symbol}/usb.c'], 'firmware': list(firmware_names)}

    def repository(self, lock, cache_dir):
        files = self.files

        class Repository:
            def read(self, name):
                if name not in files:
                    raise FileNotFoundError(name)
                value = files[name]
                return value if isinstance(value, tuple) else (value, 0o100644)

        return Repository()

    def stage(self, drivers, **kwargs):
        with patch.object(firmware, 'FirmwareRepository', self.repository):
            return firmware.stage_firmware(self.source, drivers, self.staging, self.metadata,
                                           self.lock, **kwargs)

    def whence(self, entries, license='Redistributable. See LICENSE.test for details.'):
        self.files['WHENCE'] = f'Driver: usb_test\n{entries}\nLicence: {license}\n'.encode()
        self.files['LICENSES/LICENSE.test'] = b'Example redistribution license\n'

    def test_resolves_local_headers_recursive_macros_concatenation_and_variables(self):
        driver = self.driver('#include "fw.h"\n#define NAME ROOT "chip.bin"\n'
                             'static const char *firmware_name = NAME;\n'
                             'MODULE_FIRMWARE(firmware_name);\n'
                             '// MODULE_FIRMWARE("wrong.bin");\n')
        (self.source / 'USB_TEST/fw.h').write_text('#define ROOT DIRECTORY\n#define DIRECTORY "usb/"\n')
        result = firmware.collect_firmware(self.source, [driver])
        self.assertEqual(result['files'], {'usb/chip.bin': ['USB_TEST']})
        self.assertEqual(result['unresolved'], [])
        self.assertEqual(result['drivers']['USB_TEST']['sources'], ['USB_TEST/fw.h', 'USB_TEST/usb.c'])

    def test_does_not_scan_unselected_pci_firmware(self):
        driver = self.driver('MODULE_FIRMWARE("usb.bin");')
        (self.source / 'USB_TEST/pci.c').write_text('MODULE_FIRMWARE("pci.bin");')
        self.assertEqual(list(firmware.collect_firmware(self.source, [driver])['files']), ['usb.bin'])

    def test_catalog_directory_resolves_incomplete_module_metadata_but_keeps_real_requests(self):
        driver = self.driver('MODULE_FIRMWARE("chip.bin");\n'
                             'request_firmware(&fw, runtime_path, dev);', ['usb/chip*.bin'])
        result = firmware.collect_firmware(self.source, [driver])
        self.assertEqual(list(result['files']), ['usb/chip*.bin'])
        driver = self.driver('MODULE_FIRMWARE("chip.bin");\n'
                             'request_firmware(&fw, "chip.bin", dev);', ['usb/chip*.bin'])
        self.assertEqual(set(firmware.collect_firmware(self.source, [driver])['files']), {'chip.bin', 'usb/chip*.bin'})

    def test_dynamic_filename_fallback_and_real_firmware_free_driver(self):
        dynamic = self.driver('request_firmware(&fw, runtime_name, dev);', ['usb/chip.bin'])
        no_firmware = self.driver('int usb_probe(void) { return 0; }', symbol='NO_FIRMWARE')
        result = firmware.collect_firmware(self.source, [dynamic, no_firmware])
        self.assertEqual(result['unresolved'], [])
        self.assertEqual(result['drivers']['USB_TEST']['catalog_resolved'], ['runtime_name'])
        self.assertTrue(result['drivers']['NO_FIRMWARE']['no_firmware'])
        with patch.object(firmware.FirmwareRepository, 'read', side_effect=AssertionError('network')):
            result = firmware.stage_firmware(self.source, [no_firmware], self.staging,
                                             self.metadata, self.lock)
        self.assertEqual(result['no_firmware_drivers'], ['NO_FIRMWARE'])
        self.assertEqual(result['status'], 'complete')

    def test_unknown_request_never_claimed_firmware_free(self):
        driver = self.driver('MODULE_FIRMWARE(UNKNOWN);')
        result = self.stage([driver])
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['no_firmware_drivers'], [])
        self.assertEqual(result['unresolved'], [{'driver': 'USB_TEST', 'reference': 'UNKNOWN'}])
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            self.stage([driver], strict=True)
        self.assertTrue((self.metadata / 'manifest.json').exists())

    def test_materializes_whence_aliases_under_request_names_and_keeps_licenses(self):
        driver = self.driver('MODULE_FIRMWARE("old.bin");\nMODULE_FIRMWARE("usb/latest.bin");')
        self.whence('File: usb/latest.bin\nLink: old.bin -> usb/latest.bin')
        self.files['usb/latest.bin'] = b'real raw firmware'
        result = self.stage([driver])
        self.assertEqual(result['names'], ['old.bin', 'usb/latest.bin'])
        self.assertEqual(result['status'], 'complete')
        for name in result['names']:
            self.assertEqual((self.staging / name).read_bytes(), b'real raw firmware')
            self.assertFalse((self.staging / name).is_symlink())
        self.assertEqual(result['files'][0]['sha256'], hashlib.sha256(b'real raw firmware').hexdigest())
        self.assertEqual(result['files'][0]['source_path'], 'usb/latest.bin')
        self.assertEqual(result['licenses'][0]['name'], 'LICENSE.test')
        self.assertTrue((self.metadata / 'whence/old.bin.txt').exists())
        self.assertEqual(json.loads((self.metadata / 'manifest.json').read_text()), result)

    def test_decompresses_and_resolves_git_symlink(self):
        driver = self.driver('MODULE_FIRMWARE("usb/alias.bin");')
        self.whence('File: usb/alias.bin\nFile: usb/real.bin')
        self.files['usb/alias.bin'] = (b'real.bin', 0o120000)
        self.files['usb/real.bin.xz'] = lzma.compress(b'uncompressed kernel input')
        result = self.stage([driver])
        self.assertEqual((self.staging / 'usb/alias.bin').read_bytes(), b'uncompressed kernel input')
        self.assertEqual(result['files'][0]['source_path'], 'usb/real.bin.xz')

    def test_symlink_pointing_directly_at_compressed_blob_is_decompressed(self):
        driver = self.driver('MODULE_FIRMWARE("usb/alias.bin");')
        self.whence('File: usb/alias.bin\nFile: usb/real.bin.xz')
        self.files['usb/alias.bin'] = (b'real.bin.xz', 0o120000)
        self.files['usb/real.bin.xz'] = lzma.compress(b'raw')
        result = self.stage([driver])
        self.assertEqual((self.staging / 'usb/alias.bin').read_bytes(), b'raw')
        self.assertEqual(result['files'][0]['source_path'], 'usb/real.bin.xz')

    def test_missing_candidate_is_reported_but_other_firmware_is_staged(self):
        driver = self.driver('MODULE_FIRMWARE("usb.bin");', ['missing.bin'])
        self.whence('File: usb.bin')
        self.files['usb.bin'] = b'available'
        result = self.stage([driver])
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['names'], ['usb.bin'])
        self.assertEqual(result['missing'][0]['name'], 'missing.bin')
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            self.stage([driver], strict=True)

    def test_catalog_pattern_is_expanded_only_against_whence(self):
        driver = self.driver('', ['usb/chip-*.bin'])
        self.whence('File: usb/chip-a.bin\nFile: pci/chip-b.bin')
        self.files['usb/chip-a.bin'] = b'available'
        result = self.stage([driver])
        self.assertEqual(result['names'], ['usb/chip-a.bin'])

    def test_directory_traversal_symlink_cycles_and_missing_license_fail(self):
        for name in ('../outside', '/absolute', 'usb/../../outside', 'usb/a bin', 'usb/../a'):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'unsafe'):
                firmware.safe_name(name)
        driver = self.driver('MODULE_FIRMWARE("usb.bin");')
        self.whence('Link: usb.bin -> second.bin\nLink: second.bin -> usb.bin')
        with self.assertRaisesRegex(ValueError, 'cycle'):
            self.stage([driver])
        self.whence('File: usb.bin')
        self.files['usb.bin'] = b'available'
        del self.files['LICENSES/LICENSE.test']
        with self.assertRaisesRegex(ValueError, 'license text missing'):
            self.stage([driver])
        self.assertFalse((self.staging / 'usb.bin').exists())

    def test_existing_destination_symlink_cannot_escape(self):
        driver = self.driver('MODULE_FIRMWARE("usb/blob.bin");')
        self.whence('File: usb/blob.bin')
        self.files['usb/blob.bin'] = b'available'
        self.staging.mkdir()
        (self.staging / 'usb').symlink_to(self.root / 'other')
        with self.assertRaisesRegex(ValueError, 'escapes|symlink'):
            self.stage([driver])

    def test_network_and_whence_integrity_errors_never_become_missing(self):
        driver = self.driver('MODULE_FIRMWARE("usb.bin");')
        self.whence('File: usb.bin')
        self.lock['whence_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'checksum'):
            self.stage([driver])
        with patch.object(firmware.FirmwareRepository, 'read', side_effect=ValueError('firmware download failed')):
            with self.assertRaisesRegex(ValueError, 'download failed'):
                firmware.stage_firmware(self.source, [driver], self.staging, self.metadata, self.lock)

    def test_git_blob_checksum_and_cache_tampering_are_rejected(self):
        repository = firmware.FirmwareRepository(self.lock, self.root / 'cache')
        data = b'valid firmware'
        oid = firmware._blob_hash(data)
        repository.trees['usb'] = [{'name': 'blob.bin', 'type': 'blob', 'id': oid, 'mode': 0o100644}]
        with patch.object(repository, '_fetch', return_value=data):
            self.assertEqual(repository.read('usb/blob.bin')[0], data)
        (self.root / 'cache' / self.lock['revision'] / oid).write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError, 'Git blob checksum mismatch'):
            repository.read('usb/blob.bin')

    def test_revision_is_immutable(self):
        self.lock['revision'] = 'main'
        with self.assertRaisesRegex(ValueError, 'full immutable'):
            firmware.FirmwareRepository(self.lock)

    def archive_source(self, members):
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode='w:bz2') as archive:
            for name, data in members.items():
                entry = tarfile.TarInfo(name)
                entry.size = len(data)
                archive.addfile(entry, io.BytesIO(data))
        data = output.getvalue()
        entry = {'name': 'upstream', 'release': '1.5', 'url': 'https://example.org/upstream-1.5.tar.bz2',
                 'archive_name': 'upstream-1.5.tar.bz2', 'sha256': hashlib.sha256(data).hexdigest(),
                 'license': 'GPL-2.0', 'license_files': ['upstream/COPYING', 'upstream/README'],
                 'files': {'usb/zd.bin': 'upstream/zd.bin'}}
        self.lock['extra_sources'] = [entry]
        cache = self.root / 'cache' / 'archives' / entry['sha256']
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(data)
        return entry, cache

    def test_supplemental_archive_keeps_original_sources_notices_and_blob_hashes(self):
        driver = self.driver('MODULE_FIRMWARE("usb/zd.bin");')
        self.whence('File: unrelated.bin')
        entry, cache = self.archive_source({'upstream/zd.bin': b'firmware', 'upstream/COPYING': b'GPL text',
                                            'upstream/README': b'copyright and origin',
                                            'upstream/source.h': b'original source code'})
        result = self.stage([driver], cache_dir=self.root / 'cache')
        self.assertEqual(result['status'], 'complete')
        self.assertEqual((self.staging / 'usb/zd.bin').read_bytes(), b'firmware')
        self.assertEqual(result['files'][0]['source_revision'], entry['sha256'])
        self.assertEqual((self.metadata / 'sources/upstream-1.5.tar.bz2').read_bytes(), cache.read_bytes())
        self.assertEqual((self.metadata / 'licenses/upstream-COPYING').read_bytes(), b'GPL text')

    def test_supplemental_archive_path_traversal_and_checksum_mismatch_fail(self):
        driver = self.driver('MODULE_FIRMWARE("usb/zd.bin");')
        self.whence('File: unrelated.bin')
        _, cache = self.archive_source({'../escape': b'bad'})
        with self.assertRaisesRegex(ValueError, 'unsafe'):
            self.stage([driver], cache_dir=self.root / 'cache')
        cache.write_bytes(b'tampered archive')
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            self.stage([driver], cache_dir=self.root / 'cache')

    def test_whence_accepts_unrelated_dmi_spaces_and_escaped_link_names(self):
        text = ('Driver: unrelated\nFile: brcm/Intel Corp.-BOARD.txt\n'
                'Link: brcm/Raspberry\\ Pi.txt -> Intel\\ Corp.-BOARD.txt\n'
                'Licence: Redistributable. See LICENSE.test for details.\n')
        records, links = firmware.parse_whence(text)
        self.assertIn('brcm/Intel Corp.-BOARD.txt', records)
        self.assertEqual(links['brcm/Raspberry Pi.txt'], 'brcm/Intel Corp.-BOARD.txt')

    def regdb_entries(self):
        entries, certificates = [], {}
        for release, signer in [('new', 'wens'), ('old', 'sforshee')]:
            entry, _ = self.archive_source({'upstream/regulatory.db': release.encode(),
                                            'upstream/regulatory.db.p7s': (release + ' signature').encode(),
                                            'upstream/COPYING': b'ISC license', 'upstream/README': b'regdb provenance'})
            certificate = b'\x30\x05' + signer.encode()
            entry.update(name='wireless-regdb-' + release, release=release,
                         archive_name='wireless-regdb-' + release + '.tar.bz2',
                         files={'regulatory.db': 'upstream/regulatory.db',
                                'regulatory.db.p7s': 'upstream/regulatory.db.p7s'},
                         trusted_certificate={'path': f'net/wireless/certs/{signer}.hex',
                                              'sha256': hashlib.sha256(certificate).hexdigest(),
                                              'signature': 'regulatory.db.p7s'})
            entries.append(entry)
            certificates[signer] = certificate
        self.lock['extra_sources'] = entries
        return certificates

    def regdb_driver(self, signed=True):
        names = ['regulatory.db', 'regulatory.db.p7s'] if signed else ['regulatory.db']
        driver = self.driver('request_firmware(&db, "regulatory.db", dev);\n'
                             '#ifdef CONFIG_CFG80211_REQUIRE_SIGNED_REGDB\n'
                             'request_firmware(&sig, "regulatory.db.p7s", dev);\n#endif\n', names, symbol='CFG80211')
        driver['firmware_only'] = True
        driver['regdb_use_kernel_keys'] = True
        return driver

    def kernel_certificate(self, signer, certificate):
        path = self.source / f'net/wireless/certs/{signer}.hex'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('/* comment with 0xff */\n' + ', '.join(f'0x{value:02x}' for value in certificate))

    def test_regdb_chooses_release_matching_actual_kernel_signer_bytes(self):
        certificates = self.regdb_entries()
        driver = self.regdb_driver()
        self.kernel_certificate('sforshee', certificates['sforshee'])
        result = self.stage([driver], cache_dir=self.root / 'cache')
        self.assertEqual(result['status'], 'complete')
        self.assertEqual((self.staging / 'regulatory.db').read_bytes(), b'old')
        self.assertEqual(result['files'][0]['source_release'], 'old')
        self.kernel_certificate('wens', certificates['wens'])
        result = self.stage([driver], cache_dir=self.root / 'cache')
        self.assertEqual((self.staging / 'regulatory.db').read_bytes(), b'new')
        self.assertEqual(result['files'][0]['signer_certificate_sha256'], hashlib.sha256(certificates['wens']).hexdigest())

    def test_regdb_unknown_or_disabled_kernel_signers_are_explicit_missing(self):
        certificates = self.regdb_entries()
        driver = self.regdb_driver()
        self.kernel_certificate('wens', b'wrong certificate with the same filename')
        result = self.stage([driver], cache_dir=self.root / 'cache')
        self.assertEqual(result['status'], 'none')
        self.assertEqual(result['names'], [])
        self.assertEqual({item['name'] for item in result['missing']}, {'regulatory.db', 'regulatory.db.p7s'})
        self.assertIn('trusted kernel signer', result['missing'][0]['reason'])
        self.kernel_certificate('wens', certificates['wens'])
        driver['regdb_use_kernel_keys'] = False
        result = self.stage([driver], cache_dir=self.root / 'cache')
        self.assertEqual(result['names'], [])

    def test_regdb_respects_explicit_extra_key_directory(self):
        certificates = self.regdb_entries()
        driver = self.regdb_driver()
        driver['regdb_use_kernel_keys'] = False
        directory = self.source / 'extra-keys'
        directory.mkdir()
        (directory / 'public.x509').write_bytes(certificates['wens'])
        driver['regdb_extra_keydir'] = 'extra-keys'
        result = self.stage([driver], cache_dir=self.root / 'cache')
        self.assertEqual(result['status'], 'complete')
        self.assertEqual((self.staging / 'regulatory.db').read_bytes(), b'new')

    def test_unsigned_regdb_catalog_does_not_scan_disabled_p7s_branch(self):
        self.regdb_entries()
        driver = self.regdb_driver(signed=False)
        result = self.stage([driver], cache_dir=self.root / 'cache')
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(result['names'], ['regulatory.db'])
        self.assertEqual((self.staging / 'regulatory.db').read_bytes(), b'new')
        self.assertEqual(result['drivers']['CFG80211']['sources'], ['CFG80211/usb.c'])

    def test_git_tree_encoding_matches_git_and_reuses_verified_cache_offline(self):
        data = b'firmware content'
        blob = firmware._blob_hash(data)
        child = [{'name': 'blob.bin', 'type': 'blob', 'mode': 0o100644, 'id': blob}]
        child_id = firmware._tree_hash(child)
        encoded = b'100644 blob.bin\0' + bytes.fromhex(blob)
        expected = subprocess.run(['git', 'hash-object', '-t', 'tree', '--stdin'],
                                  input=encoded, capture_output=True, check=True).stdout.decode().strip()
        self.assertEqual(child_id, expected)
        root = [{'name': 'usb', 'type': 'tree', 'mode': 0o40000, 'id': child_id}]
        self.lock['root_tree'] = firmware._tree_hash(root)
        cache = self.root / 'cache'
        repository = firmware.FirmwareRepository(self.lock, cache)

        def fetch(path, format):
            return {'/': {'entries': root}, 'usb/': {'entries': child}, 'usb/blob.bin': data}[path]

        with patch.object(repository, '_fetch', side_effect=fetch):
            self.assertEqual(repository.read('usb/blob.bin')[0], data)
        repository = firmware.FirmwareRepository(self.lock, cache)
        with patch.object(repository, '_fetch', side_effect=AssertionError('unexpected network')):
            self.assertEqual(repository.read('usb/blob.bin')[0], data)
            with self.assertRaises(FileNotFoundError):
                repository.read('absent/blob.bin')
        tree_cache = cache / self.lock['revision'] / 'trees' / (self.lock['root_tree'] + '.json')
        root[0]['id'] = '0' * 40
        tree_cache.write_text(json.dumps(root))
        repository = firmware.FirmwareRepository(self.lock, cache)
        with patch.object(repository, '_fetch', side_effect=AssertionError('unexpected network')):
            with self.assertRaisesRegex(ValueError, 'tree checksum mismatch'):
                repository.read('usb/blob.bin')

    def test_http_rate_limit_retry_is_bounded_and_respects_capped_retry_after(self):
        repository = firmware.FirmwareRepository(self.lock)
        rate_limit = urllib.error.HTTPError('https://example.org', 429, 'rate limited', {'Retry-After': '90'}, None)
        with patch.object(firmware.urllib.request, 'urlopen', side_effect=[rate_limit, io.BytesIO(base64.b64encode(b'blob'))]) as fetch:
            with patch.object(firmware.time, 'sleep') as sleep:
                self.assertEqual(repository._fetch('usb.bin', 'TEXT'), b'blob')
        self.assertEqual(fetch.call_count, 2)
        sleep.assert_called_once_with(10)
        unavailable = urllib.error.HTTPError('https://example.org', 503, 'unavailable', {}, None)
        with patch.object(firmware.urllib.request, 'urlopen', side_effect=unavailable) as fetch:
            with patch.object(firmware.time, 'sleep') as sleep:
                with self.assertRaisesRegex(ValueError, 'HTTP 503'):
                    repository._fetch('usb.bin', 'TEXT')
        self.assertEqual(fetch.call_count, 4)
        self.assertEqual(sleep.call_count, 3)
        self.assertLessEqual(sum(call.args[0] for call in sleep.call_args_list), 30)

    def test_missing_and_invalid_source_responses_are_not_retried(self):
        repository = firmware.FirmwareRepository(self.lock)
        missing = urllib.error.HTTPError('https://example.org', 404, 'missing', {}, None)
        with patch.object(firmware.urllib.request, 'urlopen', side_effect=missing) as fetch:
            with patch.object(firmware.time, 'sleep') as sleep:
                with self.assertRaises(FileNotFoundError):
                    repository._fetch('usb.bin', 'TEXT')
        self.assertEqual(fetch.call_count, 1)
        sleep.assert_not_called()
        with patch.object(firmware.urllib.request, 'urlopen', return_value=io.BytesIO(b'<html>')) as fetch:
            with patch.object(firmware.time, 'sleep') as sleep:
                with self.assertRaisesRegex(ValueError, 'invalid firmware source response'):
                    repository._fetch('usb.bin', 'TEXT')
        self.assertEqual(fetch.call_count, 1)
        sleep.assert_not_called()


if __name__ == '__main__':
    unittest.main()
