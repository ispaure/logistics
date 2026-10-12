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
        self.send_response(200)
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
