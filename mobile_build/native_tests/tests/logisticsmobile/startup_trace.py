"""Test-app-only bounded Android startup evidence and fail-closed deadline."""
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
import base64
from collections import deque
import json
from pathlib import Path
import sys
from threading import RLock, Timer
import time

_current = None
_generation = 0
_lock = RLock()
_hooks_installed = False


def frame_location(frame):
    return dict(file=Path(frame.f_code.co_filename).name,
                function=frame.f_code.co_name, line=frame.f_lineno)


def execution_snapshot(loop):
    """No locals, arguments, exception values, task names or object reprs."""
    threads = []
    for frame in list(sys._current_frames().values())[:16]:
        stack = []
        while frame is not None and len(stack) < 12:
            stack.append(frame_location(frame))
            frame = frame.f_back
        threads.append(stack)
    tasks = []
    try:
        for task in list(asyncio.all_tasks(loop))[:24]:
            chain, seen = [], set()
            value = task.get_coro()
            while value is not None and id(value) not in seen and len(chain) < 12:
                seen.add(id(value))
                frame = getattr(value, 'cr_frame', None) or getattr(value, 'gi_frame', None)
                if frame is not None:
                    chain.append(frame_location(frame))
                value = getattr(value, 'cr_await', None) or getattr(value, 'gi_yieldfrom', None)
            tasks.append(dict(done=task.done(), cancelled=task.cancelled(), chain=chain))
    except RuntimeError:
        # A changing loop can prevent a sample; never change startup's decisions.
        pass
    return dict(threads=threads, tasks=tasks)


def scheduler_snapshot(app, captured_loop):
    current_loop = getattr(app, 'loop', None)
    value = dict(loop_type=type(captured_loop).__name__,
        loop_running=captured_loop.is_running(), loop_closed=captured_loop.is_closed(),
        current_loop_matches_captured=current_loop is captured_loop)
    for name in ('startup_task', '_native_check_task'):
        task = getattr(app, name, None)
        row = dict(exists=task is not None)
        if task is not None:
            try:
                task_loop = task.get_loop()
                row.update(done=task.done(), cancelled=task.cancelled(),
                    loop_matches_captured=task_loop is captured_loop,
                    loop_matches_current=task_loop is current_loop)
            except (AttributeError, RuntimeError):
                row['state_available'] = False
        value[name] = row
    return value


def current(app):
    with _lock:
        return _current if _current is not None and _current.app is app else None


def mark(app, event, **metadata):
    trace = current(app)
    if trace is not None:
        try:
            trace.record(event, **metadata)
        except Exception:
            pass  # Diagnostics cannot change a product lifecycle callback.


def start_traced_check(app, operation):
    """Keep startup bounded until the actual check or intentional hold begins."""
    from . import start_native_check
    async def begin(owner):
        trace = current(owner)
        if trace is not None:
            trace.disarm()
        return await operation(owner)
    return start_native_check(app, begin)


