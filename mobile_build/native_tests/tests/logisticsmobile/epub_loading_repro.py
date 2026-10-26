"""Diagnostic-only A/B experiment; never emits native release acceptance."""
import asyncio
import base64
import json
import os
from pathlib import Path
import platform
import time
import traceback
from unittest.mock import patch

import toga
from toga.style import Pack
from toga.style.pack import COLUMN
from features.books.mobile.presentation import ChapterBridge, chapter_view
from .web_checks import wait_for_text
from . import start_native_check

# The existing simulator bundle names this delegate in its launch metadata.
# Match the repository's standalone native probes without starting LogisticsMobile.
if toga.platform.current_platform == 'iOS':
    from toga_iOS.app import PythonAppDelegate

    class LogisticsSceneAppDelegate(PythonAppDelegate):
        pass


START = time.monotonic()
EVENTS = []


def state(native):
    from commonUtils.ui.native.keyboard import native_value
    from rubicon.objc import ObjCClass
    window = native_value(native.window)
    return dict(loading=bool(native_value(native.isLoading)),
        progress=float(native_value(native.estimatedProgress)),
        width=float(native.bounds.size.width), height=float(native.bounds.size.height),
        attached=window is not None, hidden=bool(native_value(native.isHidden)),
        active=int(native_value(ObjCClass('UIApplication').sharedApplication.applicationState)),
        url=str(native.URL))


def event(phase, native, error=None):
    try:
        view = native.interface
        row = dict(t=round(time.monotonic()-START, 4), phase=phase,
            label=getattr(view, '_repro_label', ''), **state(native))
        if error is not None:
            row['error'] = str(error)
        EVENTS.append(row)
        print('LOGISTICS_EPUB_AB_EVENT=' + json.dumps(row), flush=True)
    except Exception as error:
        print('LOGISTICS_EPUB_AB_DIAGNOSTIC_ERROR=' + str(error), flush=True)


def loaded(view):
    view._repro_load_count += 1
    view._repro_loaded.set()
    event('onload', view._impl.native)


async def passive_text(view, expected, timeout, seen):
    """One DOM read per native load event, without repeated JS polling."""
    deadline = asyncio.get_running_loop().time()+timeout
    last = None
    while True:
        remaining = deadline-asyncio.get_running_loop().time()
        if remaining <= 0:
            raise TimeoutError('Native-event wait expired; last body=' + repr(last))
        if view._repro_load_count == seen:
            await asyncio.wait_for(view._repro_loaded.wait(), remaining)
        view._repro_loaded.clear()
        seen = view._repro_load_count
        try:
            last = await asyncio.wait_for(view.evaluate_javascript(
                'String(document.body ? document.body.textContent || "" : "")'), min(5, remaining))
        except RuntimeError as error:
            if 'WKErrorDomain Code=5' not in str(error):
                raise
        else:
            if isinstance(last, str) and expected in last:
                return last


def html(text):
    return ('<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'">'
        '<style>body{font:16px sans-serif;padding:16px;margin:0}</style></head><body><p>' + text + '</p></body></html>')


async def observation(view, kind, mode, label):
    view._repro_label = label
    seen = view._repro_load_count
    view._repro_loaded.clear()
    expected = 'Synthetic chapter ' + label
    started = time.monotonic()
    event('request', view._impl.native)
    result = dict(label=label, kind=kind, mode=mode, deadline_seconds=30,
                  deadline_met=False, late_rendered=False)
    try:
        previous = getattr(view, '_chapter_bridge', None)
        if kind == 'bridge-awaited' and previous is not None:
            pending = []
            original_evaluate = view.evaluate_javascript
            def capture(script):
                result = original_evaluate(script)
                pending.append(result)
                return result
            event('dispose-request', view._impl.native)
            with patch.object(view, 'evaluate_javascript', side_effect=capture):
                previous.dispose()
            if len(pending) != 1:
                raise RuntimeError('Expected exactly one production disposal evaluation.')
            await asyncio.wait_for(pending[0], 5)
            event('dispose-complete', view._impl.native)
        # Both variants use the production chapter_view. The awaited variant
        # has completed the previous bridge's real cleanup before replacing HTML.
        chapter_view(html(expected), view)
        remaining = max(.001, 30-(time.monotonic()-started))
        if mode == 'poll':
            await wait_for_text(view, expected, timeout=remaining)
        else:
            await passive_text(view, expected, remaining, seen)
        result['deadline_met'] = True
    except Exception as error:
        result['error'] = str(error)[:400]
        result['at_deadline'] = state(view._impl.native)
        event('deadline-expired', view._impl.native)
        # Late completion is evidence only; deadline_met always remains false.
        try:
            await passive_text(view, expected, 60, max(0, view._repro_load_count-1))
            result['late_rendered'] = True
        except Exception as late:
            result['late_error'] = str(late)[:300]
    result['seconds'] = round(time.monotonic()-started, 4)
    result['final_native_state'] = state(view._impl.native)
    print('LOGISTICS_EPUB_AB_OBSERVATION=' + json.dumps(result), flush=True)
    return result


