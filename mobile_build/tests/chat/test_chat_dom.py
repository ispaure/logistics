"""Optional browser evidence for transcript node reuse and exact final markup."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import json
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
from unittest import TestCase, skipUnless

from features.lm.domain import message
from features.lm.mobile.presentation import transcript_document, transcript_entries, transcript_update
from mobile.palette import css_variables, eink_script, set_eink_enabled

NODE = os.environ.get('LOGISTICS_NODE') or shutil.which('node')


@skipUnless(NODE, 'Set LOGISTICS_NODE and provide Playwright for browser verification')
class TranscriptDOMTests(TestCase):
    def test_stable_blocks_keep_selection_and_final_markdown_is_exact(self):
        texts = ['Stable **paragraph**.\n\nPartial',
                 'Stable **paragraph**.\n\nPartial reply\n\n```python\nprint(1)',
                 'Stable **paragraph**.\n\nPartial reply\n\n```python\nprint(1)\n```']
        entries = [transcript_entries([message('assistant', text,
                   status='complete' if index == 2 else 'streaming')])
                   for index, text in enumerate(texts)]
        try:
            set_eink_enabled(True)
            contrast_on = eink_script()
        finally:
            set_eink_enabled(False)
        fixture = dict(html=transcript_document(theme_css=css_variables()), expected=entries[-1][0]['html'],
                       scripts=[transcript_update('synthetic', value, 16, configured=True) for value in entries],
                       contrast_on=contrast_on, contrast_off=eink_script())
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'fixture.json'
            path.write_text(json.dumps(fixture))
            result = subprocess.run([NODE, str(Path(__file__).with_name('transcript_dom.cjs')), str(path)],
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertLessEqual(json.loads(result.stdout)['removed_blocks'], 3)
