"""Opt-in Explorer qualification on an unlocked, dedicated Windows test guest."""
from contextlib import ExitStack
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from threading import Thread
from time import monotonic, sleep
from unittest.mock import patch


# Inspect only the Explorer window displaying the generated test folder.
EXPLORER = r"""
$ErrorActionPreference='Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$shell=New-Object -ComObject Shell.Application
if ($env:DRAG_PROBE_OPEN -eq '1') { $shell.Explore($env:DRAG_PROBE_DIRECTORY) }
$until=[DateTime]::UtcNow.AddSeconds(12)
do {
 foreach ($window in $shell.Windows()) {
  try {
   if ($window.Document.Folder.Self.Path -ne $env:DRAG_PROBE_DIRECTORY) { continue }
   $element=[Windows.Automation.AutomationElement]::FromHandle([IntPtr][long]$window.HWND)
   $names=@($env:DRAG_PROBE_NAME,$env:DRAG_PROBE_STEM)
   foreach ($name in $names) {
    $condition=[Windows.Automation.PropertyCondition]::new([Windows.Automation.AutomationElement]::NameProperty,$name)
    $items=$element.FindAll([Windows.Automation.TreeScope]::Descendants,$condition)
    foreach($item in $items) {
     $rect=$item.Current.BoundingRectangle
     $control=$item.Current.ControlType.ProgrammaticName
     if (!$item.Current.IsOffscreen -and $rect.Width -gt 2 -and $rect.Height -gt 2 -and
         $control -in @('ControlType.ListItem','ControlType.DataItem')) {
      @{hwnd=[long]$window.HWND;x=[int]($rect.X+$rect.Width/2);y=[int]($rect.Y+$rect.Height/2)}|ConvertTo-Json -Compress
      exit 0
     }
    }
   }
  } catch [System.Runtime.InteropServices.COMException] {}
 }
 Start-Sleep -Milliseconds 150
} while ([DateTime]::UtcNow -lt $until)
throw 'Generated Explorer item has no visible native bounding rectangle.'
"""


def explorer_point(folder, name, *, open_window=False):
    env = dict(os.environ, DRAG_PROBE_DIRECTORY=str(folder), DRAG_PROBE_NAME=name,
               DRAG_PROBE_STEM=Path(name).stem, DRAG_PROBE_OPEN=str(int(open_window)))
    proc = subprocess.run(
        ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', EXPLORER],
        env=env, text=True, capture_output=True, timeout=22, creationflags=subprocess.CREATE_NO_WINDOW,
    )
    if proc.returncode:
        raise RuntimeError(proc.stderr.strip() or 'Explorer UI Automation returned no result.')
    return json.loads(proc.stdout)


class Desktop:
    def __init__(self):
        self.user = ctypes.WinDLL('user32', use_last_error=True)
        self.user.OpenInputDesktop.restype = wintypes.HANDLE
        self.user.OpenInputDesktop.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.user.CloseDesktop.argtypes = [wintypes.HANDLE]
        self.user.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
        self.user.FindWindowW.restype = wintypes.HWND
        self.user.GetUserObjectInformationW.argtypes = [
            wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
        ]
        self.user.SetForegroundWindow.argtypes = [wintypes.HWND]
        self.user.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        self.user.WindowFromPoint.argtypes = [wintypes.POINT]
        self.user.WindowFromPoint.restype = wintypes.HWND
        self.user.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        self.user.GetAncestor.restype = wintypes.HWND
        self.user.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        self.user.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        self.user.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
        self.user.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        self.user.MoveWindow.argtypes = [
            wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.BOOL,
        ]
        self.user.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        # Match UI Automation's physical-screen coordinates on a scaled guest.
        self.user.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))

    def require_input(self):
        handle = self.user.OpenInputDesktop(0, False, 1)
        if not handle:
            raise RuntimeError('Interactive input desktop is inaccessible.')
        try:
            size = wintypes.DWORD()
            name = ctypes.create_unicode_buffer(64)
            if (not self.user.GetUserObjectInformationW(handle, 2, name, ctypes.sizeof(name), ctypes.byref(size))
                    or name.value.casefold() != 'default'):
                raise RuntimeError('Windows input desktop is locked or unavailable.')
        finally:
            self.user.CloseDesktop(handle)

    def key(self, key, up=False):
        self.user.keybd_event(key, 0, 2 if up else 0, 0)

    def window_at(self, point):
        return self.user.GetAncestor(self.user.WindowFromPoint(wintypes.POINT(*point)), 2)

    def window_info(self, window):
        bounds = wintypes.RECT()
        label = ctypes.create_unicode_buffer(128)
        if window:
            self.user.GetWindowRect(window, ctypes.byref(bounds))
            self.user.GetClassNameW(window, label, len(label))
        return label.value, (bounds.left, bounds.top, bounds.right, bounds.bottom)

    def client_point(self, window, widget, point):
        area = wintypes.RECT()
        origin = wintypes.POINT()
        if not (self.user.GetClientRect(window, ctypes.byref(area))
                and self.user.ClientToScreen(window, ctypes.byref(origin))):
            raise RuntimeError('Unable to map Logistics client coordinates to the guest display.')
        return (origin.x + round(area.right * point.x() / widget.width()),
                origin.y + round(area.bottom * point.y() / widget.height()))

    def drag(self, start, end, *, key=None, escape=False):
        self.require_input()
        self.user.SetCursorPos(*start)
        sleep(.25)
        self.user.mouse_event(2, 0, 0, 0, 0)
        try:
            sleep(.2)
            if key:
                self.key(key)
            for step in range(1, 21):
                point = tuple(round(a + (b - a) * step / 20) for a, b in zip(start, end))
                self.user.SetCursorPos(*point)
                sleep(.04)
            sleep(.3)
            if escape:
                self.key(27)
                self.key(27, up=True)
        finally:
            self.user.mouse_event(4, 0, 0, 0, 0)
            if key:
                self.key(key, up=True)


