"""Exercise the actual native app in Briefcase test mode on an emulator/simulator."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.EXTENDED
import asyncio
import base64
import json
import os
from pathlib import Path
import time
import traceback
from uuid import uuid4

from commonUtils.runtime.platform import get_os, OS
from mobile.app import LogisticsMobile
from . import CASES
from .startup_trace import start_traced_check
from .fixtures import make_books
from .timings import SuiteTimings, measure


def exception_summary(formatted):
    """Keep the final exception detail when its message ends in blank lines."""
    return next((line.strip()[:600] for line in reversed(formatted.splitlines())
                 if line.strip()), 'Native check failed without an exception summary.')


async def exercise(app):
    timings = SuiteTimings(Path(app.paths.cache) / 'logistics-native-ui-timings.json')
    app._native_suite_timings = timings
    class Progress(list):
        def append(self, case):
            super().append(case)
            timings.checkpoint(case)
            print('LOGISTICS_NATIVE_CASE=' + case, flush=True)
    passed = Progress()
    try:
        assert get_os() in {OS.ANDROID, OS.IOS}
        backend = type(app._impl).__module__
        assert backend.startswith('toga_android.' if get_os() is OS.ANDROID else 'toga_iOS.')
        if get_os() is OS.IOS:
            from .ios_storage_probe import exercise_ios_storage
            exercise_ios_storage(app)
            from .navigation_checks import assert_cold_iphone_tab_labels
            await asyncio.sleep(.3)
            assert_cold_iphone_tab_labels(app)
        # Scene activation may restore a destination after startup. Exercise
        # Home explicitly once the native app is running.
        app.show_home()
        assert not any(' '.join((getattr(child, 'text', None) or '').split()) == 'Open a file or start a new document.'
                       for child in app._home_status_row.children), 'Home introduction should be absent'
        assert app.native_host.state.destination == 'home'
        assert [tab.text for tab in app.navigation.content] == ['Home', 'Workspaces', 'Documents', 'Chat', 'Settings']
        passed.append('native_hub')
        # Exercise the direct Files entry before Workspaces/cloud setup. The
        # initial credential restore must not empty a newly built local picker.
        await app.show_files()
        choices = [row.value for row in app.file_storage.items]
        assert 'Local files' in choices, ('cold local roots', choices, app.file_status.value)
        assert app.file_provider is not None and not app.file_browser.closed
        app.show_home()
        from .navigation_checks import exercise_navigation
        navigation_proof = await measure(app, 'navigation', exercise_navigation(app))
        passed.append('native_navigation_foundation')
        from .notebook_checks import exercise_notebooks
        await measure(app, 'notebooks', exercise_notebooks(app))
        passed.append('native_notebooks')
        from .document_checks import exercise_documents
        await measure(app, 'documents', exercise_documents(app, passed))
        fixtures = app.private_root / 'fixtures'
        fixtures.mkdir()
        epub, comic = make_books(fixtures)
        from .reader_checks import exercise_library
        background_comic = await measure(app, 'readers', exercise_library(app, fixtures, epub, comic, passed))
        from .scene_checks import exercise_scenes
        await measure(app, 'scenes', exercise_scenes(app))
        passed.append('native_independent_windows')
        from .chat_checks import exercise_chat
        await measure(app, 'chat', exercise_chat(app, passed))
        from .connection_checks import exercise_connections
        await measure(app, 'connections', exercise_connections(app, fixtures, background_comic, passed))
        from .localcrypt_checks import exercise_localcrypt
        await measure(app, 'localcrypt', exercise_localcrypt(app, passed))
        from .ui_review import exercise_ui_review
        ui_review = await measure(app, 'ui-review', exercise_ui_review(app))
        print('LOGISTICS_UI_REVIEW=complete; checking native browser Back', flush=True)
        from .browser_back_checks import exercise_browser_back
        ui_review.update(await measure(app, 'browser-back', exercise_browser_back(app)))
        from .rotation_checks import exercise_rotation
        ui_review.update(await measure(app, 'rotation', exercise_rotation(app)))
        passed.append('native_rotation_safe_areas')
        from .transfer_recovery_probe import exercise_recovery
        recovery = await measure(app, 'transfer-renderer-recovery', exercise_recovery(app))
        assert recovery['success'], recovery.get('error', recovery)
        passed.append('native_transfer_renderer_recovery')
        success = passed == list(CASES)
        error = ''
    except Exception:
        success = False
        traceback.print_exc()
        formatted = traceback.format_exc()
        (Path(app.paths.cache) / 'logistics-native-ui-error.txt').write_text(formatted)
        error = exception_summary(formatted)
    import mobile
    source = json.loads(Path(mobile.__file__).with_name('source.json').read_text())
    report = dict(schema=1, suite='logistics-native-ui', target='android' if get_os() is OS.ANDROID else 'ios',
                  backend=type(app._impl).__module__, cases=passed, expected_cases=list(CASES),
                  success=success, error=error, source=source, native_picker_tested=False)
    report['timings'] = timings.summary()
    report['navigation'] = locals().get('navigation_proof')
    report['ui_review'] = locals().get('ui_review')
    report['independent_windows_tested'] = app.scene_manager.supported
    report['original_scene_close_tested'] = getattr(app, 'original_scene_close_tested', False)
    report['scene_environment_limit'] = getattr(app, 'scene_environment_limit', '')
    # iOS's OS logger truncates long single-line messages. Emit independently
    # bounded chunks; the host verifier rejects missing/duplicate chunks.
    # Keep a complete result outside Apple's asynchronous/truncating log stream.
    # This runs only in the disposable test-mode app; normal launches never write it.
    result_path = Path(app.paths.cache) / 'logistics-native-ui-result.json'
    temporary_result = result_path.with_suffix('.tmp')
    temporary_result.write_text(json.dumps(report, sort_keys=True))
    temporary_result.replace(result_path)
    encoded = base64.b64encode(json.dumps(report, sort_keys=True).encode()).decode()
    chunks = [encoded[index:index + 450] for index in range(0, len(encoded), 450)]
    for index, chunk in enumerate(chunks):
        print('LOGISTICS_NATIVE_UI_CHUNK=' + json.dumps(dict(index=index, count=len(chunks), encoding='base64', data=chunk)), flush=True)
        # The Apple system logger drains asynchronously even after Python's
        # stream flush. Do not exit with the final chunks still queued.
        await asyncio.sleep(.02)
    print(f'>>>>>>>>>> EXIT {0 if success else 1} <<<<<<<<<<', flush=True)
    await asyncio.sleep(.25)
    # This is a disposable test-mode app, never the normal app entry point.
    os._exit(0 if success else 1)


class NativeCheckApp(LogisticsMobile):
    def startup(self):
        print('LOGISTICS_NATIVE_STARTUP', flush=True)
        if get_os() is OS.IOS:
            import mobile
            source = json.loads(Path(mobile.__file__).with_name('source.json').read_text())
            print('LOGISTICS_NATIVE_PROCESS=' + json.dumps(dict(pid=os.getpid(), started_ns=time.time_ns(),
                source={key: source.get(key) for key in ('logistics_commit', 'commonUtils_commit', 'source_sha256')})), flush=True)
        if get_os() is OS.ANDROID:
            from .startup_trace import install as install_startup_trace
            install_startup_trace(self)
        from .navigation_trace import install
        install(self.paths.cache)
        if get_os() is OS.IOS:
            from . import enable_native_fault_log
            self._native_fault_stream = enable_native_fault_log(self.paths.cache)
        self.navigation_hold = os.environ.get('LOGISTICS_NAVIGATION_HOLD') == '1'
        self.workspace_hold = os.environ.get('LOGISTICS_WORKSPACE_HOLD') == '1'
        self.storage_root = Path(self.paths.cache) / ('workspace-navigation-probe' if self.workspace_hold else 'navigation-foundation-probe' if self.navigation_hold
                                                     else 'native-check-' + uuid4().hex)
        try:
            super().startup()
            from .startup_trace import mark
            mark(self, 'super-startup-returned')
        except Exception:
            # Preserve chained backend errors before the native launcher wraps them.
            traceback.print_exc()
            raise

    def _startup_steps(self):
        from .startup_trace import mark
        steps = super()._startup_steps()
        index = 0
        while True:
            mark(self, 'phase-next-enter', phase=index)
            try:
                name = next(steps)
            except StopIteration:
                mark(self, 'phases-complete')
                return
            mark(self, 'phase-next-exit', phase=index)
            yield name
            index += 1

    async def _prepare_startup_phase(self, index):
        from .startup_trace import mark
        mark(self, 'phase-prepare-enter', phase=int(index))
        await super()._prepare_startup_phase(index)
        mark(self, 'phase-prepare-exit', phase=int(index))

    def on_running(self):
        from .startup_trace import mark
        mark(self, 'on-running-enter')
        self.show_documents()
        self.show_home()
        mark(self, 'on-running-navigation-ready')
        if self.workspace_hold:
            from .workspace_hold import hold_workspace
            start_traced_check(self, hold_workspace)
        elif self.navigation_hold:
            from .navigation_hold import hold_navigation
            start_traced_check(self, hold_navigation)
        else:
            start_traced_check(self, exercise)



def main():
    return NativeCheckApp('Logistics Mobile', 'io.github.ispaure.logisticsmobile')


if __name__ == '__main__':
    main().main_loop()
