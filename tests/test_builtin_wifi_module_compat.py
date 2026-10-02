import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location('wifi_module_compat', SCRIPTS / 'builtin_wifi_module_compat.py')
compat = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(compat)


class BuiltinModuleCompatTests(unittest.TestCase):
    def test_compiled_loader_only_skips_builtin_wireless_dependencies(self):
        # Compile the actual installed guard and exercise Android's EEXIST
        # convention; modular dependencies and unrelated modules must proceed.
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            path = source / 'kernel/module/main.c'
            path.parent.mkdir(parents=True)
            path.write_text(compat.ANCHOR + '\n\terr = 17;\n\treturn err;\n}\n')
            compat.install(source)
            patched = path.read_text()
            compat.install(source)
            self.assertEqual(path.read_text(), patched)
            harness = '''#include <stdbool.h>
#include <string.h>
#include <errno.h>
#define IS_BUILTIN(x) ((x) == 1)
struct module { const char *name; };
''' + patched + '''
int main(void) {
    const char *names[] = {"cfg80211", "rfkill", "qca_cld3_peach_v2", "rtl8xxxu", "cfg80211_other"};
    for (unsigned int i = 0; i < 5; i++) {
        struct module mod = {names[i]};
        int expected = ((i == 0 && CONFIG_CFG80211 == 1) ||
                        (i == 1 && CONFIG_RFKILL == 1)) ? -EEXIST : 17;
        if (add_unformed_module(&mod) != expected) return 1;
    }
    return 0;
}
'''
            c = source / 'loader.c'
            c.write_text(harness)
            for cfg in (0, 1, 2):
                for rfkill in (0, 1, 2):
                    exe = source / 'loader'
                    subprocess.run(['cc', '-Wall', '-Wextra', '-Werror',
                                    f'-DCONFIG_CFG80211={cfg}', f'-DCONFIG_RFKILL={rfkill}',
                                    str(c), '-o', str(exe)], check=True, capture_output=True)
                    subprocess.run([str(exe)], check=True)

    def test_changed_loader_is_rejected_without_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'kernel/module/main.c'
            path.parent.mkdir(parents=True)
            path.write_text('unexpected vendor module loader')
            with self.assertRaises(ValueError):
                compat.install(Path(directory))
            self.assertEqual(path.read_text(), 'unexpected vendor module loader')

    def test_other_targets_do_not_change_loader(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, str(SCRIPTS / 'builtin_wifi_module_compat.py'),
                                     '--source', directory, '--model', 'OP13T',
                                     '--os-version', 'OOS16', '--kernel', '6.6.118'],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(list(Path(directory).iterdir()))
