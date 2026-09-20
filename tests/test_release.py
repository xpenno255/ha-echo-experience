"""Release metadata must fail closed before a tag or release is published."""
import json
from pathlib import Path
import tempfile
import unittest

from scripts.prepare_release import release_details


class ReleaseTest(unittest.TestCase):
    def prepare(self, version='0.4.1', notes='## 0.4.1 - Matching\n\n- Fix names.\n\n## 0.4.0 - Earlier\n- Older.\n'):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        manifest = root / 'custom_components/echo_experience/manifest.json'
        manifest.parent.mkdir(parents=True)
        manifest.write_text(json.dumps({'version': version}))
        (root / 'CHANGELOG.md').write_text(notes)
        return root

    def test_extracts_only_requested_version(self):
        self.assertEqual(release_details(self.prepare()), ('0.4.1', '- Fix names.\n'))

    def test_rejects_invalid_or_non_stable_version(self):
        for version in ['0.4', 'v0.4.1', '0.4.1-rc1', '01.4.1', '0.4.1\n', '../oops', 41]:
            with self.subTest(version=version), self.assertRaises(ValueError):
                release_details(self.prepare(version=version))

    def test_requires_unique_nonempty_exact_version_notes(self):
        for notes in ['## 0.4.10\n- Wrong version.\n', '## 0.4.1\n\n',
                      '## 0.4.1\n- First.\n## 0.4.1\n- Duplicate.\n']:
            with self.subTest(notes=notes), self.assertRaises(ValueError):
                release_details(self.prepare(notes=notes))
