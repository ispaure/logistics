"""Per-document provider Markdown surfaces; storage and session policy stay hosted."""
import asyncio
from dataclasses import dataclass
from typing import Callable
from uuid import uuid4

import toga
from toga.style import Pack
from commonUtils.ui.native.markdown_search import MarkdownPageSearch
from .markdown_editor import FormattedMarkdownInput, retire_webview


@dataclass(frozen=True)
class ProviderMarkdownHost:
    """Capabilities supplied by the mobile host, without an application object."""
    loop: object
    reader: Callable
    valid: Callable
    access_stamp: Callable
    render: Callable
    image_source: Callable
    font_size: Callable
    stylesheet: Callable
    bind_font: Callable
    busy: Callable
    transfer_busy: Callable
    speech: Callable
    commands: Callable
    sync_toolbar: Callable
    error: Callable
    icon_button: Callable
    apply_icon: Callable


class ProviderMarkdown:
    """Own view state and pending rendering, using the session's existing source input."""

    def __init__(self, host, *, source, content, toolbar, save, actions, footer,
                 action_items, actions_menu, read_only=False):
        self.host = host
        self.source, self.content, self.toolbar = source, content, toolbar
        self.save, self.actions, self.footer = save, actions, footer
        self.action_items, self.actions_menu = list(action_items), actions_menu
        self.preview = self.formatted = self.search = self.speech = None
        self.preview_text = None
        self.pending = self.token = self.menu_state = self.mode = None
        self.closed = False
        self.preview_button = host.icon_button('view', 'View Markdown', on_press=self.toggle_preview)
        toolbar.insert(len(toolbar.children) - 1, self.preview_button)
        host.apply_icon(save, 'save', 'Save Markdown')
        if save in footer.children:
            footer.remove(save)
        self.edit_mode = None
        self.initializing = True
        if not read_only:
            self.edit_mode = toga.Selection(items=['Formatted', 'Source'], on_change=self.edit_mode_changed,
                                            style=Pack(flex=1, height=44))
            footer.add(self.edit_mode)
        self.initializing = False
        self.native_buttons = [self.preview_button, actions]

    def refresh_controls(self, *, reader=None):
        if self.closed:
            return
        reader = reader or self.host.reader()
        if reader is None:
            return
        dirty = self.source.value != reader.text and not getattr(reader, 'read_only', False)
        self.save.enabled = dirty and not self.host.busy()
        native_toolbar = type(self.toolbar._impl).__module__.startswith('toga_iOS.')
        if dirty and not native_toolbar and self.save not in self.toolbar.children:
            self.toolbar.insert(len(self.toolbar.children) - 1, self.save)
        elif not dirty and self.save in self.toolbar.children:
            self.toolbar.remove(self.save)
        self.footer.style.margin_top = 0
        if self.footer.children:
            del self.footer.style.height
        else:
            self.footer.style.height = 0
        self.native_buttons[:] = [self.save] if dirty else [self.preview_button]
        reading = self.speech is not None and self.preview is not None and self.preview in self.content.children
        state = dirty, reading
        if state != self.menu_state:
            actions = list(self.action_items)
            mode = ('View source text' if getattr(reader, 'read_only', False) else 'Edit Markdown') if reading else 'View Markdown'
            actions.insert(0, (mode, self.toggle_preview))
            if reading:
                actions.insert(0, ('Read aloud…', self.speech.show))
                if self.search is not None:
                    actions.insert(0, ('Find in this page…', self.search.show))
            self.actions_menu.dispose()
            self.actions_menu = self.host.commands(actions)
            self.menu_state = state
        self.native_buttons.append(self.actions)
        self.host.sync_toolbar()

    def clear(self):
        """Suspend surfaces and invalidate work, retaining draft and chosen mode."""
        if self.closed:
            return
        if self.search is not None:
            self.search.dispose()
            self.search = None
        self.token = None
        if self.edit_mode is not None and self.edit_mode not in self.footer.children:
            self.footer.add(self.edit_mode)
        if self.speech is not None:
            self.speech.close()
            if self.speech.button in self.toolbar.children:
                self.toolbar.remove(self.speech.button)
        if self.formatted is not None:
            self.formatted.dispose()
            if self.formatted.view in self.content.children:
                self.content.remove(self.formatted.view)
            self.formatted = None
            if self.source not in self.content.children:
                self.content.add(self.source)
        if self.pending is not None:
            self.pending.cancel()
            self.pending = None
        if self.preview is not None:
            native = getattr(self.preview._impl, 'native', None)
            if native is not None:
                native.stopLoading()
            self.preview.set_content('https://logistics.invalid/closed/', '<p>Preview closed.</p>')
            if self.preview in self.content.children:
                self.content.remove(self.preview)
                if self.source not in self.content.children:
                    self.content.add(self.source)
            self.host.apply_icon(self.preview_button, 'view', 'View Markdown')
        self.refresh_controls()

    def dispose(self):
        """Permanently retire the web surfaces when the owning document closes."""
        if self.closed:
            return
        self.clear()
        self.closed = True
        self.actions_menu.dispose()
        if self.preview is not None:
            retire_webview(self.preview)
            self.preview = None

    def source_changed(self, widget, **kwargs):
        if widget is not self.source or self.closed:
            return
        reader = self.host.reader()
        if not self.host.valid(reader):
            return
        self.refresh_controls()
        if self.formatted is not None and self.formatted.view in self.content.children:
            try:
                self.formatted.load(widget.value)
            except ValueError as error:
                self.host.error(str(error))
        if self.speech is not None:
            self.speech.close()
        if (self.preview is not None and self.preview in self.content.children
                and self.source.value != self.preview_text):
            self.schedule_preview(delay=.25)

    def schedule_preview(self, *, delay=0):
        if self.closed or self.preview is None or not self.host.valid(self.host.reader()):
            return
        if self.pending is not None:
            self.pending.cancel()
        token = object()
        self.token = token
        reader = self.host.reader()
        preview, text = self.preview, self.source.value
        size, access = self.host.font_size(), self.host.access_stamp()

        def current():
            return (not self.closed and self.token is token and self.host.valid(reader)
                    and self.source.value == text and self.preview is preview
                    and preview in self.content.children and self.host.access_stamp() == access)

        async def render():
            try:
                if not current():
                    return
                image_source = self.host.image_source(reader)
                if delay:
                    await asyncio.sleep(delay)
                content = await asyncio.to_thread(self.host.render, text, size, image_source=image_source)
                if not current():
                    return
                if self.search is not None:
                    self.search.loading()
                self.preview_text = text
                preview.set_content('https://logistics.invalid/live/', content)
            except (ValueError, OSError) as error:
                if current():
                    self.host.error(str(error))
            finally:
                if self.token is token:
                    self.pending = None
        if self.host.loop.is_running():
            self.pending = self.host.loop.create_task(render())
        else:
            self.host.loop.run_until_complete(render())

    def toggle_preview(self, widget=None, *, initial=False, rendered=None, **kwargs):
        reader = self.host.reader()
        if (self.closed or reader is None or not reader.editable or not self.host.valid(reader)
                or (not initial and self.host.busy() and not self.host.transfer_busy())):
            return
        if self.preview is not None and self.preview in self.content.children:
            self.mode = 'source'
            self.clear()
            if not getattr(reader, 'read_only', False):
                self.show_editor()
            return
        content = rendered if rendered is not None else '<p>Loading preview…</p>'
        if self.preview is None:
            self.preview = toga.WebView(on_navigation_starting=lambda widget, url, **kw: False,
                                        style=Pack(flex=1))
        preview = self.preview
        self.host.bind_font(preview, web=True)
        self.mode = 'preview'
        if self.edit_mode is not None and self.edit_mode in self.footer.children:
            self.footer.remove(self.edit_mode)
        self.content.clear()
        self.content.add(preview)
        self.search = MarkdownPageSearch(preview, self.content, valid=lambda: not self.closed and self.host.valid(self.host.reader()))
        preview.on_webview_load = self.search.loaded
        self.host.bind_font(preview, web=True)
        self.search.loading()
        self.preview_text = self.source.value if rendered is not None else None
        preview.set_content('https://logistics.invalid/' + uuid4().hex + '/', content)
        if self.speech is None:
            self.speech = self.host.speech(preview, self.content,
                lambda: not self.closed and self.host.valid(self.host.reader()))
        self.speech.close()
        self.speech.web = preview
        if self.speech.button not in self.toolbar.children:
            self.toolbar.insert(len(self.toolbar.children) - 1, self.speech.button)
        self.host.apply_icon(self.preview_button, 'view' if getattr(reader, 'read_only', False) else 'edit',
                             'View source text' if getattr(reader, 'read_only', False) else 'Edit Markdown')
        self.refresh_controls()
        if rendered is None:
            self.schedule_preview()

    def edit_mode_changed(self, widget=None, **kwargs):
        if self.initializing:
            return
        reader = self.host.reader()
        if reader is None or getattr(reader, 'read_only', False) or self.closed:
            return
        if not self.host.valid(reader):
            return
        self.clear()
        self.show_editor()

    def show_editor(self):
        reader = self.host.reader()
        if (reader is None or getattr(reader, 'read_only', False) or self.closed
                or not self.host.valid(reader)):
            return
        self.mode = 'edit'
        if getattr(self.edit_mode, 'value', 'Formatted') == 'Source':
            return
        def changed(text):
            if self.host.valid(reader) and formatted.view in self.content.children and not self.closed:
                self.source.value = text
        formatted = FormattedMarkdownInput(changed, font_size=self.host.font_size(),
            stylesheet=self.host.stylesheet(), image_source=lambda: self.host.image_source(reader))
        try:
            formatted.load(self.source.value)
        except ValueError as error:
            formatted.dispose()
            self.host.error(str(error))
            return
        self.host.bind_font(formatted.view, web=True, formatted=formatted)
        self.formatted = formatted
        self.content.clear()
        self.content.add(formatted.view)
