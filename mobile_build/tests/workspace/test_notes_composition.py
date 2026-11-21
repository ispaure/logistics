"""Notes timing diagnostics follow the opt-in marker for each host and sample."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import json
from unittest import TestCase
from unittest.mock import PropertyMock, patch

from commonUtils.testing.stages import TestStage
from mobile.composition.presentation import notes_host
from mobile_build.tests.support.app import create_document_app

TEST_STAGE = TestStage.REGRESSION


class NotesTimingTests(TestCase):
    def setUp(self):
        self.app = create_document_app(self)
        cache = self.app.storage_root / 'notes-timing'
        cache.mkdir()
        self.enterContext(patch.object(
            type(self.app.paths), 'cache', new_callable=PropertyMock, return_value=cache,
        ))
        self.marker = cache / 'notes-open-timing.enabled'
        self.report = cache / 'notes-open-timing.json'

    def test_timing_must_be_enabled_at_host_creation_and_at_each_write(self):
        disabled = notes_host(self.app)
        self.marker.touch()
        self.assertIsNone(disabled.open_timing)

        enabled = notes_host(self.app)
        sample = {'epoch': 1, 'stages_ms': {'prepared': 12}}
        enabled.open_timing(sample)
        self.assertEqual(json.loads(self.report.read_text(encoding='utf-8')), sample)

        self.marker.unlink()
        enabled.open_timing({'epoch': 2, 'stages_ms': {'prepared': 15}})
        self.assertEqual(json.loads(self.report.read_text(encoding='utf-8')), sample)

    def test_timing_write_failure_is_ignored(self):
        self.marker.touch()
        enabled = notes_host(self.app)
        sample = {'epoch': 1, 'stages_ms': {'prepared': 12}}
        with patch('commonUtils.persistence.atomic_write_json', side_effect=OSError) as write:
            enabled.open_timing(sample)
        write.assert_called_once_with(self.report, sample, max_bytes=4096)
