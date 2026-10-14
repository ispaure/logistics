"""Small native mobile text/Markdown prototype with app-private recovery."""
import asyncio
from pathlib import Path
from uuid import uuid4
import weakref
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
from .documents import DocumentStore, document_name
from .preferences import Preferences
from .preview import markdown_preview
from .reader_sessions import ReaderWorkspace
from .chat_ui import ChatUI
from .cloud_ui import CloudUI
from .native_navigation import NativeNavigationHost
from .routing import Routes
from .workspace import Workspace, MAX_SESSIONS
from .editors import TextEditorView
from .adaptive_workspace import AdaptiveWorkspace

_active_hosts = weakref.WeakValueDictionary()


class LogisticsMobile(ReaderWorkspace, ChatUI, CloudUI, toga.App):
    storage_root = None  # Host tests may supply a private fixture directory.

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Install before Android starts cooperative dispatch or registers Java
        # wake-up callbacks. Desktop/iOS loops lack this method and are unchanged.
        from .native_loop import bind_cooperative_loop
        bind_cooperative_loop(self.loop)

    def startup(self):
        root = Path(self.storage_root or self.paths.data)
        self.private_root = root
        previous_host = _active_hosts.get(str(root.resolve()))
        if previous_host is not None:
            previous_host.active_host = False
            for session in previous_host.workspace.sessions.values():
                previous_host.workspace.invalidate(session.id)
            cancelled = getattr(previous_host, '_crypt_cancel', None)
            if cancelled is not None:
                cancelled.set()
        self.active_host = True
        _active_hosts[str(root.resolve())] = self
        self.preferences = Preferences(root)
        self.store = DocumentStore(root / 'Documents')
        self.workspace = Workspace(root)
        self.text_views = {}
        self.current = None
        self.loading = True
        self.labels = {}
        self.editor_view = TextEditorView(self)
        self.editor_view.bind()
        self.native_host = NativeNavigationHost(on_select=self.select_destination)
        self.routes = Routes(self.native_host, guard=self.checkpoint, changed=self.route_changed)
        self.adaptive = AdaptiveWorkspace(self)
        self.routes.on_render = self.adaptive.render
        self.navigation = self.native_host.root
        self.body = self.routes.body()
        self.main_window = toga.MainWindow(title='Logistics', content=self.navigation,
                                           on_lose_focus=self.checkpoint, on_resize=self.resize_workspace)
        self.on_exit = self.exit_app
        self.refresh_documents()
        self.loading = False
        if self.labels:
            key = self.preferences.values['last_document']
            active = self.workspace.sessions.get(self.workspace.active)
            if active is not None and active.provider == 'managed-text':
                key = active.resource
            if self.preferences.values['restore_last_document'] != 'true' or key not in self.labels.values():
                key = next(iter(self.labels.values()))
            self.open_document(key)
        else:
            self.new_document()
        self.show_documents_hub()
        self.show_settings()
        self.show_locations()
        self.show_home()
        self.main_window.show()
        self.native_host.install(self.main_window)
        self.routes.install()
        self.adaptive.install()

    def select_destination(self, destination):
        if not self.checkpoint():
            return False
        self.save_workspace()
        self.body = self.routes.body(destination)
        # Material selection is reported before the shared destination commits.
        if self.routes.back_callback is not None:
            self.routes.back_callback.setEnabled(bool(self.routes.screens[destination]))
        return True

    def route_changed(self, body):
        self.body = body
        if (hasattr(self, 'editor_view') and self.editor_view.session is not None
                and self.document_view in body.children):
            self.editor_view.session.view['markdown_mode'] = 'edit'

    def resize_workspace(self, widget=None, *args, **kwargs):
        self.adaptive.render()

    def show_view(self, view, *, checkpoint=True, destination=None, route=None, title='', root=False):
        if checkpoint and not self.checkpoint():
            return False
        target = destination or self.native_host.state.destination
        if self.adaptive.split is not None and target == 'documents' and not root:
            self.native_host.activate('documents')
            self.adaptive.present(view, route=route, title=title)
            return True
        self.routes.show(view, destination=destination, route=route, title=title, root=root)
        if root and target == 'documents':
            self.adaptive.show_list()
        return True

    def show_home(self, widget=None, **kwargs):
        box = toga.Box(style=Pack(direction=COLUMN, margin=16))
        box.add(toga.Label('Welcome to Logistics', style=Pack(font_size=24, margin_bottom=12)))
        box.add(toga.Label('Your files, reading and writing.', style=Pack(margin_bottom=12)))
        for title, action in (('Files', self.show_locations), ('Text & Markdown', self.show_documents),
                              ('Books & Comics', self.show_library), ('LM Chat', self.show_chat)):
            box.add(toga.Button(title, on_press=action, style=Pack(height=52, margin_bottom=8)))
        self.show_view(box, destination='home', root=True)

    def show_locations(self, widget=None, **kwargs):
        box = toga.Box(style=Pack(direction=COLUMN, margin=16))
        box.add(toga.Label('Files', style=Pack(font_size=24, margin_bottom=12)))
        box.add(toga.Label('Choose a location', style=Pack(margin_bottom=12)))
        box.add(toga.Button('On this device', on_press=self.show_local_location, style=Pack(height=52)))
        box.add(toga.Button('Remote files & LocalCrypt', on_press=self.show_cloud, style=Pack(height=52, margin_top=8)))
        if self.preferences.error:
            box.add(toga.Label(self.preferences.error, style=Pack(margin_top=12)))
        self.show_view(box, destination='files', root=True)

    async def show_local_location(self, widget=None, **kwargs):
        self.show_cloud(present=False)
        restore = getattr(self, 'cloud_restore_task', None)
        if restore is not None and not restore.done():
            await restore
        await self.show_files()

    def show_documents_hub(self, widget=None, **kwargs):
        box = toga.Box(style=Pack(direction=COLUMN, margin=16))
        box.add(toga.Label('Documents', style=Pack(font_size=24, margin_bottom=12)))
        box.add(toga.Label('Read, write and continue your work.', style=Pack(margin_bottom=12)))
        box.add(toga.Button('Text & Markdown', on_press=self.show_documents, style=Pack(height=52)))
        box.add(toga.Button('Books & Comics', on_press=self.show_library, style=Pack(height=52, margin_top=8)))
        box.add(toga.Button('LM Chat', on_press=self.show_chat, style=Pack(height=52, margin_top=8)))
        box.add(toga.Label(f'{len(self.labels)} private document(s)', style=Pack(margin_top=8)))
        box.add(toga.Label('Open documents', style=Pack(font_size=18, margin_top=12)))
        for session in list(self.workspace.sessions.values()):
            try:
                if session.provider == 'managed-text':
                    title = session.title or self.store.open(session.resource).name
                elif session.provider == 'library':
                    title = session.title or self.reader_manager().catalog.library_store.read_record(session.resource)[0]['name']
                else:
                    continue
            except (OSError, ValueError, KeyError, TypeError):
                title = 'Unavailable document'
            box.add(toga.Box(children=[
                toga.Button(title if len(title) <= 32 else title[:29] + '…',
                            on_press=self.session_opener(session.id), style=Pack(flex=1, height=44)),
                toga.Button('Close', on_press=self.session_closer(session.id), style=Pack(height=44))],
                style=Pack(direction=ROW)))
        box.add(toga.Label('Stored documents', style=Pack(font_size=18, margin_top=12)))
        for title, resource in self.labels.items():
            box.add(toga.Button(title if len(title) <= 32 else title[:29] + '…',
                on_press=self.stored_document_opener(resource), style=Pack(height=44)))
        if self.workspace.error:
            box.add(toga.Label(self.workspace.error, style=Pack(margin_top=8)))
        self.show_view(toga.ScrollContainer(content=box, style=Pack(flex=1)), destination='documents', root=True)

    def stored_document_opener(self, resource):
        def activate(widget=None, **kwargs):
            if self.checkpoint():
                if self.open_document(resource):
                    self.show_documents(resume=True)
        return activate

    def session_opener(self, key):
        def activate(widget=None, **kwargs):
            session = self.workspace.sessions.get(key)
            if session is not None and self.checkpoint():
                if session.provider == 'library':
                    self.loop.create_task(self.resume_library_session(session))
                else:
                    if self.open_document(session.resource):
                        self.show_documents(resume=True)
                    else:
                        self.show_unavailable_session(key)
        return activate

    async def resume_library_session(self, session):
        try:
            await self.open_book(session.resource)
        except (OSError, ValueError, KeyError, TypeError):
            if session.id in self.workspace.sessions:
                self.show_unavailable_session(session.id)

    def show_unavailable_session(self, key):
        box = toga.Box(style=Pack(direction=COLUMN, margin=16, flex=1))
        box.add(toga.Label('Document unavailable', style=Pack(font_size=18)))
        box.add(toga.Label('Its stored data could not be opened.\nExisting files have been preserved.'))
        box.add(toga.Button('Try again', on_press=self.session_opener(key), style=Pack(height=44)))
        box.add(toga.Button('Remove from open documents', on_press=self.session_closer(key), style=Pack(height=44)))
        box.add(toga.Button('All documents', on_press=self.show_documents_hub, style=Pack(height=44)))
        self.show_view(box, destination='documents', route='unavailable:' + key, title='Unavailable document')

    def session_closer(self, key):
        def close(widget=None, **kwargs):
            self.request_close_session(key)
        return close

    def request_close_session(self, key):
        owner = self.text_views.get(key)
        if owner is None or not owner.document.modified:
            return self.close_session(key)
        box = toga.Box(style=Pack(direction=COLUMN, margin=16, flex=1))
        from .cloud_ui import import_hint
        box.add(toga.Label(import_hint('Close ' + owner.document.name), style=Pack(font_size=18)))
        box.add(toga.Label('Choose what to do with\nyour unsaved changes.', style=Pack(margin_bottom=12)))
        def choose(choice):
            def action(widget=None, **kwargs):
                self.close_session(key, choice=choice)
            return action
        box.add(toga.Button('Save and close', on_press=choose('save'), style=Pack(height=44)))
        if not getattr(owner.document, 'private', False):
            box.add(toga.Button('Keep draft and close', on_press=choose('keep'), style=Pack(height=44)))
        box.add(toga.Button('Discard changes and close', on_press=choose('discard'), style=Pack(height=44)))
        box.add(toga.Button('Cancel', on_press=lambda widget, **kw: self.cancel_close_session(key), style=Pack(height=44)))
        self.close_notice = toga.Label('', style=Pack(margin_top=8))
        box.add(self.close_notice)
        return self.show_view(box, checkpoint=False, route='close:' + key, destination='documents', title='Close document')

    def cancel_close_session(self, key):
        owner = self.text_views.get(key)
        if owner is not None:
            owner.bind()
            self.workspace.activate(key)
            self.show_documents()

    def close_session(self, key, *, choice='keep'):
        if key not in self.workspace.sessions:
            return False
        if choice == 'cancel':
            return False
        if choice not in ('keep', 'save', 'discard'):
            raise ValueError('Unsupported close action.')
        if self.workspace.sessions[key].provider == 'library':
            return self.reader_manager().close(key)
        owner = self.text_views.get(key)
        def guard(session):
            if owner is None:
                return True
            if choice == 'keep' and getattr(owner.document, 'private', False) and owner.document.modified:
                owner.status.text = 'Save this session-only draft before closing.'
                return False
            try:
                if choice == 'save':
                    self.store.save(owner.document)
                elif choice == 'discard':
                    self.store.discard(owner.document)
                else:
                    self.store.checkpoint(owner.document)
                return True
            except (OSError, ValueError) as error:
                owner.status.text = 'Could not close; edits retained: ' + str(error)
                if hasattr(self, 'close_notice'):
                    self.close_notice.text = owner.status.text
                return False
        was_current = owner is self.editor_view
        if not self.workspace.close(key, guard=guard):
            return False
        self.text_views.pop(key, None)
        if was_current:
            self.current = None
            remaining = self.workspace.sessions.get(self.workspace.active)
            if remaining is not None and remaining.provider == 'managed-text':
                self.open_document(remaining.resource)
            else:
                self.editor_view = TextEditorView(self)
                self.editor_view.bind()
        self.save_workspace()
        self.refresh_documents()
        self.show_documents_hub()
        if was_current and self.adaptive.split is not None:
            if self.current is not None:
                self.adaptive.present(self.document_view, route='editor', title='Text & Markdown')
                self.adaptive.show_list()
            else:
                self.adaptive.clear_details()
        return True

    def save_workspace(self, *, capture=True):
        if not self.active_host:
            return
        if capture:
            self.editor_view.capture()
        for view in self.text_views.values():
            view.session.transient = bool(getattr(view.document, 'private', False))
        try:
            self.workspace.save()
        except (OSError, ValueError) as error:
            self.recovery_notice.text = str(error)

    def show_documents(self, widget=None, *, resume=False, **kwargs):
        if self.current is None:
            self.new_document()
        if self.current is None:
            return False
        preview = resume and self.editor_view.session.view.get('markdown_mode') == 'preview'
        self.editor_view.session.view['markdown_mode'] = 'edit'
        self.show_view(self.document_view, destination='documents', route='editor', title='Text & Markdown')
        if preview:
            return self.show_preview()

    def show_editor_actions(self, owner):
        box = toga.Box(style=Pack(direction=COLUMN, margin=12))
        for title, action in owner.actions.actions:
            def command(widget=None, target=action, **kwargs):
                owner.actions.invoke(target)
            box.add(toga.Button(title, on_press=command, style=Pack(height=44)))
        self.show_view(toga.ScrollContainer(content=box, style=Pack(flex=1)), route='actions', title='Document actions')

    def show_settings(self, widget=None, **kwargs):
        box = toga.Box(style=Pack(direction=COLUMN, margin=16))
        box.add(toga.Label('Preferences', style=Pack(font_size=22, margin_bottom=12)))
        self.font_choice = toga.Selection(items=['12', '14', '16', '18', '20', '24', '28', '32'],
            value=self.preferences.values['font_size'], style=Pack(height=44))
        self.restore_choice = toga.Switch('Restore last document',
            value=self.preferences.values['restore_last_document'] == 'true', style=Pack(height=44))
        self.settings_status = toga.Label(self.preferences.error, style=Pack(margin_top=12))
        box.add(toga.Label('Editor and preview font size'))
        box.add(self.font_choice)
        box.add(self.restore_choice)
        box.add(toga.Button('Save preferences', on_press=self.save_preferences, style=Pack(height=44)))
        box.add(toga.Button('Reload preferences', on_press=self.reload_preferences, style=Pack(height=44)))
        box.add(self.settings_status)
        box.add(toga.Button('Remote connections…', on_press=self.show_cloud_connections, style=Pack(height=44, margin_top=12)))
        self.show_view(box, destination='settings', root=True)

    def save_preferences(self, widget=None, **kwargs):
        try:
            self.preferences.save(font_size=self.font_choice.value,
                restore_last_document='true' if self.restore_choice.value else 'false')
            self.editor.style.font_size = int(self.preferences.values['font_size'])
            self.settings_status.text = 'Preferences saved on this device.'
        except (OSError, ValueError) as error:
            self.settings_status.text = str(error)

    def reload_preferences(self, widget=None, **kwargs):
        self.preferences.reload()
        self.editor.style.font_size = int(self.preferences.values['font_size'])
        self.show_settings()

    def show_preview(self, widget=None, **kwargs):
        if self.current is None or not self.checkpoint():
            return
        try:
            content = markdown_preview(self.current.text, int(self.preferences.values['font_size']))
        except ValueError as error:
            self.status.text = str(error)
            return
        if not hasattr(self, 'preview'):
            self.preview = toga.WebView(on_navigation_starting=lambda widget, url, **kw: False,
                                       style=Pack(flex=1))
        # A fresh WebView may still be navigating to its initial about:blank.
        # Give the HTML load a distinct local-document origin so that blank
        # navigation cannot consume Toga's one approved content navigation.
        self.preview.set_content('https://logistics.invalid/' + uuid4().hex + '/', content)
        self.editor_view.session.view['markdown_mode'] = 'preview'
        previous = getattr(self, 'preview_box', None)
        if previous is not None:
            previous.remove(self.preview)
        owner = self.editor_view
        token = self.workspace.token(owner.session.id)
        def back_to_editor(widget=None, **kwargs):
            if self.active_host and self.workspace.accepts(token):
                if not self.checkpoint():
                    return
                owner.bind()
                self.workspace.activate(owner.session.id)
                self.show_documents()
        self.preview_box = toga.Box(children=[
            toga.Button('Back to editor', on_press=back_to_editor, style=Pack(height=44)),
            self.preview], style=Pack(direction=COLUMN, flex=1))
        self.show_view(self.preview_box, route='preview', title='Markdown preview')
        self.save_workspace()

    def refresh_documents(self):
        previous = self.loading
        self.loading = True
        documents, failures = self.store.documents()
        counts, self.labels = {}, {}
        for doc in documents:
            counts[doc.name] = counts.get(doc.name, 0) + 1
            label = doc.name + (f' ({counts[doc.name]})' if counts[doc.name] > 1 else '')
            while label in self.labels:
                label += ' (copy)'
            self.labels[label] = doc.id
        self.selector.items = list(self.labels)
        if self.current:
            self.selector.value = next((label for label, key in self.labels.items()
                                        if key == self.current.id), None)
        self.loading = previous
        self.recovery_notice.text = (f'{len(failures)} recovery record(s) could not be opened; they were preserved.'
                                     if failures else '')

    def open_document(self, key):
        opened = False
        previous_view = self.document_view
        displaying = (hasattr(self, 'routes') and previous_view in self.routes.body('documents').children)
        self.editor_view.capture()
        self.loading = True
        try:
            doc = self.store.open(key)
            session = self.workspace.open('managed-text', key,
                'markdown' if doc.name.lower().endswith(('.md', '.markdown')) else 'text', doc.name)
            view = self.text_views.get(session.id)
            if view is None:
                view = self.editor_view if self.editor_view.document is None else TextEditorView(self)
                view.load(doc, session)
                self.text_views[session.id] = view
            elif doc.conflict:
                view.document.conflict = True
                view.status.text = 'Stored file changed. Save a copy to keep recovered edits.'
            view.bind()
            opened = True
            session.title = self.current.name
            self.selector.items = list(self.labels)
            self.selector.value = next((label for label, identity in self.labels.items() if identity == key), None)
            try:
                self.preferences.save(last_document=key)
            except (OSError, ValueError) as error:
                self.status.text += ' · ' + str(error)
        except (OSError, ValueError, KeyError, TypeError) as error:
            self.status.text = str(error)
        finally:
            self.loading = False
        self.save_workspace(capture=False)
        if displaying:
            self.show_documents(resume=True)
        self.editor_view.restore()
        return opened

    def select_document(self, widget, **kwargs):
        if not self.loading and widget.value in self.labels:
            if self.checkpoint():
                self.open_document(self.labels[widget.value])

    def new_document(self, widget=None, **kwargs):
        if not self.checkpoint():
            return
        try:
            if len(self.workspace.sessions) >= MAX_SESSIONS:
                raise ValueError('Close an open document before creating another (limit: 32).')
            created = self.store.create()
            self.refresh_documents()
            self.open_document(created.id)
        except (OSError, ValueError) as error:
            self.status.text = str(error)

    def name_changed(self, widget, **kwargs):
        if self.loading or self.current is None:
            return
        try:
            self.current.name = document_name(widget.value)
            self.checkpoint()
        except ValueError:
            pass  # Allow an empty field while the user replaces its name.

    def text_changed(self, widget, **kwargs):
        if self.loading or self.current is None:
            return
        self.current.text = widget.value
        if self.checkpoint():
            self.status.text = 'Draft preserved' if self.current.modified else 'Saved'

    def checkpoint(self, *args, **kwargs):
        if not self.active_host:
            return False
        if self.current is None or self.loading:
            return True
        if getattr(self.current, 'private', False):
            self.status.text = 'This draft is session-only. Save it before leaving.'
            return not self.current.modified
        try:
            self.store.checkpoint(self.current)
            self.save_workspace()
            return True
        except (OSError, ValueError) as error:
            self.status.text = 'Could not preserve edits: ' + str(error)
            return False

    def save_document(self, widget=None, **kwargs):
        if self.current is None:
            return
        try:
            self.current.name = document_name(self.name.value)
            self.store.save(self.current)
            self.refresh_documents()
            self.status.text = 'Saved'
        except (OSError, ValueError) as error:
            self.status.text = str(error)

    def save_copy(self, widget=None, **kwargs):
        if self.current is None:
            return
        try:
            copy = self.store.save_copy(self.current, document_name(self.name.value))
            self.refresh_documents()
            self.open_document(copy.id)
        except (OSError, ValueError) as error:
            self.status.text = str(error)

    async def import_document(self, widget=None, *, origin=None, **kwargs):
        from .pickers import pick_document
        origin = origin or self.editor_view
        if origin.session is None or origin.session.id not in self.workspace.sessions or not origin.import_button.enabled:
            return
        if not self.checkpoint():
            return
        token = self.workspace.token(origin.session.id)
        origin.import_button.enabled = False
        try:
            selected = await pick_document(self)
            if selected:
                imported = await asyncio.to_thread(self.store.import_document, *selected)
                if not self.active_host or not self.workspace.accepts(token):
                    return  # The stored import remains available; never reopen a closed screen.
                if self.editor_view is not origin:
                    active = self.workspace.active
                    session = self.workspace.open('managed-text', imported.id,
                        'markdown' if imported.name.lower().endswith(('.md', '.markdown')) else 'text', imported.name)
                    view = TextEditorView(self)
                    view.load(imported, session)
                    self.text_views[session.id] = view
                    self.workspace.active = active
                    origin.status.text = 'Imported document is available in Open documents.'
                    self.refresh_documents()
                    self.save_workspace()
                    return
                self.refresh_documents()
                self.open_document(imported.id)
        except Exception as error:
            # Native bridge errors are not necessarily OSError subclasses.
            if self.active_host and self.workspace.accepts(token):
                origin.status.text = 'Import failed: ' + str(error)[:500]
        finally:
            origin.import_button.enabled = True

    async def export_document(self, widget=None, *, origin=None, **kwargs):
        from .pickers import export_document
        origin = origin or self.editor_view
        if origin.session is None or origin.session.id not in self.workspace.sessions or not origin.export_button.enabled:
            return
        if self.current is None or not self.checkpoint():
            return
        token = self.workspace.token(origin.session.id)
        origin.export_button.enabled = False
        try:
            document = origin.document
            done = await export_document(self, document_name(origin.name.value),
                                        document.snapshot.encode(document.text))
            if self.active_host and self.workspace.accepts(token):
                origin.status.text = 'Document copy exported.' if done else 'Export cancelled.'
        except Exception as error:
            if self.active_host and self.workspace.accepts(token):
                origin.status.text = 'Export failed: ' + str(error)[:500]
        finally:
            origin.export_button.enabled = True

    def exit_app(self, app, **kwargs):
        if getattr(self, 'cloud_busy', False):
            self.cancel_cloud()
            return False
        if hasattr(self, "crypt_reader"):
            if not self.clear_private_reader():
                return False
        if getattr(self, 'cloud_client', None):
            self.cloud_client.cancel()
        if getattr(self, 'chat_client', None):
            self.chat_client.cancel()
        if hasattr(self, 'chat_current') and not self.checkpoint_chat():
            return False
        return self.checkpoint()


def main():
    return LogisticsMobile('Logistics Mobile', 'io.github.ispaure.logisticsmobile')
