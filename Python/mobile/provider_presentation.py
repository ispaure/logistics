"""Build provider document chrome after the host has approved/opened a session.

Credential identity, publication, private drafts and disposal stay with the provider
session owner. Format-specific navigation remains feature-owned.
"""
from pathlib import Path
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
from .control_icons import icon_button
from .reader_controls import ReadingFrame, PageFooter, page_buttons


def compact_private_view(self, view):
    from .action_menu import FeatureCommands
    old = view.crypt_view
    comic = view.crypt_reader.kind in {'.cbz', '.zip'}
    view.crypt_actions = icon_button('more', 'Reader actions' if comic else 'Private document actions')
    for control in (view.crypt_title, view.crypt_page, view.crypt_read_page, view.crypt_content, view.crypt_save):
        if control in old.children:
            old.remove(control)
    view.crypt_tools_view = toga.ScrollContainer(horizontal=False, content=old, style=Pack(flex=1))
    old.add(toga.Button('Return to private document', on_press=self.resume_crypt, style=Pack(height=44)))
    if view.crypt_reader.book is not None:
        old.insert(0, toga.Button('Contents and bookmarks', on_press=self.show_provider_epub_navigation,
                                 style=Pack(height=44)))
    actions, neighbors = _private_actions(self, view, comic)
    view.crypt_action_items = list(actions)
    view.crypt_actions_menu = FeatureCommands(view.crypt_actions, self, actions, self.show_private_tools, document=True)
    view.crypt_title.style.flex = 1
    view.crypt_page.style.flex = 1
    view.crypt_title.style.font_size = 12
    if comic:
        view.crypt_title.text = f'Page 1/{len(view.crypt_reader.labels)}'
        view.crypt_title.style.text_align = 'center'
    controls = [toga.Box(children=[view.crypt_title, view.crypt_actions], style=Pack(direction=ROW))]
    view.reader_toolbar = controls[0]
    if view.crypt_reader.book is not None:
        view.reader_speech_button = icon_button('speaker', 'Read aloud', on_press=self.show_provider_read_aloud)
        view.reader_toolbar.insert(1, view.reader_speech_button)
    if view.crypt_reader.kind == '.pdf':
        controls.append(_pdf_tools(self, view))
    elif (not view.crypt_reader.editable and not comic and view.crypt_reader.book is None
          and not getattr(view.crypt_reader, 'image_document', False)):
        controls.append(toga.Box(children=[view.crypt_page, view.crypt_read_page], style=Pack(direction=ROW)))
    controls.append(view.crypt_content)
    if view.crypt_reader.editable:
        view.crypt_save.text = 'Save'
        footer = toga.Box(children=[] if getattr(view.crypt_reader, 'read_only', False) else [view.crypt_save],
                          style=Pack(direction=ROW, margin_top=4))
        view.crypt_save.style.flex = 1
        if view.crypt_reader.kind in {'.md', '.markdown'}:
            from .composition.presentation import provider_markdown
            view._provider_markdown = provider_markdown(self, view, footer)
            view.crypt_preview_button = view._provider_markdown.preview_button
            view.crypt_edit_mode = view._provider_markdown.edit_mode
            view.crypt_markdown_footer = footer
        if footer.children or view.crypt_reader.kind in {'.md', '.markdown'}:
            controls.append(footer)
    if not view.crypt_reader.editable:
        _mount_reader(self, view, controls, comic, neighbors)
    else:
        _mount_editor(self, view, controls)
    from .document_location import install_document_location
    install_document_location(view.crypt_view, copies=view._crypt_reader_store, reader=view.crypt_reader)
    view.crypt_view._native_reader_title = lambda: (Path(view.crypt_reader.name).name +
        (' (🕵️ Session-Only)' if 'Session-Only' in view.crypt_view._document_storage_status else ''))
    view.crypt_immersive = view.crypt_reader.kind in {'.cbz', '.zip'}
    if view.crypt_immersive:
        view.reading_frame.set_immersive(True, comic=True)
    self.register_transfer_status(view.crypt_view)



