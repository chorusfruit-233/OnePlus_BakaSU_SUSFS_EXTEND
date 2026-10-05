import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("builtin_hybridmount", Path(__file__).resolve().parents[1] / "scripts/builtin_hybridmount.py")
nm = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(nm)


class HybridMountTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "kernel"
        (self.source / "fs").mkdir(parents=True)
        (self.source / "fs/Kconfig").write_text('menu "File systems"\nendmenu\n')
        (self.source / "fs/Makefile").write_text('obj-y += open.o\n')
        self.defconfig = self.source / "arch/arm64/configs/gki_defconfig"
        self.defconfig.parent.mkdir(parents=True)
        self.defconfig.write_text('CONFIG_HYBRIDMOUNT=m\n# CONFIG_KEYS is not set\nCONFIG_USB=y\n')
        self.xattr = self.source / "include/linux/xattr.h"
        self.xattr.parent.mkdir(parents=True)
        self.xattr.write_text('int (*get)(const struct xattr_handler *, struct dentry *, struct inode *, const char *, void *, size_t);\nssize_t __vfs_getxattr(struct dentry *, struct inode *, const char *, void *, size_t);\n')
        self.archive = self.root / "source.tar.gz"
        with tarfile.open(self.archive, "w:gz") as tar:
            for name in nm.FILES + ("LICENSE",):
                data = (name + "\n").encode()
                if name == "hybridmount.h":
                    data = (nm.FLAGS_CONDITION + '\n#define FLAGS_ARG , int flags\n#endif\n').encode()
                if name == "hybridmount.c":
                    data = b'xattr_full_name(handler, name), buffer, size FLAGS_VAL)\n'
                member = tarfile.TarInfo('meta-hybrid_mount-pinned/module/vfs/src/' + name)
                member.size = len(data)
                tar.addfile(member, io.BytesIO(data))
        self.lock = dict(repository="https://github.com/Hybrid-Mount/meta-hybrid_mount", revision="pinned", sha256=hashlib.sha256(self.archive.read_bytes()).hexdigest())

    def install(self):
        nm.install(self.source, self.archive, self.lock)

    def test_install_idempotent_and_replaces_module_configuration(self):
        self.install()
        self.install()
        self.assertEqual(self.defconfig.read_text(), 'CONFIG_USB=y\nCONFIG_KEYS=y\nCONFIG_HYBRIDMOUNT=y\n')
        self.assertEqual((self.source / "fs/Makefile").read_text().count(nm.MAKEFILE), 1)
        self.assertEqual((self.source / "fs/Kconfig").read_text().count(nm.KCONFIG), 1)
        self.assertTrue((self.source / "hybridmount-support/LICENSE").is_file())

    def test_invalid_archive_does_not_modify_kernel(self):
        self.archive.write_bytes(b"corrupt")
        with self.assertRaisesRegex(ValueError, "SHA256"):
            self.install()
        self.assertFalse((self.source / "fs/hybridmount").exists())

    def test_conflicting_existing_source_is_preserved(self):
        self.install()
        path = self.source / "fs/hybridmount/hybridmount.c"
        path.write_text("other implementation")
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            self.install()
        self.assertEqual(path.read_text(), "other implementation")

    def test_symlink_source_is_refused(self):
        (self.source / "fs/hybridmount").symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            self.install()

    def test_final_config_cannot_fall_back_to_module(self):
        self.install()
        for config in ('CONFIG_KEYS=y\nCONFIG_HYBRIDMOUNT=m\n', 'CONFIG_KEYS=n\nCONFIG_HYBRIDMOUNT=y\n'):
            self.defconfig.write_text(config)
            with self.assertRaisesRegex(ValueError, "must remain built-in"):
                nm.verify(self.source, self.defconfig)

    def test_source_change_fails_verification(self):
        self.install()
        (self.source / "fs/hybridmount/hybridmount.h").write_text("modified")
        with self.assertRaisesRegex(ValueError, "source changed"):
            nm.verify(self.source, self.defconfig)

    def test_linkage_audit_with_lto_symbol_suffix(self):
        self.install()
        symbols = self.root / "System.map"
        image = self.root / "Image"
        symbols.write_text('ffff t hybridmount_init.llvm.123\nffff d hm_key_type\n')
        image.write_bytes(b'kernel\x00hybridmount: Loaded successfully\n\x00')
        self.assertIn("linkage verified", nm.verify(self.source, self.defconfig, symbols, image))
        symbols.write_text('ffff t unrelated\n')
        with self.assertRaisesRegex(ValueError, "not linked"):
            nm.verify(self.source, self.defconfig, symbols, image)
        symbols.write_text('ffff t hybridmount_init\nffff d hm_key_type\n')
        image.write_bytes(b"stale kernel")
        with self.assertRaisesRegex(ValueError, "absent"):
            nm.verify(self.source, self.defconfig, symbols, image)

    def test_vendor_xattr_flags_detected_from_headers(self):
        self.xattr.write_text(self.xattr.read_text().replace('size_t)', 'size_t, int flags)'))
        self.install()
        header = (self.source / "fs/hybridmount/hybridmount.h").read_text()
        self.assertIn('#if 1', header)
        self.assertIn('#define HM_VFS_FLAGS_VAL , flags', header)
        manifest = json.loads((self.source / "hybridmount-support/manifest.json").read_text())
        self.assertTrue(manifest['xattr_api']['get'])

    def test_unknown_xattr_api_fails_before_install(self):
        self.xattr.write_text('unsupported API')
        with self.assertRaisesRegex(ValueError, "Cannot determine"):
            self.install()
        self.assertFalse((self.source / "fs/hybridmount").exists())

    def test_nomount_coexistence_is_rejected_before_writing(self):
        self.defconfig.write_text('CONFIG_NOMOUNT=y\nCONFIG_USB=y\n')
        with self.assertRaisesRegex(ValueError, 'must not coexist'):
            self.install()
        self.assertFalse((self.source / 'fs/hybridmount').exists())
        self.defconfig.write_text('CONFIG_USB=y\n')
        (self.source / 'fs/nomount').mkdir()
        with self.assertRaisesRegex(ValueError, 'must not coexist'):
            self.install()

    def test_late_nomount_enablement_is_rejected(self):
        self.install()
        with self.defconfig.open('a') as out:
            out.write('CONFIG_NOMOUNT=m\n')
        with self.assertRaisesRegex(ValueError, 'must not coexist'):
            nm.verify(self.source, self.defconfig)

    def test_generated_makefile_changes_fail_verification(self):
        self.install()
        (self.source / 'fs/hybridmount/Makefile').write_text('obj-m += hybridmount.o\n')
        with self.assertRaisesRegex(ValueError, 'source changed'):
            nm.verify(self.source, self.defconfig)


if __name__ == "__main__":
    unittest.main()
