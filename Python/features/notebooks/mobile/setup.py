"""Native mobile creation controls backed by the shared original template catalog."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import asyncio
from functools import lru_cache
import logging

import toga
from toga.style import Pack
from toga.style.pack import CENTER, COLUMN, NONE, ROW
from commonUtils.ui.native.forms import FittedLabel, fit_text
from ..notebook import Notebook
from ..templates import CATALOG, FORMATS, TEMPLATE_NOTICE, description, view_bounds


@lru_cache(maxsize=24)
def preview_png(template, paper_format):
    from features.pdf.document import PDFDocument
    from ..remarkable_export import backgrounds_pdf

    book = Notebook.new(template=template, paper_format=paper_format)
    return PDFDocument.render_page(backgrounds_pdf(book), 0, edge=384)


class NotebookTemplateChoices(toga.Box):
    def __init__(self, changed):
        super().__init__(style=Pack(direction=COLUMN, margin_top=12))
        self.changed = changed
        self._width = None
        self._enabled = True
        self._preview_active = False
        self._preview_task = None
        self._preview_choice = None
        self.template = toga.Selection(items=list(CATALOG.values()), style=Pack(height=48))
        self.paper_format = toga.Selection(items=list(FORMATS.values()), style=Pack(height=48))
        self.preview = toga.ImageView(style=Pack(height=138, background_color='white'))
        self.preview_frame = toga.Box(children=[self.preview],
            style=Pack(direction=COLUMN, align_items=CENTER, margin_top=8, background_color='#e5e5e5'))
        self.description = FittedLabel('', style=Pack(margin_top=8))
        self.notice = FittedLabel(TEMPLATE_NOTICE, style=Pack(font_size=12, margin_top=8))
        self.format_label = toga.Label('Template size', style=Pack(margin_top=8))
        self.choices = toga.Box(
            children=[toga.Label('First page template'), self.template, self.format_label, self.paper_format],
            style=Pack(direction=COLUMN))
        self.preview_layout = toga.Box(children=[self.choices, self.preview_frame], style=Pack(direction=COLUMN))
        self.add(self.preview_layout, self.description, self.notice)
        self.template.on_change = self.update_choice
        self.paper_format.on_change = self.update_choice
        self.update_choice()

    def selection(self):
        """Read native values at the action boundary, not only from callbacks."""
        template_value, format_value = self.template.value, self.paper_format.value
        template = next((key for key, label in CATALOG.items() if label == template_value), None)
        paper_format = next((key for key, label in FORMATS.items() if label == format_value), None)
        if template is None or paper_format is None:
            raise ValueError('Choose a page template and template size before creating the notebook.')
        return template, paper_format

    def update_choice(self, widget=None, **kwargs):
        if not self._enabled:
            return
        try:
            template, paper_format = self.selection()
        except ValueError:
            # Native reattachment can briefly report no selected row.
            return
        self.description.text = description(template)
        self.changed(template, paper_format)
        self.update_preview(template, paper_format)
        if self._width is not None:
            self.fit(self._width)

    def set_preview_active(self, active):
        self._preview_active = active
        if active:
            self.update_choice()
        else:
            self.cancel_preview()

    def cancel_preview(self):
        if self._preview_task is not None:
            self._preview_task.cancel()
            self._preview_task = None
        self._preview_choice = None

    def update_preview(self, template, paper_format):
        bounds = view_bounds([], paper_format == 'move')
        width = round(self.preview.style.height * bounds['width'] / bounds['height'])
        if self.preview.style.width != width:
            self.preview.style.width = width
        if not self._preview_active or (template, paper_format) == self._preview_choice:
            return
        self.cancel_preview()
        self.preview.image = None
        if template == 'Blank':
            self._preview_choice = (template, paper_format)
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._preview_choice = (template, paper_format)
        self._preview_task = loop.create_task(self.load_preview(template, paper_format))

    async def load_preview(self, template, paper_format):
        try:
            # Coalesce fast native picker callbacks before starting the renderer.
            await asyncio.sleep(.05)
            png = await asyncio.to_thread(preview_png, template, paper_format)
            self.preview.image = toga.Image(src=png)
        except Exception:
            logging.getLogger(__name__).exception('Could not load notebook template preview')
            self._preview_choice = None
        finally:
            if self._preview_task is asyncio.current_task():
                self._preview_task = None

    def set_enabled(self, enabled):
        was_enabled = self._enabled
        self._enabled = bool(enabled)
        self.template.enabled = self._enabled
        self.paper_format.enabled = self._enabled
        if self._enabled and not was_enabled:
            self.update_choice()

    def fit(self, width):
        self._width = width
        direction = ROW if width >= 480 else COLUMN
        if self.preview_layout.style.direction != direction:
            self.preview_layout.style.direction = direction
            self.choices.style.flex = int(direction == ROW)
            self.preview_frame.style.width = 152 if direction == ROW else NONE
            self.preview_frame.style.margin_left = 12 if direction == ROW else 0
        for label in (self.description, self.notice):
            fit_text(label, max(120, width - 40))
            if type(label._impl).__module__.startswith('toga_iOS.'):
                # UIKit's retained label can keep its previous intrinsic height
                # after a template change adds wrapped lines. Reserve the actual
                # measured text height before laying out the next form row.
                rendered = getattr(label, '_settings_rendered_text', label.text)
                label.style.height = int(float(label._impl.native.font.lineHeight)
                                         * len(rendered.split('\n')) + 2)


async def choose_new_notebook(panel, *, name='Notebook'):
    """Mount the shared form in the notebook library until Create or Cancel."""
    decision = asyncio.get_running_loop().create_future()
    controls = NotebookTemplateChoices(lambda *_: None)

    def finish(widget, **kwargs):
        if decision.done():
            return
        if widget is create:
            try:
                choice = controls.selection()
            except ValueError:
                return
        else:
            choice = None
        decision.set_result(choice)

    create = toga.Button('Create notebook', on_press=finish, style=Pack(height=48, flex=1))
    actions = toga.Box(children=[toga.Button('Cancel', on_press=finish, style=Pack(height=48)), create],
                       style=Pack(direction=ROW, margin=12))
    fields = toga.Box(children=[toga.Label('New notebook'), controls],
                      style=Pack(direction=COLUMN, margin=16))
    form = toga.Box(children=[toga.ScrollContainer(content=fields, horizontal=False, style=Pack(flex=1)),
                             actions], style=Pack(direction=COLUMN, flex=1))
    previous = list(panel.view.children)
    panel.view.clear()
    panel.view.add(form)
    panel.template_decision = decision
    try:
        controls.fit(panel.app.main_window.size.width)
        controls.set_preview_active(True)
        choice = await decision
    finally:
        controls.set_preview_active(False)
        panel.template_decision = None
        if form.parent is panel.view:
            panel.view.remove(form)
            if not panel.closed:
                panel.view.add(*previous)
    if choice is not None:
        template, paper_format = choice
        return Notebook.new(name, template=template, paper_format=paper_format)
