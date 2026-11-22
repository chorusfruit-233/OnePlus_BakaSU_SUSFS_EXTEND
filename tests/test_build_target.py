import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("build_target", ROOT / "scripts/build_target.py")
target = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(target)


class BuildTargetTests(unittest.TestCase):
    def test_repository_has_only_the_coloros17_target(self):
        for directory, pattern, maintained in (("configs", "*.json", target.TARGET_CONFIG),
                                              ("manifests", "*.xml", target.TARGET_MANIFEST)):
            self.assertEqual([p.relative_to(ROOT).as_posix() for p in (ROOT / directory).rglob(pattern)], [maintained])

    def test_default_explicit_and_mirror_matrices_are_identical(self):
        config = json.loads((ROOT / target.TARGET_CONFIG).read_text())
        self.assertEqual(config["os_version"], "COS17")
        self.assertEqual(config["uname"], "OP-BAKASU")
        for args in ([], ["--target", "cos17"], ["--all"]):
            result = subprocess.run([sys.executable, SPEC.origin, "--root", str(ROOT), *args],
                                    check=True, capture_output=True, text=True)
            self.assertEqual(json.loads(result.stdout), [config])

    def test_changed_targets_are_rejected(self):
        for key in target.TARGET:
            with self.subTest(key=key), self.assertRaises(ValueError):
                target.validate(dict(target.TARGET, **{key: "wrong"}))

    def test_cli_rejects_retired_system(self):
        result = subprocess.run([sys.executable, SPEC.origin, "--target", "oos16"], capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(result.stdout)

    def test_action_validation_rejects_wrong_kernel_or_os(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps(dict(target.TARGET, manifest="wrong.xml")))
            result = subprocess.run([sys.executable, SPEC.origin, "--config", str(path)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn("Only OP13 COS17", result.stderr)


if __name__ == "__main__":
    unittest.main()
