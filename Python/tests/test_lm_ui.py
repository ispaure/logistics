"""Real asynchronous HTTP and Qt ownership checks, using a local fixture server."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
from time import monotonic, sleep
from unittest.mock import patch

from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from PySide6.QtTest import QTest
from features.lm.domain import conversation, message
from features.lm.page import LMPage, ProfilesDialog
from features.lm.storage import Store


SETTINGS = dict(context_tokens=8192, max_tokens=1024, temperature=None, top_p=None, system_prompt='Be helpful.')


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.server.gets.append(self.path)
        if self.server.mode == 'auth':
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b'{"error":"secret-session-token"}')
            return
        if self.server.mode == 'redirect':
            self.send_response(302)
            self.send_header('Location', self.server.url + '/redirected')
            self.end_headers()
            return
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(b'{"data":[{"id":"fixture-model"}]}')

    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.server.requests.append(data)
        if self.server.mode.startswith('reject_'):
            self.send_response(400)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            reason = ('No models loaded. secret-session-token' if self.server.mode == 'reject_empty'
                      else 'Unrecognized request containing secret-session-token')
            self.wfile.write(json.dumps({'error': {'message': reason}}).encode())
            return
        self.send_response(200)
        if self.server.mode.startswith('tools'):
            tool_reply = not any(m['role'] == 'tool' for m in data['messages']) or self.server.mode == 'tools_forever'
            if tool_reply:
                name = 'read_file' if self.server.mode != 'tools_unknown' else 'run_command'
                args = json.dumps(dict(path='main.py', start_line=1, end_line=2))
                if self.server.mode == 'tools_bad_path':
                    args = json.dumps(dict(path='../secret', start_line=1, end_line=2))
                call = dict(id='read-1', type='function', function=dict(name=name, arguments=args))
                if self.server.mode == 'tools_json':
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'choices': [{'message': {'content': None, 'tool_calls': [call]},
                                                             'finish_reason': 'tool_calls'}]}).encode())
                else:
                    self.send_header('Content-Type', 'text/event-stream')
                    self.end_headers()
                    for fragment in (dict(index=0, id='read-1', type='function', function=dict(name=name, arguments=args[:10])),
                                     dict(index=0, function=dict(arguments=args[10:]))):
                        event = {'choices': [{'delta': {'tool_calls': [fragment]}, 'finish_reason': None}]}
                        self.wfile.write(('data: ' + json.dumps(event) + '\n\n').encode())
                    self.wfile.write(b'data: {"choices":[{"delta":{},"finish_reason":"tool_calls"}]}\n\ndata: [DONE]\n\n')
                return
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"choices":[{"message":{"content":"main.py:1 contains the project value."},"finish_reason":"stop"}]}')
            return
        if self.server.mode == 'json':
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"choices":[{"message":{"content":"Plain response"},"finish_reason":"stop"}]}')
            return
        self.send_header('Content-Type', 'text/event-stream')
        self.end_headers()
        event = json.dumps({'choices': [{'delta': {'content': 'Bonjour 🌍'}, 'finish_reason': None}]}, ensure_ascii=False)
        try:
            if self.server.mode == 'malformed_after_text':
                self.wfile.write(('data: ' + event + '\n\ndata: {invalid}\n\n').encode())
                self.wfile.flush()
                return
            self.wfile.write(('data: ' + event + '\r\n\r\n').encode())
            self.wfile.flush()
            if self.server.mode == 'slow':
                self.server.release.wait(3)
            if self.server.mode != 'truncated':
                self.wfile.write(b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n')
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass


class LMUITests(QtTestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.QApplication.instance() or qt.QApplication([])

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        self.server.url = f'http://127.0.0.1:{self.server.server_port}/v1'
        self.server.mode = 'normal'
        self.server.requests = []
        self.server.gets = []
        self.server.release = threading.Event()
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        self.store = Store(self.temp.name)
        original = self.store.profiles()
        self.store.save_profiles([dict(id='fixture', name='Fixture', base_url=self.server.url)], original)
        self.page = LMPage(store=self.store)
        self.addCleanup(self.close_page)

    def close_page(self):
        self.server.release.set()
        self.page.client.cancel()
        self.until(lambda: not self.page.client.busy)
        self.page.prepare_close()
        self.page.deleteLater()
        self.app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)

    def stop_server(self):
        self.server.release.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def until(self, condition):
        deadline = monotonic() + 5
        while not condition():
            self.assertLess(monotonic(), deadline, 'Qt/HTTP fixture did not finish')
            self.app.processEvents()
            sleep(.005)
        self.app.processEvents()

    def chat(self, text='Hello'):
        if self.page.data is None:
            self.page.new_conversation()
        self.page.model.setCurrentText('fixture-model')
        self.page.composer.setPlainText(text)
        self.page.send()

    def test_injected_project_context_does_not_discover_ide_widgets(self):
        from types import SimpleNamespace
        project = object()
        self.page.project_context = SimpleNamespace(
            projects=lambda: {'fixture': project}, buffers=lambda selected: ({'file.py': 'unsaved'}, []))
        with patch('features.lm.ui.page.registered_projects', side_effect=AssertionError('IDE discovery')), \
             patch('features.lm.ui.page.editor_context', side_effect=AssertionError('IDE buffers')):
            self.assertEqual(self.page.context_projects(), {'fixture': project})
            self.assertEqual(self.page.context_buffers(project), ({'file.py': 'unsaved'}, []))

    def configure_code(self):
        from features.ide.projects import Project
        project = Project('Project fixture', self.temp.name, id='project-fixture')
        (Path(self.temp.name) / 'main.py').write_text('disk value\nsecond line\n')
        registered = patch('features.lm.ui.page.registered_projects', return_value={project.id: project})
        snapshots = patch('features.lm.ui.page.editor_context', return_value=({'main.py': 'unsaved value\nsecond line\n'},
                                                                         [('main.py', 1, 'unsaved value')]))
        registered.start()
        snapshots.start()
        self.addCleanup(registered.stop)
        self.addCleanup(snapshots.stop)
        self.page.new_conversation()
        self.page.mode.setCurrentIndex(1)
        self.page.project_picker.setCurrentIndex(self.page.project_picker.findData(project.id))
        return project

    def test_code_tools_stream_and_json_feed_snapshot_back_then_save_answer(self):
        self.configure_code()
        for mode in ('tools', 'tools_json'):
            with self.subTest(mode=mode):
                self.server.mode = mode
                self.chat('Explain main.py')
                self.until(lambda: not self.page.client.busy)
                self.assertEqual(self.page.data['messages'][-1]['status'], 'complete')
                request = self.server.requests[-1]
                self.assertEqual(request['messages'][-1]['role'], 'tool')
                self.assertIn('unsaved value', request['messages'][-1]['content'])
                self.assertEqual(request['messages'][-2]['tool_calls'][0]['id'], 'read-1')
                self.assertIn('tools', request)
                saved = self.store.load(self.page.data['id'])
                self.assertEqual(saved['mode'], 'code')
                self.assertEqual(saved['project_id'], 'project-fixture')
                self.assertEqual(saved['messages'][-1]['response']['tool_steps'][0]['name'], 'read_file')
                self.assertEqual((Path(self.temp.name) / 'main.py').read_text(), 'disk value\nsecond line\n')

    def test_code_invalid_tool_and_outside_path_return_errors_without_execution(self):
        self.configure_code()
        for mode in ('tools_unknown', 'tools_bad_path'):
            self.server.mode = mode
            self.chat()
            self.until(lambda: not self.page.client.busy)
            result = json.loads(self.server.requests[-1]['messages'][-1]['content'])
            self.assertIn('error', result)
            self.assertEqual(self.page.data['messages'][-1]['status'], 'complete')

    def test_code_limits_repeated_tools_and_chat_rejects_them(self):
        self.configure_code()
        self.server.mode = 'tools_forever'
        self.chat()
        self.until(lambda: not self.page.client.busy)
        self.assertEqual(self.page.data['messages'][-1]['status'], 'failed')
        self.assertIn('tool limit', self.page.status.text())
        count = len(self.server.requests)
        self.page.mode.setCurrentIndex(0)
        self.chat()
        self.until(lambda: not self.page.client.busy)
        self.assertEqual(len(self.server.requests), count + 1)
        self.assertNotIn('tools', self.server.requests[-1])
        self.assertEqual(self.page.data['messages'][-1]['status'], 'failed')

    def test_code_attachments_and_project_choice_survive_reopen(self):
        self.configure_code()
        self.page.attach_selection()
        self.assertIn('IDE selection: main.py', self.page.composer.toPlainText())
        with patch('features.lm.ui.page.qt.QFileDialog.getOpenFileNames', return_value=([str(Path(self.temp.name) / 'main.py')], '')):
            self.page.attach_files()
        self.assertIn('Project file: main.py (editor snapshot)', self.page.composer.toPlainText())
        self.assertTrue(self.page.persist())
        key = self.page.data['id']
        self.page.new_conversation()
        self.page.open_conversation(key)
        self.assertEqual(self.page.mode.currentData(), 'code')
        self.assertEqual(self.page.project_picker.currentData(), 'project-fixture')
        self.assertIn('unsaved value', self.page.composer.toPlainText())

    def test_code_uses_real_ide_registration_buffer_and_selection(self):
        from features.ide.ui.page import IDEPage
        from features.ide.projects import Project
        from features.lm.ide_context import registered_projects, editor_context
        root = Path(self.temp.name) / 'source'
        root.mkdir()
        path = root / 'main.py'
        path.write_text('disk value\n')
        project = Project('Live project', str(root), autosave='off')
        ide = IDEPage(store_path=Path(self.temp.name) / 'ide.json')
        def cleanup_ide():
            for workspace in ide.views:
                for document in workspace.documents.values():
                    document.document().setModified(False)
            ide.prepare_close()
            self.until(lambda: all(workspace.worker is None for workspace in ide.views))
            ide.deleteLater()
            self.app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
        self.addCleanup(cleanup_ide)
        ide.store.projects[project.id] = project
        workspace = ide.open_project(project)
        workspace.open_path(path)
        self.until(lambda: bool(workspace.documents) and workspace.worker is None)
        document = next(iter(workspace.documents.values()))
        document.setPlainText('unsaved live value\n')
        cursor = document.textCursor()
        cursor.select(qt.QTextCursor.SelectionType.LineUnderCursor)
        document.setTextCursor(cursor)
        self.assertIn(project.id, registered_projects(self.page))
        buffers, selections = editor_context(self.page, project)
        self.assertEqual(buffers['main.py'], 'unsaved live value\n')
        self.assertEqual(selections, [('main.py', 1, 'unsaved live value')])
        self.page.new_conversation()
        self.page.mode.setCurrentIndex(1)
        self.page.project_picker.setCurrentIndex(self.page.project_picker.findData(project.id))
        self.page.attach_selection()
        self.assertIn('unsaved live value', self.page.composer.toPlainText())
        self.server.mode = 'tools'
        self.chat('Explain main.py')
        self.until(lambda: not self.page.client.busy)
        self.assertIn('unsaved live value', self.server.requests[-1]['messages'][-1]['content'])
        self.assertEqual(path.read_text(), 'disk value\n')

    def test_code_result_overflow_stops_before_next_request(self):
        self.configure_code()
        self.server.mode = 'tools'
        with patch('features.lm.project_tools.ProjectTools.execute', return_value='x' * 30000):
            self.chat()
            self.until(lambda: not self.page.client.busy)
        self.assertEqual(len(self.server.requests), 1)
        self.assertEqual(self.page.data['messages'][-1]['status'], 'failed')
        self.assertIn('context limit', self.page.status.text())

    def test_code_missing_project_blocks_send_and_preserves_draft(self):
        self.configure_code()
        self.page.project_picker.setCurrentIndex(0)
        self.chat('Keep this draft')
        self.assertEqual(self.server.requests, [])
        self.assertEqual(self.page.composer.toPlainText(), 'Keep this draft')
        self.assertEqual(self.page.data['messages'], [])

    def test_stop_and_close_wait_for_read_only_worker(self):
        self.configure_code()
        self.server.mode = 'tools'
        entered, release = threading.Event(), threading.Event()
        def blocked(*args, cancelled, **kwargs):
            entered.set()
            release.wait(2)
            return '{"text":"read result"}'
        with patch('features.lm.project_tools.ProjectTools.execute', side_effect=blocked):
            try:
                self.chat()
                self.until(entered.is_set)
                self.assertTrue(self.page.client.busy)
                self.assertFalse(self.page.prepare_close())
                release.set()
                self.until(lambda: not self.page.client.busy)
                self.assertEqual(len(self.server.requests), 1)
                self.assertEqual(self.page.data['messages'][-1]['status'], 'cancelled')
                self.assertTrue(self.page.prepare_close())
            finally:
                release.set()

    def test_chat_and_code_tabs_have_separate_lists_and_restore_drafts(self):
        self.page.new_conversation()
        chat_key = self.page.data['id']
        self.page.composer.setPlainText('Chat draft')
        self.page.mode.setCurrentIndex(1)
        code_key = self.page.data['id']
        self.assertNotEqual(code_key, chat_key)
        self.assertEqual(self.page.data['mode'], 'code')
        self.page.composer.setPlainText('Code draft')
        visible = lambda: {item.data(0, qt.Qt.ItemDataRole.UserRole) for item in self.page.tree_items()
                           if item.data(0, qt.Qt.ItemDataRole.UserRole)}
        self.assertEqual(visible(), {code_key})
        self.page.mode.setCurrentIndex(0)
        self.assertEqual(self.page.data['id'], chat_key)
        self.assertEqual(self.page.composer.toPlainText(), 'Chat draft')
        self.assertEqual(visible(), {chat_key})
        self.page.mode.setCurrentIndex(1)
        self.assertEqual(self.page.data['id'], code_key)
        self.assertEqual(self.page.composer.toPlainText(), 'Code draft')
        self.page.new_conversation()
        self.assertEqual(self.page.data['mode'], 'code')
        self.assertEqual(self.store.load(chat_key)['mode'], 'chat')
        self.assertEqual(self.store.load(code_key)['mode'], 'code')
        self.assertIs(self.page.mode.parentWidget(), self.page.sidebar)

    def test_tab_switch_save_failure_keeps_conversation_and_draft(self):
        self.page.new_conversation()
        key = self.page.data['id']
        self.page.composer.setPlainText('Preserve me')
        with patch.object(self.store, 'save', side_effect=OSError('Fixture save failure')):
            self.page.mode.setCurrentIndex(1)
        self.assertEqual(self.page.mode.currentData(), 'chat')
        self.assertEqual(self.page.data['id'], key)
        self.assertEqual(self.page.composer.toPlainText(), 'Preserve me')
        self.assertTrue(self.page.persist())

    def test_no_loaded_model_has_specific_error_without_server_text_leak(self):
        self.server.mode = 'reject_empty'
        self.chat()
        self.until(lambda: not self.page.client.busy)
        self.assertIn('No model is loaded', self.page.status.text())
        self.assertNotIn('secret-session-token', self.page.status.text())
        self.configure_code()
        self.chat()
        self.until(lambda: not self.page.client.busy)
        self.assertIn('No model is loaded', self.page.status.text())
        saved = self.store.load(self.page.data['id'])
        self.assertNotIn('secret-session-token', json.dumps(saved))
        self.server.mode = 'reject_unknown'
        self.chat()
        self.until(lambda: not self.page.client.busy)
        self.assertIn('Server rejected', self.page.status.text())
        self.assertNotIn('secret-session-token', self.page.status.text())

    def paste_image(self):
        image = qt.QImage(320, 180, qt.QImage.Format.Format_RGB32)
        image.fill(qt.QColor('#2468ac'))
        mime = qt.QMimeData()
        mime.setImageData(image)
        qt.QApplication.clipboard().setMimeData(mime)
        self.page.composer.paste()
        self.addCleanup(qt.QApplication.clipboard().clear)
        return image

    def test_dragged_image_file_attaches_in_composer_and_chat_without_file_uri_text(self):
        self.page.new_conversation()
        image = qt.QImage(250, 150, qt.QImage.Format.Format_RGB32)
        image.fill(qt.QColor('green'))
        path = Path(self.temp.name) / 'Dragged screenshot.png'
        self.assertTrue(image.save(str(path), 'PNG'))
        mime = qt.QMimeData()
        mime.setUrls([qt.QUrl.fromLocalFile(str(path))])
        # Exercise the actual Qt drag-enter/drop dispatch on the composer viewport.
        self.page.resize(900, 650)
        self.page.show()
        self.app.processEvents()
        for target in (self.page.composer.viewport(), self.page):
            enter = qt.QDragEnterEvent(qt.QPoint(10, 10), qt.Qt.DropAction.CopyAction, mime,
                qt.Qt.MouseButton.LeftButton, qt.Qt.KeyboardModifier.NoModifier)
            self.app.sendEvent(target, enter)
            self.assertTrue(enter.isAccepted())
            move = qt.QDragMoveEvent(qt.QPoint(10, 10), qt.Qt.DropAction.CopyAction, mime,
                qt.Qt.MouseButton.LeftButton, qt.Qt.KeyboardModifier.NoModifier)
            self.app.sendEvent(target, move)
            self.assertTrue(move.isAccepted())
            drop = qt.QDropEvent(qt.QPointF(10, 10), qt.Qt.DropAction.CopyAction, mime,
                qt.Qt.MouseButton.LeftButton, qt.Qt.KeyboardModifier.NoModifier)
            self.app.sendEvent(target, drop)
            self.assertTrue(drop.isAccepted())
            self.assertEqual(drop.dropAction(), qt.Qt.DropAction.CopyAction)
        self.assertTrue(path.exists())
        self.assertEqual(len(self.page.draft_images), 2)
        self.assertEqual(self.page.composer.toPlainText(), '')
        self.assertEqual(self.page.draft_images[0]['width'], 250)
        self.assertTrue(self.page.persist())
        self.assertEqual(len(self.store.load(self.page.data['id'])['draft_images']), 2)

    def test_finder_file_paste_reads_actual_pixels_instead_of_icon_preview(self):
        self.page.new_conversation()
        screenshot = qt.QImage(321, 123, qt.QImage.Format.Format_RGB32)
        screenshot.fill(qt.QColor('#12ab34'))
        path = Path(self.temp.name) / 'Screenshot with spaces.png'
        self.assertTrue(screenshot.save(str(path), 'PNG'))
        icon = qt.QImage(1024, 1024, qt.QImage.Format.Format_RGB32)
        icon.fill(qt.QColor('white'))
        mime = qt.QMimeData()
        mime.setUrls([qt.QUrl.fromLocalFile(str(path))])
        mime.setImageData(icon)  # macOS Finder's alternate clipboard representation.
        qt.QApplication.clipboard().setMimeData(mime)
        self.addCleanup(qt.QApplication.clipboard().clear)
        self.page.composer.paste()
        self.assertEqual(len(self.page.draft_images), 1)
        record = self.page.draft_images[0]
        self.assertEqual((record['width'], record['height']), (321, 123))
        from features.lm.screenshots import image_bytes
        restored = qt.QImage.fromData(image_bytes(record), 'PNG')
        self.assertEqual(restored.pixelColor(1, 1), qt.QColor('#12ab34'))
        self.assertTrue(self.page.persist())
        saved = self.store.load(self.page.data['id'])['draft_images'][0]
        self.assertEqual(saved, record)

    def test_file_url_paste_without_image_preview_and_invalid_file_do_not_use_icons(self):
        self.page.new_conversation()
        screenshot = qt.QImage(100, 80, qt.QImage.Format.Format_RGB32)
        screenshot.fill(qt.QColor('blue'))
        path = Path(self.temp.name) / 'capture.png'
        self.assertTrue(screenshot.save(str(path), 'PNG'))
        mime = qt.QMimeData()
        mime.setUrls([qt.QUrl.fromLocalFile(str(path))])
        self.assertTrue(self.page.composer.canInsertFromMimeData(mime))
        self.page.composer.insertFromMimeData(mime)
        self.assertEqual(len(self.page.draft_images), 1)
        invalid = Path(self.temp.name) / 'broken.png'
        invalid.write_bytes(b'not a PNG')
        mime.setUrls([qt.QUrl.fromLocalFile(str(invalid))])
        mime.setImageData(screenshot)
        self.page.composer.insertFromMimeData(mime)
        self.assertEqual(len(self.page.draft_images), 1)
        self.assertIn('not a supported raster image', self.page.status.text())
        mime.setUrls([qt.QUrl.fromLocalFile(str(Path(self.temp.name) / 'missing.png'))])
        self.page.composer.insertFromMimeData(mime)
        self.assertEqual(len(self.page.draft_images), 1)

    def test_pasted_screenshot_is_previewed_sent_and_retained_after_reopen(self):
        self.page.new_conversation()
        self.paste_image()
        self.assertEqual(len(self.page.draft_images), 1)
        self.assertFalse(self.page.image_drafts.isHidden())
        record = self.page.draft_images[0]
        self.page.model.setCurrentText('fixture-model')
        self.page.send()  # An image-only message is valid.
        self.until(lambda: not self.page.client.busy)
        request = self.server.requests[-1]
        content = request['messages'][-1]['content']
        self.assertEqual(content[0]['type'], 'image_url')
        self.assertTrue(content[0]['image_url']['url'].startswith('data:image/png;base64,'))
        self.assertEqual(self.page.draft_images, [])
        user = self.page.data['messages'][0]
        self.assertEqual(user['images'], [record])
        bubble = self.page.transcript.bubbles[user['id']]
        self.assertEqual(len(bubble.images), 1)
        self.assertFalse(bubble.images[0].original.isNull())
        key = self.page.data['id']
        self.page.new_conversation()
        self.page.open_conversation(key)
        self.assertEqual(self.page.data['messages'][0]['images'], [record])
        self.chat('What was in the screenshot?')
        self.until(lambda: not self.page.client.busy)
        self.assertEqual(self.server.requests[-1]['messages'][1]['content'][0]['type'], 'image_url')
        self.page.fork_conversation()
        self.assertEqual(self.page.data['messages'][0]['images'], [record])
        from features.lm.storage import export_markdown
        self.assertIn('![Screenshot](data:image/png;base64,', export_markdown(self.page.data))

    def test_screenshot_draft_survives_mode_switch_and_page_restart_and_can_be_removed(self):
        self.page.new_conversation()
        self.paste_image()
        record = self.page.draft_images[0]
        key = self.page.data['id']
        self.page.mode.setCurrentIndex(1)
        self.assertEqual(self.page.draft_images, [])
        self.page.mode.setCurrentIndex(0)
        self.assertEqual(self.page.data['id'], key)
        self.assertEqual(self.page.draft_images, [record])
        self.assertTrue(self.page.persist())
        self.assertTrue(self.page.prepare_close())
        reopened = LMPage(store=Store(self.temp.name))
        try:
            self.assertEqual(reopened.data['id'], key)
            self.assertEqual(reopened.draft_images, [record])
            reopened.remove_screenshot(record['id'])
            self.assertTrue(reopened.persist())
            self.assertEqual(self.store.load(key)['draft_images'], [])
        finally:
            reopened.prepare_close()
            reopened.deleteLater()
            self.app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)

    def test_failed_screenshot_publication_preserves_image_and_draft(self):
        self.page.new_conversation()
        self.paste_image()
        self.page.model.setCurrentText('fixture-model')
        self.assertTrue(self.page.persist())
        record = self.page.draft_images[0]
        with patch.object(self.store, 'save', side_effect=OSError('Fixture publication failure')):
            self.page.send()
        self.assertEqual(self.server.requests, [])
        self.assertEqual(self.page.data['messages'], [])
        self.assertEqual(self.page.draft_images, [record])
        self.assertTrue(self.page.persist())

    def test_screenshots_work_in_code_tool_continuations_and_have_bounded_dimensions(self):
        self.configure_code()
        self.paste_image()
        self.server.mode = 'tools'
        self.chat('Explain this screenshot and main.py')
        self.until(lambda: not self.page.client.busy)
        self.assertEqual(self.page.data['messages'][-1]['status'], 'complete')
        content = next(entry['content'] for entry in self.server.requests[-1]['messages'] if entry['role'] == 'user')
        self.assertEqual([part['type'] for part in content], ['text', 'image_url'])
        from features.lm.screenshots import encode_screenshot
        large = qt.QImage(3000, 1800, qt.QImage.Format.Format_RGB32)
        large.fill(qt.QColor('white'))
        resized = encode_screenshot(large)
        self.assertEqual(resized['width'], 2048)
        self.assertLessEqual(resized['height'], 2048)
        self.assertAlmostEqual(resized['width'] / resized['height'], 3000 / 1800, delta=.002)
        for _ in range(4):
            self.paste_image()
        self.assertEqual(len(self.page.draft_images), 4)
        self.paste_image()
        self.assertEqual(len(self.page.draft_images), 4)
        self.assertIn('four screenshots', self.page.status.text())

    def test_registration_and_construction_do_not_connect(self):
        from features.lm import register
        entry = register()
        self.assertEqual(entry.pages[0].page_id, 'lm.chat')
        self.app.processEvents()
        self.assertEqual(self.server.gets, [])
        self.assertEqual(self.server.requests, [])
        self.assertFalse(self.store.folder.exists())

    def test_discovery_and_streaming_persist_context_and_settings(self):
        self.page.refresh_models()
        self.until(lambda: not self.page.client.busy)
        self.assertEqual(self.page.model.currentText(), 'fixture-model')
        self.chat()
        self.until(lambda: not self.page.client.busy)
        self.assertEqual(self.page.data['messages'][-1]['content'], 'Bonjour 🌍')
        self.assertEqual(self.page.data['messages'][-1]['status'], 'complete')
        self.page.temperature.setValue(.3)
        self.page.token.setText('secret-session-token')
        self.chat('Remember Hello?')
        self.until(lambda: not self.page.client.busy)
        request = self.server.requests[-1]
        self.assertEqual(request['temperature'], .3)
        self.assertEqual([m['role'] for m in request['messages']], ['system', 'user', 'assistant', 'user'])
        saved = self.store.load(self.page.data['id'])
        self.assertEqual(saved['messages'][-1]['content'], 'Bonjour 🌍')
        self.assertNotIn('secret-session-token', self.store.path(saved['id']).read_text())
        self.assertNotIn('secret-session-token', (self.store.root / 'profiles.json').read_text())

    def test_cancel_preserves_partial_output_and_excludes_it_from_next_context(self):
        self.server.mode = 'slow'
        self.chat()
        self.until(lambda: bool(self.page.data['messages'][-1]['content']))
        self.assertFalse(self.page.list.isEnabled())
        self.page.client.cancel()
        self.until(lambda: not self.page.client.busy)
        self.assertEqual(self.page.data['messages'][-1]['status'], 'cancelled')
        self.assertEqual(self.page.data['messages'][-1]['content'], 'Bonjour 🌍')
        self.server.mode = 'normal'
        self.server.release.set()
        self.chat('Second message')
        self.until(lambda: not self.page.client.busy)
        self.assertEqual([m['role'] for m in self.server.requests[-1]['messages']], ['system', 'user'])

    def test_reopen_recovers_interrupted_response_and_draft(self):
        data = conversation(SETTINGS, 'fixture', 'fixture-model')
        data['draft'] = 'Unsaved question'
        data['messages'] = [message('user', 'Hello'), message('assistant', 'Partial', 'streaming')]
        self.store.save(data)
        self.page.open_conversation(data['id'])
        self.assertEqual(self.page.composer.toPlainText(), 'Unsaved question')
        self.assertEqual(self.page.data['messages'][-1]['status'], 'interrupted')
        self.assertEqual(self.store.load(data['id'])['messages'][-1]['status'], 'interrupted')

    def test_regeneration_preserves_alternatives_and_does_not_duplicate_user(self):
        self.chat()
        self.until(lambda: not self.page.client.busy)
        self.page.composer.setPlainText('Draft for the next question')
        self.page.retry()
        self.until(lambda: not self.page.client.busy)
        self.assertEqual([m['role'] for m in self.page.data['messages']], ['user', 'assistant', 'assistant'])
        self.assertEqual([m['role'] for m in self.server.requests[-1]['messages']], ['system', 'user'])
        self.assertEqual(self.page.composer.toPlainText(), 'Draft for the next question')
        self.assertEqual(self.store.load(self.page.data['id'])['draft'], 'Draft for the next question')

    def test_network_truncation_is_failed_and_keeps_partial_output(self):
        self.server.mode = 'truncated'
        self.chat()
        self.until(lambda: not self.page.client.busy)
        self.assertEqual(self.page.data['messages'][-1]['status'], 'failed')
        self.assertEqual(self.page.data['messages'][-1]['content'], 'Bonjour 🌍')

    def test_json_fallback_for_servers_ignoring_stream_flag(self):
        self.server.mode = 'json'
        self.chat()
        self.until(lambda: not self.page.client.busy)
        self.assertEqual(self.page.data['messages'][-1]['content'], 'Plain response')
        self.assertEqual(self.page.data['messages'][-1]['status'], 'complete')

    def test_auth_error_does_not_echo_server_body(self):
        self.server.mode = 'auth'
        self.page.token.setText('secret-session-token')
        self.page.refresh_models()
        self.until(lambda: not self.page.client.busy)
        self.assertIn('Authentication', self.page.status.text())
        self.assertNotIn('secret-session-token', self.page.status.text())

    def test_redirect_is_not_followed(self):
        self.server.mode = 'redirect'
        self.page.refresh_models()
        self.until(lambda: not self.page.client.busy)
        self.assertEqual(self.server.gets, ['/v1/models'])
        self.assertIn('302', self.page.status.text())

    def test_inactivity_timeout_preserves_partial_output(self):
        self.server.mode = 'slow'
        self.page.client.timeout_ms = 150
        self.chat()
        self.until(lambda: not self.page.client.busy)
        self.assertEqual(self.page.data['messages'][-1]['status'], 'failed')
        self.assertIn('timed out', self.page.status.text())
        self.assertEqual(self.page.data['messages'][-1]['content'], 'Bonjour 🌍')

    def test_close_aborts_generation_and_releases_edit_lease(self):
        self.server.mode = 'slow'
        self.chat()
        self.until(lambda: bool(self.page.data['messages'][-1]['content']))
        self.assertTrue(self.page.can_close())
        self.page.prepare_close()
        self.until(lambda: not self.page.client.busy)
        self.assertTrue(self.page.prepare_close())
        lease = self.store.lease(self.page.data['id'])
        lease.unlock()
        self.assertEqual(self.store.load(self.page.data['id'])['messages'][-1]['status'], 'cancelled')

    def test_failed_save_prevents_network_request_and_keeps_draft(self):
        self.page.new_conversation()
        self.page.model.setCurrentText('fixture-model')
        self.page.composer.setPlainText('Keep this question')
        with patch.object(self.store, 'save', side_effect=OSError('Disk full')):
            self.page.send()
            self.assertTrue(self.page.dirty)
            self.assertIn('Disk full', self.page.save_error.text())
        self.assertEqual(self.server.requests, [])
        self.assertEqual(self.page.composer.toPlainText(), 'Keep this question')
        self.assertTrue(self.page.persist())

    def test_conflict_does_not_switch_or_lose_current_draft(self):
        self.page.new_conversation()
        key = self.page.data['id']
        other = self.store.load(key)
        other['title'] = 'External change'
        self.store.save(other)
        next_data = conversation(SETTINGS)
        self.store.save(next_data)
        self.page.composer.setPlainText('Local draft')
        self.page.open_conversation(next_data['id'])
        self.assertEqual(self.page.data['id'], key)
        self.assertEqual(self.page.composer.toPlainText(), 'Local draft')
        self.assertIn('changed on disk', self.page.save_error.text())
        # Explicitly discard this test-only conflicting draft before teardown.
        self.page.discard_approved = True

    def test_profile_editor_preserves_identity_and_saves(self):
        dialog = ProfilesDialog(self.store, self.page)
        original = self.store.profiles()
        dialog.table.item(0, 0).setText('New name')
        dialog.save()
        self.assertEqual(self.store.profiles()[0]['id'], original[0]['id'])
        self.assertEqual(self.store.profiles()[0]['name'], 'New name')

    def test_markdown_does_not_load_local_or_remote_resources(self):
        data = conversation(SETTINGS, 'fixture', 'fixture-model')
        data['messages'] = [message('assistant', '![image](http://localhost/private)\n<script>bad</script>')]
        self.store.save(data)
        self.page.open_conversation(data['id'])
        self.assertEqual(bytes(self.page.transcript.loadResource(2, qt.QUrl('file:///etc/passwd'))), b'')

    def test_second_window_cannot_edit_open_conversation(self):
        self.page.new_conversation()
        second = LMPage(store=self.store)
        self.assertIsNone(second.data)
        self.assertIn('another Logistics window', second.status.text())
        second.prepare_close()
        second.deleteLater()

    def test_export_keeps_unsaved_copy_and_cannot_overwrite_storage(self):
        self.page.new_conversation()
        self.page.composer.setPlainText('Draft for export')
        # Use a sibling folder, since exports deliberately cannot target LM storage.
        with TemporaryDirectory() as exports:
            target = Path(exports) / 'chat.json'
            with patch.object(qt.QFileDialog, 'getSaveFileName', return_value=(str(target), 'JSON (*.json)')):
                self.page.export()
            self.assertEqual(json.loads(target.read_text())['draft'], 'Draft for export')
        original = self.store.path(self.page.data['id']).read_bytes()
        with patch.object(qt.QFileDialog, 'getSaveFileName', return_value=(str(self.store.path(self.page.data['id'])), 'JSON (*.json)')):
            self.page.export()
        self.assertEqual(self.store.path(self.page.data['id']).read_bytes(), original)

    def test_invalid_default_context_is_rejected(self):
        from features.lm.configuration import validate
        with self.assertRaises(ValueError):
            validate({('Chat', 'context_tokens_int'): '512', ('Chat', 'max_tokens_int'): '1024'})

    def test_refresh_reacquires_lease_after_another_page_vetoes_close(self):
        self.page.new_conversation()
        self.assertTrue(self.page.prepare_close())
        self.assertFalse(self.page.send_button.isEnabled())
        self.page.refresh()
        self.assertIsNotNone(self.page.lease)
        self.assertTrue(self.page.send_button.isEnabled())

    def test_sampling_default_steps_directly_to_zero(self):
        self.page.new_conversation()
        self.page.temperature.setValue(-1)
        self.page.temperature.stepBy(1)
        self.assertEqual(self.page.temperature.value(), 0)
        self.page.temperature.stepBy(-1)
        self.assertEqual(self.page.temperature.value(), -1)

    def test_destruction_releases_lease_without_explicit_preparation(self):
        self.page.new_conversation()
        key = self.page.data['id']
        other = LMPage(store=self.store)
        other.new_conversation()
        other_key = other.data['id']
        other.deleteLater()
        self.app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
        lease = self.store.lease(other_key)
        lease.unlock()
        self.assertEqual(self.page.data['id'], key)

    def test_failed_generation_checkpoint_cancels_and_keeps_exportable_text(self):
        self.server.mode = 'slow'
        self.chat()
        self.until(lambda: bool(self.page.data['messages'][-1]['content']))
        with patch.object(self.store, 'save', side_effect=OSError('Disk full')):
            self.page.checkpoint()
            self.until(lambda: not self.page.client.busy)
            self.assertIn('Disk full', self.page.save_error.text())
            self.assertEqual(self.page.data['messages'][-1]['content'], 'Bonjour 🌍')
        self.assertTrue(self.page.persist())

    def test_first_publication_failure_keeps_unsent_user_draft(self):
        self.page.new_conversation()
        self.page.model.setCurrentText('fixture-model')
        self.page.composer.setPlainText('Keep this message')
        self.assertTrue(self.page.persist())
        with patch.object(self.store, 'save', side_effect=OSError('Disk full')):
            self.page.send()
        self.assertEqual(self.server.requests, [])
        self.assertEqual(self.page.data['messages'], [])
        self.assertEqual(self.page.composer.toPlainText(), 'Keep this message')

    def test_nested_tree_new_conversation_move_and_restart(self):
        with patch.object(qt.QInputDialog, 'getText', return_value=('Projects/Planning/2026', True)):
            self.page.new_folder()
        self.assertEqual(self.page.selected_folder(), 'Projects/Planning/2026')
        self.page.new_conversation()
        key = self.page.data['id']
        self.assertEqual(self.page.data['folder'], 'Projects/Planning/2026')
        self.assertTrue((self.store.folder / 'Projects/Planning/2026' / (key + '.json')).is_file())
        self.page.composer.setPlainText('Draft in a folder')
        with patch.object(qt.QInputDialog, 'getItem', return_value=('Archive/Old/Chats', True)):
            self.page.move_conversation()
        self.assertEqual(self.page.data['folder'], 'Archive/Old/Chats')
        self.assertEqual(self.page.composer.toPlainText(), 'Draft in a folder')
        self.assertTrue(self.page.prepare_close())
        self.page.open_conversation(key)
        self.assertEqual(self.page.data['folder'], 'Archive/Old/Chats')
        self.assertEqual(self.page.composer.toPlainText(), 'Draft in a folder')
        self.page.search.setText('Draft')
        # Search matches transcript/title, not an unsent draft.
        self.page.refresh()
        self.page.search.clear()
        self.page.refresh()
        self.assertIn('Archive/Old/Chats', self.page.folder_items)

    def test_enter_sends_and_shift_enter_inserts_newline_only_in_composer(self):
        self.page.new_conversation()
        self.page.model.setCurrentText('fixture-model')
        self.page.composer.setPlainText('First line')
        self.page.composer.moveCursor(qt.QTextCursor.MoveOperation.End)
        QTest.keyClick(self.page.composer, qt.Qt.Key.Key_Return, qt.Qt.KeyboardModifier.ShiftModifier)
        QTest.keyClicks(self.page.composer, 'Second line')
        self.assertEqual(self.page.composer.toPlainText(), 'First line\nSecond line')
        self.assertEqual(self.server.requests, [])
        QTest.keyClick(self.page.composer, qt.Qt.Key.Key_Return)
        self.until(lambda: not self.page.client.busy)
        self.assertEqual(self.server.requests[-1]['messages'][-1]['content'], 'First line\nSecond line')
        self.assertEqual(self.page.composer.toPlainText(), '')
        before = len(self.server.requests)
        self.page.system.moveCursor(qt.QTextCursor.MoveOperation.End)
        QTest.keyClick(self.page.system, qt.Qt.Key.Key_Return)
        self.assertTrue(self.page.system.toPlainText().endswith('\n'))
        self.assertEqual(len(self.server.requests), before)
        self.assertIn('Shift+Enter', self.page.composer.placeholderText())

    def test_empty_enter_does_not_send_or_insert_newline(self):
        self.page.new_conversation()
        QTest.keyClick(self.page.composer, qt.Qt.Key.Key_Enter)
        self.assertEqual(self.page.composer.toPlainText(), '')
        self.assertEqual(self.server.requests, [])

    def test_send_control_becomes_stop_and_returns_to_send(self):
        self.server.mode = 'slow'
        self.chat()
        self.until(lambda: bool(self.page.data['messages'][-1]['content']))
        self.assertTrue(self.page.send_button.isEnabled())
        self.assertIn('Stop', self.page.send_button.accessibleName())
        self.page.send_button.click()
        self.until(lambda: not self.page.client.busy)
        self.assertEqual(self.page.send_button.accessibleName(), 'Send message')
        self.assertEqual(self.page.data['messages'][-1]['status'], 'cancelled')

    def test_chat_uses_shared_markdown_reading_font(self):
        expected = self.page.styling.font('reading')
        self.assertEqual(self.page.transcript.font().family(), expected.family())
        self.assertEqual(self.page.transcript.font().pointSize(), expected.pointSize())
        self.assertEqual(self.page.composer.font().pointSize(), expected.pointSize())
        self.assertIn('localhost default', self.store.__class__(Path(self.temp.name) / 'empty').profiles()[0]['name'])

    def test_conversation_bubbles_keep_prior_selection_during_streaming(self):
        self.server.mode = 'slow'
        self.chat()
        self.until(lambda: bool(self.page.data['messages'][-1]['content']))
        entries = self.page.data['messages']
        user = self.page.transcript.bubbles[entries[0]['id']]
        assistant = self.page.transcript.bubbles[entries[1]['id']]
        self.assertEqual(user.objectName(), 'userBubble')
        self.assertEqual(assistant.objectName(), 'assistantBubble')
        cursor = user.browser.textCursor()
        cursor.select(qt.QTextCursor.SelectionType.Document)
        user.browser.setTextCursor(cursor)
        self.page.append_delta(' More text')
        self.page.render()
        self.assertEqual(user.browser.textCursor().selectedText(), 'Hello')
        self.assertIs(self.page.transcript.bubbles[entries[1]['id']], assistant)
        self.assertIn('More text', assistant.browser.toPlainText())

    def test_shared_status_footer_is_muted_and_does_not_grow_for_long_messages(self):
        from commonUtils.ui.appearance.status_line import StatusLine
        self.assertIsInstance(self.page.status, StatusLine)
        self.page.status.resize(160, 30)
        message = 'A very long status message ' * 100
        self.page.status.setText(message)
        self.assertEqual(self.page.status.text(), message)
        self.assertEqual(self.page.status.toolTip(), message)
        self.assertFalse(self.page.status.wordWrap())
        self.assertLess(self.page.status.sizeHint().height(), 50)

    def test_stream_follows_bottom_without_interrupting_manual_scroll(self):
        self.page.new_conversation()
        self.page.resize(900, 600)
        self.page.show()
        self.page.data['messages'] = [message('user' if i % 2 == 0 else 'assistant',
            ('Line of text\n\n' * 5) + str(i)) for i in range(12)]
        self.page.render()
        bar = self.page.transcript.verticalScrollBar()
        self.until(lambda: bar.maximum() > 0)
        self.assertEqual(bar.value(), bar.maximum())
        bar.setValue(0)
        self.page.data['messages'][-1]['content'] += '\nMore streamed text\n' * 10
        self.page.render()
        self.app.processEvents()
        self.assertEqual(bar.value(), 0)

    def test_send_preserves_code_indentation_and_leading_trailing_lines(self):
        source = '\n    print("Indented code")\n\n'
        self.chat(source)
        self.until(lambda: not self.page.client.busy)
        self.assertEqual(self.server.requests[-1]['messages'][-1]['content'], source)
        self.assertEqual(self.page.data['messages'][0]['content'], source)

    def test_next_draft_can_be_written_and_saved_while_reply_streams(self):
        self.server.mode = 'slow'
        self.chat()
        self.until(lambda: bool(self.page.data['messages'][-1]['content']))
        self.assertTrue(self.page.composer.isEnabled())
        self.page.composer.setPlainText('My next question')
        self.assertTrue(self.page.persist())
        self.assertEqual(self.store.load(self.page.data['id'])['draft'], 'My next question')
        QTest.keyClick(self.page.composer, qt.Qt.Key.Key_Return)
        self.assertEqual(len(self.server.requests), 1)
        self.page.client.cancel()
        self.until(lambda: not self.page.client.busy)
        self.assertEqual(self.page.composer.toPlainText(), 'My next question')

    def test_valid_text_before_bad_stream_record_is_kept(self):
        self.server.mode = 'malformed_after_text'
        self.chat()
        self.until(lambda: not self.page.client.busy)
        self.assertEqual(self.page.data['messages'][-1]['status'], 'failed')
        self.assertEqual(self.page.data['messages'][-1]['content'], 'Bonjour 🌍')
        saved = self.store.load(self.page.data['id'])
        self.assertEqual(saved['messages'][-1]['content'], 'Bonjour 🌍')

    def test_refresh_keeps_folder_selection_and_collapsed_branches(self):
        self.page.new_conversation()
        self.store.create_folder('Work/Nested')
        self.page.refresh()
        self.page.folder_items['Work'].setExpanded(False)
        self.page.list.setCurrentItem(self.page.folder_items['Work'])
        self.page.refresh()
        self.assertEqual(self.page.selected_folder(), 'Work')
        self.assertFalse(self.page.folder_items['Work'].isExpanded())
        self.page.new_conversation()
        self.assertEqual(self.page.data['folder'], 'Work')
        self.assertTrue(self.page.folder_items['Work'].isExpanded())

    def test_new_conversation_clears_filter_and_is_visible(self):
        self.page.search.setText('No matching conversation')
        self.page.refresh()
        self.page.new_conversation()
        self.assertEqual(self.page.search.text(), '')
        self.assertEqual(self.page.list.currentItem().data(0, qt.Qt.ItemDataRole.UserRole), self.page.data['id'])

    def test_reopened_failed_response_shows_saved_error(self):
        data = conversation(SETTINGS, 'fixture', 'fixture-model')
        entry = message('assistant', 'Partial text', 'failed', error='Connection ended before completion.')
        data['messages'] = [entry]
        self.store.save(data)
        self.page.open_conversation(data['id'])
        bubble = self.page.transcript.bubbles[entry['id']]
        self.assertEqual(bubble.error.text(), entry['error'])
        self.assertFalse(bubble.error.isHidden())

    def test_each_bubble_copies_exact_source_including_whitespace(self):
        self.chat('    print("Keep indentation")\n')
        self.until(lambda: not self.page.client.busy)
        entry = self.page.data['messages'][0]
        self.page.transcript.bubbles[entry['id']].copy_button.click()
        self.assertEqual(self.app.clipboard().text(), entry['content'])

    def test_reply_footer_actions_and_compact_composer(self):
        self.chat('First question')
        self.until(lambda: not self.page.client.busy)
        first = self.page.data['messages'][-1]['id']
        self.chat('Second question')
        self.until(lambda: not self.page.client.busy)
        last = self.page.data['messages'][-1]['id']
        self.page.resize(900, 650)
        self.page.show()
        self.app.processEvents()
        earlier = self.page.transcript.bubbles[first]
        latest = self.page.transcript.bubbles[last]
        self.assertTrue(earlier.retry_button.isHidden())
        self.assertFalse(latest.retry_button.isHidden())
        self.assertGreaterEqual(latest.copy_button.y(), latest.browser.geometry().bottom())
        self.assertIs(self.page.send_button.parent(), self.page.composer_frame)
        self.assertLess(self.page.send_button.y(), self.page.composer.geometry().bottom())
        self.assertGreater(self.page.send_button.geometry().bottom(), self.page.composer.y())
        self.assertTrue(self.page.save_error.isHidden())
        self.assertEqual(self.page.disclaimer.text(), 'Language Models can make mistakes. Check important info.')
        latest.copy_button.click()
        self.assertEqual(self.app.clipboard().text(), self.page.data['messages'][-1]['content'])
        latest.retry_button.click()
        self.assertTrue(self.page.client.busy)
        self.assertFalse(latest.retry_button.isEnabled())
        self.until(lambda: not self.page.client.busy)
        self.assertEqual(self.server.requests[-1]['messages'][-1]['content'], 'Second question')

    def test_switching_conversations_returns_to_latest_messages(self):
        self.page.new_conversation()
        self.page.resize(900, 600)
        self.page.show()
        self.page.data['messages'] = [message('assistant', 'Long message\n\n' * 10) for _ in range(10)]
        self.page.render()
        bar = self.page.transcript.verticalScrollBar()
        self.until(lambda: bar.maximum() > 0)
        bar.setValue(0)
        data = conversation(SETTINGS, 'fixture', 'fixture-model')
        data['messages'] = [message('assistant', 'Other message\n\n' * 10) for _ in range(10)]
        self.store.save(data)
        self.page.open_conversation(data['id'])
        self.until(lambda: bar.maximum() > 0 and bar.value() == bar.maximum())
        self.assertEqual(self.page.transcript.key, data['id'])

    def test_pin_fork_menus_and_timestamp_preserve_original_conversation(self):
        self.chat('Keep this history')
        self.until(lambda: not self.page.client.busy)
        original = self.page.data['id']
        self.page.toggle_pin()
        self.assertTrue(self.store.load(original)['pinned'])
        self.assertEqual(self.page.pin_action.text(), 'Unpin conversation')
        entry = self.page.data['messages'][0]
        timestamp = self.page.transcript.bubbles[entry['id']].timestamp
        self.assertTrue(timestamp.text())
        self.assertTrue(timestamp.toolTip())
        self.page.composer.setPlainText('A draft to branch')
        requests = len(self.server.requests)
        self.page.fork_conversation()
        self.assertEqual(len(self.server.requests), requests)
        self.assertEqual(self.page.data['draft'], 'A draft to branch')
        self.assertEqual(self.store.load(original)['draft'], 'A draft to branch')
        self.assertNotEqual(self.page.data['id'], original)
        self.assertFalse(self.page.data['pinned'])
        self.assertEqual(self.page.data['messages'][0]['content'], 'Keep this history')
        self.assertNotEqual(self.page.data['messages'][0]['id'], entry['id'])
        self.assertTrue(self.store.load(original)['pinned'])
        self.assertEqual([a.text() for a in self.page.menu_bar.actions()],
                         ['File', 'Edit', 'Conversation', 'View', 'Server'])
        self.assertEqual(self.page.status.contentsMargins().bottom(), 0)
        content = self.page.status.parentWidget()
        self.assertEqual(content.layout().contentsMargins().bottom(), 8)

    def test_tree_move_persists_conversation_and_folder_destinations(self):
        self.page.new_conversation()
        key = self.page.data['id']
        self.store.create_folder('Work/Nested')
        self.store.create_folder('Archive')
        from types import SimpleNamespace
        self.page.refresh()
        self.page.resize(900, 650)
        self.page.show()
        self.app.processEvents()
        tree = self.page.list
        target = self.page.folder_items['Work/Nested']
        point = tree.visualItemRect(target).center()
        event = SimpleNamespace(source=lambda: tree, position=lambda: qt.QPointF(point), ignore=lambda: None)
        tree.dropEvent(event)
        self.assertEqual(self.store.load(key)['folder'], 'Work/Nested')
        self.page.move_tree_item((None, 'Work'), 'Archive')
        self.assertEqual(self.page.data['folder'], 'Archive/Work/Nested')
        self.assertEqual(self.store.load(key)['folder'], 'Archive/Work/Nested')
        self.page.composer.setPlainText('Still editable after moving')
        self.assertTrue(self.page.persist())
        self.assertEqual(self.store.load(key)['draft'], 'Still editable after moving')
