"""Full-host native IME, UIKit scenes and Android Activity replacement checks.

Use only the separate QA bundle below. Synthetic drafts live in its cache.
Retain old Android hosts deliberately so GC cannot conceal missing retirement.
"""
import asyncio
import json
import os
import sys
from pathlib import Path
import traceback
from uuid import uuid4

from mobile.app import LogisticsMobile
from mobile import application_lifecycle
from commonUtils.persistence import atomic_write_json
from commonUtils.ui.native import navigation
from .native_lifecycle_probe import fingerprint

BUNDLE = 'io.github.ispaure.logisticslifecyclecontinuation'
RESULT = 'native-host-lifecycle.json'
_owners = []
_stderr_capture = None


class CapturedErrors:
    """Keep Python errors even when the platform bridges stderr to its logger."""
    def __init__(self, original, path):
        self.original = original
        self.evidence = path.open('w', encoding='utf-8', errors='backslashreplace')

    def write(self, value):
        self.evidence.write(value)
        self.evidence.flush()
        return self.original.write(value)

    def flush(self):
        self.evidence.flush()
        self.original.flush()

    def __getattr__(self, name):
        return getattr(self.original, name)


async def until(predicate, message, timeout=10):
    for _ in range(int(timeout * 10)):
        value = predicate()
        if value:
            return value
        await asyncio.sleep(.1)
    raise AssertionError(message() if callable(message) else message)


def phase(host, name):
    atomic_write_json(Path(host.paths.cache) / 'native-host-lifecycle-phase.json',
        dict(name=name, pid=os.getpid(), window=host.window_id))


def scene_status(host):
    from rubicon.objc import ObjCClass
    return dict(error=host.scene_manager.error, active=host.scene_active, host_active=host.active_host,
        session=str(host.native_scene.session.persistentIdentifier),
        opened=[str(session.persistentIdentifier)
                for session in ObjCClass('UIApplication').sharedApplication.openSessions.allObjects()])


def keyboard_state(host):
    adapter = host.native_host.adapter
    if hasattr(adapter, 'keyboard_visible'):
        return dict(visible=adapter.keyboard_visible, inset=adapter.keyboard_inset,
                    hidden=adapter.tabs_hidden())
    from java import jclass
    insets = jclass('androidx.core.view.ViewCompat').getRootWindowInsets(adapter.impl.native)
    visible = bool(insets and insets.isVisible(jclass('androidx.core.view.WindowInsetsCompat$Type').ime()))
    return dict(visible=visible, inset=adapter.impl.native.getPaddingBottom(),
                hidden=adapter.impl.native_navigationview.getVisibility() != 0,
                temporary_chrome=adapter.keyboard_chrome is not None)


def focus(host):
    host.editor.focus()
    if type(host._impl).__module__.startswith('toga_android.'):
        from android.content import Context
        from android.view.inputmethod import InputMethodManager
        host._impl.native.getSystemService(Context.INPUT_METHOD_SERVICE).showSoftInput(
            host.editor._impl.native, InputMethodManager.SHOW_IMPLICIT)


def blur(host):
    if type(host._impl).__module__.startswith('toga_iOS.'):
        host.editor._impl.native.resignFirstResponder()
    else:
        from android.content import Context
        host._impl.native.getSystemService(Context.INPUT_METHOD_SERVICE).hideSoftInputFromWindow(
            host.editor._impl.native.getWindowToken(), 0)


async def exercise_landscape_ime(host):
    try:
        host._impl.native.setRequestedOrientation(0)
        await until(lambda: host.main_window.size.width > host.main_window.size.height,
                    'Android did not enter landscape')
        samples = await exercise_ime(host)
        assert all(sample['shown']['temporary_chrome'] for sample in samples), 'Short IME viewport was not exercised'
        return samples
    finally:
        blur(host)
        host._impl.native.setRequestedOrientation(1)
        await until(lambda: host.main_window.size.height > host.main_window.size.width,
                    'Android did not restore portrait')


