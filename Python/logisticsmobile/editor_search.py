"""Per-editor literal Find/Replace with native selection and retained drafts."""
import re
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW


class EditorSearch:
    def __init__(self, owner):
        self.owner = owner
        self.span = None
        self.query = toga.TextInput(placeholder='Find text', on_change=self.changed, style=Pack(flex=1, height=44))
        self.replacement = toga.TextInput(placeholder='Replace with', style=Pack(flex=1, height=44))
        self.case = toga.Switch('Match case', on_change=self.changed, style=Pack(height=44))
        self.notice = toga.Label('', style=Pack(font_size=12, flex=1))
        self.box = toga.Box(children=[
            toga.Box(children=[self.query, toga.Button('Done', on_press=self.toggle, style=Pack(height=44))], style=Pack(direction=ROW)),
            toga.Box(children=[toga.Button('Previous', on_press=self.previous, style=Pack(flex=1, height=44)),
                               toga.Button('Next', on_press=self.next, style=Pack(flex=1, height=44))], style=Pack(direction=ROW)),
            toga.Box(children=[self.replacement, toga.Button('Replace', on_press=self.replace, style=Pack(height=44))], style=Pack(direction=ROW)),
            toga.Box(children=[self.case, toga.Button('Replace all', on_press=self.replace_all, style=Pack(flex=1, height=44))], style=Pack(direction=ROW)),
            self.notice],
            style=Pack(direction=COLUMN, margin_bottom=8))

    def toggle(self, widget=None, **kwargs):
        view = self.owner.document_view
        if self.box in view.children:
            view.remove(self.box)
        else:
            view.insert(1, self.box)
            self.query.focus()
            self.changed()

    def pattern(self):
        return re.compile(re.escape(self.query.value), 0 if self.case.value else re.IGNORECASE) if self.query.value else None

    def changed(self, widget=None, **kwargs):
        self.span = None
        pattern = self.pattern()
        count = sum(1 for _ in pattern.finditer(self.owner.editor.value)) if pattern else 0
        self.notice.text = f'{count} match(es)' if pattern else 'Enter text to find.'

    def next(self, widget=None, **kwargs):
        self.find()

    def previous(self, widget=None, **kwargs):
        self.find(backwards=True)

    def find(self, *, backwards=False):
        pattern, text = self.pattern(), self.owner.editor.value
        if pattern is None:
            return
        boundary = (self.span[0] if backwards else self.span[1]) if self.span else (len(text) if backwards else 0)
        if backwards:
            match = None
            for candidate in pattern.finditer(text):
                if candidate.start() >= boundary:
                    break
                match = candidate
            if match is None:
                for match in pattern.finditer(text):
                    pass
        else:
            match = pattern.search(text, boundary) or pattern.search(text)
        if match is None:
            self.span = None
            self.notice.text = 'No matches'
            return
        self.span = match.span()
        self.select_match()
        self.notice.text = 'Match selected · search wraps'

    def select_match(self):
        editor, text = self.owner.editor, self.owner.editor.value
        start, end = (len(text[:offset].encode('utf-16-le')) // 2 for offset in self.span)
        backend = type(editor._impl).__module__
        editor.focus()
        if backend.startswith('toga_android.'):
            editor._impl.native.setSelection(start, end)
        elif backend.startswith('toga_iOS.'):
            from rubicon.objc import NSRange
            editor._impl.native.selectedRange = NSRange(start, end - start)
            editor._impl.native.scrollRangeToVisible(NSRange(start, end - start))

    def replace(self, widget=None, **kwargs):
        pattern, text = self.pattern(), self.owner.editor.value
        if self.span is None:
            self.find()
            return
        start, end = self.span
        if pattern is None or pattern.fullmatch(text[start:end]) is None:
            self.changed()
            return
        self.owner.editor.value = text[:start] + self.replacement.value + text[end:]
        self.span = (start, start + len(self.replacement.value))
        self.find()

    def replace_all(self, widget=None, **kwargs):
        pattern = self.pattern()
        if pattern is None:
            return
        text, count = pattern.subn(lambda match: self.replacement.value, self.owner.editor.value)
        if count:
            self.owner.editor.value = text
        self.span = None
        self.notice.text = f'Replaced {count} match(es)'
