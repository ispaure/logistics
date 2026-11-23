"""Measure the Qt model, visible row and selection through the browser's folder path."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import json
import os
from pathlib import Path
import platform
import sys
from time import monotonic, sleep
from unittest.mock import patch

workspace, destination = map(Path, sys.argv[1:])
os.environ['COMMONUTILS_STORAGE_ROOT'] = str(workspace / 'isolated')
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from commonUtils.ui import pyside as qt
from desktop.file_browser import FileBrowserWindow
from features.application import registry

from commonUtils.ui.file_browser import model as models
from commonUtils.ui.file_browser.index_worker import _FolderScan

app = qt.QApplication([])
samples = []

def until(predicate):
    end = monotonic() + 30
    while True:
        app.processEvents()
        if predicate():
            return monotonic()
        if monotonic() > end:
            raise AssertionError('Timed out waiting for an actionable browser row')
        sleep(.002)

root = workspace / 'fixture'
(root / 'next').mkdir(parents=True)
(root / 'next' / 'select-next.txt').touch()
for size, count in [('small', 160), ('large', 6000)]:
    for child in (root / size, root / (size + '-leave')):
        child.mkdir()
        for index in range(count):
            (child / f'file-{index:05}.txt').touch()

with patch.object(registry, 'get_browser_extensions', return_value=[]):
    window = FileBrowserWindow(root)
    window.resize(900, 660)
    window.show()
    browser = window.file_browser
    model = browser.model
    browser.view_selector.setCurrentIndex(0)
    model.directoryLoaded.connect(lambda path: loaded.update({path: monotonic()}))
    loaded = {}
    until(lambda: not browser.busy and not browser.folder_busy)

    def select(path):
        view = browser.views.currentWidget()
        if browser.navigation.directory != path:
            return False
        idx = model.index(0, 0, view.rootIndex())
        if not idx.isValid() or idx.parent() != view.rootIndex() or not view.visualRect(idx).isValid():
            return False
        if Path(model.filePath(browser.views.source_index(idx))).parent != path:
            return False
        browser.views.select_source(browser.views.source_index(idx))
        return (view.selectionModel().isSelected(view.source_to_view(idx))
                and browser.selected_objects()[0].path.parent == path)

    original = models.format_datetime
    original_scan = _FolderScan.__call__
    for size, count in [('small', 160), ('large', 6000)]:
        for cold in (True, False, False):
            folder = root / size
            phases = {}
            def count_time(label, function):
                def measured(*args, **kwargs):
                    start = monotonic()
                    try:
                        return function(*args, **kwargs)
                    finally:
                        phases[label] = phases.get(label, 0) + monotonic() - start
                return measured

            with patch.object(models, 'format_datetime', count_time('timestamp_formatting_gui', original)), \
                    patch.object(model, 'item', count_time('model_item_gui', model.item)), \
                    patch.object(_FolderScan, '__call__', count_time('index_worker', original_scan)):
                loaded.pop(str(folder), None)
                start = monotonic()
                browser.navigate(folder)
                navigation_return = monotonic() - start
                first = until(lambda: select(folder)) - start
                count_complete = until(lambda: model.rowCount(browser.views.currentWidget().rootIndex()) == count) - start
                index_idle = until(lambda: not browser.folder_busy) - start
                enumeration_signal = loaded.get(str(folder))
            samples.append(dict(size=size, count=count, cold=cold, first=first,
                                folder_open_return=navigation_return, enumeration_complete=count_complete,
                                directory_loaded_signal=(enumeration_signal-start if enumeration_signal is not None else None),
                                index_idle=index_idle, phases=phases))
            browser.navigate(root / 'next')
            until(lambda: select(root / 'next') and not browser.folder_busy)

        leave_folder = root / (size + '-leave')
        for sample in samples[-3:]:
            browser.navigate(leave_folder)
            if sample['cold']:
                parent = model.browse_index(leave_folder)
                if model.canFetchMore(parent):
                    model.fetchMore(parent)
            next_folder = root / 'next'
            events = {}
            if sample['cold']:
                assert str(leave_folder) not in loaded
            leave = monotonic()

            def on_input():
                events.setdefault('input_dispatch', monotonic() - leave)
                if select(next_folder):
                    events['selection'] = monotonic() - leave
                else:
                    qt.QTimer.singleShot(1, on_input)

            # Timestamp selection inside the queued input turn. The outer
            # event pump can continue draining unrelated callbacks afterward.
            qt.QTimer.singleShot(0, on_input)
            browser.navigate(next_folder)
            events['navigation_return'] = monotonic() - leave
            sample['leave_pump_return'] = until(lambda: 'selection' in events) - leave
            sample['leave_to_action'] = events['selection']
            sample['leave_event_phases'] = events
            sample['left_loaded_at_selection'] = (str(leave_folder) in loaded
                and loaded[str(leave_folder)] - leave <= events['selection'])
            until(lambda: not browser.folder_busy)
            if sample['cold']:
                # Navigation away may cancel the native scan. QFileSystemModel
                # need not emit directoryLoaded for a relinquished folder.
                # Drain late events without requiring the old folder to finish.
                settle = qt.QEventLoop()
                qt.QTimer.singleShot(350, settle.quit)
                settle.exec()
                sample['left_loaded_after_navigation'] = str(leave_folder) in loaded
            current = browser.views.source_index(browser.views.currentWidget().currentIndex())
            assert Path(model.filePath(current)).name == 'select-next.txt'
    last = root / 'small' / 'file-00000.txt'
    browser.navigate(last.parent)
    until(lambda: model.browse_index(last).isValid())
    assert model.setData(model.browse_index(last), 'renamed-sample.txt')
    until(lambda: model.browse_index(last.with_name('renamed-sample.txt')).isValid()
          and not model.browse_index(last).isValid())
    window.close()
    app.processEvents()
destination.write_text(json.dumps(dict(platform=platform.platform(), rendering='Qt offscreen QWidget',
                                       samples=samples, rename_invalidation=True), indent=2))
