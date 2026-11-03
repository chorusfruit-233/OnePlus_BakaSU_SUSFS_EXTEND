import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import validate_release_assets as assets


class ReleaseAssetsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.matrix = self.root / "matrix.json"
        self.matrix.write_text(json.dumps([{"model": "OP13", "os_version": "OOS16"}]))
        self.archive = self.root / "AK3_OP13_OOS16_android15-6.6.118_BakaSU_USBWiFi.zip"

    def package(self, path=None):
        with zipfile.ZipFile(path or self.archive, "w") as output:
            output.writestr("Image", b"kernel test fixture")
            output.writestr("anykernel.sh", "#!/sbin/sh\n")

    def test_complete_extracted_assets_pass(self):
        self.package()
        self.assertEqual(assets.validate(self.root, 1), [self.archive])

    def test_matrix_left_inside_artifact_zip_is_rejected(self):
        self.package()
        self.matrix.unlink()
        with self.assertRaises(OSError):
            assets.validate(self.root, 1)

    def test_nested_artifact_archive_is_not_a_flashable_zip(self):
        self.package()
        raw = self.archive.read_bytes()
        with zipfile.ZipFile(self.archive, "w") as output:
            output.writestr(self.archive.name, raw)
        with self.assertRaisesRegex(ValueError, "missing Image"):
            assets.validate(self.root, 1)

    def test_missing_or_extra_kernel_asset_is_rejected(self):
        with self.assertRaises(ValueError):
            assets.validate(self.root, 1)
        self.package()
        self.package(self.root / "AK3_OP13_OOS16_other_USBWiFi.zip")
        with self.assertRaises(ValueError):
            assets.validate(self.root, 1)

    def test_wrong_target_is_rejected(self):
        self.package(self.root / "AK3_OP12_OOS16_kernel_USBWiFi.zip")
        with self.assertRaises(ValueError):
            assets.validate(self.root, 1)

    def test_invalid_zip_is_rejected(self):
        self.archive.write_bytes(b"invalid archive")
        with self.assertRaises(zipfile.BadZipFile):
            assets.validate(self.root, 1)

    def test_cos17_matrix_rejects_an_oos16_image_package(self):
        self.matrix.write_text(json.dumps([{"model": "OP13", "os_version": "COS17"}]))
        self.package()
        with self.assertRaisesRegex(ValueError, "Missing or duplicated release asset"):
            assets.validate(self.root, 1)
        cos17 = self.archive.with_name(self.archive.name.replace("_OOS16_", "_COS17_"))
        self.archive.rename(cos17)
        self.assertEqual(assets.validate(self.root, 1), [cos17])