class StartupTrace:
    def __init__(self, app, generation, *, timer_factory=Timer, failure=None):
        self.app, self.generation = app, generation
        self.cache, self.loop = Path(app.paths.cache), app.loop
        self.backend = type(app._impl).__module__
        self.started = time.monotonic()
        self.records = deque(maxlen=80)
        self.frames = 0
        self.emitted = 0
        self.last_geometry = None
        self.disarmed = False
        self.failure = failure or self.fail
        self.timers = []
        for seconds in (15, 30, 60, 120):
            timer = timer_factory(seconds, self.deadline if seconds == 120 else self.sample)
            timer.daemon = True
            self.timers.append(timer)
            timer.start()
        self.record('installed')

    def active(self):
        return _current is self and not self.disarmed

    def record(self, event, **metadata):
        with _lock:
            if not self.active():
                return
            value = dict(event=event, generation=self.generation,
                         elapsed_s=round(time.monotonic() - self.started, 3), **metadata)
            self.records.append(value)
            if self.emitted < 128:
                self.emitted += 1
                print('LOGISTICS_NATIVE_STARTUP_TRACE=' + json.dumps(value, sort_keys=True), flush=True)

    def snapshot(self):
        return dict(generation=self.generation, elapsed_s=round(time.monotonic() - self.started, 3),
                    frames=self.frames, last_geometry=self.last_geometry,
                    records=list(self.records), scheduler=scheduler_snapshot(self.app, self.loop),
                    execution=execution_snapshot(self.loop))

    def sample(self):
        with _lock:
            if not self.active():
                return
            value = self.snapshot()
            self.cache.mkdir(parents=True, exist_ok=True)
            (self.cache / 'logistics-native-startup-diagnostics.json').write_text(json.dumps(value))
            # The report is bounded by fixed thread/task/frame/record counts.
            encoded = base64.b64encode(json.dumps(value, sort_keys=True).encode()).decode()
            chunks = [encoded[index:index + 450] for index in range(0, len(encoded), 450)]
            for index, data in enumerate(chunks):
                print('LOGISTICS_NATIVE_STARTUP_SNAPSHOT_CHUNK=' + json.dumps(dict(
                    index=index, count=len(chunks), encoding='base64', data=data)), flush=True)

    def deadline(self):
        with _lock:
            if not self.active():
                return
            try:
                self.sample()
            except Exception:
                self.record('snapshot-write-unavailable')
            self.disarmed = True
            try:
                self.failure(self.snapshot())
            except Exception:
                # Even a damaged evidence path must not leave the test app
                # hanging until the outer host's forty-minute timeout.
                print('LOGISTICS_NATIVE_STARTUP_WATCHDOG_REPORT_ERROR', flush=True)
                print('>>>>>>>>>> EXIT 1 <<<<<<<<<<', flush=True)
                import os
                os._exit(1)

    def disarm(self):
        with _lock:
            self.record('exercise-entered')
            self.disarmed = True
            for timer in self.timers:
                timer.cancel()

    def before_draw(self, cover):
        # Called only from the UI-thread listener. Timer threads never touch Java.
        root, content = cover.app.navigation._impl.native, cover.app.navigation._impl.native_content
        geometry = dict(root_width=int(root.getWidth()), root_height=int(root.getHeight()),
            content_width=int(content.getWidth()), content_height=int(content.getHeight()),
            root_layout_requested=bool(root.isLayoutRequested()),
            content_layout_requested=bool(content.isLayoutRequested()),
            root_attached=bool(root.isAttachedToWindow()), content_attached=bool(content.isAttachedToWindow()),
            root_visibility=int(root.getVisibility()), content_visibility=int(content.getVisibility()))
        self.frames += 1
        if geometry != self.last_geometry or self.frames in (1, 2, 4, 16, 64, 256):
            self.record('cover-before-draw', frame=self.frames, **geometry)
        self.last_geometry = geometry

    def fail(self, diagnostics):
        import mobile
        from . import CASES
        source = json.loads(Path(mobile.__file__).with_name('source.json').read_text())
        report = dict(schema=1, suite='logistics-native-ui', target='android', backend=self.backend,
            cases=[], expected_cases=list(CASES), success=False,
            error='StartupWatchdogTimeout: native exercise did not begin within 120 seconds',
            source=source, native_picker_tested=False, startup_diagnostics=diagnostics)
        emit_failure(self.cache, report)


def emit_failure(cache, report, *, output=print, pause=time.sleep, exit_process=None):
    """Use the established native report protocol; never turn timeout into success."""
    import os
    exit_process = exit_process or os._exit
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / 'logistics-native-ui-result.json'
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(report, sort_keys=True))
    temporary.replace(path)
    encoded = base64.b64encode(json.dumps(report, sort_keys=True).encode()).decode()
    chunks = [encoded[index:index + 450] for index in range(0, len(encoded), 450)]
    for index, data in enumerate(chunks):
        output('LOGISTICS_NATIVE_UI_CHUNK=' + json.dumps(dict(index=index, count=len(chunks),
            encoding='base64', data=data)), flush=True)
        pause(.02)
    output('>>>>>>>>>> EXIT 1 <<<<<<<<<<', flush=True)
    pause(.25)
    exit_process(1)


def install(app, *, timer_factory=Timer, failure=None):
    global _current, _generation
    with _lock:
        if _current is not None:
            _current.disarm()
        _generation += 1
        # Publish before arming callbacks; stale Activity timers cannot kill a
        # newer startup, including one whose exercise has already begun.
        trace = StartupTrace.__new__(StartupTrace)
        _current = trace
        StartupTrace.__init__(trace, app, _generation, timer_factory=timer_factory, failure=failure)
    install_hooks()
    return trace


def install_hooks():
    global _hooks_installed
    if _hooks_installed:
        return
    from mobile.startup import AndroidStartupCover
    original_ready, original_draw = AndroidStartupCover.ready, AndroidStartupCover.before_draw

    async def ready(cover):
        mark(cover.app, 'cover-ready-enter')
        try:
            return await original_ready(cover)
        finally:
            mark(cover.app, 'cover-ready-exit', future_done=cover.future.done(),
                 future_cancelled=cover.future.cancelled())

    def before_draw(cover):
        trace = current(cover.app)
        if trace is not None and trace.active():
            try:
                trace.before_draw(cover)
            except Exception:
                mark(cover.app, 'geometry-sample-unavailable')
        return original_draw(cover)

    AndroidStartupCover.ready, AndroidStartupCover.before_draw = ready, before_draw
    _hooks_installed = True
