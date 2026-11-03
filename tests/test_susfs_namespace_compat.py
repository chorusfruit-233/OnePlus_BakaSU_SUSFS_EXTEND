from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import susfs_namespace_compat as compat

SOURCE = '#include <linux/mnt_idmapping.h>\n#include "internal.h"\n\nint keep_me;\n'
REJECT = """--- fs/namespace.c
+++ fs/namespace.c
@@ -39,6 +39,17 @@
 #include <linux/mnt_idmapping.h>
+#ifdef CONFIG_KSU_SUSFS
+#include <linux/susfs_def.h>
+#endif // #ifdef CONFIG_KSU_SUSFS
 #include "internal.h"
+#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT
+extern bool susfs_is_current_ksu_domain(void);
+extern struct static_key_true susfs_is_sdcard_android_data_not_decrypted;
+
+#define CL_COPY_MNT_NS BIT(25) /* used by copy_mnt_ns() */
+#endif // #ifdef CONFIG_KSU_SUSFS_SUS_MOUNT
"""


class NamespaceCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "fs").mkdir()
        self.target = self.root / "fs/namespace.c"
        self.reject = self.root / "fs/namespace.c.rej"
        self.target.write_text(SOURCE)
        self.reject.write_text(REJECT)

    def test_recovers_known_context_and_keeps_original_code(self):
        self.assertTrue(compat.recover(self.root))
        text = self.target.read_text()
        self.assertEqual(text.count("#include <linux/susfs_def.h>"), 1)
        self.assertEqual(text.count("#define CL_COPY_MNT_NS"), 1)
        self.assertTrue(text.endswith("int keep_me;\n"))
        self.assertFalse(self.reject.exists())
        before = self.target.read_bytes()
        self.assertFalse(compat.recover(self.root))
        self.assertEqual(self.target.read_bytes(), before)

    def test_already_applied_headers_are_not_duplicated(self):
        compat.recover(self.root)
        before = self.target.read_bytes()
        self.reject.write_text(REJECT)
        self.assertTrue(compat.recover(self.root))
        self.assertEqual(self.target.read_bytes(), before)

    def test_unknown_functional_change_keeps_reject(self):
        for change in ("+return 0;", "+++reference_count;", "-existing_check();"):
            with self.subTest(change=change):
                self.reject.write_text(REJECT + change + "\n")
                self.assertFalse(compat.recover(self.root))
                self.assertEqual(self.target.read_text(), SOURCE)
                self.assertTrue(self.reject.exists())

    def test_another_hunk_keeps_entire_reject(self):
        self.reject.write_text(REJECT + "@@ -500,1 +511,2 @@\n+unhandled_change();\n")
        self.assertFalse(compat.recover(self.root))
        self.assertEqual(self.target.read_text(), SOURCE)
        self.assertTrue(self.reject.exists())

    def test_missing_anchor_does_not_partially_modify_source(self):
        self.target.write_text('#include <linux/mnt_idmapping.h>\nint keep_me;\n')
        before = self.target.read_bytes()
        self.assertFalse(compat.recover(self.root))
        self.assertEqual(self.target.read_bytes(), before)
        self.assertTrue(self.reject.exists())
