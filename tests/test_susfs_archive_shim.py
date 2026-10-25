import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SHIM = Path(__file__).resolve().parents[1] / '.github/scripts/susfs-archive-bin/aria2c'
SHA = 'c51cd8aa' + '0' * 32
API = 'https://gitlab.com/api/v4/projects/simonpunk%2Fsusfs4ksu/repository/archive.tar.gz'


class SusfsArchiveShimTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.shared = self.root / 'susfs-archives'
        self.shared.mkdir()
        self.content = b'shared archive bytes'
        (self.shared / f'susfs4ksu-{SHA}.tar.gz').write_bytes(self.content)
        self.output = self.root / 'output'
        self.log = self.root / 'passthrough.json'
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        real = self.bin / 'aria2c'
        real.write_text('#!/usr/bin/env python3\nimport json, os, sys\n'
                        'open(os.environ["SHIM_TEST_LOG"], "w").write(json.dumps(sys.argv[1:]))\n'
                        'sys.exit(17)\n')
        real.chmod(0o755)
        self.env = dict(os.environ, GITHUB_WORKSPACE=str(self.root),
                        SHIM_TEST_LOG=str(self.log),
                        PATH=f'{SHIM.parent}:{self.bin}:' + os.environ['PATH'])

    def invoke(self, url, output=True):
        args = ['bash', str(SHIM), '-x16', '-s16', '--header', 'Accept: */*']
        if output:
            args += ['-d', str(self.output), '-o', 'susfs.tar.gz']
        args.append(url)
        return subprocess.run(args, env=self.env, text=True, capture_output=True)

    def test_api_archive_reuses_shared_commit_without_download(self):
        for query in (f'sha={SHA}', f'include_lfs_blobs=false&sha={SHA}',
                      f'sha={SHA}&include_lfs_blobs=false'):
            with self.subTest(query=query):
                result = self.invoke(API + '?' + query)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual((self.output / 'susfs.tar.gz').read_bytes(), self.content)
                self.assertFalse(self.log.exists())

    def test_legacy_archive_still_reuses_shared_commit(self):
        result = self.invoke(f'https://gitlab.com/simonpunk/susfs4ksu/-/archive/{SHA}/archive.tar.gz')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.output / 'susfs.tar.gz').read_bytes(), self.content)

    def test_missing_shared_archive_fails_without_redownloading(self):
        result = self.invoke(API + '?sha=' + '1' * 40)
        self.assertEqual(result.returncode, 1)
        self.assertIn('Shared SUSFS archive is missing', result.stderr)
        self.assertFalse(self.log.exists())

    def test_api_rejects_unresolved_or_missing_commit(self):
        for query in ('sha=gki-android15-6.6', 'sha=../../other', 'include_lfs_blobs=false'):
            with self.subTest(query=query):
                result = self.invoke(API + '?' + query)
                self.assertEqual(result.returncode, 2)
                self.assertIn('requires a resolved commit SHA', result.stderr)
                self.assertFalse(self.log.exists())

    def test_missing_output_fails_without_downloading(self):
        result = self.invoke(API + '?sha=' + SHA, output=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn('output filename', result.stderr)
        self.assertFalse(self.log.exists())

    def test_unrelated_download_preserves_arguments_and_exit_status(self):
        url = 'https://example.org/another-source.tar.gz'
        result = self.invoke(url)
        self.assertEqual(result.returncode, 17)
        self.assertEqual(json.loads(self.log.read_text()), [
            '-x16', '-s16', '--header', 'Accept: */*',
            '-d', str(self.output), '-o', 'susfs.tar.gz', url,
        ])


if __name__ == '__main__':
    unittest.main()
