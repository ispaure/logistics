"""Settings entry for the shared native Markdown wiki and bundled Logistics guides."""
from pathlib import Path
from commonUtils.ui.native.markdown import MarkdownWikiView
from .preview import markdown_preview
from .markdown_speech import MarkdownSpeech


class DocumentationReader(MarkdownWikiView):
    """Add host-owned speech without changing the shared wiki's navigation API."""
    def __init__(self, app, *args, **kwargs):
        self.speech = None
        super().__init__(*args, **kwargs)
        self.speech = MarkdownSpeech(app, self.web, self.article,
            valid=lambda: app.active_host and getattr(app, 'documentation', None) is self and self.path is not None)
        self.speech.button.on_press = self.show_speech
        self.speech.button.enabled = self.path is not None
        self.navigation.add(self.speech.button)

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
