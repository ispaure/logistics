"""Opt-in lifetime trace around the unchanged, complete native acceptance journey.

Launch this module only in an owned disposable simulator app. It adds no waits,
retries, pose filtering, forced collection, or native retain/release operations.
Native getters and line-buffered output still perturb timing: a passing trace is
not proof that the uninstrumented crash is fixed.
"""

from commonUtils.testing.stages import TestStage
from commonUtils.ui.native.keyboard import native_value

TEST_STAGE = TestStage.EXTENDED
import gc
import json
import os
from pathlib import Path
import threading
import time
import weakref


def address(value):
    """Store scalars, never an Objective-C wrapper or controller description."""
    value = native_value(value)
    return None if value is None else int(value.ptr.value)


def native_flag(owner, name):
    """Rubicon may expose a Boolean getter as either a property or a method."""
    return bool(native_value(getattr(owner, name)))


def controller_state(controller):
    controller = native_value(controller)
    if controller is None:
        return None
    return dict(address=address(controller), parent=address(controller.parentViewController),
                presented=address(controller.presentedViewController),
                presenting=address(controller.presentingViewController),
                transition=address(controller.transitionCoordinator))


def native_state(app):
    from rubicon.objc import ObjCClass
    window = app.main_window._impl.native
    scene = native_value(window.windowScene)
    host = app.native_host
    adapter = host.adapter
    navigation = None if adapter is None else adapter.navigation_for(host.state.destination)
    application = native_value(ObjCClass('UIApplication').sharedApplication)
    scenes = native_value(application.connectedScenes).allObjects()
    return dict(main_thread=native_flag(ObjCClass('NSThread'), 'isMainThread'),
                window=address(window), scene=address(scene),
                activation=None if scene is None else int(native_value(scene.activationState)),
                orientation=None if scene is None else int(native_value(scene.interfaceOrientation)),
                key_window=native_flag(window, 'isKeyWindow'),
                root=controller_state(window.rootViewController),
                navigation=controller_state(navigation),
                destination=host.state.destination,
                hosts=[dict(scene=address(item), activation=int(native_value(item.activationState)),
                            windows=[address(w) for w in native_value(item.windows)])
                       for item in scenes],
                routes={key: [row[0] for row in rows] for key, rows in app.routes.screens.items()})


class RotationTrace:
    def __init__(self, app, *, snapshot=native_state):
        self.app = weakref.ref(app)
        self.snapshot = snapshot
        self.started = time.monotonic_ns()
        self.path = Path(app.paths.cache) / 'logistics-native-ui-rotation-trace.jsonl'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = self.path.open('w', buffering=1)
        self.sequence = 0
        self.request = 0
        self.panel = None

    def emit(self, event, *, native=False, **details):
        # Diagnostics cannot replace an original exception or acceptance result.
        try:
            self.sequence += 1
            row = dict(sequence=self.sequence, event=event, pid=os.getpid(),
                       elapsed_ns=time.monotonic_ns() - self.started,
                       python_main_thread=threading.current_thread() is threading.main_thread(),
                       panel=self.panel, request=self.request, gc_counts=gc.get_count(), **details)
            app = self.app()
            if native and app is not None:
                try:
                    row['native'] = self.snapshot(app)
                except Exception as error:
                    row['snapshot_error'] = type(error).__name__ + ': ' + str(error)[:240]
            self.stream.write(json.dumps(row) + '\n')
        except Exception:
            pass


def install(trace):
    """Install once in this diagnostic process, before native host creation."""
    from commonUtils.testing.rotation import NativeRotation
    from commonUtils.ui.native.navigation import NativeNavigationHost
    from . import rotation_checks
    from .timings import SuiteTimings

    original_request = NativeRotation.request
    original_acknowledge = rotation_checks.acknowledge_rotation
    original_checkpoint = SuiteTimings.checkpoint

    def request(rotation, orientation, *, on_rejected=None):
        trace.request += 1
        request_id = trace.request
        # Finalization observes Python ownership only. UIKit may still own a
        # copied Block, which Rubicon independently holds in its keepalive table.
        weakref.finalize(rotation, trace.emit, 'rotation-owner-collected', owner=id(rotation))
        trace.emit('request-before', native=True, orientation=orientation, owner=id(rotation))

        def rejected(error):
            trace.emit('request-rejected', request_id=request_id, orientation=orientation, error=error)
            if on_rejected is not None:
                on_rejected(error)

        try:
            result = original_request(rotation, orientation, on_rejected=rejected)
        except BaseException as error:
            trace.emit('request-raised', exception=type(error).__name__)
            raise
        block = getattr(rotation, '_rejection', None)
        trace.emit('request-returned', orientation=orientation,
                   block=None if block is None else int(block.block.value))
        return result

    async def acknowledge(app, orientation, *, timeout=None, panel=None):
        previous, trace.panel = trace.panel, panel
        try:
            result = await original_acknowledge(app, orientation, timeout=timeout, panel=panel)
            trace.emit('acknowledged', native=True, orientation=orientation)
            return result  # Preserve the original retained predicate and owner.
        except BaseException as error:
            trace.emit('acknowledgement-raised', native=True, orientation=orientation,
                       exception=type(error).__name__)
            raise
        finally:
            trace.panel = previous

    def checkpoint(timer, case):
        result = original_checkpoint(timer, case)
        trace.emit('case-complete', native=True, case=case)
        return result

    def lifecycle(name, original):
        def call(host, *args, **kwargs):
            trace.emit(name + '-before', host=id(host))
            try:
                return original(host, *args, **kwargs)
            finally:
                trace.emit(name + '-after', host=id(host))
        return call

    NativeRotation.request = request
    rotation_checks.acknowledge_rotation = acknowledge
    SuiteTimings.checkpoint = checkpoint
    for name in ('install', 'uninstall'):
        setattr(NativeNavigationHost, name, lifecycle(name, getattr(NativeNavigationHost, name)))
    trace.emit('trace-installed')