async def exercise_ime(host):
    host.show_documents()
    await asyncio.sleep(.5)
    original = host.editor.value
    host.editor.value = 'Synthetic IME restoration draft'
    baseline = keyboard_state(host)
    assert not baseline['visible'], baseline
    samples = []
    try:
        for cycle in range(3):
            phase(host, 'ime-focus-' + str(cycle))
            focus(host)
            await until(lambda: keyboard_state(host)['visible'], 'Native keyboard did not appear')
            await asyncio.sleep(.3)
            shown = keyboard_state(host)
            if hasattr(host.native_host.adapter, 'keyboard_visible'):
                assert shown['hidden'], shown
            blur(host)
            await until(lambda: not keyboard_state(host)['visible'], 'Keyboard did not dismiss')
            await until(lambda: keyboard_state(host)['hidden'] == baseline['hidden'], 'Navigation chrome was not restored')
            await until(lambda: abs(keyboard_state(host)['inset'] - baseline['inset']) < 1, 'Keyboard inset was not restored')
            assert host.editor.value == 'Synthetic IME restoration draft'
            host.show_home()
            await until(lambda: not keyboard_state(host)['hidden'], 'Destinations stayed hidden after leaving the editor')
            host.show_documents()
            await until(lambda: keyboard_state(host)['hidden'] == baseline['hidden'], 'Document chrome was not reapplied')
            samples.append(dict(cycle=cycle, shown=shown, restored=keyboard_state(host)))
            phase(host, 'ime-restored-' + str(cycle))
    finally:
        blur(host)
        host.editor.value = original
    return samples


class HostLifecycleProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / 'native-host-lifecycle'
        self.run_id = uuid4().hex
        self.previous_probe = _owners[-1] if _owners else None
        _owners.append(self)
        super().startup()

    def on_running(self):
        if getattr(self, '_host_probe_task', None) is None:
            if type(self._impl).__module__.startswith('toga_iOS.'):
                import faulthandler
                from . import enable_native_fault_log
                self._probe_fault_log = enable_native_fault_log(self.paths.cache)
                faulthandler.dump_traceback_later(20, repeat=True, file=self._probe_fault_log)
            self._host_probe_task = self.loop.create_task(self.exercise())

    async def exercise(self):
        cache = Path(self.paths.cache)
        history = cache / 'native-host-lifecycle-history.json'
        report = dict(success=False, pid=os.getpid(), run_id=self.run_id, checks=[],
                      navigation=fingerprint(navigation), host_lifecycle=fingerprint(application_lifecycle))
        try:
            phase(self, 'startup')
            await until(lambda: not self._startup_in_progress, 'Logistics startup did not finish', timeout=40)
            apple = type(self._impl).__module__.startswith('toga_iOS.')
            phase(self, 'ready')
            if apple:
                report['ime'] = await exercise_ime(self)
                report['checks'].append('ime_restoration')
                report['windows'] = await self.independent_windows()
                report['checks'].append('independent_windows')
            else:
                previous = json.loads(history.read_text()) if history.exists() else None
                self.show_documents()
                await asyncio.sleep(.3)
                activity = int(self._impl.native.hashCode())
                boots = 1 if previous is None else previous['boots'] + 1
                report.update(activity=activity, boots=boots)
                if previous is not None:
                    assert previous['pid'] == os.getpid(), 'Recreation restarted the process'
                    assert previous['activity'] != activity, 'Activity was not replaced'
                    assert previous['run_id'] != self.run_id
                    assert self.current.id == previous['document_id'], 'Recreation changed the draft identity'
                    assert self.editor.value == previous['text'], 'Recreation lost the draft'
                    old = self.previous_probe
                    assert old is not None and not old.active_host
                    assert old.native_host.adapter is None, 'Replaced Activity retained navigation listeners'
                    assert old.native_host.on_select is None, 'Replaced Activity retained navigation callback'
                    assert old.routes.back_callback is None, 'Replaced Activity retained native Back'
                    old.probe_adapter.window_resized(old.main_window)
                    old.resize_workspace(old.main_window)
                    report['checks'].append('previous_host_retired')
                self.probe_adapter = self.native_host.adapter
                report['ime'] = await exercise_ime(self)
                report['checks'].append('ime_restoration')
                if boots == 1:
                    report['landscape_ime'] = await exercise_landscape_ime(self)
                self.editor.value = 'Durable synthetic Activity draft ' + str(boots)
                assert self.checkpoint()
                record = dict(pid=os.getpid(), run_id=self.run_id, activity=activity, boots=boots,
                              document_id=self.current.id, text=self.editor.value)
                record['runs'] = ([] if previous is None else previous['runs']) + [dict(
                    run_id=self.run_id, activity=activity, boots=boots,
                    retired_previous=previous is not None, ime=report['ime'],
                    landscape_ime=report.get('landscape_ime', []))]
                atomic_write_json(history, record)
                if boots <= 3:
                    report['recreating'] = True
                    atomic_write_json(cache / 'native-host-lifecycle-progress.json', report)
                    self._impl.native.recreate()
                    return
                report['checks'].append('three_activity_recreations')
                report['activity_runs'] = record['runs']
            await asyncio.sleep(.3)
            report['success'] = True
        except Exception:
            report['error'] = traceback.format_exc()
        atomic_write_json(cache / RESULT, report)
        if type(self._impl).__module__.startswith('toga_iOS.'):
            import faulthandler
            faulthandler.cancel_dump_traceback_later()
        print('NATIVE_HOST_LIFECYCLE=' + json.dumps(report), flush=True)

    async def independent_windows(self):
        manager = self.scene_manager
        assert manager.supported, 'Use an iPad with independent UIKit scenes'
        primary_id = self.current.id
        original = self.editor.value
        self.editor.value = 'Primary scene synthetic draft'
        results = []
        try:
            for cycle in range(3):
                phase(self, 'scene-create-' + str(cycle))
                self.show_documents()
                focus(self)
                await until(lambda: keyboard_state(self)['visible'], 'Primary keyboard did not appear before scene activation')
                assert manager.new_window(), manager.error
                child = await until(lambda: next((host for host in manager.owners.hosts.values()
                    if host is not self and getattr(host, 'scene_active', False)), None), 'Second system scene did not activate')
                child.show_documents()
                phase(child, 'scene-active-' + str(cycle))
                await until(lambda: not keyboard_state(self)['visible'], 'Keyboard ownership stayed with the inactive primary scene')
                assert child.main_window._impl.native.windowScene != self.main_window._impl.native.windowScene
                assert child.routes is not self.routes and child.editor is not self.editor
                child.editor.value = 'Independent scene draft ' + str(cycle)
                child_id = child.current.id
                assert not child.open_document(primary_id), 'Second writer was admitted'
                assert child.current.id == child_id
                await exercise_ime(child)
                assert not keyboard_state(self)['visible'], 'Another window changed primary keyboard ownership'
                assert self.editor.value == 'Primary scene synthetic draft'
                focus(child)
                await until(lambda: keyboard_state(child)['visible'], 'Second scene keyboard did not appear')
                from rubicon.objc import ObjCClass
                ObjCClass('UIApplication').sharedApplication.requestSceneSessionActivation(
                    self.native_scene.session, userActivity=None, options=None, errorHandler=None)
                await until(lambda: self.scene_active and not child.scene_active, 'Primary scene did not regain focus')
                await until(lambda: not keyboard_state(child)['visible'], 'Inactive child retained its keyboard inset')
                await until(lambda: keyboard_state(self)['visible'], 'Primary editor did not recover its keyboard')
                blur(self)
                await until(lambda: not keyboard_state(self)['visible'], 'Primary keyboard did not dismiss after restoration')
                child.show_settings()
                # Close through the same active-window path as the UI. The
                # iOS 27 beta simulator can silently retain inactive sessions.
                ObjCClass('UIApplication').sharedApplication.requestSceneSessionActivation(
                    child.native_scene.session, userActivity=None, options=None, errorHandler=None)
                await until(lambda: child.scene_active, 'Second scene did not reactivate for closure')
                phase(child, 'scene-close-' + str(cycle))
                retired_adapter = child.native_host.adapter
                assert manager.close_window(child)
                await until(lambda: len(manager.owners.hosts) == 1,
                    lambda: 'Second scene did not disconnect: ' + str(scene_status(child)))
                assert not child.active_host and child.native_host.adapter is None
                assert child.native_host.on_select is None
                assert not retired_adapter.keyboard_focus_observers
                retired_adapter.keyboard_focus_changed(object())
                retired_adapter.refresh_keyboard_focus()
                assert manager.new_window(workspace_id=child.window_id)
                restored = await until(lambda: next((host for host in manager.owners.hosts.values()
                    if host is not self and getattr(host, 'scene_active', False)), None), 'Scene did not reopen')
                assert restored is not child and restored.window_id == child.window_id
                assert restored.current.id == child_id
                assert restored.editor.value == 'Independent scene draft ' + str(cycle)
                assert restored.native_host.state.destination == 'settings'
                assert manager.close_window(restored)
                await until(lambda: len(manager.owners.hosts) == 1, 'Restored scene did not disconnect')
                results.append(dict(cycle=cycle, writer_separated=True, reopened=True,
                                    keyboard_transferred_back=True, late_notifications_retired=True))
        finally:
            blur(self)
            self.editor.value = original
        return results


def main():
    global _stderr_capture
    app = HostLifecycleProbe('Native host lifecycle', BUNDLE)
    if _stderr_capture is None:
        if type(app._impl).__module__.startswith('toga_android.'):
            # Toga binds App._impl.native later, in main_loop/create. The
            # Activity already exists when its Python launcher calls main().
            from org.beeware.android import MainActivity
            cache = Path(str(MainActivity.singletonThis.getCacheDir().getAbsolutePath()))
        else:
            cache = Path(app.paths.cache)
        path = cache / 'native-host-python-stderr.log'
        path.parent.mkdir(parents=True, exist_ok=True)
        _stderr_capture = sys.stderr = CapturedErrors(sys.stderr, path)
        print('NATIVE_HOST_STDERR_CAPTURE=started', file=sys.stderr, flush=True)
    return app
