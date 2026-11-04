"""Synthetic crypt fixtures revoke credentials even when setup or close fails."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch
import unittest

from commonUtils.testing.stages import TestStage
from tests import local_crypt_fixture as fixture

TEST_STAGE = TestStage.REGRESSION


class CryptFixtureCleanupTests(unittest.TestCase):
    def test_setup_failure_forgets_already_loaded_credentials(self):
        with TemporaryDirectory() as directory:
            context = Path(directory).resolve() / 'Accounts.session'
            self.addCleanup(fixture.session.forget, context)

            def failed_launch(*args):
                self.assertIsNotNone(fixture.session.credentials(context))
                raise RuntimeError('Fixture launch failed')

            with patch.object(fixture, 'obscured_password', return_value='synthetic'), \
                    patch.object(fixture.session, 'launch', side_effect=failed_launch):
                with self.assertRaisesRegex(RuntimeError, 'Fixture launch failed'):
                    with fixture.crypt_fixture(directory, Path('/synthetic/rclone')):
                        self.fail('Setup failure must prevent entering the fixture')
            self.assertIsNone(fixture.session.credentials(context))

    def test_close_failure_still_forgets_credentials(self):
        with TemporaryDirectory() as directory:
            context = Path(directory).resolve() / 'Accounts.session'
            self.addCleanup(fixture.session.forget, context)
            provider = Mock()
            provider.close.side_effect = RuntimeError('Fixture close failed')
            with patch.object(fixture, 'obscured_password', return_value='synthetic'), \
                    patch.object(fixture, 'run_bytes', return_value=b''), \
                    patch.object(fixture.local_crypt, 'CryptResources', return_value=provider):
                with self.assertRaisesRegex(RuntimeError, 'Fixture close failed'):
                    with fixture.crypt_fixture(directory, Path('/synthetic/rclone'), pull=False):
                        self.assertIsNotNone(fixture.session.credentials(context))
            self.assertIsNone(fixture.session.credentials(context))
