import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('build_target', ROOT / 'scripts/build_target.py')
target = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(target)


class BuildTargetTests(unittest.TestCase):
    def test_repository_only_contains_maintained_config_and_manifest(self):
        self.assertEqual(sorted(str(p.relative_to(ROOT)) for p in (ROOT / 'configs').rglob('*') if p.is_file()),
                         [target.TARGET_CONFIG])
        self.assertEqual(sorted(str(p.relative_to(ROOT)) for p in (ROOT / 'manifests').rglob('*') if p.is_file()),
                         [target.TARGET_MANIFEST])

    def test_cli_generates_exactly_one_maintained_build(self):
        result = subprocess.run([sys.executable, SPEC.origin, '--root', str(ROOT)],
                                check=True, capture_output=True, text=True)
        matrix = json.loads(result.stdout)
        self.assertEqual(len(matrix), 1)
        self.assertEqual(target.validate(matrix[0]), matrix[0])
        self.assertEqual(matrix[0]['uname'], 'OP-BAKASU')

    def test_changed_target_is_rejected(self):
        config = json.loads((ROOT / target.TARGET_CONFIG).read_text())
        for key in target.TARGET:
            with self.subTest(key=key), self.assertRaises(ValueError):
                target.validate(dict(config, **{key: 'other'}))
        with self.assertRaises(ValueError):
            target.validate([])

    def test_action_config_validation_fails_before_building_other_target(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.json'
            path.write_text(json.dumps(dict(target.TARGET, manifest='oneplus_13_6.6.89_w.xml')))
            result = subprocess.run([sys.executable, SPEC.origin, '--config', str(path)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn('Only OP13 OOS16', result.stderr)
