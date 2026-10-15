"""Isolated Qt Widgets iOS reuse experiment; never replaces the Toga app."""
# ruff: noqa: E402 -- Qt host and private storage must precede UI imports.
import base64
import faulthandler
import io
import json
import os
from pathlib import Path
import sys
import traceback
from zipfile import ZipFile

from PySide6.QtCore import QStandardPaths, QTimer, qVersion
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QTabWidget, QVBoxLayout, QWidget

app = QApplication(sys.argv)
app.setApplicationName('Logistics Qt Proof')
root = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)) / 'proof'
root.mkdir(parents=True, exist_ok=True)
(root / 'evidence.json').unlink(missing_ok=True)
crash_log = (root / 'crash.log').open('w')
faulthandler.enable(file=crash_log)
os.environ['COMMONUTILS_STORAGE_ROOT'] = str(root / 'common')
from commonUtils.runtime.platform.capabilities import register_qt_ui_host
register_qt_ui_host(app)
from commonUtils.configuration.layered import register_settings
from commonUtils.configuration.settings import settings_path
register_settings(settings_path(), root / 'settings.ini')
from commonUtils.ui.file_browser import FileBrowser
from commonUtils.ui.code_editor import CodeEdit
from commonUtils.ui.code_editor.syntax import SyntaxHighlighter
from commonUtils.ui.markdown.viewer import MarkdownViewer
from commonUtils.ui.workspaces.scoped_tabs import ScopedTabBar
from features.rclone.mobile.cloud import CloudClient

source = root / 'sample.py'
if not source.exists():
    source.write_text('# Existing CodeEdit and Pygments\ndef greet(name):\n    return f"Hello {name}"\n', encoding='utf-8')
markdown = root / 'sample.md'
markdown.write_text('# Logistics Qt iOS proof\n\nThis is the existing **Markdown reader**.\n\n## Second heading\n\n- Browser tabs\n- Highlighted editor\n- Native rclone bridge\n', encoding='utf-8')
(root / 'subfolder').mkdir(exist_ok=True)
(root / 'subfolder' / 'second.txt').write_text('Independent browser location\n', encoding='utf-8')
window = QTabWidget()
window.setWindowTitle('Logistics Qt Proof')
window.resize(390, 780)
browsers = QTabWidget()
browsers.setTabBar(ScopedTabBar(browsers, window, lambda: [browsers], lambda *args: False))
first = FileBrowser(root, calculate_folder_sizes=False, column_navigation=False)
second = FileBrowser(root / 'subfolder', calculate_folder_sizes=False, column_navigation=False)
browsers.addTab(first, 'Files 1')
browsers.addTab(second, 'Files 2')
window.addTab(browsers, 'Files')
editor_page = QWidget()
editor_layout = QVBoxLayout(editor_page)
editor = CodeEdit()
editor.setPlainText(source.read_text(encoding='utf-8'))
highlighter = SyntaxHighlighter(editor, language='python')
editor_layout.addWidget(editor)
save = QPushButton('Save private copy')
def save_text():
    temporary = source.with_suffix('.pending')
    temporary.write_text(editor.toPlainText(), encoding='utf-8')
    temporary.replace(source)
    editor.document().setModified(False)
save.clicked.connect(save_text)
editor_layout.addWidget(save)
window.addTab(editor_page, 'Editor')
reader = MarkdownViewer(markdown)
window.addTab(reader, 'Reader')
cloud_page = QWidget()
cloud_layout = QVBoxLayout(cloud_page)
cloud_status = QLabel('Synthetic memory connection only. No user credentials.')
cloud_status.setWordWrap(True)
cloud_layout.addWidget(cloud_status)
cloud_button = QPushButton('Test native rclone import / list / preview')
cloud_layout.addWidget(cloud_button)
cloud_layout.addStretch()
window.addTab(cloud_page, 'Rclone')

def cloud_check():
    client = CloudClient(library=os.environ.get('LOGISTICS_QT_CLOUD_LIBRARY'))
    package = io.BytesIO()
    with ZipFile(package, 'w') as archive:
        archive.writestr('proof.txt', '[proof]\ntype = memory\n')
    names = client.request('import', package=base64.b64encode(package.getvalue()).decode('ascii'), password='', package_name='Synthetic.zip', session_only=True)
    version = client.request('probe')
    entries = client.entries('proof', 'logistics-native-check')
    identity = client.connection_identity('proof')
    values = dict(remote='proof', path='logistics-native-check/fixture.txt', identity=identity)
    metadata = client.request('remote_stat', **values)
    data = base64.b64decode(client.request('remote_range', **values,
        expected=metadata['revision'], offset=0, count=metadata['size'])['data'], validate=True)
    assert 'proof' in names and entries and data == b'Native rclone fixture\n'
    client.clear()
    cloud_status.setText(f'Native rclone {version}: import, list and direct preview passed.')
    return {'version': version, 'entries': len(entries), 'preview_bytes': len(data)}

def cloud_clicked():
    try:
        cloud_check()
    except Exception as error:
        cloud_status.setText(str(error))
cloud_button.clicked.connect(cloud_clicked)

# Simulator evidence is written inside this separate app's private container.
def evidence():
    result = {'qt': qVersion(), 'platform': sys.platform, 'root': str(root), 'passed': []}
    try:
        assert browsers.count() == 2
        assert first.model.rowCount(first.model.index(str(root))) >= 3
        assert second.model.rowCount(second.model.index(str(root / 'subfolder'))) == 1
        assert first.model.index(str(source)).isValid()
        first.navigate(root / 'subfolder')
        browsers.setCurrentIndex(1)
        assert second.views.navigation_root != first.views.navigation_root
        browsers.setCurrentIndex(0)
        assert first.views.root == root / 'subfolder'
        first.navigation.back.click()
        assert first.views.root == root
        first.navigation.forward.click()
        assert first.views.root == root / 'subfolder'
        first.navigation.back.click()
        result['passed'].append('existing_file_browser_independent_tabs')
        window.setCurrentIndex(1)
        highlighter.rehighlight()
        assert editor.document().firstBlock().layout().formats()
        original = editor.toPlainText()
        editor.insertPlainText('# saved proof\n')
        save.click()
        assert source.read_text(encoding='utf-8') == editor.toPlainText()
        result['passed'].append('existing_code_editor_highlighting_save')
        editor.setPlainText(original)
        save.click()
        assert 'Second heading' in reader.browser.toPlainText()
        result['passed'].append('existing_markdown_reader')
        result['rclone'] = cloud_check()
        result['passed'].append('native_rclone_import_list_download_probe')
        for index, name in enumerate(('files', 'editor', 'reader', 'rclone')):
            window.setCurrentIndex(index)
            app.processEvents()
            window.grab().save(str(root / f'{name}.png'))
        window.setCurrentIndex(0)
    except Exception:
        result['error'] = traceback.format_exc()
    (root / 'evidence.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print('LOGISTICS_QT_PROOF ' + json.dumps(result), flush=True)
window.show()
QTimer.singleShot(2500, evidence)
app.exec()
