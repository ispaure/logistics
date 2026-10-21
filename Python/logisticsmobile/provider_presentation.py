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
    from .provider_ui import private_label
    from .action_menu import FeatureCommands
    from .reader_controls import ComicHeader, comic_actions, comic_pages
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
    if comic:
        host = getattr(self, 'app', self)
        writable = not getattr(view.crypt_reader, 'read_only', False)
        neighbors = writable and getattr(view._crypt_reader_store, 'provider', None) is not None
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
    if view.crypt_reader.book is not None or view.crypt_reader.kind in {'.md', '.markdown'}:
        app = getattr(self, 'app', self)
        actions.append(('Open beside another document', app.adaptive.show_pair_picker))
    from .document_sources import folder_location, show_in_folder
    if folder_location(self.app, self.session, view) is not None:
        actions.append(('Show in folder', lambda: show_in_folder(self.app, self.session, self)))
    actions.append(('All documents', self.show_documents_hub))
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
        async def jump(widget=None, **kwargs):
            from features.pdf.document import page_index
            try:
                index = page_index(view.pdf_number.value, len(view.crypt_reader.labels))
            except ValueError as error:
                view.crypt_title.text = private_label(error)
                view.pdf_jump_status.text = str(error)
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
        controls.append(view.pdf_tools.widget)
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
            from .feature_hosts import provider_markdown
            view._provider_markdown = provider_markdown(self, view, footer)
            view.crypt_preview_button = view._provider_markdown.preview_button
            view.crypt_edit_mode = view._provider_markdown.edit_mode
            view.crypt_markdown_footer = footer
        if footer.children:
            controls.append(footer)
    if not view.crypt_reader.editable:
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
                                      unit='chapter' if view.crypt_reader.book is not None else 'page')
        view.page_footer.sync(comic=view.crypt_reader.kind in {'.cbz', '.zip'},
                              count=len(view.crypt_reader.labels), index=0,
                              right_to_left=getattr(view.crypt_reader, 'right_to_left', False))
        if view.crypt_reader.book is not None:
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
        view.reading_frame = ReadingFrame(view.crypt_content, reader_controls,
            margin=0, restore=view.reader_restore,
            top_controls=2 if view.crypt_reader.kind == '.pdf' else 1)
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
            view.crypt_view._native_reader_buttons = lambda: [view.fit_button, view.crypt_actions]
        if reader_menu is not None:
            view.crypt_view._workspace_menu_button = reader_menu
        view.crypt_controls = view.reading_frame.controls
        view.previous_page.enabled = False
        view.next_page.enabled = (view.crypt_reader.comic_navigation.next(0) is not None if comic
                                  else view.crypt_reader.book is not None or len(view.crypt_reader.labels) > 1)
    else:
        markdown = view.crypt_reader.kind in {'.md', '.markdown'}
        view.crypt_view = toga.Box(children=controls, style=Pack(direction=COLUMN, margin=0 if markdown else 12, flex=1))
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
    view.crypt_view._native_reader_title = lambda: Path(view.crypt_reader.name).name
    view.crypt_immersive = view.crypt_reader.kind in {'.cbz', '.zip'}
    if view.crypt_immersive:
        view.reading_frame.set_immersive(True, comic=True)
    self.register_transfer_status(view.crypt_view)