def _private_actions(self, view, comic):
    """Choose document actions before mounting shared reader chrome."""
    from .reader_controls import comic_actions, comic_pages
    if comic:
        host = getattr(self, 'app', self)
        writable = not getattr(view.crypt_reader, 'read_only', False)
        neighbors = (getattr(view._crypt_reader_store, 'provider', None) is not None
                     or getattr(view._crypt_reader_store, 'resource', None) is not None)
        actions = comic_actions(pages=self.show_private_tools, appearance=self.show_provider_layout,
            reading_mode=self.toggle_private_reading_mode, fit=self.fit_private_page,
            metadata=self.edit_crypt_metadata if writable else None, info=self.show_provider_comic_info,
            close=self.close_crypt)
        view.crypt_tools_view = comic_pages(view.crypt_page, self.resume_crypt)
    elif getattr(view.crypt_reader, 'read_only', False):
        actions = []
        if view.crypt_reader.book is not None:
            actions.extend([('Chapters and bookmarks…', self.show_provider_epub_navigation),
                ('Read aloud…', self.show_provider_read_aloud), ('Find in chapter…', self.show_provider_epub_find),
                ('Appearance…', self.show_provider_layout)])
        elif view.crypt_reader.kind == '.pdf':
            actions.append(('Pages and search', lambda: view.pdf_tools.toggle()))
        elif getattr(view.crypt_reader, 'image_document', False):
            actions.append(('Fit image', self.fit_private_page))
        actions.append(('Close private document', self.close_crypt))
    else:
        actions = [('File actions…' if view.crypt_reader.editable else 'Open / Metadata…', self.show_private_tools)]
        if view.crypt_reader.book is not None:
            actions.extend([('Read aloud…', self.show_provider_read_aloud), ('Find in chapter…', self.show_provider_epub_find),
                ('Appearance…', self.show_provider_layout)])
        actions.append(('Close private document', self.close_crypt))
    if view.crypt_reader.book is not None or view.crypt_reader.kind == '.pdf':
        actions.append(('Fullscreen', self.toggle_private_reading_mode))
    if view.crypt_reader.kind == '.pdf':
        from features.pdf.annotation import LABEL
        from features.pdf.mobile.annotation import annotate_pdf
        actions.append((LABEL, lambda: annotate_pdf(self, view.crypt_reader)))
    if view.crypt_reader.book is not None or view.crypt_reader.kind in {'.md', '.markdown'}:
        app = getattr(self, 'app', self)
        actions.append(('Open beside another document', app.adaptive.show_pair_picker))
    from .document_sources import folder_location, show_in_folder
    if folder_location(self.app, self.session, view) is not None:
        actions.append(('Show in folder', lambda: show_in_folder(self.app, self.session, self)))
    actions.append(('All documents', self.show_documents_hub))
    return actions, neighbors if comic else False


def _pdf_tools(self, view):
    """Assemble PDF navigation with the existing retained-session guards."""
    from .provider_ui import private_label
    async def jump(widget=None, **kwargs):
        from features.pdf.document import page_index
        reader = view.crypt_reader
        if reader is None:
            return
        try:
            index = page_index(view.pdf_number.value, len(reader.labels))
        except ValueError as error:
            view.crypt_title.text = private_label(error)
            view.pdf_jump_status.text = str(error)
            return
        token = self.workspace.token(self.session.id)
        navigation = self.app.navigation_generation
        # A native viewport refresh can already be rendering the current page.
        # Retain the submitted number before that refresh synchronizes the input.
        while self.cloud_busy:
            view.pdf_jump_status.text = 'Loading the current page…'
            await self.operation_idle.wait()
        if (not self.active_host or view.crypt_reader is not reader
                or not self.workspace.accepts(token) or self.manager.active is not self
                or self.app.navigation_generation != navigation):
            if self.active_host and view.crypt_reader is reader and self.workspace.accepts(token):
                view.pdf_jump_status.text = 'Page jump cancelled.'
            return
        view.pdf_jump_status.text = ''
        await self.move_private_page(index)
    view.pdf_number = toga.TextInput(value='1', on_confirm=jump, style=Pack(flex=1, height=44))
    view.pdf_jump_status = toga.Label('')
    jump_row = toga.Box(children=[toga.Label(f'Page / {len(view.crypt_reader.labels)}'),
        view.pdf_number, toga.Button('Go', on_press=jump, style=Pack(height=44))], style=Pack(direction=ROW))
    from features.pdf.mobile.search import PDFSearchBar
    reader = view.crypt_reader
    view.pdf_search = PDFSearchBar(reader.pdf, on_page=self.move_private_page,
        alive=lambda: self.active_host and self.crypt_reader is reader
            and self.session.id in self.workspace.sessions and self.manager.active is self)
    from features.pdf.mobile.canvas import PDFTools
    from features.pdf.mobile.contents import PDFContents
    from .appearance import hierarchy_row_style
    view.pdf_contents = PDFContents(reader.pdf, on_page=self.move_private_page,
        alive=lambda: self.active_host and self.crypt_reader is reader
            and self.session.id in self.workspace.sessions and self.manager.active is self,
        row_style=hierarchy_row_style)
    view.pdf_tools = PDFTools([jump_row, view.pdf_jump_status, view.pdf_contents, view.pdf_search])
    return view.pdf_tools.widget


