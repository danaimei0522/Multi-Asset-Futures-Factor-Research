"""Publishing boundary tests. Do not participate in backtest decisions."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile

spec = importlib.util.spec_from_file_location('release', Path(__file__).resolve().parents[1]/'scripts/release.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.listed = ['README.md', 'release_allowlist.txt', 'release_manifest.json']
        (self.root/'README.md').write_text('Research only, no verified performance.\n')
        self.write_list()
        release.refresh_manifest(self.root)

    def write_list(self):
        (self.root/'release_allowlist.txt').write_text('\n'.join(sorted(self.listed))+'\n')

    def test_manifest_and_deterministic_export(self):
        a=self.root/'a.zip'; b=self.root/'b.zip'
        release.export(self.root,a); release.export(self.root,b)
        self.assertEqual(a.read_bytes(),b.read_bytes())
        with zipfile.ZipFile(a) as z: self.assertEqual(z.namelist(),self.listed)

    def test_hash_change_rejected(self):
        (self.root/'README.md').write_text('changed')
        with self.assertRaisesRegex(ValueError,'mismatch'): release.verify(self.root)

    def test_unlisted_private_material_excluded(self):
        (self.root/'.env').write_text('not public')
        (self.root/'outputs').mkdir(); (self.root/'outputs/result.json').write_text('{}')
        a=self.root/'a.zip'; release.export(self.root,a)
        with zipfile.ZipFile(a) as z: self.assertEqual(z.namelist(),self.listed)

    def test_excluded_file_cannot_be_added_to_allowlist(self):
        (self.root/'.env').write_text('not public'); self.listed.append('.env'); self.write_list()
        with self.assertRaisesRegex(ValueError,'Excluded'): release.refresh_manifest(self.root)

    def test_missing_file_rejected(self):
        (self.root/'README.md').unlink()
        with self.assertRaisesRegex(ValueError,'Missing'): release.verify(self.root)

    def test_symlink_rejected(self):
        (self.root/'README.md').unlink(); (self.root/'target').write_text('test')
        (self.root/'README.md').symlink_to(self.root/'target')
        with self.assertRaisesRegex(ValueError,'Symlink'): release.verify(self.root)

    def test_sensitive_pattern_rejected_without_echoing_content(self):
        token='gh'+'p_'+'A'*36
        (self.root/'README.md').write_text(token)
        with self.assertRaises(ValueError) as caught: release.refresh_manifest(self.root)
        self.assertNotIn(token,str(caught.exception))

    def test_traversal_rejected(self):
        self.listed.append('../outside'); self.write_list()
        with self.assertRaisesRegex(ValueError,'escaping'): release.refresh_manifest(self.root)

    def test_manifest_set_mismatch_rejected(self):
        (self.root/'LICENSE').write_text('Rights reserved')
        self.listed.append('LICENSE'); self.write_list()
        with self.assertRaisesRegex(ValueError,'mismatch'): release.verify(self.root)

    def test_export_cannot_overwrite_source(self):
        with self.assertRaisesRegex(ValueError,'overwrite'): release.export(self.root,self.root/'README.md')
