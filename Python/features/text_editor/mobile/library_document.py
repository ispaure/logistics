"""Embedded Markdown over the shared provider-backed library text draft."""
import asyncio
from .library_text import LibraryText
from .markdown_editor import FormattedMarkdownInput, prepare_editor


class LibraryMarkdown(LibraryText):
    kind = 'markdown'

    @classmethod
    def preparation_inputs(cls, library, path):
        return dict(font_size=library.host.presentation.font_size('markdown'),
                    stylesheet=library.host.presentation.css_variables(),
                    image_source=library.library.image_source(path))

    @classmethod
    def prepare(cls, text, **inputs):
        return prepare_editor(text, **inputs) if len(text.encode('utf-8')) <= 1024 * 1024 else None

    def build_input(self, prepared):
        library, path = self.library, self.path
        self.formatted = FormattedMarkdownInput(self.changed,
            font_size=library.host.presentation.font_size('markdown'),
            image_source=lambda: library.library.image_source(path), private=not library.access.policy.persistent,
            stylesheet=library.host.presentation.css_variables(), presentation=library.host.presentation)
        self.formatted.scroll_top = library.positions.get(path, 0)
        library.host.presentation.bind_font(self.formatted.view, 'markdown', web=True, formatted=self.formatted)
        try:
            self.formatted.load(self.text, prepared=prepared)
            self.view.add(self.formatted.view)
        except ValueError as error:
            library.notice.text = str(error)
            self.view.add(self.source_input())

    async def choose_mode(self, formatted=True):
        if self.closed or not self.library.valid():
            return False
        self.mode_generation += 1
        generation = self.mode_generation
        def current():
            return not self.closed and self.library.valid() and generation == self.mode_generation
        try:
            await self.flush()
            if not current():
                return False
            if formatted:
                text = self.text
                prepared = await asyncio.to_thread(prepare_editor, text, **self.formatted.preparation_inputs())
                if not current() or self.text != text:
                    return False
                self.formatted.load(text, prepared=prepared)
                surface = self.formatted.view
            else:
                surface = self.source_input()
            finding = hasattr(self, 'finder') and self.finder.box in self.view.children
            self.view.clear()
            self.view.add(surface)
            if not formatted and finding:
                self.view.insert(0, self.finder.box)
            return True
        except ValueError as error:
            if current():
                self.library.notice.text = str(error)
            return False

    async def flush(self):
        if self.formatted.view in self.view.children:
            await self.formatted.flush()
        await super().flush()
