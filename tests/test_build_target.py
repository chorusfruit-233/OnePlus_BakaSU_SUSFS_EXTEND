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
    def test_repository_targets_are_explicit(self):
        self.assertEqual(
            sorted(str(p.relative_to(ROOT)) for p in (ROOT / "configs").rglob("*.json")),
            sorted(target.config_path(t) for t in target.TARGETS),
        )
        self.assertEqual(
            sorted(str(p.relative_to(ROOT)) for p in (ROOT / "manifests").rglob("*.xml")),
            sorted(target.manifest_path(t) for t in target.TARGETS),
        )

    def test_cli_generates_each_maintained_build(self):
        for name, os_version in [("oos16", "OOS16"), ("cos17", "COS17")]:
            with self.subTest(target=name):
                result = subprocess.run([sys.executable, SPEC.origin, "--root", str(ROOT),
                                         "--target", name], check=True, capture_output=True, text=True)
                matrix = json.loads(result.stdout)
                self.assertEqual(len(matrix), 1)
                self.assertEqual(target.validate(matrix[0], name), matrix[0])
                self.assertEqual(matrix[0]["os_version"], os_version)
                self.assertEqual(matrix[0]["uname"], "OP-BAKASU")
        # Keep stable OOS16 as the CLI default.
        result = subprocess.run([sys.executable, SPEC.origin, "--root", str(ROOT)],
                                check=True, capture_output=True, text=True)
        self.assertEqual(json.loads(result.stdout)[0]["os_version"], "OOS16")

    def test_changed_targets_are_rejected(self):
        for name, expected in target.TARGETS.items():
            config = json.loads((ROOT / target.config_path(name)).read_text())
            for key in expected:
                with self.subTest(target=name, key=key), self.assertRaises(ValueError):
                    target.validate(dict(config, **{key: "other"}), name)
        with self.assertRaises(ValueError):
            target.validate([])

    def test_action_validation_rejects_wrong_kernel_or_os(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps(dict(target.TARGETS["cos17"], manifest="wrong.xml")))
            result = subprocess.run([sys.executable, SPEC.origin, "--config", str(path)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn("Only OP13 OOS16 or COS17", result.stderr)


if __name__ == "__main__":
    unittest.main()