async def exercise(app):
    from importlib.metadata import version
    from rubicon.objc import ObjCClass, objc_method, py_from_ns
    from toga_iOS.widgets import webview
    observations = []
    report = dict(schema=1, suite='epub-loading-reproduction', diagnostic_only=True,
        canonical_native_acceptance=False, original_timeout_seconds=30,
        planned_observations=32, observations=observations,
        experiment='production-immediate-vs-awaited-disposal; crossed-with-poll-vs-native-event',
        packages={name:version(name) for name in ['toga-core','toga-iOS','rubicon-objc']},
        python=platform.python_version(), machine=platform.machine())
    import mobile
    report['source'] = json.loads(Path(mobile.__file__).with_name('source.json').read_text())
    report['ios_version'] = str(ObjCClass('NSProcessInfo').processInfo.operatingSystemVersionString)
    original_native = webview.TogaWebView
    original_loaded = ChapterBridge.loaded
    class ReproWebView(original_native):
        @objc_method
        def webView_didStartProvisionalNavigation_(self, webview, navigation) -> None:
            event('start', self)
        @objc_method
        def webView_didCommitNavigation_(self, webview, navigation) -> None:
            event('commit', self)
        @objc_method
        def webView_didFailProvisionalNavigation_withError_(self, webview, navigation, error) -> None:
            event('provisional-error', self, py_from_ns(error))
        @objc_method
        def webView_didFailNavigation_withError_(self, webview, navigation, error) -> None:
            event('load-error', self, py_from_ns(error))
        @objc_method
        def webViewWebContentProcessDidTerminate_(self, webview) -> None:
            event('web-process-terminated', self)
    def bridge_loaded(bridge, widget, **kwargs):
        original_loaded(bridge, widget, **kwargs)
        loaded(widget)
    sequence = [('bridge','poll'),('bridge-awaited','poll'),('bridge','passive'),('bridge-awaited','passive')]
    deadline = time.monotonic()+16*60
    try:
        with patch.object(webview, 'TogaWebView', ReproWebView), \
                patch.object(ChapterBridge, 'loaded', bridge_loaded):
            for round_number, pairs in enumerate([sequence, list(reversed(sequence)), sequence, list(reversed(sequence))], 1):
                for kind, mode in pairs:
                    if time.monotonic()+90 > deadline:
                        report['budget_exhausted'] = True
                        break
                    view = toga.WebView(style=Pack(flex=1))
                    view._repro_loaded = asyncio.Event()
                    view._repro_load_count = 0
                    view._repro_label = f'{round_number}-{kind}-{mode}-mount'
                    view.on_webview_load = loaded
                    app.container.add(view)
                    await asyncio.sleep(.2)
                    try:
                        for chapter in (1, 2):
                            observations.append(await observation(view, kind, mode,
                                f'{round_number}-{kind}-{mode}-{chapter}'))
                    finally:
                        bridge = getattr(view, '_chapter_bridge', None)
                        if bridge is not None:
                            bridge.dispose()
                        view.on_webview_load = None
                        view._impl.native.stopLoading()
                        app.container.remove(view)
                if report.get('budget_exhausted'):
                    break
    except Exception:
        report['experiment_error'] = traceback.format_exc()
        traceback.print_exc()
    report['events'] = EVENTS
    report['complete'] = len(observations) == report['planned_observations'] and not report.get('experiment_error')
    report['elapsed_seconds'] = round(time.monotonic()-START, 4)
    path = Path(app.paths.cache)/'logistics-epub-repro.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(report,indent=2)+'\n')
    temporary.replace(path)
    encoded = base64.b64encode(json.dumps(report).encode()).decode()
    chunks = [encoded[i:i+450] for i in range(0,len(encoded),450)]
    for index, chunk in enumerate(chunks):
        print('LOGISTICS_EPUB_AB_CHUNK=' + json.dumps(dict(index=index,count=len(chunks),data=chunk)), flush=True)
        await asyncio.sleep(.01)
    print('>>>>>>>>>> EXIT 0 <<<<<<<<<<', flush=True)
    await asyncio.sleep(.25)
    os._exit(0)


class ReproductionApp(toga.App):
    def startup(self):
        self.main_window = toga.MainWindow(title='EPUB loading diagnostic')
        self.container = toga.Box(style=Pack(direction=COLUMN, flex=1))
        self.main_window.content = self.container
        self.main_window.show()
    def on_running(self):
        start_native_check(self, exercise)


def main():
    ReproductionApp('Logistics Mobile', 'io.github.ispaure.logisticsmobile').main_loop()
