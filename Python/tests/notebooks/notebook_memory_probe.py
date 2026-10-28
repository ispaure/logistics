"""Native desktop page-two/zoom bounds, raster fidelity and saved ink regression."""
import argparse
from hashlib import sha256
import json
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


def main(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    app = qt.QApplication.instance() or qt.QApplication([])
    report = dict(success=False, platform=platform.system(), surfaces=[], raster=[], samples=[])
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
                        probe.js(f'memoryProbe.stroke({tool},{ordinal % 3 + 1})')
                        probe.wait(lambda: probe.js('memoryProbe.done'), 'timed pen samples')
                        assert probe.js('memoryProbe.error') is None
                        probe.idle()
                    surface = probe.js('memoryProbe.surface()')
                    assert surface['width'] * surface['height'] <= 16 * 1024 * 1024
                    report['surfaces'].append(dict(zoom=zoom, page=index + 1, **surface))
                    report['samples'].append(dict(zoom=zoom, page=index + 1,
                        host_peak_rss_bytes=peak_rss_bytes(), **recovery_history_stats(probe.panel.editor)))
                    stats = report['samples'][-1]
                    assert stats['retained_strokes'] == stats['visible_strokes'], stats
                    assert stats['retained_native_blocks'] == stats['visible_strokes'], stats
                    (output / 'desktop-memory-progress.json').write_text(json.dumps(report, indent=2))
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
            probe.panel.web.grab().save(str(output / 'desktop-memory.png'))
            report.update(success=True, strokes_per_page=counts, source_unchanged_until_save=True,
                          native_mouse_page_two=True, page_switches_preserve_ink=True, saved_native_ink_identical=True,
                          recovery_enabled=True, recovery_reopened_ink_identical=True,
                          undo_redo_steps=36, undo_redo_ink_and_raster_identical=True,
                          history=recovery_history_stats(probe.panel.editor))
        finally:
            probe.close()
            app.processEvents()
            (output / 'desktop-memory-result.json').write_text(json.dumps(report, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    main(parser.parse_args().output)