def main():
    from .__main__ import NativeCheckApp

    class RotationCrashApp(NativeCheckApp):
        def startup(self):
            self._rotation_crash_trace = RotationTrace(self)
            install(self._rotation_crash_trace)
            super().startup()

    return RotationCrashApp('Rotation trace QA', 'io.github.ispaure.logisticsnotebookqa')


def settings_snapshot(app):
    state = native_state(app)
    adapter = app.native_host.adapter
    tab = adapter.controller
    selected = native_value(tab.selectedViewController)
    navigation = adapter.navigation_for(app.native_host.state.destination)
    state.update(tab=controller_state(tab), selected_index=int(native_value(tab.selectedIndex)),
                 selected_controller=controller_state(selected),
                 top=controller_state(navigation.topViewController),
                 visible=controller_state(navigation.visibleViewController),
                 category=app.settings_navigation.selected,
                 wide=app.settings_navigation.wide)
    return state


async def run_settings_comparison(app, mode):
    """Compare Settings transitions in two fresh copies of the same test app."""
    import asyncio
    import traceback

    from mobile.routes import contains
    from .rotation_checks import rotate, wait_until

    trace = RotationTrace(app, snapshot=settings_snapshot)

    def transition_finished():
        adapter = app.native_host.adapter
        navigation = adapter.navigation_for('settings')
        return all(native_value(owner.transitionCoordinator) is None
                   for owner in (adapter.controller, navigation))

    def choose(category):
        app.settings_navigation.choose(category)
        navigation = app.settings_navigation
        assert navigation.selected == category and navigation.detail_requested, category
        assert contains(app.body, navigation.options[category]), category

    try:
        assert mode in ('held', 'immediate'), mode
        app.show_settings()
        assert app.select_destination('settings')
        orientations = ('landscape-left', 'landscape-right', 'portrait')
        trace.emit('start', native=True, mode=mode)
        choose('Text')
        await asyncio.sleep(.5)
        for index, orientation in enumerate(orientations * 12):
            category = ('Text' if index < 18 else 'EPUB') if mode == 'held' else (
                'EPUB' if index % 2 == 0 else 'Text')
            trace.request = index + 1
            trace.panel = category
            if app.settings_navigation.selected != category:
                trace.emit('switch-before', native=True)
                app.routes.back()
                choose(category)
            if mode == 'held':
                await wait_until(transition_finished, timeout=5,
                                 message='Held Settings transition did not settle')
            # In the immediate arm no loop turn occurs between choose and the native request.
            trace.emit('request-before', native=True, orientation=orientation)
            await rotate(app, orientation)
            assert app.settings_navigation.selected == category
            assert contains(app.body, app.settings_navigation.options[category]), category
            trace.emit('request-settled', native=True, orientation=orientation)
        trace.emit('complete', native=True, mode=mode, samples=trace.request)
        print(f'LOGISTICS_SETTINGS_ROTATION_COMPLETE={mode}:36', flush=True)
        status = 0
    except Exception:
        traceback.print_exc()
        trace.emit('python-error', traceback=traceback.format_exc())
        status = 1
    finally:
        trace.stream.close()
    await asyncio.sleep(.25)
    os._exit(status)



async def run_warm_settings(app):
    """Keep the original preceding journey and stop after the last suspect panel."""
    import asyncio
    import traceback
    from . import rotation_checks
    from .rotation_screens import SCREENS

    trace = RotationTrace(app, snapshot=settings_snapshot)
    inventory = [screen.panel for screen in SCREENS]
    panels = inventory[:inventory.index('settings-epub') + 1]
    settings = panels[panels.index('settings'):]
    original = rotation_checks.rotate_panel

    async def traced(app, *, panel, cycle, orientation):
        if panel not in settings:
            return await original(app, panel=panel, cycle=cycle, orientation=orientation)
        trace.panel = panel
        trace.request += 1
        trace.emit('request-before', native=True, orientation=orientation, cycle=cycle)
        result = await original(app, panel=panel, cycle=cycle, orientation=orientation)
        trace.emit('request-settled', native=True, orientation=orientation, cycle=cycle)
        return result

    try:
        trace.emit('warm-rotation-start', native=True)
        rotation_checks.rotate_panel = traced
        await rotation_checks.exercise_rotation(app, panels=panels)
        assert trace.request == 50
        trace.emit('complete', native=True, mode='warm', samples=trace.request)
        status = 0
    except Exception:
        traceback.print_exc()
        trace.emit('python-error', traceback=traceback.format_exc())
        status = 1
    finally:
        rotation_checks.rotate_panel = original
        trace.stream.close()
    await asyncio.sleep(.25)
    os._exit(status)
