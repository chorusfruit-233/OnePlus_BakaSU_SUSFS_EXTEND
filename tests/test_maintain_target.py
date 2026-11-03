import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import maintain_target as maintenance


def workflow_script(name):
    lines = (ROOT / '.github/workflows/opencode.yml').read_text().splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip() == '- name: ' + name)
    start = next(i for i in range(start, len(lines)) if lines[i] == '        run: |') + 1
    end = start
    while end < len(lines) and (not lines[end].strip() or lines[end].startswith('          ')):
        end += 1
    return textwrap.dedent('\n'.join(lines[start:end]))


class MaintainTargetTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        targets = tuple(path for target in maintenance.TARGETS
                        for path in (maintenance.target_config_path(target),
                                     maintenance.target_manifest_path(target)))
        for relative in (*targets, '.github/opencode/guidelines.txt',
                         'scripts/maintain_target.py', 'scripts/build_target.py'):
            destination = self.root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, destination)
        self.config_path = self.root / maintenance.TARGET_CONFIG
        self.manifest_path = self.root / maintenance.TARGET_MANIFEST
        self.config = json.loads(self.config_path.read_text())
        self.manifest = self.manifest_path.read_text()
        for relative in ('configs/oos16/OP-N6X.json', 'configs/a15/OP9.json',
                         'manifests/oos16/oneplus_other.xml'):
            destination = self.root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text('upstream addition\n')

    def snapshot(self):
        return {str(path.relative_to(self.root)): path.read_bytes()
                for path in self.root.rglob('*') if path.is_file()}

    def test_prunes_restored_targets_and_reapplies_brand_idempotently(self):
        self.config_path.write_text(json.dumps(dict(self.config, uname='OP-RESUKISU')))
        maintenance.enforce(self.root)
        self.assertEqual(json.loads(self.config_path.read_text())['uname'], 'OP-BAKASU')
        for directory, selector in (('configs', maintenance.target_config_path),
                                    ('manifests', maintenance.target_manifest_path)):
            self.assertEqual(sorted(str(p.relative_to(self.root))
                                    for p in (self.root / directory).rglob('*') if p.is_file()),
                             sorted(selector(target) for target in maintenance.TARGETS))
        self.assertTrue((self.root / '.github/opencode/guidelines.txt').is_file())
        before = self.snapshot()
        maintenance.enforce(self.root)
        self.assertEqual(self.snapshot(), before)

    def test_missing_or_invalid_target_aborts_before_any_changes(self):
        for scenario in ('missing-config', 'missing-manifest', 'other-model', 'invalid-manifest'):
            with self.subTest(scenario=scenario):
                self.config_path.write_text(json.dumps(dict(self.config, uname='OP-RESUKISU')))
                self.manifest_path.write_text(self.manifest)
                if scenario == 'missing-config':
                    self.config_path.unlink()
                elif scenario == 'missing-manifest':
                    self.manifest_path.unlink()
                elif scenario == 'other-model':
                    self.config_path.write_text(json.dumps(dict(self.config, model='OP12')))
                else:
                    self.manifest_path.write_text('<manifest/>')
                before = self.snapshot()
                with self.assertRaises((OSError, ValueError)):
                    maintenance.enforce(self.root)
                self.assertEqual(self.snapshot(), before)

    def test_check_rejects_extra_devices_or_wrong_brand_without_writing(self):
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'Unmaintained targets'):
            maintenance.enforce(self.root, check=True)
        self.assertEqual(self.snapshot(), before)
        maintenance.enforce(self.root)
        maintenance.enforce(self.root, check=True)
        self.config_path.write_text(json.dumps(dict(self.config, uname='OP-RESUKISU')))
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'OP-BAKASU'):
            maintenance.enforce(self.root, check=True)
        self.assertEqual(self.snapshot(), before)

    def test_guidelines_adapter_preserves_protected_source(self):
        original = (self.root / '.github/opencode/guidelines.txt').read_bytes()
        result = subprocess.run([sys.executable, str(self.root / 'scripts/maintain_target.py'),
                                 '--root', str(self.root), '--guidelines'],
                                check=True, capture_output=True, text=True)
        self.assertIn('https://github.com/Baka-SU/BakaSU', result.stdout)
        self.assertIn('OP-BAKASU', result.stdout)
        self.assertIn('Hybrid Mount VFS', result.stdout)
        self.assertIn('configs/{oos16,cos17}/OP13.json', result.stdout)
        self.assertIn('experimental COS17', result.stdout)
        self.assertNotIn('ReSukiSU', result.stdout)
        self.assertNotIn('OP-RESUKISU', result.stdout)
        self.assertEqual((self.root / '.github/opencode/guidelines.txt').read_bytes(), original)

    def test_invalid_cos17_does_not_modify_oos16_or_prune_other_files(self):
        self.config_path.write_text(json.dumps(dict(self.config, uname='OP-RESUKISU')))
        path = self.root / maintenance.target_config_path('cos17')
        path.unlink()
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'Missing maintained target'):
            maintenance.enforce(self.root)
        self.assertEqual(self.snapshot(), before)

    def test_wrong_cos17_label_is_rejected_even_when_oos16_is_valid(self):
        path = self.root / maintenance.target_config_path('cos17')
        config = json.loads(path.read_text())
        path.write_text(json.dumps(dict(config, os_version='OOS16')))
        before = self.snapshot()
        with self.assertRaises(ValueError):
            maintenance.enforce(self.root)
        self.assertEqual(self.snapshot(), before)

    def test_real_prompt_block_preserves_user_text_and_adapts_only_guidelines(self):
        prompt = 'Keep OP-RESUKISU and https://github.com/ReSukiSU/ReSukiSU in this quoted example.\n$(touch injected)'
        output = self.root / 'outputs.txt'
        environment = dict(os.environ, EVENT_NAME='workflow_dispatch', DISPATCH_PROMPT=prompt,
                           GITHUB_WORKSPACE=str(self.root), GITHUB_OUTPUT=str(output))
        subprocess.run(['bash', '-c', workflow_script('Prepare Prompt')], cwd=self.root,
                       env=environment, check=True, capture_output=True, text=True)
        lines = output.read_text().splitlines(keepends=True)
        delimiter = lines[0].removeprefix('prompt<<').strip()
        end = next(i for i, line in enumerate(lines[1:], 1) if line.strip() == delimiter)
        assembled = ''.join(lines[1:end])
        prefix = prompt + '\n\n---\n'
        self.assertTrue(assembled.startswith(prefix))
        self.assertNotIn('ReSukiSU', assembled[len(prefix):])
        self.assertIn('OP-BAKASU', assembled[len(prefix):])
        self.assertFalse((self.root / 'injected').exists())

    def test_auto_pr_block_refuses_unmaintained_targets_before_skipping_agent(self):
        subprocess.run(['git', 'init', '--quiet'], cwd=self.root, check=True)
        output = self.root / 'outputs.txt'
        environment = dict(os.environ, GITHUB_WORKSPACE=str(self.root), GITHUB_OUTPUT=str(output))
        result = subprocess.run(['bash', '-c', workflow_script('Auto-PR on Clean Merge')],
                                cwd=self.root, env=environment, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Unmaintained targets remain', result.stderr)
        self.assertFalse(output.exists())