def exercise(root, cleanup):
    from commonUtils.tests.qt_test_case import QtTestCase
    from commonUtils.ui import pyside as qt
    from commonUtils.ui.tasks.process_progress import _windows
    from desktop.file_browser import FileBrowserWindow
    from features.application import registry

    desktop = Desktop()
    desktop.require_input()
    app = qt.QApplication([])
    if app.platformName() != 'windows' or len(app.screens()) != 1:
        raise RuntimeError('Native Explorer qualification requires the Windows Qt backend and one display.')
    ratio = app.primaryScreen().devicePixelRatio()
    bounds = app.primaryScreen().availableGeometry()
    width, height = int(bounds.width() * ratio), int(bounds.height() * ratio)
    if width < 1000 or height < 600:
        raise RuntimeError(f'Guest display is too small for two drop windows ({width}×{height}).')
    print(json.dumps(dict(backend=app.platformName(), display=[width, height], device_ratio=ratio)), flush=True)
    shell, local = root / 'Explorer side', root / 'Logistics side'
    shell.mkdir()
    local.mkdir()
    receive = shell / 'Receive'
    receive.mkdir()

    def tree(parent, name):
        target = parent / name / 'nested'
        target.mkdir(parents=True)
        (target / 'file.txt').write_bytes(b'generated nested bytes')
        return target.parent

    copied = tree(shell, 'Copy In')
    cancelled = tree(shell, 'Cancel In')
    outbound = tree(local, 'Copy Out')
    moved = shell / 'Move In.txt'
    moved.write_bytes(b'generated move in')
    outbound_file = local / 'Move Out.txt'
    outbound_file.write_bytes(b'generated move out')
    (shell / 'Collision.txt').write_bytes(b'incoming')
    (local / 'Collision.txt').write_bytes(b'existing')
    folder = explorer_point(shell, receive.name, open_window=True)
    explorer = folder['hwnd']
    cleanup.callback(desktop.user.PostMessageW, explorer, 0x10, 0, 0)
    desktop.user.ShowWindow(explorer, 9)
    desktop.user.MoveWindow(explorer, 0, 0, width // 2, height - 20, True)
    cleanup.callback(QtTestCase()._release_windows, set())
    with patch.object(registry, 'get_browser_extensions', return_value=[]):
        window = FileBrowserWindow(local)
    window.show()
    logistics = int(window.winId())
    desktop.user.MoveWindow(logistics, width // 2, 0, width // 2, height - 20, True)
    browser = window.file_browser
    view = browser.views.navigation_views[0]
    viewport = view.viewport()

    def until(predicate, description, seconds=12):
        deadline = monotonic() + seconds
        while monotonic() < deadline:
            app.processEvents()
            if predicate():
                return
            sleep(.025)
        raise AssertionError(description)

    def step(source, destination, source_window, target_window, *, key=None, escape=False):
        for point, expected in ((source, source_window), (destination, target_window)):
            actual = desktop.window_at(point)
            if actual != expected:
                raise RuntimeError(f'Generated test point {point} is outside its expected window. '
                                   f'Expected {desktop.window_info(expected)}, observed {desktop.window_info(actual)}.')
        errors = []

        def gesture():
            try:
                desktop.drag(source, destination, key=key, escape=escape)
            except Exception as error:
                errors.append(error)
        thread = Thread(target=gesture, daemon=True)
        thread.start()
        until(lambda: not thread.is_alive(), 'Native mouse gesture did not finish.')
        if errors:
            raise errors[0]

    def shell_point(name):
        row = explorer_point(shell, name)
        assert row['hwnd'] == explorer
        return row['x'], row['y']

    def qt_point(point):
        return desktop.client_point(logistics, window, viewport.mapTo(window, point))

    def to_qt(path, key, *, escape=False):
        desktop.user.SetForegroundWindow(explorer)
        before = set(_windows)
        step(shell_point(path.name), qt_point(qt.QPoint(35, viewport.height() * 2 // 3)),
             explorer, logistics, key=key, escape=escape)
        if escape:
            until(lambda: not window.workspace.active_view.move_actions.busy, 'Cancelled drag started a job.')
            assert set(_windows) == before
            return None
        until(lambda: bool(set(_windows) - before), 'Explorer drop did not reach Logistics Transfers.')
        job, = set(_windows) - before
        until(lambda: job.result is not None, 'Logistics transfer did not retire.')
        outcome = job.result.state
        job.close()
        app.processEvents()
        return outcome

    def to_explorer(path, key, *, escape=False):
        desktop.user.SetForegroundWindow(logistics)
        until(lambda: browser.model.browse_index(path).isValid(), 'Logistics source did not load.')
        index = browser.sort_model.mapFromSource(browser.model.browse_index(path))
        until(lambda: not view.visualRect(index).isEmpty(), 'Logistics row is not visible.')
        step(qt_point(view.visualRect(index).center()), shell_point(receive.name), logistics, explorer,
             key=key, escape=escape)

    until(lambda: not browser.busy and view.isVisible(), 'Logistics native browser did not settle.')
    assert to_qt(copied, 17) == 'succeeded'
    assert (local / copied.name / 'nested/file.txt').read_bytes() == b'generated nested bytes' and copied.exists()
    print('Explorer → Logistics: Ctrl copy preserved source and nested bytes.', flush=True)
    assert to_qt(moved, 16) == 'succeeded'
    assert (local / moved.name).read_bytes() == b'generated move in' and not moved.exists()
    print('Explorer → Logistics: Shift move removed source after publication.', flush=True)
    assert to_qt(shell / 'Collision.txt', 17) == 'failed'
    assert (local / 'Collision.txt').read_bytes() == b'existing' and (shell / 'Collision.txt').read_bytes() == b'incoming'
    print('Explorer → Logistics: collision preserved both files and reported failure.', flush=True)
    to_qt(cancelled, 17, escape=True)
    assert not (local / cancelled.name).exists() and cancelled.exists()
    print('Explorer → Logistics: Escape left source unchanged.', flush=True)
    to_explorer(outbound, 17)
    received = receive / outbound.name / 'nested/file.txt'
    until(received.is_file, 'Explorer did not copy the nested folder.')
    assert received.read_bytes() == b'generated nested bytes' and outbound.exists()
    print('Logistics → Explorer: Ctrl copy handed off and preserved nested bytes.', flush=True)
    to_explorer(outbound_file, 16, escape=True)
    assert outbound_file.exists() and not (receive / outbound_file.name).exists()
    print('Logistics → Explorer: Escape preserved the source.', flush=True)
    to_explorer(outbound_file, 16)
    until(lambda: (receive / outbound_file.name).is_file() and not outbound_file.exists(), 'Explorer did not move the file.')
    assert (receive / outbound_file.name).read_bytes() == b'generated move out'
    status = window.workspace.active_view.move_actions.operation.message.text()
    assert 'Check the file manager' in status
    print('Logistics → Explorer: Shift move succeeded and Logistics reported handoff.', flush=True)
    collision = local / 'Collision.txt'
    existing = receive / collision.name
    existing.write_bytes(b'existing at native destination')
    assert not desktop.user.FindWindowW(None, 'Replace or Skip Files')
    to_explorer(collision, 17)
    until(lambda: desktop.user.FindWindowW(None, 'Replace or Skip Files'), 'Explorer did not show its conflict dialog.')
    dialog = desktop.user.FindWindowW(None, 'Replace or Skip Files')
    desktop.user.SetForegroundWindow(dialog)
    desktop.key(27)
    desktop.key(27, up=True)
    until(lambda: not desktop.user.FindWindowW(None, 'Replace or Skip Files'), 'Explorer conflict remains open.')
    assert existing.read_bytes() == b'existing at native destination' and collision.read_bytes() == b'existing'
    print('Logistics → Explorer: native conflict dialog cancelled and preserved both files.', flush=True)
    assert not list(local.glob('.drag-*'))


def main():
    if os.name != 'nt':
        raise SystemExit('This probe is for a dedicated Windows desktop only.')
    import sys
    subprocess.run([sys.executable, 'dev.py', 'test', 'desktop', 'test_file_browser_window.py',
                    '--python', sys.executable], check=True)
    os.environ['QT_QPA_PLATFORM'] = 'windows'
    with ExitStack() as cleanup:
        scratch = Path.cwd() / 'tmp'
        scratch.mkdir(exist_ok=True)
        root = Path(cleanup.enter_context(TemporaryDirectory(prefix='explorer-exchange-', dir=scratch)))
        os.environ['COMMONUTILS_STORAGE_ROOT'] = str(root / 'state')
        home = root / 'home'
        home.mkdir()
        cleanup.enter_context(patch.dict(os.environ, APPDATA=str(home / 'AppData' / 'Roaming'),
                                         LOCALAPPDATA=str(home / 'AppData' / 'Local')))
        cleanup.enter_context(patch.object(Path, 'home', return_value=home))
        exercise(root, cleanup)


if __name__ == '__main__':
    main()
