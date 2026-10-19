"""Settings entry for the shared native Markdown wiki and bundled Logistics guides."""
from pathlib import Path
from commonUtils.ui.native.markdown import MarkdownWikiView
from .preview import markdown_preview
from .markdown_speech import MarkdownSpeech
from .browser_ui import entry_icon, middle_filename
from .appearance import accessible_name, hierarchy_row_style
from toga.style.pack import CENTER


class DocumentationReader(MarkdownWikiView):
    """Add host-owned speech without changing the shared wiki's navigation API."""
    def __init__(self, app, *args, **kwargs):
        self.speech = None
        super().__init__(*args, **kwargs)
        self.speech = MarkdownSpeech(app, self.web, self.article,
            document_title=lambda: self.path,
            valid=lambda: app.active_host and getattr(app, 'documentation', None) is self and self.path is not None)
        self.speech.button.on_press = self.show_speech
        self.speech.button.enabled = self.path is not None
        self.navigation.add(self.speech.button)

    def reflow(self, width):
        super().reflow(width)
        parent = self.article if self.wide else self.view
        if self.navigation.parent is not parent:
            self.navigation.parent.remove(self.navigation)
            parent.insert(0, self.navigation)

    def filter(self, widget=None, **kwargs):
        super().filter(widget, **kwargs)
        if not hasattr(self, 'rows'):
            return
        query = self.search.value or ''
        mode = 'content' if self.mode.value == 'Page text' else 'filename'
        def visible(entries):
            for entry in entries:
                yield entry
                if query or entry.location in self.expanded:
                    yield from visible(entry.children)
        for row, entry in zip(self.rows.children, visible(self.catalog.search(query, mode))):
            button = row.children[-1]
            button.text = entry.title
            middle_filename(button)
            button.wiki_path = entry.page
            row.style.align_items = CENTER
            directory = entry.location != entry.page
            row.insert(2, entry_icon(directory, landing_page=entry.page is not None))
            accessible_name(button, entry.title + (' — Open folder page' if directory and entry.page is not None else ''))
            selected = self.path is not None and entry.page == self.path
            hierarchy_row_style(row, selected)

    def show_speech(self, widget=None, **kwargs):
        self.reading = True
        self.layout()
        self.speech.show()

    def open_page(self, *args, **kwargs):
        if self.speech is not None:
            self.speech.close()
        opened = super().open_page(*args, **kwargs)
        if self.speech is not None:
            self.speech.button.enabled = self.path is not None
        return opened


def show_documentation(app, directory=None, path=None):
    previous = getattr(app, 'documentation', None)
    if previous is not None and getattr(previous, 'speech', None) is not None:
        previous.speech.close()
    if directory is None:
        # The curated payload mirrors documentation paths below this package so
        # relative links between systemic and feature wikis also work offline.
        packaged = Path(__file__).with_name('help') / 'docs'
        directory = packaged if packaged.is_dir() else Path(__file__).resolve().parents[2] / 'docs'
        if path is None:
            path = directory / 'user_mobile/user_mobile.md' 
    def open_file(path):
        from commonUtils.runtime.local_files import LocalFiles
        from features.text_editor.resources import LocalTextCopies
        if not hasattr(app, 'cloud_client'):
            app.show_cloud(present=False)
        app.loop.create_task(app.open_crypt(copies=LocalTextCopies(LocalFiles(path.parent)), key=path.name))

    owner = DocumentationReader(app, directory, path, width=app.adaptive.content_width('settings', margin=0),
                             font_size=int(app.preferences.values['font_size']), render=markdown_preview, open_file=open_file)
    if app.show_view(owner.view, route='documentation', title='Documentation') is not False:
        app.documentation = owner
    return owner
