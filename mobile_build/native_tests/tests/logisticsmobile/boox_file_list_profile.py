"""QA-only paired BOOX benchmark; requires the original browser and Java collector.

Install only in a disposable application ID. Data is synthetic; no storage,
credentials, network or production launchers are involved.
"""
import asyncio
import cProfile
from io import StringIO
import json
from pathlib import Path
import pstats
from time import perf_counter
from types import SimpleNamespace
import traceback

import toga
from toga.style import Pack
from java import dynamic_proxy, jclass

from mobile.browser_ui import FileBrowser
from mobile.legacy_browser_ui import FileBrowser as OriginalBrowser


class Probe(toga.App):
    def startup(self):
        from commonUtils.ui.native.event_loop import bind_cooperative_loop
        bind_cooperative_loop(self.loop)
        from mobile.appearance import install_appearance
        install_appearance(self)
        self.active_host = True
        self.body = toga.Box(style=Pack(flex=1))
        self.routes = SimpleNamespace(body=lambda: self.body)
        self.main_window = toga.MainWindow(title='BOOX file-list profiling', content=self.body)
        self.main_window.show()
        self.provider = SimpleNamespace(root=Path('/synthetic'), relative=lambda path: path)
        self.collector_class = jclass('io.github.ispaure.logisticsmobile.FileListBenchmark')
        self.report = dict(success=False, opening=[], scrolling=[], progress='starting',
            appearance='Normal system theme with production appearance hooks; no forced monochrome override',
            methodology='Paired implementations in one QA process; synthetic data; opening excludes provider I/O and app startup; steady-state scrolling waits for all 200 old rows. Android frame metrics do not measure physical E Ink panel refresh.')
        self.output = Path(self.paths.cache) / 'boox-file-list-profile'
        self.output.mkdir(exist_ok=True)
        self.save()

    def on_running(self):
        if not getattr(self, 'measuring', False):
            self.measuring = True
            self.loop.create_task(self.measure())

    def save(self):
        (self.output / 'result.json').write_text(json.dumps(self.report, indent=2))

    def progress(self, text):
        self.report['progress'] = text
        self.save()
        print('LIST_PROFILE_PROGRESS=' + text, flush=True)

    async def draw_after(self, work):
        future = self.loop.create_future()
        native = self.body._impl.native
        class Draw(dynamic_proxy(jclass('android.view.ViewTreeObserver$OnDrawListener'))):
            def onDraw(listener):
                if not future.done():
                    future.set_result(perf_counter())
        observer = native.getViewTreeObserver()
        listener = Draw()
        observer.addOnDrawListener(listener)
        start = perf_counter()
        try:
            work()
            callback = perf_counter() - start
            native.invalidate()
            drawn = await asyncio.wait_for(future, 15)
            return dict(callback_ms=callback * 1000, next_draw_ms=(drawn - start) * 1000)
        finally:
            if observer.isAlive():
                observer.removeOnDrawListener(listener)

    async def mount(self, kind):
        cls = OriginalBrowser if kind == 'original' else FileBrowser
        started = perf_counter()
        browser = cls(preview=False)
        view = browser.scroll_container()
        browser._profile_construct_ms = (perf_counter() - started) * 1000
        self.body.add(view)
        await asyncio.sleep(.35)
        return browser, view

    async def retire(self, browser, view):
        browser.stop()
        if view in self.body.children:
            self.body.remove(view)
        await browser.close()
        await asyncio.sleep(.2)

    def rows(self, count):
        return [dict(path=f'file-{i:05d}.md', name=f'file-{i:05d}.md', directory=False)
                for i in range(count)]

    async def opening(self, kind, count, trial, profiled=False):
        self.progress(f'Opening {kind}, {count} files, trial {trial}')
        browser, view = await self.mount(kind)
        rows = self.rows(count)
        profiler = cProfile.Profile() if profiled else None
        def work():
            if profiler:
                profiler.enable()
            try:
                browser.set_entries(self.provider, '', rows)
            finally:
                if profiler:
                    profiler.disable()
        try:
            stats = await self.draw_after(work)
            stats.update(kind=kind, count=count, trial=trial, profiled=profiled,
                         construction_ms=browser._profile_construct_ms,
                         native_views=int(self.collector_class.countViews(self.body._impl.native)),
                         toga_row_buttons=len(browser.buttons))
            self.report['opening'].append(stats)
            if profiler:
                name = kind + '-200-cprofile'
                profiler.dump_stats(str(self.output / (name + '.prof')))
                stream = StringIO()
                pstats.Stats(profiler, stream=stream).strip_dirs().sort_stats('cumulative').print_stats(35)
                (self.output / (name + '.txt')).write_text(stream.getvalue())
            self.save()
        finally:
            await self.retire(browser, view)

    async def scrolling(self, kind):
        self.progress('Preparing steady-state scrolling: ' + kind)
        browser, view = await self.mount(kind)
        native = view._impl.native if kind == 'original' else browser.native_list._impl.native
        collector = self.collector_class(self._impl.native.getWindow())
        try:
            start = perf_counter()
            browser.set_entries(self.provider, '', self.rows(200))
            # Old progressive population must finish before comparing scrolling
            # over equal content. New lists publish all records immediately.
            deadline = self.loop.time() + 120
            while kind == 'original' and len(browser.buttons) < 200:
                if self.loop.time() > deadline:
                    raise TimeoutError('Original browser did not finish 200 rows within 120 seconds')
                self.progress(f'Preparing original scroll: {len(browser.buttons)}/200 rows')
                await asyncio.sleep(1)
            ready_ms = (perf_counter() - start) * 1000
            await asyncio.sleep(.5)
            for trial in range(3):
                self.progress(f'Steady-state scroll {kind}, trial {trial}')
                if kind == 'original':
                    view.vertical_position = 0
                else:
                    browser.native_list.scroll_to_top()
                await asyncio.sleep(.4)
                collector.start()
                collector.swipes(native, 4)
                await asyncio.sleep(3.8)
                collector.stop()
                stats = json.loads(str(collector.report()))
                position = int(native.getScrollY()) if kind == 'original' else int(native.getFirstVisiblePosition())
                if position <= 0 or stats['frames'] == 0:
                    raise AssertionError('Native swipe did not scroll: ' + repr((kind, position, stats)))
                stats.update(kind=kind, count=200, trial=trial, all_rows_ready_ms=ready_ms,
                    final_scroll_position=position,
                    native_views=int(self.collector_class.countViews(self.body._impl.native)),
                    visible_rows=None if kind == 'original' else int(native.getChildCount()),
                    ready_row_records=len(browser.buttons) if kind == 'original' else len(browser.native_list.data))
                self.report['scrolling'].append(stats)
                self.save()
        finally:
            collector.dispose()
            await self.retire(browser, view)

    async def measure(self):
        try:
            from android.os import Build
            self.report.update(device=str(Build.MODEL), sdk=int(Build.VERSION.SDK_INT),
                refresh_rate_hz=float(self._impl.native.getWindowManager().getDefaultDisplay().getRefreshRate()))
            await asyncio.sleep(1)
            # One excluded warmup per implementation warms JNI/image/import paths.
            for kind in ('original', 'recycled'):
                await self.opening(kind, 40, -1)
            for count in (40, 200, 1000):
                for trial in range(5):
                    order = ('original', 'recycled') if trial % 2 == 0 else ('recycled', 'original')
                    for kind in order:
                        await self.opening(kind, count, trial)
            for kind in ('original', 'recycled'):
                await self.scrolling(kind)
            for kind in ('original', 'recycled'):
                await self.opening(kind, 200, 0, profiled=True)
            self.report['success'] = True
            self.progress('complete')
        except Exception:
            self.report['error'] = traceback.format_exc()
            self.progress('failed')
        self.save()


def main():
    return Probe('BOOX file-list profiling', 'io.github.ispaure.logisticsmobile.listqa')
