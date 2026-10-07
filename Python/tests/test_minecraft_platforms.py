"""Bedrock platform executable discovery without starting a server."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from commonUtils.osUtils import OS
from features.minecraft import server


class BedrockPlatformTests(unittest.TestCase):
    @unittest.skipIf(os.name == 'nt', 'POSIX execute permissions require a POSIX host')
    def test_linux_binary_is_bedrock_and_requires_execute_permission(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            binary = root / 'bedrock_server'
            binary.touch()
            binary.chmod(0o644)
            with patch.object(server, 'get_os', return_value=OS.LINUX), patch.object(server.appUtils, 'DiskApp') as app, patch.object(server, 'log'):
                value = server.MinecraftServer(root)
                self.assertEqual(value.type, server.MinecraftServerType.BEDROCK)
                self.assertFalse(value.is_launchable())
                app.assert_not_called()
                binary.chmod(0o755)
                value = server.MinecraftServer(root)
                self.assertTrue(value.is_launchable())
                app.assert_called_once_with(root.name, binary, root)

    def test_windows_binary_does_not_offer_linux_launch(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'bedrock_server.exe').touch()
            with patch.object(server, 'get_os', return_value=OS.LINUX), patch.object(server.appUtils, 'DiskApp') as app, patch.object(server, 'log'):
                value = server.MinecraftServer(root)
                self.assertFalse(value.is_launchable())
                app.assert_not_called()
