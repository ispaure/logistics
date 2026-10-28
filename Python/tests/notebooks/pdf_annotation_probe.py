"""Native desktop PDF menu conversion, background display and saved annotation."""
import argparse
import json
from pathlib import Path
import traceback
from unittest.mock import patch

from commonUtils.ui import pyside as qt
from logistics_build.build_retention import scratch
from features.notebooks.notebook import Notebook
from features.notebooks.ui.workspace import NotebookWindow
from features.pdf.ui.reader import open_pdf
from Python.tests.readers.test_pdf_reader import pdf_bytes
from Python.tests.notebooks.notebook_desktop_stress_probe import Probe


def main(output):
    output.mkdir(parents=True, exist_ok=True)
    app = qt.QApplication.instance() or qt.QApplication([])
    report = dict(success=False, backend=app.platformName())
    with scratch() as root:
        reader = probe = None
        try:
            source = root / 'paper.pdf'
            original = pdf_bytes()
            source.write_bytes(original)
            reader = open_pdf(source)
            reader.show()
            reader.actions_menu.actions()[0].trigger()
            window, = [w for w in app.topLevelWidgets() if isinstance(w, NotebookWindow)]
            probe = Probe.__new__(Probe)
            probe.window_states, probe.window, probe.panel = [], window, window.centralWidget()
            window.show()
            window.raise_()
            window.activateWindow()
            probe.ready()
            probe.wait(lambda: probe.js("!$('pdfBackground').hidden && $('pdfBackground').naturalWidth>0"), 'PDF background')
            first = probe.js("$('pdfBackground').src")
            probe.action('page', index=1)
            assert probe.js("$('pdfBackground').src") != first
            probe.stroke(samples=40, pace_ms=2)
            probe.idle()
            assert probe.count() == 1
            probe.action('save')
            saved = source.with_suffix('.rmdoc').read_bytes()
            reopened = Notebook.read(saved)
            assert len(reopened.page(1).strokes) == 1
            assert reopened.members[reopened.id + '.pdf'] == original
            assert source.read_bytes() == original
            with patch.object(qt.QMessageBox, 'warning') as warning:
                reader.actions_menu.actions()[0].trigger()
                assert warning.call_count == 1
                assert 'already exists' in warning.call_args.args[-1]
            assert source.with_suffix('.rmdoc').read_bytes() == saved
            window.grab().save(str(output / 'desktop.png'))
            report.update(success=True, menu_conversion=True, distinct_page_backgrounds=True,
                          native_mouse_annotation=True, saved_ink_readback=True, collision_popup=True)
        except BaseException:
            report['error'] = traceback.format_exc()
        finally:
            if probe is not None:
                probe.close()
            if reader is not None:
                reader.close()
            qt.QCoreApplication.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
    (output / 'result.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report), flush=True)
    return int(not report['success'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    raise SystemExit(main(parser.parse_args().output))