def _mount_reader(self, view, controls, comic, neighbors):
    from .reader_controls import ComicHeader
    from .workspace_navigation import menu_button
    host = getattr(self, 'app', self)
    reader_menu = None if comic else (menu_button(self.toggle_provider_epub_tools, label='Contents and bookmarks')
                   if view.crypt_reader.book is not None else menu_button(lambda widget, **kw:
                       host.adaptive.show_browser(getattr(view, 'presentation_destination', 'documents'))))
    if reader_menu is not None:
        controls[0].insert(0, reader_menu)
    if comic:
        controls[0].remove(view.crypt_actions)
        controls[0].remove(view.crypt_title)
        view.comic_header = ComicHeader(view.crypt_actions,
            previous=self.previous_provider_comic_file if neighbors else None,
            following=self.next_provider_comic_file if neighbors else None)
        header = view.comic_header.widget
    else:
        header = controls[0]
    view.previous_page, view.next_page = page_buttons(self.previous_private_page, self.next_private_page)
    view.page_footer = PageFooter(view.previous_page, view.next_page, self.move_private_page,
                                  status=view.crypt_title if comic else None,
                                  unit='chapter' if view.crypt_reader.book is not None else 'page',
                                  vertical=view.crypt_reader.kind == '.pdf')
    view.page_footer.sync(comic=view.crypt_reader.kind in {'.cbz', '.zip'},
                          count=len(view.crypt_reader.labels), index=0,
                          right_to_left=getattr(view.crypt_reader, 'right_to_left', False))
    if view.crypt_reader.book is not None:
        async def seek(chapter, fraction):
            self._provider_epub_target = ('fraction', fraction)
            await self.move_private_page(chapter)
        view.page_footer.set_book(view.crypt_reader.book, seek)
        panel = view.provider_epub_view
        view.page_footer.chapter_progress(0, len(view.crypt_reader.labels), panel.offset, panel.chapter.length)
    footer = view.page_footer.widget
    if view.crypt_reader.book is not None:
        view.crypt_title.style.update(flex=1, width=1, height=48, margin=0)
    view.reader_restore = (toga.Button('Show reading controls', on_press=self.toggle_private_reading_mode,
                                     style=Pack(height=48)) if view.crypt_reader.book is not None or view.crypt_reader.kind == '.pdf' else None)
    image = getattr(view.crypt_reader, 'image_document', False)
    reader_controls = [header] if image else [header, footer]
    if view.crypt_reader.kind == '.pdf':
        reader_controls.insert(1, view.pdf_tools.widget)
        from .control_icons import apply_icon
        def tools_changed():
            apply_icon(view.pdf_tools.button, 'find',
                'Hide pages and search' if view.pdf_tools.panel in view.pdf_tools.widget.children else 'Pages and search')
            if hasattr(view, 'crypt_view'):
                self.app.refresh_reader_exit(view.crypt_view)
                self.app.adaptive.render()
        view.pdf_tools.on_state_change = tools_changed
        view.pdf_tools.refresh_control()
        # PDF progress follows the vertical page gesture, beside the reading area.
        view.pdf_body = toga.Box(children=[view.crypt_content, footer], style=Pack(direction=ROW, flex=1))
        reader_controls.remove(footer)
    view.reading_frame = ReadingFrame(view.pdf_body if view.crypt_reader.kind == '.pdf' else view.crypt_content, reader_controls,
        margin=0, restore=view.reader_restore,
        top_controls=2 if view.crypt_reader.kind == '.pdf' else 1)
    if view.crypt_reader.kind == '.pdf':
        view.reading_frame.side_controls = [(view.pdf_body, footer)]
    view.crypt_view = view.reading_frame.widget
    view.crypt_view._image_preview_surface = bool(image)
    view.crypt_view._native_reader_toolbar = header
    view.crypt_view._native_reader_status = view.crypt_title
    if view.crypt_reader.book is not None:
        view.crypt_view._native_reader_buttons = lambda: [view.reader_speech_button, view.crypt_actions]
    elif comic:
        view.crypt_view._native_reader_buttons = lambda: [
            *([view.comic_header.previous] if view.comic_header.available[0] else []),
            *([view.comic_header.following] if view.comic_header.available[1] else []), view.crypt_actions]
    elif view.crypt_reader.kind == '.pdf':
        view.crypt_view._native_reader_buttons = lambda: [view.pdf_tools.button, view.crypt_actions]
    else:
        view.fit_button = icon_button('fit', 'Fit image', on_press=self.fit_private_page)
        if image:
            from features.images.mobile.navigation import install
            view.image_file_buttons = install(self, view)
            for button in view.image_file_buttons:
                header.insert(len(header.children) - 1, button)
        view.crypt_view._native_reader_buttons = lambda: [*getattr(view, 'image_file_buttons', ()), view.fit_button, view.crypt_actions]
    if reader_menu is not None:
        view.crypt_view._workspace_menu_button = reader_menu
    view.crypt_controls = view.reading_frame.controls
    view.previous_page.enabled = False
    view.next_page.enabled = (view.crypt_reader.comic_navigation.next(0) is not None if comic
                              else view.crypt_reader.book is not None or len(view.crypt_reader.labels) > 1)
    if view.crypt_reader.kind == '.pdf':
        from features.pdf.mobile.canvas import sync_pdf_progress
        sync_pdf_progress(view)


