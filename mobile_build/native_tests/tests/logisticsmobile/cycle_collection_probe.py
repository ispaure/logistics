"""Disposable iOS reproduction of worker GC finalizing native constraints.

Run as a separate native probe, never as a release acceptance report. Set
LOGISTICS_CYCLE_COLLECTION_CONTROL=1 only to reproduce the unsafe automatic
collector; the default exercises the application's UI-loop collection owner.
"""
import asyncio
import gc
import json
import os
from pathlib import Path
import sys
import threading
import traceback
import weakref

import toga
from toga_iOS.app import PythonAppDelegate


class LogisticsSceneAppDelegate(PythonAppDelegate):
    pass


class CycleCollectionProbe(toga.App):
    def startup(self):
        self.main_window = toga.MainWindow(title='UI cycle collection probe')
        self.main_window.content = toga.Box(children=[toga.Label('Starting')])
        self.main_window.show()
        self.started = False

    def on_running(self):
        if not self.started:
            self.started = True
            self.loop.create_task(self.probe())

    async def probe(self):
        from mobile.cycle_collection import UICycleCollection
        from toga_iOS.constraints import Constraints
        automatic = os.environ.get('LOGISTICS_CYCLE_COLLECTION_CONTROL') == '1'
        report = dict(diagnostic_only=True, automatic_control=automatic,
                      success=False, finalizers=[], error='')
        original = Constraints._remove_constraints
        was_enabled, owner = gc.isenabled(), None
        retired = []

        def traced(constraints):
            # Normal route detachment also calls this method. Measure only
            # actual finalization of still-mounted nested constraints.
            if (sys._getframe(1).f_code.co_name == '__del__'
                    and constraints.container and constraints.container.native
                    and constraints.constraints_created):
                report['finalizers'].append(dict(
                    main=threading.current_thread() is threading.main_thread(),
                    thread=threading.current_thread().name))
            return original(constraints)

        Constraints._remove_constraints = traced
        try:
            gc.collect()
            gc.disable()
            for _ in range(8):
                box = toga.Box(children=[toga.Selection(items=['One', 'Two']),
                                         toga.TextInput(value='Synthetic'),
                                         toga.Button('Action')])
                scroll = toga.ScrollContainer(content=box)
                retired.extend((weakref.ref(box), weakref.ref(scroll)))
                self.main_window.content = scroll
                await asyncio.sleep(.02)
                self.main_window.content = toga.Box(children=[toga.Label('Next')])
                del box, scroll
            if not automatic:
                owner = UICycleCollection(self.loop, interval=.01)

            def allocate():
                if automatic:
                    gc.enable()
                # Trigger ordinary allocation pressure, not explicit worker GC.
                for _ in range(10000):
                    cycle = []
                    cycle.append(cycle)

            await asyncio.to_thread(allocate)
            gc.disable()
            for _ in range(100):
                if all(reference() is None for reference in retired):
                    break
                await asyncio.sleep(.01)
            background = sum(not row['main'] for row in report['finalizers'])
            report['background_finalizers'] = background
            assert all(reference() is None for reference in retired), 'Retired widgets remain alive.'
            assert report['finalizers'], 'No native constraint finalization was measured.'
            assert background == 0, report
            report['success'] = True
        except Exception:
            report['error'] = traceback.format_exc()
        finally:
            if owner is not None:
                owner.close()
            gc.collect()
            Constraints._remove_constraints = original
            if was_enabled:
                gc.enable()
            else:
                gc.disable()
        (Path(self.paths.cache) / 'cycle-collection-probe.json').write_text(
            json.dumps(report, indent=2))


def main():
    CycleCollectionProbe('UI cycle collection probe',
                         'io.github.ispaure.logisticscyclegcprobe').main_loop()


if __name__ == '__main__':
    main()
