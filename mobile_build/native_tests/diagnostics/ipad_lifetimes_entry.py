"""Diagnostic-only entry wrapping the untouched original complete native suite."""
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.EXTENDED
import json
from pathlib import Path
import threading
import time
import weakref

from tests.logisticsmobile import __main__ as original


def value(owner, name):
    try:
        current = getattr(owner, name)
        return current() if callable(current) else current
    except (AttributeError, TypeError):
        return None


def pointer(native):
    return int(native.ptr.value) if native is not None else None


def _native_state(native):
    if native is None:
        return None
    result = dict(pointer=pointer(native), class_name=str(value(native, 'className')),
                  window=pointer(value(native, 'window')))
    layer = value(native, 'layer')
    if layer is not None:
        result['animation_keys'] = [str(key) for key in value(layer, 'animationKeys') or ()]
        result['model_frame'] = str(value(layer, 'frame'))
        presentation = value(layer, 'presentationLayer')
        result['presentation_frame'] = str(value(presentation, 'frame')) if presentation else None
    return result


def native_state(native):
    try:
        return _native_state(native)
    except Exception as error:
        return dict(observer_error=type(error).__name__)


def transition(controller):
    if controller is None:
        return None
    coordinator = value(controller, 'transitionCoordinator')
    result = dict(controller=pointer(controller), active=coordinator is not None)
    if coordinator is not None:
        for name in ('isAnimated', 'isInteractive', 'percentComplete', 'transitionDuration'):
            current = value(coordinator, name)
            result[name] = float(current) if current is not None else None
    return result



def observe(callback):
    """Only diagnostic preprocessing is guarded; never catch original actions."""
    try:
        callback()
    except Exception:
        pass


def install(app):
    path = Path(app.paths.cache) / 'diagnostic-ui-boundaries.jsonl'
    retired = []
    def emit(label, **details):
        # Never let an observer failure replace the original suite's behavior.
        try:
            adapter = app.native_host.adapter
            destination = app.native_host.state.destination
            window = app.main_window._impl.native
            snapshot = dict(diagnostic_only=True, label=label, monotonic=time.monotonic(),
                main_thread=threading.current_thread() is threading.main_thread(),
                destination=destination, window=native_state(window),
                controllers=[transition(adapter.content_controller(destination)),
                    transition(adapter.navigation_for(destination)), transition(window.rootViewController)],
                retired_python_alive=sum(reference() is not None for reference in retired), **details)
        except Exception as error:
            snapshot = dict(diagnostic_only=True, label=label, observer_error=type(error).__name__)
        try:
            with path.open('a') as stream:
                stream.write(json.dumps(snapshot, default=str) + '\n')
                stream.flush()
        except OSError:
            # Missing/incomplete diagnostics are rejected by the host, without
            # replacing the original suite's assertions or control flow.
            pass
    home = app.show_home
    def show_home(*args, **kwargs):
        def before():
            old = list(app.routes.roots['home'].children)
            retired.extend(weakref.ref(widget) for widget in old)
            emit('show-home-before', old_views=[native_state(widget._impl.native) for widget in old])
        observe(before)
        result = home(*args, **kwargs)
        observe(lambda: emit('show-home-after'))
        return result
    picker = app.open_hub_file
    async def open_hub_file(*args, **kwargs):
        observe(lambda: emit('file-picker-before'))
        result = await picker(*args, **kwargs)
        observe(lambda: emit('file-picker-after'))
        return result
    release = app.native_host.adapter.release_pane
    def release_pane(container):
        observe(lambda: emit('release-pane-before', native=native_state(container.native), controller=pointer(container.controller)))
        result = release(container)
        observe(lambda: emit('release-pane-after'))
        return result
    app.show_home = show_home
    app.open_hub_file = open_hub_file
    app.native_host.adapter.release_pane = release_pane
    observe(lambda: emit('full-original-suite-start'))


exercise = original.exercise
async def traced_exercise(app):
    install(app)
    # No new await, delay, case filtering or scheduler changes precede this call.
    await exercise(app)

original.exercise = traced_exercise


def main():
    return original.main()


if __name__ == '__main__':
    main().main_loop()
