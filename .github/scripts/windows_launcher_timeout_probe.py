"""Instrument a disposable copy of the packaged Windows launcher."""

import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import platform
import subprocess
from tempfile import TemporaryDirectory
from time import monotonic
from zipfile import ZipFile

from package_release import package


ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = 'Python/commonUtils/launchers/LaunchPythonProject_WIN.bat'
ENTRY = 'LaunchLogistics_WIN.bat'
OUTPUT = ROOT / 'test-results/windows-launcher-probe'


class ProcessEntry(ctypes.Structure):
    _fields_ = [
        ('size', wintypes.DWORD), ('usage', wintypes.DWORD), ('pid', wintypes.DWORD),
        ('heap', ctypes.c_size_t), ('module', wintypes.DWORD), ('threads', wintypes.DWORD),
        ('parent', wintypes.DWORD), ('priority', wintypes.LONG), ('flags', wintypes.DWORD),
        ('image', wintypes.WCHAR * 260),
    ]


def descendants(pid):
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    for name in ('Process32FirstW', 'Process32NextW'):
        function = getattr(kernel, name)
        function.argtypes = (wintypes.HANDLE, ctypes.POINTER(ProcessEntry))
        function.restype = wintypes.BOOL
    snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
    if snapshot == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    rows = []
    try:
        item = ProcessEntry(size=ctypes.sizeof(ProcessEntry))
        emit = kernel.Process32FirstW
        while emit(snapshot, ctypes.byref(item)):
            rows.append(dict(pid=item.pid, parent=item.parent, image=item.image, threads=item.threads))
            emit = kernel.Process32NextW
    finally:
        kernel.CloseHandle(snapshot)
    seen = {pid}
    while True:
        expanded = seen | {item['pid'] for item in rows if item['parent'] in seen}
        if expanded == seen:
            return [item for item in rows if item['pid'] in seen]
        seen = expanded


def fixture(root):
    original = (ROOT / LAUNCHER).read_text(encoding='utf-8')
    markers = (
        ("$ErrorActionPreference='Stop'; $paths=@($env:CONFIG_FILE);",
         "$ErrorActionPreference='Stop'; [Console]::WriteLine('PROBE_POWERSHELL_ENTERED'); $paths=@($env:CONFIG_FILE);"),
        ('foreach($path in $paths){ $inLaunch',
         "foreach($path in $paths){ [Console]::WriteLine('PROBE_BEFORE_READ'); $inLaunch"),
        ('foreach($key in $outputs.Keys){',
         "[Console]::WriteLine('PROBE_BEFORE_WRITE'); foreach($key in $outputs.Keys){"),
        ('set "READ_STATUS=%ERRORLEVEL%"', 'echo PROBE_POWERSHELL_RETURNED\nset "READ_STATUS=%ERRORLEVEL%"'),
    )
    for before, after in markers:
        assert original.count(before) == 1, before
        original = original.replace(before, after)
    (root / LAUNCHER).parent.mkdir(parents=True)
    (root / LAUNCHER).write_bytes(original.encode('utf-8'))
    (root / ENTRY).write_bytes((ROOT / ENTRY).read_bytes().replace(b'\r\n', b'\n'))
    (root / 'launch_config.ini').write_text(
        '[Launch]\ncommonutils_root = Python/commonUtils\nsource_dir = missing-source\n'
        'launch_file = main\nensure_user_dir =\npause_after_completed = false\n',
        encoding='utf-8',
    )
    package(root, root / 'release.zip', (ENTRY, LAUNCHER, 'launch_config.ini'), required=set())
    with ZipFile(root / 'release.zip') as archive:
        archive.extractall(root / 'extracted')
    return root / 'extracted/Logistics'


def attempt(label, *, override_local_appdata):
    with TemporaryDirectory(prefix='Logistics launch ', ignore_cleanup_errors=True) as directory:
        root = Path(directory)
        cwd = fixture(root)
        locations = {name: root / name for name in ('appdata', 'local-appdata', 'launch-temp')}
        for path in locations.values():
            path.mkdir()
        env = dict(os.environ, APPDATA=str(locations['appdata']), TEMP=str(locations['launch-temp']),
                   TMP=str(locations['launch-temp']))
        if override_local_appdata:
            env['LOCALAPPDATA'] = str(locations['local-appdata'])
        env.pop('COMMONUTILS_ROOT', None)
        path = OUTPUT / (label + '.log')
        result = dict(label=label, override_local_appdata=override_local_appdata)
        start = monotonic()
        with path.open('wb') as log:
            child = subprocess.Popen(['cmd.exe', '/d', '/c', ENTRY], cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                     stdout=log, stderr=subprocess.STDOUT,
                                     creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
            try:
                result['exit_code'] = child.wait(timeout=60)
            except subprocess.TimeoutExpired:
                result['timeout'] = True
                result['process_tree'] = descendants(child.pid)
                subprocess.run(['taskkill.exe', '/f', '/t', '/pid', str(child.pid)], timeout=20,
                               stdout=log, stderr=subprocess.STDOUT, check=False)
                child.wait(timeout=10)
        result['seconds'] = round(monotonic() - start, 2)
        output = path.read_text(encoding='utf-8', errors='replace')
        result['markers'] = [row.strip() for row in output.splitlines() if row.startswith('PROBE_')]
        result['expected_error'] = 'Configured source_dir does not exist or is not a directory:' in output
        result['config_staging_fields'] = sorted(p.name for folder in locations['launch-temp'].glob('commonutils_launch_*')
                                                  for p in folder.iterdir())
    result['temporary_directory_removed'] = not root.exists()
    (OUTPUT / (label + '.json')).write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result), flush=True)
    return result


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    platform_data = dict(platform=platform.platform(), python=platform.machine(),
                         process=os.environ.get('PROCESSOR_ARCHITECTURE'),
                         native=os.environ.get('PROCESSOR_ARCHITEW6432'))
    print(json.dumps(platform_data), flush=True)
    (OUTPUT / 'platform.json').write_text(json.dumps(platform_data, indent=2), encoding='utf-8')
    for label, override in [('original-1', True), ('native-profile-1', False),
                            ('original-2', True), ('native-profile-2', False)]:
        attempt(label, override_local_appdata=override)


if __name__ == '__main__':
    main()
