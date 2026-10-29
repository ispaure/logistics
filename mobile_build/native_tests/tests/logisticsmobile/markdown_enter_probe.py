"""Native WebView Enter and native plain/source newline checks on isolated data."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
import json
from pathlib import Path
import traceback
from uuid import uuid4

from mobile.app import LogisticsMobile
from .web_checks import wait_for_text


class MarkdownEnterProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / ('markdown-enter-' + uuid4().hex)
        super().startup()

    def on_running(self):
        if not getattr(self, '_enter_started', False):
            self._enter_started = True
            self.loop.create_task(self.probe())

    async def probe(self):
        output = Path(self.paths.cache) / 'markdown-enter-evidence'
        output.mkdir(exist_ok=True)
        report = dict(success=False, backend=type(self._impl).__module__)
        try:
            document = self.store.create('Enter.md', b'Original paragraph\n\n')
            self.open_document(document.id)
            self.show_documents(edit=True)
            owner = self.editor_view
            web = owner.formatted.view
            await wait_for_text(web, 'Original paragraph')
            await web.evaluate_javascript('''(() => {
                const section=root.lastElementChild;section.focus();
                const range=document.createRange();range.selectNodeContents(section);range.collapse(true);
                getSelection().removeAllRanges();getSelection().addRange(range);
                document.execCommand('insertText',false,'first');
            })()''')
            android = type(self._impl).__module__.startswith('toga_android.')
            if android:
                from android.view import KeyEvent
                from android.view.inputmethod import EditorInfo
                native = web._impl.native
                native.requestFocus()
                connection = native.onCreateInputConnection(EditorInfo())
                assert connection is not None
                connection.sendKeyEvent(KeyEvent(KeyEvent.ACTION_DOWN, KeyEvent.KEYCODE_ENTER))
                connection.sendKeyEvent(KeyEvent(KeyEvent.ACTION_UP, KeyEvent.KEYCODE_ENTER))
                await asyncio.sleep(.3)
                report['enter_input'] = 'Android InputConnection KeyEvent'
            else:
                await web.evaluate_javascript("document.execCommand('insertParagraph')")
                report['enter_input'] = 'WebKit insertParagraph'
            await web.evaluate_javascript("document.execCommand('insertText',false,'second')")
            await owner.formatted.flush()
            assert 'first\n\nsecond' in owner.formatted.text, owner.formatted.text
            report['formatted_enter'] = True
            await web.evaluate_javascript("document.execCommand('insertLineBreak');document.execCommand('insertText',false,'third')")
            await owner.formatted.flush()
            assert 'second\nthird' in owner.formatted.text, owner.formatted.text
            report['shift_enter'] = True
            await web.evaluate_javascript("command('undo');command('redo');document.execCommand('insertText',false,'!')")
            await owner.formatted.flush()
            assert 'third!' in owner.formatted.text, owner.formatted.text
            report['undo_redo_caret'] = True
            for name in ('Source.md', 'Plain.txt'):
                document = self.store.create(name, b'')
                self.open_document(document.id)
                self.show_documents(edit=True)
                owner = self.editor_view
                if name.endswith('.md'):
                    owner.edit_mode.value = 'Source'
                native = owner.editor._impl.native
                if android:
                    native.requestFocus()
                    connection = native.onCreateInputConnection(EditorInfo())
                    connection.commitText('first\nsecond', 1)
                else:
                    native.becomeFirstResponder()
                    native.insertText('first\nsecond')
                await asyncio.sleep(.2)
                assert 'first\nsecond' in owner.editor.value, owner.editor.value
                report[name] = True
            report['success'] = True
        except BaseException:
            report['error'] = traceback.format_exc()
        (output / 'result.json').write_text(json.dumps(report, indent=2))


def main():
    return MarkdownEnterProbe('Markdown Enter QA', 'io.github.ispaure.logisticsmarkdownenterqa')
