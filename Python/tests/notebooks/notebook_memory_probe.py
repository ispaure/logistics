"""Native desktop page-two/zoom bounds, raster fidelity and saved ink regression."""
import argparse
from hashlib import sha256
import json
import math
from pathlib import Path
import platform

from commonUtils.ui import pyside as qt
from commonUtils.runtime.resources.local import LocalFiles
from logistics_build.build_retention import scratch
from services.documents.storage import DocumentResource
from features.notebooks.notebook import Notebook, MAX_ARCHIVE
from features.notebooks.storage import NotebookDocument
from Python.tests.notebooks.notebook_desktop_stress_probe import Probe
from mobile_build.native_tests.tests.logisticsmobile.notebook_memory_checks import INSTALL, ink_signature, recovery_history_stats
from tests.notebooks.process_memory import process_tree_memory, record_sample, finish_report


def peak_rss_bytes():
    """Measure this host process consistently; renderer children are separate."""
    if platform.system() == 'Windows':
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD),
                        *[(name, ctypes.c_size_t) for name in (
                            'PeakWorkingSetSize', 'WorkingSetSize', 'QuotaPeakPagedPoolUsage',
                            'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage',
                            'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage')]]

        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        query = ctypes.WinDLL('psapi', use_last_error=True).GetProcessMemoryInfo
        query.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        if not query(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            raise ctypes.WinError(ctypes.get_last_error())
        return counters.PeakWorkingSetSize
    import resource
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value if platform.system() == 'Darwin' else value * 1024


def main(output, *, max_process_tree_mib=None, max_remount_growth_mib=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    app = qt.QApplication.instance() or qt.QApplication([])
    report = dict(success=False, platform=platform.system(), surfaces=[], raster=[], samples=[], remounts=[],
                  memory_limits=dict(process_tree_mib=max_process_tree_mib, remount_growth_mib=max_remount_growth_mib))
    def memory_sample():
        sample = process_tree_memory()
        renderer = int(probe.panel.web.page().renderProcessPid())
        return record_sample(report, sample, renderer, max_process_tree_mib)
    with scratch() as root:
        probe = Probe(root)
        try:
            book = Notebook.new('Desktop page two memory QA')
            for _ in range(3):
                book.add_page()
            source = root / 'original.rmdoc'
            source.write_bytes(book.to_bytes())
            source_hash = sha256(source.read_bytes()).hexdigest()
            resource_ = DocumentResource(LocalFiles(root), source.name, max_bytes=MAX_ARCHIVE)
            probe.panel.open_resource(NotebookDocument(Notebook.read(resource_.read()), resource=resource_,
                                                       recovery=probe.panel.repository))
            probe.ready()
            probe.js(INSTALL)
            tools = list(probe.panel.state()['tools'].values())
            for zoom in ('page', '1', '1.5', '2', '4', 'page'):
                probe.js('memoryProbe.zoom(' + json.dumps(zoom) + ')')
                probe.idle()
                for index in range(4):
                    signature = ink_signature(probe.panel.editor.notebook)
                    writes = probe.js('memoryProbe.writes')
                    probe.action('page', index=index)
                    assert probe.js('memoryProbe.writes') == writes
                    assert ink_signature(probe.panel.editor.notebook) == signature
                    for ordinal, tool in enumerate(tools):
                        before_stroke = probe.count()
                        probe.js(f'memoryProbe.stroke({tool},{ordinal % 3 + 1})')
                        probe.wait(lambda: probe.js('memoryProbe.done'), 'timed pen samples')
                        assert probe.js('memoryProbe.error') is None
                        probe.idle(layout=False)
                        assert probe.count() == before_stroke + 1, dict(tool=tool, expected=before_stroke + 1,
                            actual=probe.count(), browser=probe.js("({width:$('width').value,status:$('status').textContent})"))
                    surface = probe.js('memoryProbe.surface()')
                    assert surface['width'] * surface['height'] <= 16 * 1024 * 1024
                    report['surfaces'].append(dict(zoom=zoom, page=index + 1, **surface))
                    report['samples'].append(dict(zoom=zoom, page=index + 1,
                        host_peak_rss_bytes=peak_rss_bytes(), **recovery_history_stats(probe.panel.editor)))
                    stats = report['samples'][-1]
                    assert stats['retained_strokes'] == stats['visible_strokes'], stats
                    assert stats['retained_native_blocks'] == stats['visible_strokes'], stats
                    (output / 'desktop-memory-progress.json').write_text(json.dumps(report, indent=2))
                report['samples'][-1]['process_tree'] = memory_sample()
                if zoom in ('page', '2'):
                    probe.js('memoryProbe.raster()')
                    probe.wait(lambda: probe.js('memoryProbe.rasterDone'), 'zoom raster round trip')
                    assert probe.js('memoryProbe.rasterError') is None
                    pixels = probe.js('memoryProbe.rasterResult')
                    assert pixels['inkPixels'] > 0 and pixels['differentPixels'] == 0, pixels
                    report['raster'].append(dict(zoom=zoom, **pixels))
            # Native OS mouse input on page two still enters the same queue.
            probe.action('page', index=1)
            probe.stroke(samples=60, pace_ms=5)
            probe.idle()
            book = probe.panel.editor.notebook
            counts = [len(book.page(i).strokes) for i in range(4)]
            assert counts == [54, 55, 54, 54], counts
            expected = ink_signature(book)
            probe.js('(()=>{draw();memoryProbe.historyRaster=canvas.toDataURL();return true})()')
            for _ in range(36):
                probe.action('undo')
            assert sum(len(book.page(i).strokes) for i in range(4)) == 217 - 36
            for _ in range(36):
                probe.action('redo')
            probe.action('page', index=1)
            assert ink_signature(book) == expected
            assert probe.js('(()=>{draw();return canvas.toDataURL()===memoryProbe.historyRaster})()')
            assert ink_signature(probe.panel.repository.open(probe.panel.document.key)) == expected
            assert sha256(source.read_bytes()).hexdigest() == source_hash
            probe.action('save')
            assert ink_signature(Notebook.read(source.read_bytes())) == expected
            destination = output / 'desktop-memory.rmdoc'
            destination.write_bytes(book.to_bytes())
            assert ink_signature(Notebook.read(destination.read_bytes())) == expected
            history = recovery_history_stats(probe.panel.editor)
            # Recreate the complete workspace/WebEngine view, rather than only
            # changing pages in a retained editor. Warm one remount before the
            # baseline; report current RSS, including Chromium descendants.
            for index in range(7):
                probe.close()
                qt.QCoreApplication.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
                probe = Probe(root)
                probe.panel.open_resource(NotebookDocument(Notebook.read(destination.read_bytes())))
                probe.ready()
                assert ink_signature(probe.panel.editor.notebook) == expected
                sample = memory_sample()
                report['remounts'].append(dict(remount=index, **sample))
                growth = sample['rss_bytes'] - report['remounts'][0]['rss_bytes']
                if max_remount_growth_mib is not None:
                    assert growth <= max_remount_growth_mib * 1024 ** 2, dict(growth_bytes=growth, **sample)
                (output / 'desktop-memory-progress.json').write_text(json.dumps(report, indent=2))
            probe.panel.web.grab().save(str(output / 'desktop-memory.png'))
            report.update(success=True, strokes_per_page=counts, source_unchanged_until_save=True,
                          native_mouse_page_two=True, page_switches_preserve_ink=True, saved_native_ink_identical=True,
                          recovery_enabled=True, recovery_reopened_ink_identical=True,
                          undo_redo_steps=36, undo_redo_ink_and_raster_identical=True,
                          history=history,
                          remount_growth_bytes=report['remounts'][-1]['rss_bytes'] - report['remounts'][0]['rss_bytes'])
        except BaseException as error:
            report['error'] = repr(error)
            raise
        finally:
            finish_report(output / 'desktop-memory-result.json', report,
                          lambda: (probe.close(), app.processEvents()))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--max-process-tree-mib', type=float,
                        help='Optional current RSS ceiling for the probe and its renderer descendants on a controlled host.')
    parser.add_argument('--max-remount-growth-mib', type=float,
                        help='Optional RSS growth ceiling after a warm remount; six further remounts retain exact saved ink.')
    args = parser.parse_args()
    for value in (args.max_process_tree_mib, args.max_remount_growth_mib):
        if value is not None and (not math.isfinite(value) or value <= 0):
            parser.error('Memory limits must be finite and positive')
    main(args.output, max_process_tree_mib=args.max_process_tree_mib,
         max_remount_growth_mib=args.max_remount_growth_mib)
