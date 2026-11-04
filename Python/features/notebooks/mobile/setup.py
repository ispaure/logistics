"""Native mobile creation controls backed by the shared original template catalog."""
import toga
from toga.style import Pack
from toga.style.pack import COLUMN
from commonUtils.ui.native.forms import FittedLabel, fit_text
from ..notebook import Notebook
from ..templates import CATALOG, FORMATS, TEMPLATE_NOTICE, description


class NotebookTemplateChoices(toga.Box):
    def __init__(self, changed):
        super().__init__(style=Pack(direction=COLUMN, margin_top=12))
        self.changed = changed
        self._width = None
        self._enabled = True
        self.template = toga.Selection(items=list(CATALOG.values()), style=Pack(height=48))
        self.paper_format = toga.Selection(items=list(FORMATS.values()), style=Pack(height=48))
        self.description = FittedLabel('', style=Pack(margin_top=8))
        self.notice = FittedLabel(TEMPLATE_NOTICE, style=Pack(font_size=12, margin_top=8))
        self.format_label = toga.Label('Template size', style=Pack(margin_top=8))
        self.add(toga.Label('First page template'), self.template, self.description,
                 self.format_label, self.paper_format,
                 self.notice)
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
        self.paper_format.enabled = template.startswith('Logistics ')
        self.description.text = description(template)
        self.changed(template, paper_format)
        if self._width is not None:
            self.fit(self._width)

    def set_enabled(self, enabled):
        was_enabled = self._enabled
        self._enabled = bool(enabled)
        self.template.enabled = self._enabled
        self.paper_format.enabled = self._enabled and self.template.value in [
            label for key, label in CATALOG.items() if key.startswith('Logistics ')]
        if self._enabled and not was_enabled:
            self.update_choice()

    def fit(self, width):
        self._width = width
        for label in (self.description, self.notice):
            fit_text(label, max(120, width - 40))
            if type(label._impl).__module__.startswith('toga_iOS.'):
                # UIKit's retained label can keep its previous intrinsic height
                # after a template change adds wrapped lines. Reserve the actual
                # measured text height before laying out the next form row.
                rendered = getattr(label, '_settings_rendered_text', label.text)
                label.style.height = int(float(label._impl.native.font.lineHeight)
                                         * len(rendered.split('\n')) + 2)


async def choose_new_notebook(app, *, name='Notebook'):
    """Legacy notebook-library entry uses native scrolling template choices."""
    from services.documents.authoring.document_dialogs import DocumentTypeDialog
    generation = getattr(app, 'navigation_generation', None)
    def current():
        return (getattr(app, 'active_host', True)
                and generation == getattr(app, 'navigation_generation', None))
    dialog = DocumentTypeDialog(choices=[(label, key) for key, label in CATALOG.items()])
    dialog.title = 'New notebook — first page template'
    dialog.message = TEMPLATE_NOTICE
    template = await app.main_window.dialog(dialog)
    if not current() or template not in CATALOG:
        return None
    paper_format = 'pro'
    if template.startswith('Logistics '):
        dialog = DocumentTypeDialog(choices=[(label, key) for key, label in FORMATS.items()])
        dialog.title, dialog.message = 'Template size', description(template)
        paper_format = await app.main_window.dialog(dialog)
        if not current() or paper_format not in FORMATS:
            return None
    return Notebook.new(name, template=template, paper_format=paper_format)
