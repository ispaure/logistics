"""The mobile allowlist must carry the new-stroke sampler and editor closure."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

from commonUtils.testing.stages import TestStage
from logistics_build.build_retention import scratch
from mobile_build.tools import stage

TEST_STAGE = TestStage.REGRESSION
REPO = Path(__file__).resolve().parents[3]


class NotebookSamplingPackageTests(unittest.TestCase):
    def declared(self):
        return json.loads((REPO / 'Python/features/notebooks/mobile_sources.json').read_text())['modules']

    def test_sampler_is_explicitly_declared_for_mobile_staging(self):
        self.assertIn('sampling.py', self.declared())

    def test_existing_native_viewport_and_palm_dependencies_are_declared(self):
        self.assertTrue({'assets/palm.js', 'mobile/viewport.py', 'mobile/ios_input.py'}.issubset(self.declared()))

    def test_staged_payload_imports_and_compacts_without_checkout_fallback(self):
        # Fail at the precise packaging boundary before creating staging work.
        self.assertIn('sampling.py', self.declared())
        with scratch(REPO) as workspace:
            payload = workspace / 'payload'
            stage(REPO, payload, allow_dirty=True)
            script = r'''
from pathlib import Path
import json
import sys
from unittest.mock import patch
payload = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(payload))
home = Path('home').resolve()
home.mkdir()
patch.object(Path, 'home', return_value=home).start()
from features.notebooks import ink, sampling, editor, notebook
from features.notebooks.mobile.surface import mobile_editor_html
from features.notebooks.mobile import viewport, ios_input
for module in (ink, sampling, editor, notebook, viewport, ios_input):
    assert Path(module.__file__).resolve().is_relative_to(payload), module.__file__
book = notebook.Notebook.new('Synthetic staged sampler')
engine = editor.Editor(book)
samples = [[20 + i * .05, 80., .6] for i in range(1000)]
engine.apply(dict(op='stroke', points=samples, tool=17, color=6, width=2))
assert len(book.page(0).strokes[0].points) == 2
reopened = notebook.Notebook.read(book.to_bytes())
assert len(reopened.page(0).strokes[0].points) == 2
html = mobile_editor_html(engine.state(), 'logistics-notebook://staged-sampling/')
assert 'penTouchBlocked' in html and 'warmSelectedGraphite' in html
assert viewport.tablet_viewport(None) is None
assert not any(name.startswith(('PySide6', 'toga', 'java', 'rubicon')) for name in sys.modules)
print(json.dumps(dict(success=True, retained_points=2, source_points=1000,
    sampler_path=str(sampling.__file__), editor_html_bytes=len(html),
    scope='isolated staged Python/assets; no native SDK or hardware')))
'''
            result = subprocess.run([sys.executable, '-I', '-c', script, str(payload)], cwd=workspace,
                                    env=dict(os.environ, PYTHONPATH=''), capture_output=True, text=True, timeout=45)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads(result.stdout.strip().splitlines()[-1])
            self.assertTrue(report['success'])
            self.assertEqual(report['retained_points'], 2)
        self.assertFalse(workspace.exists(), 'The owned staging workspace was not removed')
        report['workspace_removed'] = True
        print(json.dumps(report, sort_keys=True))