def _mount_editor(self, view, controls):
    markdown = view.crypt_reader.kind in {'.md', '.markdown'}
    view.crypt_view = toga.Box(children=controls, style=Pack(direction=COLUMN, margin=0 if markdown else 12, flex=1))
    view.crypt_view._keyboard_actions_required = True
    if markdown:
        view.crypt_view._workspace_toolbar = view.reader_toolbar
        view._native_reading_buttons = view._provider_markdown.native_buttons
        view.crypt_view._native_reader_toolbar = view.reader_toolbar
        view.crypt_view._native_reader_status = view.crypt_title
        view.crypt_view._native_reader_buttons = lambda: view._native_reading_buttons
        view.crypt_title.style.update(flex=1, width=1, height=48, margin=0)
        self.refresh_private_text_controls(view=view)
    else:
        from .control_icons import apply_icon
        apply_icon(view.crypt_save, 'save', 'Save text')
        view.crypt_view._workspace_toolbar = view.reader_toolbar
        view._native_reading_buttons = [view.crypt_actions]
        view.crypt_view._native_reader_toolbar = view.reader_toolbar
        view.crypt_view._native_reader_status = view.crypt_title
        view.crypt_view._native_reader_buttons = lambda: view._native_reading_buttons
        view.crypt_view._native_reader_hidden = [view.crypt_save]
        self.refresh_private_text_controls(view=view)
    view.crypt_controls = [control for control in controls if control is not view.crypt_content]


