"""Isolated Android file replacement/reopen check on an explicit test directory."""
from io import BytesIO
import json
from pathlib import Path
import shutil
import traceback

import toga

BUNDLE = 'io.github.ispaure.logisticssdsaveqa'


class SaveProbe(toga.App):
    def startup(self):
        self.main_window = toga.MainWindow(title='SD save QA')
        self.main_window.content = toga.Label('Checking save and reopen…')
        self.main_window.show()
        self.loop.call_soon(self.check)

    def check(self):
        from services.documents.locations import MobileLocalFiles
        from features.text_editor.resources import LocalTextCopies
        cache = Path(self.paths.cache)
        report = dict(success=False, cases=[])
        root = None
        owned = False
        try:
            control = json.loads((cache / 'sd-save-control.json').read_text())
            root = Path(control['root'])
            root.mkdir()  # Refuse existing directories; cleanup owns only this allocation.
            owned = True
            provider = MobileLocalFiles(root)
            copies = LocalTextCopies(provider)
            from features.notebooks.notebook import Notebook, MAX_ARCHIVE
            from services.documents.storage import DocumentResource
            data = Notebook.new('Received sketch').to_bytes()
            DocumentResource.publish(provider, 'Received sketch.rmdoc', data, max_bytes=MAX_ARCHIVE)
            assert Notebook.read((root / 'Received sketch.rmdoc').read_bytes()).name == 'Received sketch'
            try:
                DocumentResource.publish(provider, 'Received sketch.rmdoc', b'collision', max_bytes=MAX_ARCHIVE)
            except FileExistsError:
                pass
            else:
                raise AssertionError('Creation overwrote an existing notebook')
            assert (root / 'Received sketch.rmdoc').read_bytes() == data
            report['cases'].append(dict(format='rmdoc', success=True, exclusive_creation=True))
            for suffix in ('txt', 'md'):
                name = 'document.' + suffix
                provider.create_file(name, BytesIO(b'initial'))
                reader = copies.open(name)
                case = dict(format=suffix, before=provider.entry(name)['revision'])
                try:
                    for text in ('first saved version', 'second saved version'):
                        reader = copies.save(reader, text)
                        reopened = copies.open(name)
                        assert reopened.text == text
                        assert reopened.revision == reader.revision
                    case['success'] = True
                except Exception:
                    case['success'] = False
                    case['error'] = traceback.format_exc()
                    try:
                        case['after'] = provider.entry(name)['revision']
                        case['disk_bytes'] = (root / name).read_text()
                    except Exception:
                        case['inspection_error'] = traceback.format_exc()
                report['cases'].append(case)
            report['success'] = all(case['success'] for case in report['cases'])
        except Exception:
            report['error'] = traceback.format_exc()
        finally:
            if owned:
                try:
                    shutil.rmtree(root)
                    report['test_directory_removed'] = True
                except Exception:
                    report['cleanup_error'] = traceback.format_exc()
            (cache / 'sd-save-result.json').write_text(json.dumps(report, indent=2))
            self.main_window.content.text = 'Finished; result saved.'


def main():
    return SaveProbe('SD save QA', BUNDLE)
