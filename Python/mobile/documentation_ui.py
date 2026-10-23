"""Settings entry for the shared native Markdown wiki and bundled Logistics guides."""
from pathlib import Path
from commonUtils.ui.native.markdown import MarkdownWikiView
from commonUtils.ui.native.markdown_images import local_image_source
from .preview import markdown_preview
from .markdown_speech import MarkdownSpeech
from .browser_ui import entry_icon, middle_filename
from .appearance import accessible_name, hierarchy_row_style
from toga.style.pack import CENTER


class DocumentationReader(MarkdownWikiView):
    """Add host-owned speech without changing the shared wiki's navigation API."""
    def __init__(self, app, *args, **kwargs):
        self.host_app = app
        self.speech = None
        kwargs.setdefault('image_source_factory', local_image_source)
        super().__init__(*args, **kwargs)
        from .font_scaling import bind
        bind(app, self.web, 'markdown', web=True)
        self.speech = MarkdownSpeech(app, self.web, self.article,
            document_title=lambda: self.path,
            valid=lambda: app.active_host and getattr(app, 'documentation', None) is self and self.path is not None)
        self.speech.button.on_press = self.show_speech
        self.speech.button.enabled = self.path is not None
        from .control_icons import apply_icon
        apply_icon(self.page_search.button, 'find', 'Find in this page')
        self.navigation.add(self.speech.button)
        from .workspace_navigation import menu_button
        from .control_icons import icon_button
        self.reader_menu = menu_button(self.toggle_browse, label='Browse documentation')
        self.reader_actions_button = icon_button('more', 'Documentation actions')
        self.view._workspace_menu_button = self.reader_menu
        self.view._native_reader_toolbar = self.navigation
        self.view._native_reader_buttons = lambda: [self.speech.button, self.reader_actions_button]
        self.view._native_reader_title = lambda: self.title.text
        self.view._native_reader_hidden = [self.title]
        self.refresh_reader_actions()

    def back_action(self):
        """Close compact browsing before retracing documentation links."""
        if not self.sidebar.expanded and self.sidebar.sidebar_open and self.path is not None:
            def close_sidebar():
                self.sidebar.show_detail()
                self.reading = True
            return close_sidebar
        if self.history_index > 0:
            return lambda: self.navigate_history(-1)
        return None

    def reflow(self, width):
        super().reflow(width)
        parent = self.article if self.wide else self.view
        if not self.host_app.routes.apple and self.navigation.parent is not parent:
            if self.navigation.parent is not None:
                self.navigation.parent.remove(self.navigation)
            parent.insert(0, self.navigation)

    def refresh_reader_actions(self):
        if hasattr(self, 'reader_actions'):
            self.reader_actions.dispose()
        from .action_menu import FeatureCommands
        actions = []
        if self.back_button.enabled:
            actions.append(('Previous page', self.back))
        if self.forward_button.enabled:
            actions.append(('Next page', self.forward))
        if self.up_button.enabled:
            actions.append(('Parent folder page', self.up))
        actions.append(('Find in this page…', self.show_page_search))
        actions.append(('Browse documentation', self.toggle_browse))
        self.reader_actions = FeatureCommands(self.reader_actions_button, self.host_app, actions, self.show_browse)

    def update_navigation(self):
        super().update_navigation()
        if hasattr(self, 'reader_actions_button'):
            self.refresh_reader_actions()

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

    def show_page_search(self, widget=None, **kwargs):
        self.reading = True
        self.layout()
        self.page_search.show()

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
        if hasattr(self, 'reader_actions_button'):
            self.refresh_reader_actions()
            self.host_app.adaptive.render()
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
        from commonUtils.runtime.resources.local import LocalFiles
        from features.text_editor.resources import LocalTextCopies
        if not hasattr(app, 'cloud_client'):
            app.show_cloud(present=False)
        app.loop.create_task(app.open_crypt(copies=LocalTextCopies(LocalFiles(path.parent)), key=path.name))

    owner = DocumentationReader(app, directory, path, width=app.adaptive.content_width('settings', margin=0),
                             font_size=int(app.preferences.values['markdown_font_size']), render=markdown_preview, open_file=open_file)
    if app.show_view(owner.view, route='documentation', title='Documentation') is not False:
        app.documentation = owner
    return owner
