"""Application hosts construct credential-bound resources through the service."""
import ast
from pathlib import Path
import unittest


class ServiceBoundaryTests(unittest.TestCase):
    def test_provider_construction_and_engine_launch_stay_in_platform_adapters(self):
        root = Path(__file__).resolve().parents[2]
        providers = {'CryptResources', 'CryptFiles', 'DownloadedCryptFile', 'RemoteResources',
                     'NativeRemoteResources', 'RemoteReaders'}
        adapters = {
            'features/rclone/desktop_service.py', 'features/rclone/mobile/service.py',
            'features/rclone/mobile/remote_resources.py',
            'features/rclone/transfers/desktop.py', 'features/rclone/transfers/push_policy.py',
        }
        violations = []
        for owner in ('features/rclone', 'features/text_editor', 'features/youtube_downloader',
                      'services/documents', 'mobile'):
            for path in (root / owner).rglob('*.py'):
                relative = path.relative_to(root).as_posix()
                if relative in adapters:
                    continue
                tree = ast.parse(path.read_text(encoding='utf-8'))
                imported = set()
                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom) and node.module and 'rclone' in node.module:
                        imported.update(alias.asname or alias.name for alias in node.names if alias.name in providers)
                        if node.module == 'features.rclone.transfers.sync':
                            violations.append(relative + ': direct transfer engine import')
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call):
                        name = (node.func.id if isinstance(node.func, ast.Name) else
                                node.func.attr if isinstance(node.func, ast.Attribute) else '')
                        if name in imported or isinstance(node.func, ast.Attribute) and name in providers:
                            violations.append(f'{relative}:{node.lineno}: direct {name} construction')
        self.assertEqual(violations, [], '\n'.join(violations))
