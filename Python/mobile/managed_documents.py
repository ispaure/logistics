"""Managed-text host workflows over the existing store, workspace and editor views.

The host retains startup and aggregate checkpoint/navigation guards. This mixin
owns no additional state: views retain per-document controls and the workspace
retains identities and generations, including picker completion admission.
"""
import asyncio
from hashlib import sha256
from uuid import uuid4

import toga
from toga.style import Pack

from features.text_editor.mobile.ui import TextEditorView
from .documents import document_name
from .hub_ui import text_document_kind
from .preview import markdown_preview
from .workspace import MAX_SESSIONS


class ManagedDocumentWorkflows:
    def show_preview(self, widget=None, **kwargs):
        if self.current is None or not self.checkpoint():
            return
        try:
            from .font_scaling import font_size
            content = markdown_preview(self.current.text, font_size(self, self.editor_view.session.kind))
        except ValueError as error:
            self.status.text = str(error)
            return
        owner = self.editor_view
        if owner.preview is None:
            owner.preview = toga.WebView(on_navigation_starting=lambda widget, url, **kw: False,
                                         style=Pack(flex=1))
            owner.preview_digest = None
        from .font_scaling import bind
        bind(self, owner.preview, lambda: owner.session.kind, web=True)
        self.preview = owner.preview
        owner.session.view['markdown_mode'] = 'preview'
        token = self.workspace.token(owner.session.id)
        def back_to_editor(widget=None, **kwargs):
            if self.active_host and self.workspace.accepts(token):
                if not self.checkpoint():
                    return
                owner.bind()
                self.workspace.activate(owner.session.id)
                self.show_documents(edit=True)
        from .preview import prepare_managed_preview
        prepare_managed_preview(owner, on_edit=back_to_editor,
            valid=lambda: self.active_host and owner.session.id in self.workspace.sessions)
        bind(self, owner.preview, lambda: owner.session.kind, web=True)
        from .action_menu import ActionMenu
        from .document_sources import folder_action
        if hasattr(owner, 'preview_actions'):
            owner.preview_actions.dispose()
        owner.preview_actions = ActionMenu(owner.preview_actions_button, owner,
            folder_action(self, owner.session) + [
                ('Find in this page…', owner.preview_search.show),
                ('Read aloud…', lambda: owner.markdown_speech.show()),
                ('Close document', lambda: self.request_close_session(owner.session.id)),
                ('Delete document…', lambda: self.request_delete_document(owner.session.id))])
        from .markdown_speech import MarkdownSpeech
        speech = getattr(owner, 'markdown_speech', None)
        if speech is None:
            owner.markdown_speech = speech = MarkdownSpeech(self, owner.preview, owner.preview_box,
                document_title=lambda: owner.document.name)
            owner.preview_toolbar.insert(len(owner.preview_toolbar.children) - 1, speech.button)
        speech.close()
        self.preview_box = owner.preview_box
        shown = self.show_view(self.preview_box, destination=kwargs.get('destination'),
                               route='preview', title=owner.document.name)
        digest = sha256(content.encode('utf-8')).digest()
        if digest != getattr(owner, 'preview_digest', None):
            owner.preview_search.loading()
            saved = self.__dict__.get('_closed_text_positions', {}).get(owner.session.resource)
            if saved is not None:
                from .reader_lifecycle import restore_loaded_scroll
                restore_loaded_scroll(owner.preview, saved[1], lambda: self.workspace.accepts(token))
            self.preview.set_content('https://logistics.invalid/' + uuid4().hex + '/', content)
            # Re-presenting an unchanged preview must preserve its in-flight
            # navigation, DOM and scroll rather than cancel it with another UUID.
            owner.preview_digest = digest
        self.save_workspace()
        return shown

    def refresh_documents(self):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            documents, failures = self.store.summaries()
            self._publish_document_summaries(documents, failures)
            return
        if getattr(self, '_startup_in_progress', False):
            documents, failures = ((self.store.cached_summaries(), [])
                if getattr(self, '_async_startup', False) else self.store.summaries())
            self._publish_document_summaries(documents, failures)
            return
        self._publish_document_summaries(self.store.cached_summaries(), [])
        self._document_refresh_again = True
        task = getattr(self, '_document_refresh_task', None)
        if task is None or task.done():
            async def refresh():
                while self.active_host and self._document_refresh_again:
                    self._document_refresh_again = False
                    records, warnings = await asyncio.to_thread(self.store.summaries)
                    if self.active_host and not self._document_refresh_again:
                        self._publish_document_summaries(records, warnings)
            self._document_refresh_task = self.loop.create_task(refresh())

    def _publish_document_summaries(self, documents, failures):
        previous = self.loading
        self.loading = True
        self.stored_document_kinds = {doc.id: text_document_kind(doc.name) for doc in documents}
        counts, self.labels = {}, {}
        for doc in documents:
            counts[doc.name] = counts.get(doc.name, 0) + 1
            label = doc.name + (f' ({counts[doc.name]})' if counts[doc.name] > 1 else '')
            while label in self.labels:
                label += ' (copy)'
            self.labels[label] = doc.id
        self.selector.items = list(self.labels)
        if self.current:
            selected = next((label for label, key in self.labels.items()
                             if key == self.current.id), None)
            if selected is not None:
                self.selector.value = selected
        self.loading = previous
        self.recovery_notice.text = (f'{len(failures)} recovery record(s) could not be opened; they were preserved.'
                                     if failures else '')
        self.refresh_document_list()

    def open_document(self, key):
        if not self.require_feature('text_editor'):
            return False
        self.__dict__.pop('_pending_managed_restore', None)
        opened = False
        previous_view = self.document_view
        displaying = (hasattr(self, 'routes') and previous_view in self.routes.body().children)
        self.editor_view.capture()
        self.loading = True
        try:
            doc = self.store.open(key)
            session = self.workspace.open('managed-text', key,
                'markdown' if doc.name.lower().endswith(('.md', '.markdown')) else 'text', doc.name)
            view = self.text_views.get(session.id)
            if view is None:
                saved = self.__dict__.get('_closed_text_positions', {}).get(key)
                if saved is not None:
                    session.view.update(saved[0])
                view = self.editor_view if self.editor_view.document is None else TextEditorView(self)
                view.load(doc, session)
                self.text_views[session.id] = view
            elif doc.conflict:
                view.document.conflict = True
                view.status.text = 'Stored file changed. Save a copy to keep recovered edits.'
            view.bind()
            self.pending_reader_restore = None
            opened = True
            session.title = self.current.name
            self.selector.items = list(self.labels)
            selected = next((label for label, identity in self.labels.items() if identity == key), None)
            if selected is not None:
                self.selector.value = selected
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

    def clear_restored_documents(self):
        """Prune only proven clean sessions; preserve unreadable recovery records."""
        for session in list(self.workspace.sessions.values()):
            if (self.preferences.values['restore_last_document'] == 'true'
                    and session.id == self.workspace.active):
                continue
            if session.provider == 'managed-text':
                try:
                    document = self.store.open(session.resource)
                except (OSError, ValueError, KeyError, TypeError):
                    continue
                if document.modified or document.conflict:
                    continue
            self.workspace.close(session.id, guard=lambda value: True)

    def choose_document_type(self, widget=None, **kwargs):
        if not self.checkpoint():
            return
        from .document_choices import choose_document_type
        return choose_document_type(self)

    def create_chosen_document(self, extension, *, name=None, content=''):
        previous = self.current
        self.new_document(extension=extension, name=name, content=content)
        if self.current is not previous:
            # Creation is complete. Retire its form before the editor captures
            # its Close destination, while failures retain the form for retry.
            destination = self.native_host.state.destination
            details = self.adaptive.detail_routes
            if (destination == 'documents' and self.adaptive.split is not None
                    and details and details[-1][0] == 'new-document'):
                self.adaptive.trim_details(len(details) - 1)
            else:
                screens = self.routes.screens[destination]
                if screens and screens[-1][0] == 'new-document':
                    self.routes.trim(destination, len(screens) - 1)
            self.show_documents(edit=True)
            return True
        return False

    def new_document(self, widget=None, *, extension='txt', name=None, content='', **kwargs):
        if not self.require_feature('text_editor'):
            return False
        if not self.checkpoint():
            return
        try:
            if len(self.workspace.sessions) >= MAX_SESSIONS:
                raise ValueError('Close an open document before creating another (limit: 32).')
            if extension not in ('txt', 'md'):
                raise ValueError('Choose TXT or Markdown.')
            created = self.store.create(name if name is not None else 'Untitled.' + extension,
                                        content=content.encode('utf-8'))
            self.refresh_documents()
            self.open_document(created.id)
            self.editor_view.session.view['markdown_mode'] = 'edit'
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
            self.editor_view.refresh_status()

    def save_document(self, widget=None, **kwargs):
        if self.current is None:
            return
        try:
            self.current.name = document_name(self.name.value)
            self.store.save(self.current)
            self.refresh_documents()
            self.editor_view.refresh_status()
        except (OSError, ValueError) as error:
            self.editor_view.refresh_status()
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