def prepare_comic_spread(controller, view, content):
    """Decode a replacement before publication can retire displayed pixels.

    A retained SpreadView returns a delayed commit callback. Its old pixels stay
    authoritative if preparation fails or publication rejects the reader token.
    """
    publish_spread = None
    from features.comics.mobile.presentation import SpreadView
    from commonUtils.ui.native.image_canvas import ImageCanvas
    _, data = content
    # Decode/compose before retiring the displayed private pixels. Native
    # allocation or decoder failures must preserve the previous spread.
    previous = getattr(view, 'provider_spread', None)
    if isinstance(previous, SpreadView) and previous in view.crypt_content.children:
        prepared_spread = previous
        publish_spread = previous.prepare_replacement(data,
            right_to_left=getattr(view.crypt_reader, 'right_to_left', False),
            viewport=controller.private_comic_viewport(view), seam=controller.private_comic_seam(view),
            crop=view.crypt_reader.comic_navigation.crop,
            seam_gap=controller.format_services.seam_gap(view.crypt_content),
            anchor_right=controller.private_comic_seam(view) is not None)
    else:
        prepared_spread = SpreadView(data, canvas=ImageCanvas,
            on_page=controller.swipe_crypt_page, on_toggle=controller.toggle_private_reading_mode,
            right_to_left=getattr(view.crypt_reader, 'right_to_left', False),
            viewport=controller.private_comic_viewport(view),
            seam=controller.private_comic_seam(view),
            crop=view.crypt_reader.comic_navigation.crop,
            seam_gap=controller.format_services.seam_gap(view.crypt_content),
            anchor_right=controller.private_comic_seam(view) is not None)
    from .magnifier import bind
    bind(controller, prepared_spread)
    return prepared_spread, publish_spread


def prepare_epub_page(host, controller, view, content):
    """Build one chapter using host appearance and session-owned navigation.

    The view retains chapter positions and bookmark controls. The controller owns
    navigation callbacks; the application host supplies typography and drawers.
    Publication, stale-token checks and old-view disposal remain with the caller.
    """
    from features.books.mobile.provider_reader import provider_view
    from .page_animation import begin_page_slide, finish_page_slide
    from features.books.mobile.typography import options as typography_options
    book = view.crypt_reader.book
    index = view.crypt_reader.labels.index(view.crypt_page.value)
    locations = getattr(view, '_provider_epub_locations', {})
    view._provider_epub_locations = locations
    target = getattr(controller, '_provider_epub_target', None)
    controller._provider_epub_target = None
    offset = locations.get(book.spine[index], 0)
    if target is not None:
        offset = (round(content[1].length * target[1]) if isinstance(target, tuple)
                  else content[1].anchors.get(target, 0) if isinstance(target, str) else target)
    from .palette import themed_chapter
    content = (themed_chapter(content[0], host.preferences.values['reading_theme']), content[1])
    def position_changed(value):
        locations[book.spine[index]] = value
        if hasattr(view, 'page_footer'):
            view.page_footer.chapter_progress(index, len(book.spine), value, content[1].length)
    from .chapter_drawer import ChapterDrawer
    view.provider_epub_view = provider_view(book, index, offset=offset, prepared=content,
        font_size=int(host.preferences.values['epub_font_size']),
        margin=int(host.preferences.values['reading_margin']), theme=host.preferences.values['reading_theme'], typography=typography_options(host.preferences.values),
        on_chapter=controller.open_provider_epub_chapter,
        on_position=position_changed,
        motion_enabled=host.preferences.values.get('android_eink') != 'true',
        sidebar_factory=lambda *args, **kwargs: ChapterDrawer(*args, app=host, **kwargs))
    from .font_scaling import bind
    epub_surface = getattr(view.provider_epub_view, 'webview', None)
    if epub_surface is not None:
        from .fold_layout import bind_epub_geometry
        bind_epub_geometry(epub_surface)
        bind(host, epub_surface, 'epub', web=True)
    else:
        bind(host, view.provider_epub_view.text, 'epub')
    chapters = getattr(view.provider_epub_view, 'chapters', None)
    if chapters is not None:
        from .appearance import hierarchy_row_style
        chapters.row_style, chapters.current = hierarchy_row_style, index
        chapters.render()
    view.provider_epub_view.page_motion_enabled = lambda: host.preferences.values.get('android_eink') != 'true'
    if epub_surface is None:
        view.provider_epub_view.page_motion = (
            lambda surface, delta: begin_page_slide(surface, delta, host.preferences.values),
            lambda surface, delta: finish_page_slide(surface, delta, host.preferences.values))
    tools = view.provider_epub_view.tools
    if tools.button in tools.widget.children:
        tools.widget.remove(tools.button)
    for control in (view.crypt_bookmark_button, view.crypt_bookmark_selector):
        if control.parent is not None:
            control.parent.remove(control)
        tools.panel.add(control)
    tools.panel.add(toga.Label('Bookmarks stay in this session\nand are cleared on close.'))
    return view.provider_epub_view
