"""Session destinations survive restart without persisting credential values."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import json
from pathlib import Path
import os
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from features.rclone import desktop_catalog, session, configuration
from features.rclone.desktop_credentials import DesktopCredentialLoad
from features.rclone.desktop_service import service
from features.rclone.credential_loading import CredentialContext


class DesktopCredentialCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.context = self.root / 'Account.session'
        self.package = self.root / 'Account.zip'
        self.package.touch()
        self.enterContext(patch.object(configuration, 'get_rclone_config_dir', return_value=self.root))
        self.addCleanup(session.forget, self.context)

    def test_restart_remembers_names_and_package_but_requires_unlock(self):
        values = {'Books': {'type': 'drive', 'token': 'synthetic-secret-token'},
                  'Legacy-Books': {'type': 'crypt', 'password': 'synthetic-secret-password'}}
        with patch.object(session, 'read_package', return_value=values):
            service.credentials.load(DesktopCredentialLoad(self.package, self.context), 'zip-password')
        record = desktop_catalog.record_path(self.context)
        content = record.read_text()
        self.assertEqual(set(json.loads(content)), {'schema', 'package', 'remotes'})
        self.assertNotIn('synthetic-secret', content)
        self.assertNotIn('zip-password', content)
        self.assertNotIn('token', content)
        self.assertFalse(self.context.exists())
        service.credentials.lock(self.context)
        self.assertTrue(record.exists())
        from features.rclone.ui_contributions import _get_remote_sources
        with patch('models.folder_discovery.get_local_folders', return_value=[]), \
                patch('features.rclone.localcrypt.mapping.connections', return_value=[]), \
                patch('features.rclone.localcrypt.connections.connections', return_value=[]):
            sources = _get_remote_sources()
            self.assertEqual([source.context for source in sources], [self.context])
            self.assertIn('(locked)', sources[0].name)
        script = '''
from pathlib import Path
import sys
from unittest.mock import patch
from features.rclone import desktop_catalog, session, configuration
from features.rclone.ui.workspace_unlock import unlock_target
from features.rclone.ui.remote_browser import RemoteLocation
context, package = map(Path, sys.argv[1:])
with patch.object(configuration, 'get_rclone_config_dir', return_value=context.parent):
    assert desktop_catalog.contexts() == [context]
    assert session.credentials(context) is None
    assert session.package_path(context) == package
    assert configuration.get_rclone_remote_names(context) == ['Books', 'Legacy-Books']
    assert unlock_target(RemoteLocation(context, 'Books')) == (context, package)
'''
        result = subprocess.run([sys.executable, '-c', script, str(self.context), str(self.package)],
                                env=dict(os.environ), capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        service.credentials.forget(self.context)
        self.assertFalse(record.exists())
        self.assertEqual(desktop_catalog.contexts(), [])
        self.assertTrue(self.package.exists())

    def test_cancelled_and_failed_loads_do_not_write_metadata(self):
        request = DesktopCredentialLoad(self.package, self.context)
        with patch.object(session, 'read_package', side_effect=ValueError('wrong password')):
            with self.assertRaises(ValueError):
                service.credentials.load(request, 'wrong')
        with patch.object(session, 'read_package', return_value={'Books': {'type': 'drive'}}):
            from commonUtils.runtime.operations import OperationCancelled
            with self.assertRaises(OperationCancelled):
                service.credentials.load(request, 'fixture', CredentialContext(cancelled=lambda: True))
        self.assertFalse(desktop_catalog.record_path(self.context).exists())
        self.assertIsNone(session.credentials(self.context))

    def test_invalid_catalogue_is_ignored_without_loading_or_guessing_credentials(self):
        path = desktop_catalog.record_path(self.context)
        for content in ('not json', '[]', json.dumps({'schema': 1, 'package': 'relative.zip', 'remotes': ['Books']}),
                        json.dumps({'schema': 1, 'package': str(self.package), 'remotes': ['x' * 257]}), 'x' * 65537):
            with self.subTest(content=content[:30]):
                path.write_text(content)
                self.assertIsNone(desktop_catalog.read(self.context))
                self.assertEqual(desktop_catalog.contexts(), [])

    def test_saved_config_suppresses_duplicate_locked_placeholder(self):
        from features.rclone.ui_contributions import _get_remote_sources
        desktop_catalog.remember(self.context, self.package, ['Books'])
        saved = self.context.with_suffix('.conf')
        saved.write_text('[Books]\ntype=local\n')
        with patch('models.folder_discovery.get_local_folders', return_value=[]), \
                patch('features.rclone.localcrypt.mapping.connections', return_value=[]), \
                patch('features.rclone.localcrypt.connections.connections', return_value=[]):
            sources = _get_remote_sources()
            self.assertEqual([source.context for source in sources], [saved])
