"""The public Windows wrapper must reach the real project sync argument parser."""
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import json
import os
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase, skipUnless

from logistics_build import tooling_bootstrap

ROOT = Path(__file__).resolve().parents[3]


@skipUnless(os.name == 'nt' and shutil.which('uv.exe'),
            'Native Windows and an already installed uv.exe are required')
class WindowsLogisticsLauncherTests(TestCase):
    def exercise_launcher(self, app_status):
        # Reuse the shared owner's bounded, identity-checked Windows fixture
        # cleanup; never remove or repair the running test interpreter.
        from commonUtils.tests.integrations.test_launcher_environment_sync import (
            cleanup_windows_fixture, run_windows_batch)
        temporary = TemporaryDirectory(prefix='logistics-consumer-launch-')
        parent = Path(temporary.name).resolve()
        root = parent / 'Logistics'
        root.mkdir()
        # The shared cleanup guard must bind the actual nested project's venv;
        # its delegate still removes our entire uniquely owned parent fixture.
        self.addCleanup(cleanup_windows_fixture,
            SimpleNamespace(name=str(root), cleanup=temporary.cleanup))
        source = root / 'Python'
        source.mkdir()
        launchers = source / 'commonUtils/launchers'
        launchers.mkdir(parents=True)
        shutil.copyfile(ROOT / 'LaunchLogistics_WIN.bat', root / 'LaunchLogistics_WIN.bat')
        shutil.copyfile(ROOT / 'Python/commonUtils/launchers/LaunchPythonProject_WIN.bat',
                        launchers / 'LaunchPythonProject_WIN.bat')
        scripts = root / 'logistics_build'
        scripts.mkdir()
        for name in ('tooling_bootstrap.py', 'device_workspace_paths.py'):
            shutil.copyfile(ROOT / 'logistics_build' / name, scripts / name)
        # Use the real consumer config and parser. The dependency-free manifest
        # plus offline policy permits no installation or download from a service.
        shutil.copyfile(ROOT / 'launch_config.ini', root / 'launch_config.ini')
        (source / '.python-version').write_text(sys.version.split()[0])
        (source / 'pyproject.toml').write_text(
            '[project]\nname="logistics-launcher-fixture"\nversion="0.0.0"\n'
            f'requires-python=">={sys.version_info.major}.{sys.version_info.minor}"\n'
            'dependencies=[]\n')
        report = parent / 'app.json'
        (source / 'launch.py').write_text(
            "import json, os, sys\nfrom pathlib import Path\n"
            "Path(os.environ['LOGISTICS_LAUNCH_TEST_REPORT']).write_text(json.dumps(dict("
            "root=os.environ['LOGISTICS_ROOT'],cwd=str(Path.cwd()),prefix=sys.prefix,argv=sys.argv[1:])))\n"
            f'raise SystemExit({app_status})\n')
        roaming, home = parent / 'roaming', parent / 'home'
        roaming.mkdir()
        home.mkdir()
        environment = dict(os.environ, APPDATA=str(roaming), USERPROFILE=str(home),
            UV_PYTHON=sys.executable, UV_PYTHON_DOWNLOADS='never', UV_OFFLINE='1',
            UV_CACHE_DIR=str(parent / 'uv-cache'),
            LOGISTICS_LAUNCH_TEST_REPORT=str(report))
        environment.pop('COMMONUTILS_ROOT', None)
        environment.pop('LOGISTICS_ALLY_ROOT', None)
        environment.pop('UV_PROJECT_ENVIRONMENT', None)
        self.assertFalse((parent / 'ally-tools').exists())
        # No PROJECT_ROOT argument: the real wrapper must supply %~dp0, whose
        # trailing slash exposed the CRT quoting bug in tooling_bootstrap.main.
        completed = run_windows_batch([str(root / 'LaunchLogistics_WIN.bat')],
                                      env=environment, timeout=90)
        diagnostic = (completed.stdout or b'') + (completed.stderr or b'')
        self.assertEqual(completed.returncode, app_status, diagnostic.decode('utf-8', errors='replace'))
        self.assertTrue(report.is_file(), diagnostic.decode('utf-8', errors='replace'))
        observed = json.loads(report.read_text())
        self.assertEqual(Path(observed['root']).resolve(), root)
        self.assertEqual(Path(observed['cwd']).resolve(), source)
        self.assertEqual(Path(observed['prefix']).resolve(), root / '.venv')
        self.assertEqual(observed['argv'], [])
        self.assertTrue((source / 'uv.lock').is_file())
        self.assertTrue(tooling_bootstrap.lock_path(root).is_file())
        self.assertFalse(tooling_bootstrap.enrollment(root).exists())
        self.assertNotIn(b'sync requires --venv', diagnostic)
        self.assertNotIn(b'Using private Ally environment', diagnostic)

    def test_top_level_wrapper_reaches_real_sync_parser_and_owned_app(self):
        self.exercise_launcher(0)

    def test_top_level_wrapper_preserves_application_failure_status(self):
        self.exercise_launcher(37)
