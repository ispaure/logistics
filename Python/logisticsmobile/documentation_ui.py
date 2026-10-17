"""Settings entry for the shared native Markdown wiki and bundled Logistics guides."""
from pathlib import Path
from commonUtils.ui.native.markdown import MarkdownWikiView
from .preview import markdown_preview


def show_documentation(app, directory=None, path=None):
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

    owner = MarkdownWikiView(directory, path, width=app.adaptive.content_width('settings', margin=0),
                             font_size=int(app.preferences.values['font_size']), render=markdown_preview, open_file=open_file)
    if app.show_view(owner.view, route='documentation', title='Documentation') is not False:
        app.documentation = owner
    return owner
