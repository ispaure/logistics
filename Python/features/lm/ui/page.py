"""LM workspace presentation and navigation, backed by an owned conversation session."""
from commonUtils.ui.appearance.typography import point_size
from copy import deepcopy
from math import ceil

from commonUtils.ui import pyside as qt
from ..domain import validate_settings
from ..storage import Store
from ..session import ConversationSession
from ..agent import AgentClient
from ..screenshots import encode_screenshot, MAX_IMAGES
from .image_view import ScreenshotView
from ..generation import GenerationCoordinator, GenerationInputs
from .ide_context import registered_projects, editor_context
from .project_edits import ProjectEditDispatcher
from .icons import chat_icon, action_button
from .layout import build_layout
from .menus import build_menus
from .attachments import AttachmentController
from .composer import Composer
from .profiles import ProfilesDialog


class LMPage(qt.QWidget):
    idle = qt.Signal()

    # Existing hosts and callers can inspect these without duplicating state.
    @property
    def data(self):
        return self.session.data

    @data.setter
    def data(self, value):
        self.session.data = value

    @property
    def lease(self):
        return self.session.lease

    @property
    def dirty(self):
        return self.session.dirty

    @dirty.setter
    def dirty(self, value):
        self.session.dirty = value

    @property
    def active_message(self):
        return self.session.active_message

    def context_projects(self):
        if self.project_context is not None:
            return self.project_context.projects()
        return registered_projects(self)

    def context_buffers(self, project):
        if self.project_context is not None:
            return self.project_context.buffers(project)
        return editor_context(self, project)

    def __init__(self, parent=None, *, store=None, client=None, project_context=None):
        super().__init__(parent)
        from .conversation_actions import ConversationActions
        self.conversations = ConversationActions(self)
        self.attachments = AttachmentController(self)
        self.project_context = project_context
        self.store = store or Store()
        self.client = client or AgentClient(self)
        self.projects = {}
        self.draft_images = []
        self.browser_mode = 'chat'
        self.last_conversations = {}
        self.mode_search = {}
        self.session = ConversationSession(self.store)
        self.project_edits = ProjectEditDispatcher(self)
        self.project_edits.changes_saved.connect(self.record_changes)
        from ..execution.desktop import project_tools
        self.generation = GenerationCoordinator(self.session, self.client, project_tools=project_tools)
        session = self.session
        # Capture only the session, never the widget being destroyed.
        self.destroyed.connect(lambda: session.release_lease())
        self.session_tokens = {}
        self.profiles = []
        self.loading = False
        self.dirty = False
        self.discard_approved = False
        self.closing = False
        layout = build_layout(self)
        self._bind_session_controls()
        from commonUtils.ui.appearance.styling import styling
        self.styling = styling(qt.QApplication.instance())
        self.styling.bind(self.transcript, 'reading')
        self.styling.bind(self.composer, 'reading')
        self.styling.changed.connect(self.render)
        build_menus(self, layout)
        self.apply_chrome()
        self.styling.changed.connect(self.apply_chrome)
        theme = getattr(qt.QApplication.instance(), '_commonutils_theme', None)
        if theme is not None:
            theme.changed.connect(self.apply_chrome)
        self.load_profiles()
        self.refresh()
        first = next((item for item in self.tree_items() if item.data(0, qt.Qt.ItemDataRole.UserRole)), None)
        if first is not None:
            self.list.setCurrentItem(first)
        self.update_controls()

    def _bind_session_controls(self):
        """Retain timers and bind widgets/transport to the existing session owner."""
        self.composer_fit_timer = qt.QTimer(self)
        self.composer_fit_timer.setSingleShot(True)
        self.composer_fit_timer.setInterval(0)
        self.composer_fit_timer.timeout.connect(self.fit_composer)
        self.chat_body.installEventFilter(self)
        self.message_surface.installEventFilter(self)
        self.composer_dock.installEventFilter(self)
        self.composer.viewport().installEventFilter(self)
        self.save_timer = qt.QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(700)
        self.save_timer.timeout.connect(self.persist)
        self.checkpoint_timer = qt.QTimer(self)
        self.checkpoint_timer.setInterval(1000)
        self.checkpoint_timer.timeout.connect(self.checkpoint)
        self.render_timer = qt.QTimer(self)
        self.render_timer.setSingleShot(True)
        self.render_timer.setInterval(80)
        self.render_timer.timeout.connect(self.render)
        self.search_timer = qt.QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(400)
        self.search_timer.timeout.connect(self.refresh)
        self.search.textChanged.connect(lambda: self.search_timer.start())
        self.list.currentItemChanged.connect(self.select)
        self.profile.currentIndexChanged.connect(self.profile_changed)
        self.token.textChanged.connect(self.token_changed)
        self.model.currentTextChanged.connect(self.changed)
        self.composer.textChanged.connect(self.draft_changed)
        self.composer.textChanged.connect(self.fit_composer)
        self.system.textChanged.connect(self.changed)
        for widget in (self.temperature, self.top_p, self.context, self.max_tokens):
            widget.valueChanged.connect(self.changed)
        self.client.delta.connect(self.append_delta)
        self.transcript.speech_error.connect(self.status.setText)
        if hasattr(self.client, 'reasoning_delta'):
            self.client.reasoning_delta.connect(self.append_reasoning)
        self.client.models.connect(self.models_loaded)
        self.client.completed.connect(self.completed)
        if hasattr(self.client, 'activity'):
            self.client.activity.connect(self.status.setText)

    @staticmethod
    def button(title, callback, layout):
        button = qt.QPushButton(title)
        button.clicked.connect(callback)
        layout.addWidget(button)
        return button

    def icon_button(self, title, callback, icon, layout):
        button = action_button(title, callback, icon)
        layout.addWidget(button)
        return button

    def apply_chrome(self):
        palette = qt.QApplication.palette()
        border = palette.color(qt.QPalette.ColorRole.Mid).name()
        base = palette.color(qt.QPalette.ColorRole.Base).name()
        accent = palette.color(qt.QPalette.ColorRole.Highlight).name()
        font = self.styling.font('reading')
        family = font.family().replace('\\', '\\\\').replace('"', '\\"')
        self.composer_frame.setStyleSheet(f'QFrame#lmComposerFrame {{ background: {base}; border: 1px solid {border}; border-radius: 20px; }}')
        muted = palette.color(qt.QPalette.ColorRole.PlaceholderText).name()
        self.disclaimer.setStyleSheet(f'color: {muted}; font-size: {point_size(max(6, self.styling.values["ui_font_size_int"] - .75))}pt;')
        self.composer.setStyleSheet(f'QPlainTextEdit {{ background: transparent; border: none; padding: 8px; font-family: "{family}"; font-size: {font.pointSizeF()}pt; }}')
        self.composer.document().setDefaultFont(font)
        self.send_button.setStyleSheet(f'QToolButton {{ border: 1px solid {border}; border-radius: 15px; background: {accent}; }} QToolButton:disabled {{ background: {base}; }}')
        self.model.setStyleSheet('QComboBox { border: none; background: transparent; padding: 2px 4px; }')
        self.model.refresh_name()
        self.transcript.setFrameShape(qt.QFrame.Shape.NoFrame)
        self.search.setStyleSheet(f'QLineEdit {{ border: 1px solid {border}; border-radius: 8px; padding: 7px; }}')
        self.fit_composer()

    def fit_composer(self):
        if getattr(self, '_fitting_composer', False):
            return
        self._fitting_composer = True
        try:
            editor = self.composer
            document = editor.document()
            # Hidden editors can retain their old viewport size until Qt lays out.
            chrome = max(0, editor.height() - editor.viewport().height())
            minimum = 2 * editor.fontMetrics().lineSpacing() + 2 * document.documentMargin() + chrome
            # The draft overlays the transcript, with matching scroll padding below messages.
            available = min(self.height(), self.message_surface.height())
            dock_chrome = max(0, self.composer_dock.sizeHint().height() - editor.height())
            maximum = max(minimum, available // 2 - dock_chrome)
            height = document.documentMargin() + chrome
            block = document.begin()
            while block.isValid() and height < maximum:
                # Force layout of wrapped/off-screen blocks, not just paragraph counts.
                height += document.documentLayout().blockBoundingRect(block).height()
                block = block.next()
            # Qt needs a little rounding slack to fit the last full text line.
            height = ceil(min(maximum, max(minimum, height + 2)))
            if editor.height() != height:
                editor.setFixedHeight(height)
            self.transcript.set_bottom_inset(self.composer_dock.height() + 8)
        finally:
            self._fitting_composer = False

    def eventFilter(self, watched, event):
        if event.type() in (qt.QEvent.Type.Resize, qt.QEvent.Type.LayoutRequest):
            if hasattr(self, 'composer_fit_timer'):
                self.composer_fit_timer.start()
        return super().eventFilter(watched, event)

    def dragEnterEvent(self, event):
        if Composer.image_source(event.mimeData()) and (self.data is None or self.lease is not None):
            Composer.accept_image_drop(event)
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        self.dragEnterEvent(event)

    def dropEvent(self, event):
        if Composer.image_source(event.mimeData()) and (self.data is None or self.lease is not None):
            self.composer.insertFromMimeData(event.mimeData())
            Composer.accept_image_drop(event)
        else:
            event.ignore()

    def paste_screenshot(self, image):
        if self.data is None:
            self.conversations.new_conversation()
        if self.data is None or self.lease is None:
            return
        try:
            if len(self.draft_images) >= MAX_IMAGES:
                raise ValueError('Attach at most four screenshots per message.')
            self.draft_images.append(encode_screenshot(image))
        except ValueError as error:
            self.status.setText(str(error))
            return
        self.refresh_draft_images()
        self.changed()
        self.status.setText('Screenshot attached. Add a message or send it directly; image input requires a vision-capable model.')

    def remove_screenshot(self, key):
        self.draft_images = [image for image in self.draft_images if image['id'] != key]
        self.refresh_draft_images()
        self.changed()

    def refresh_draft_images(self):
        while self.image_draft_layout.count():
            item = self.image_draft_layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        for image in self.draft_images:
            card = qt.QWidget()
            layout = qt.QVBoxLayout(card)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(ScreenshotView(image, card, preview=True))
            remove = qt.QPushButton('Remove')
            remove.setAccessibleName('Remove screenshot')
            remove.clicked.connect(lambda checked=False, key=image['id']: self.remove_screenshot(key))
            layout.addWidget(remove)
            self.image_draft_layout.addWidget(card)
        self.image_draft_layout.addStretch()
        self.image_drafts.setVisible(bool(self.draft_images))

    def load_projects(self):
        key = (self.data.get('project_id', '') if self.loading and self.data
               else self.project_picker.currentData())
        try:
            self.projects = self.context_projects()
        except (ValueError, OSError) as error:
            self.status.setText(str(error))
            self.projects = {}
        self.project_picker.blockSignals(True)
        self.project_picker.clear()
        self.project_picker.addItem('Select IDE project…', '')
        for project in sorted(self.projects.values(), key=lambda p: p.name.casefold()):
            self.project_picker.addItem(project.name, project.id)
            self.project_picker.setItemData(self.project_picker.count() - 1, str(project.root), qt.Qt.ItemDataRole.ToolTipRole)
        if key:
            if key not in self.projects:
                self.project_picker.addItem('Unavailable project — select another', key)
            self.project_picker.setCurrentIndex(self.project_picker.findData(key))
        self.project_picker.blockSignals(False)

    def mode_changed(self):
        if self.loading:
            return
        target = self.mode.currentData()
        previous = self.browser_mode
        if self.client.busy or not self.persist():
            self.mode.blockSignals(True)
            self.mode.setCurrentIndex(self.mode.findData(previous))
            self.mode.blockSignals(False)
            return
        if self.data:
            self.last_conversations[previous] = self.data['id']
        self.mode_search[previous] = self.search.text()
        self.release_lease()
        self.data = None
        self.dirty = False
        self.browser_mode = target
        self.loading = True
        self.composer.clear()
        self.draft_images = []
        self.refresh_draft_images()
        self.transcript.clear()
        self.search.setText(self.mode_search.get(target, ''))
        self.loading = False
        self.list.blockSignals(True)
        self.list.clear()
        self.folder_items = {}
        self.list.blockSignals(False)
        if target == 'code':
            self.load_projects()
        self.refresh()
        keys = [item.data(0, qt.Qt.ItemDataRole.UserRole) for item in self.tree_items()
                if item.data(0, qt.Qt.ItemDataRole.UserRole)]
        remembered = self.last_conversations.get(target)
        if remembered:
            try:
                record = self.store.load(remembered)
                if record.get('mode', 'chat') != target:
                    remembered = None
            except (OSError, ValueError):
                remembered = None
        key = remembered or (keys[0] if keys else None)
        if key:
            self.open_conversation(key)
            self.refresh(reveal_current=True)
        elif not self.search.text():
            self.conversations.new_conversation()
        self.update_controls()

    def project_changed(self):
        self.changed()
        project = self.projects.get(self.project_picker.currentData())
        if project:
            access = 'Edits save directly' if self.allow_edits.isChecked() else 'Read-only access'
            self.status.setText(f'Code mode: {project.name}. Project text may be sent to the selected server. {access}; IDE exclusions apply.')

    def attachment_context(self):
        return self.attachments.attachment_context()

    def append_attachment(self, text):
        return self.attachments.append_attachment(text)

    def attach_files(self):
        return self.attachments.attach_files()

    def attach_selection(self):
        return self.attachments.attach_selection()

    @staticmethod
    def selection_allowed(tools, path):
        return AttachmentController.selection_allowed(tools, path)

    def send_or_stop(self):
        if self.client.busy:
            self.client.cancel()
        else:
            self.send()

    def load_profiles(self):
        try:
            self.profiles = self.store.profiles()
        except (OSError, ValueError, UnicodeError) as error:
            self.profiles = []
            self.status.setText(f'Could not read server profiles: {error}')
        selected = self.data['profile_id'] if self.data else self.profile.currentData()
        self.loading = True
        self.profile.clear()
        for profile in self.profiles:
            self.profile.addItem(profile['name'], profile['id'])
        index = self.profile.findData(selected)
        self.profile.setCurrentIndex(index if selected else (0 if self.profiles else -1))
        self.token.setText(self.session_tokens.get(self.profile.currentData(), ''))
        self.loading = False

    def current_profile(self):
        return next((p for p in self.profiles if p['id'] == self.profile.currentData()), None)

    def profile_changed(self):
        if self.loading:
            return
        self.token.setText(self.session_tokens.get(self.profile.currentData(), ''))
        self.model.clear()
        self.changed()

    def token_changed(self, text):
        if not self.loading and self.profile.currentData():
            self.session_tokens[self.profile.currentData()] = text

    def refresh(self, *, reveal_current=False):
        if self.client.busy:
            return
        if self.data is not None and self.lease is None:
            # A different application page can veto closing after we retired.
            # Explicit Refresh reopens from disk and reacquires ownership.
            key = self.data['id']
            self.data = None
            self.dirty = False
            self.closing = False
            self.open_conversation(key)
        current = self.data['id'] if self.data else None
        selected = self.list.currentItem()
        selected_folder = (selected.data(0, qt.Qt.ItemDataRole.UserRole + 1)
                           if selected is not None and not selected.data(0, qt.Qt.ItemDataRole.UserRole) else None)
        expanded = {path: item.isExpanded() for path, item in getattr(self, 'folder_items', {}).items()}
        try:
            records, warnings = self.store.list(self.search.text())
            records = [record for record in records if record.get('mode', 'chat') == self.mode.currentData()]
            folders = self.store.folders()
        except (OSError, ValueError) as error:
            self.status.setText(str(error))
            return
        self.list.blockSignals(True)
        self._populate_conversation_tree(records, folders, current)
        if selected_folder in self.folder_items and not reveal_current:
            self.list.setCurrentItem(self.folder_items[selected_folder])
        for path, item in self.folder_items.items():
            item.setExpanded(True if self.search.text() else expanded.get(path, True))
        if reveal_current and self.list.currentItem() is not None:
            parent = self.list.currentItem().parent()
            while parent is not None:
                parent.setExpanded(True)
                parent = parent.parent()
        self.list.blockSignals(False)
        self.update_controls()
        if warnings:
            self.status.setText('Some conversation files could not be read and were preserved. ' + '\n'.join(warnings[:3]))

    def _populate_conversation_tree(self, records, folders, current):
        """Project records/folders while refresh retains the selection and signal guard."""
        self.list.clear()
        root = qt.QTreeWidgetItem(self.list, ['Conversations'])
        root.setData(0, qt.Qt.ItemDataRole.UserRole + 1, '')
        self.folder_items = {'': root}
        visible_folders = set(folders) if not self.search.text() else set()
        for data in records:
            path = data['folder']
            while path:
                visible_folders.add(path)
                path = path.rpartition('/')[0]
        for path in sorted(visible_folders, key=lambda name: (name.count('/'), name.casefold())):
            parent, _, label = path.rpartition('/')
            item = qt.QTreeWidgetItem(self.folder_items[parent], [label])
            item.setData(0, qt.Qt.ItemDataRole.UserRole + 1, path)
            item.setIcon(0, self.style().standardIcon(qt.QStyle.StandardPixmap.SP_DirIcon))
            self.folder_items[path] = item
        for data in records:
            item = qt.QTreeWidgetItem(self.folder_items[data['folder']], [('★ ' if data.get('pinned') else '') + data['title']])
            item.setData(0, qt.Qt.ItemDataRole.UserRole, data['id'])
            item.setData(0, qt.Qt.ItemDataRole.UserRole + 1, data['folder'])
            if data['id'] == current:
                self.list.setCurrentItem(item)

    def select(self, item, previous=None):
        if item is None or self.client.busy:
            return
        key = item.data(0, qt.Qt.ItemDataRole.UserRole)
        if not key:
            self.update_controls()
            return
        if self.data and self.data['id'] == key:
            self.update_controls()
            return
        self.open_conversation(key)

    def tree_items(self):
        iterator = qt.QTreeWidgetItemIterator(self.list)
        while iterator.value() is not None:
            yield iterator.value()
            iterator += 1

    def selected_folder(self):
        item = self.list.currentItem()
        return item.data(0, qt.Qt.ItemDataRole.UserRole + 1) if item is not None else ''



    def open_conversation(self, key):
        if not self.persist():
            self.refresh()
            return
        previous_mode = self.browser_mode
        try:
            interrupted = self.session.open(key)
        except (OSError, ValueError, UnicodeError) as error:
            self.status.setText(str(error))
            self.refresh()
            return
        self.restore()
        self.dirty = interrupted
        if interrupted:
            self.status.setText('An interrupted response was recovered. Retry to generate a new answer; partial text is retained.')
            self.persist()
        else:
            self.status.setText('Conversation opened.')
        if previous_mode != self.browser_mode:
            self.refresh(reveal_current=True)
        self.update_controls()

    def release_lease(self):
        self.session.release_lease()

    def restore(self):
        self.loading = True
        data = self.data
        self.profile.setCurrentIndex(self.profile.findData(data['profile_id']))
        self.token.setText(self.session_tokens.get(data['profile_id'], ''))
        self.model.setCurrentText(data['model'])
        self.mode.setCurrentIndex(self.mode.findData(data.get('mode', 'chat')))
        self.browser_mode = data.get('mode', 'chat')
        self.last_conversations[self.browser_mode] = data['id']
        if data.get('mode') == 'code':
            self.load_projects()
        self.project_picker.setCurrentIndex(self.project_picker.findData(data.get('project_id', '')))
        self.allow_edits.setChecked(data.get('allow_edits', False))
        self.composer.setPlainText(data['draft'])
        self.draft_images = deepcopy(data.get('draft_images', []))
        self.refresh_draft_images()
        settings = data['settings']
        self.temperature.setValue(settings['temperature'] if settings['temperature'] is not None else -1)
        self.top_p.setValue(settings['top_p'] if settings['top_p'] is not None else -1)
        self.context.setValue(settings['context_tokens'])
        self.max_tokens.setValue(settings['max_tokens'])
        self.system.setPlainText(settings['system_prompt'])
        self.loading = False
        self.dirty = False
        self.discard_approved = False
        self.save_error.clear()
        self.save_error.hide()
        self.transcript.clear()
        self.render()

    def collect(self):
        if self.data is None:
            return
        self.data['draft'] = self.composer.toPlainText()
        self.data['draft_images'] = deepcopy(self.draft_images)
        self.data['project_id'] = self.project_picker.currentData() or ''
        self.data['allow_edits'] = self.allow_edits.isChecked()
        self.data['model'] = self.model.currentText().strip()
        self.data['profile_id'] = self.profile.currentData() or ''
        self.data['settings'] = validate_settings(dict(
            temperature=None if self.temperature.value() < 0 else self.temperature.value(),
            top_p=None if self.top_p.value() < 0 else self.top_p.value(),
            context_tokens=self.context.value(), max_tokens=self.max_tokens.value(),
            system_prompt=self.system.toPlainText()))

    def changed(self, *args):
        if self.loading or self.data is None:
            return
        self.dirty = True
        self.discard_approved = False
        self.save_timer.start()

    def draft_changed(self):
        # Font/palette updates can emit textChanged without changing draft text.
        if self.data is not None and self.composer.toPlainText() != self.data['draft']:
            self.changed()

    def show_save_error(self, error):
        self.save_error.setText(f'Conversation not saved: {error} Use Export to keep your current copy.')
        self.save_error.show()

    def persist(self):
        self.save_timer.stop()
        if self.data is None or not self.dirty:
            return True
        try:
            self.collect()
            self.session.save()
        except (OSError, ValueError, UnicodeError) as error:
            self.show_save_error(error)
            return False
        self.reflect_saved_state()
        return True

    def reflect_saved_state(self):
        """Refresh publication feedback without recollecting or resaving the draft."""
        self.save_error.clear()
        self.save_error.hide()
        for item in self.tree_items():
            if item.data(0, qt.Qt.ItemDataRole.UserRole) == self.data['id']:
                item.setText(0, ('★ ' if self.data.get('pinned') else '') + self.data['title'])


    def edit_profiles(self):
        if self.client.busy or not self.persist():
            return
        try:
            dialog = ProfilesDialog(self.store, self)
        except (OSError, ValueError, UnicodeError) as error:
            self.status.setText(str(error))
            return
        if dialog.exec() == qt.QDialog.DialogCode.Accepted:
            self.load_profiles()
            self.changed()
            self.update_controls()

    def refresh_models(self):
        profile = self.current_profile()
        if self.client.busy or profile is None:
            self.status.setText('Choose a server profile first.')
            return
        try:
            self.client.start(profile, self.token.text())
        except ValueError as error:
            self.status.setText(str(error))
            return
        self.status.setText('Connecting and loading models…')
        self.update_controls()

    def models_loaded(self, models):
        current = self.model.currentText()
        self.loading = True
        self.model.clear()
        self.model.addItems(models)
        self.model.setCurrentText(current or (models[0] if models else ''))
        self.loading = False
        self.changed()
        self.status.setText(f'Connected. {len(models)} models available.' if models else 'Connected, but no models were listed. Load a model on the server and refresh models.')

    def send(self):
        if self.client.busy:
            return
        if self.data is None:
            self.conversations.new_conversation()
        if self.data is None or (not self.composer.toPlainText().strip() and not self.draft_images):
            return
        if not self.persist():
            return
        self.collect()
        text = self.composer.toPlainText()
        snapshot = self.session.append_user(text, images=self.draft_images)
        if not self.begin_generation():
            self.session.rollback(snapshot)
            self.render()

    def retry(self):
        if self.client.busy or not self.data or not self.data['messages'] or not self.persist():
            return
        # Existing assistant alternatives are retained; request builder chooses the latest completed alternative for earlier turns.
        self.begin_generation(clear_draft=False)

    def begin_generation(self, *, clear_draft=True):
        profile = self.current_profile()
        if profile is None:
            self.status.setText('Choose a server profile first.')
            return False
        try:
            self.collect()
            project, buffers = None, None
            if self.data.get('mode') == 'code':
                key = self.project_picker.currentData()
                self.projects = self.context_projects()
                project = self.projects.get(key)
                if project is not None:
                    buffers, _ = self.context_buffers(project)
            plan = self.generation.prepare(GenerationInputs(profile, project, buffers, self.project_edits.dispatch))
        except ValueError as error:
            self.status.setText(str(error))
            return False
        self.save_timer.stop()

        def published():
            self.reflect_saved_state()
            if clear_draft:
                self.draft_images = []
                self.refresh_draft_images()
                self.loading = True
                self.composer.clear()
                self.loading = False

        try:
            result = self.generation.start(plan, self.token.text(), clear_draft=clear_draft, published=published)
        except (OSError, ValueError, UnicodeError) as error:
            self.show_save_error(error)
            return False
        if not result.started:
            if result.save_error is not None:
                self.show_save_error(result.save_error)
            else:
                self.reflect_saved_state()
            self.status.setText(result.error)
            self.render()
            return True  # The saved user turn remains retryable.
        metadata = plan.metadata
        self.status.setText(f'Generating… Approximately {metadata["estimated_input_tokens"]} input tokens; {metadata["omitted_turns"]} earlier turns omitted.')
        self.checkpoint_timer.start()
        self.render()
        self.update_controls()
        return True

    def record_changes(self, changes):
        if self.active_message is None:
            return
        self.active_message['changes'] = deepcopy(changes)
        self.dirty = True
        # Publish after each successful edit, before another model round starts.
        # A later failed/cancelled response still retains its already-saved edits.
        self.checkpoint()
        self.render()

    def undo_changes(self, message_id):
        if self.client.busy or self.data is None or self.lease is None or not self.persist():
            return
        entry = next((item for item in self.data['messages'] if item['id'] == message_id), None)
        if not entry or not any(not item.get('undone', False) for item in entry.get('changes', [])):
            return
        changes = entry['changes']
        previous = sum(bool(item.get('undone')) for item in changes)
        try:
            from pathlib import Path
            request = entry.get('request', {})
            project = self.context_projects().get(request.get('project_id'))
            if project is None or not request.get('project_root') or project.root.resolve() != Path(request['project_root']).resolve():
                raise ValueError('The original IDE project registration is missing or its root changed.')
            def saved():
                self.dirty = True
                if not self.persist():
                    raise ValueError('Undo progress could not be saved. Stop here and export or retry saving the conversation.')
            self.project_edits.undo_changes(project, changes, saved)
            count = sum(bool(item.get('undone')) for item in changes) - previous
            self.status.setText(f'Undid this response’s changes in {count} file{"s" if count != 1 else ""}. Later unrelated edits were retained.')
        except (OSError, ValueError) as error:
            count = sum(bool(item.get('undone')) for item in changes) - previous
            progress = f'{count} file(s) already reverted; remaining files were not reverted. ' if count else 'No files were reverted. '
            self.status.setText('Undo stopped. ' + progress + str(error))
        self.render()
        self.update_controls()

    def show_changes(self, message_id, path):
        entry = next((item for item in self.data['messages'] if item['id'] == message_id), None) if self.data else None
        if entry and entry.get('changes'):
            key = (self.data['id'], message_id)
            if not self.changes_pane.isHidden() and self.changes_pane.key == key and self.changes_pane.files.currentData() == path:
                self.changes_pane.hide()
                return
            was_hidden = self.changes_pane.isHidden()
            self.changes_pane.show_changes((self.data['id'], message_id), entry['changes'], path)
            if was_hidden:
                width = max(600, self.content_splitter.width())
                self.content_splitter.setSizes([width // 2, width // 2])

    def edit_changed_file(self, message_id, path):
        entry = next((item for item in self.data['messages'] if item['id'] == message_id), None) if self.data else None
        if not entry or path not in {item['path'] for item in entry.get('changes', [])}:
            return
        try:
            from pathlib import Path
            from ..project_tools import ProjectTools
            request = entry.get('request', {})
            project = self.context_projects().get(request.get('project_id'))
            if project is None or not request.get('project_root') or project.root.resolve() != Path(request['project_root']).resolve():
                raise ValueError('The original IDE project registration is missing or its root changed.')
            target = ProjectTools(project).path(path)
            if not target.is_file():
                raise ValueError('This file no longer exists.')
            opener = getattr(self, 'working_file_opener', None)
            if opener is None or not opener(target):
                raise ValueError('Enable and open the IDE workspace to edit this file.')
        except (OSError, ValueError) as error:
            self.status.setText(f'Could not open file in IDE: {error}')

    def append_delta(self, text):
        if not self.session.append_delta(text):
            return
        if not self.render_timer.isActive():
            self.render_timer.start()

    def append_reasoning(self, text):
        if self.session.append_reasoning(text) and not self.render_timer.isActive():
            self.render_timer.start()

    def checkpoint(self):
        if not self.persist():
            self.client.cancel()
            self.status.setText('Generation stopped because the conversation could not be saved. Partial output remains available for export.')

    def completed(self, status, error, metadata):
        self.checkpoint_timer.stop()
        if self.session.complete_response(status, error, metadata):
            saved = self.persist() if not self.discard_approved else False
            self.render()
            if error:
                self.status.setText(error)
            elif saved:
                self.status.setText('Response saved.' if status == 'complete' else 'Stopped. Partial response saved and excluded from future context.')
            if metadata.get('finish_reason') == 'length':
                self.status.setText('Response reached the output limit. Increase maximum response tokens and regenerate if needed.')
            if status == 'complete' and not error and not self.discard_approved:
                from ..configuration import response_notifications_enabled
                if response_notifications_enabled() and not self.response_is_visible():
                    from desktop.notifications import notify
                    notify('lm', 'LM Chat · New AI reply',
                           'Your AI reply is ready.', native=True)
        elif error:
            self.status.setText(error)
        elif status == 'cancelled':
            self.status.setText('Connection check stopped.')
        self.update_controls()
        self.idle.emit()

    def response_is_visible(self):
        window = self.window()
        return self.isVisible() and window.isActiveWindow() and not window.isMinimized()

    def render(self):
        self.render_timer.stop()
        bar = self.transcript.verticalScrollBar()
        current = self.data['id'] if self.data else None
        bottom = self.transcript.key != current or bar.value() >= bar.maximum() - 12
        old = bar.value()
        self.transcript.sync(self.data)
        self.disclaimer.setVisible(not self.data or not self.data['messages'])
        pane = self.changes_pane
        if pane.key is not None:
            entry = next((item for item in self.data['messages'] if item['id'] == pane.key[1]), None) if self.data else None
            if self.data is None or pane.key[0] != self.data['id'] or not entry or not entry.get('changes'):
                pane.clear()
            elif not pane.isHidden() and pane.records != entry['changes']:
                pane.show_changes(pane.key, entry['changes'], pane.files.currentData())
        self.transcript.body.layout().activate()
        bar.setValue(bar.maximum() if bottom else old)

    def update_controls(self):
        busy = self.client.busy
        editable = self.data is not None and self.lease is not None
        for widget in (self.list, self.new_button, self.refresh_button, self.search, self.folder_button):
            widget.setEnabled(not busy)
        self.connection_box.setEnabled(not busy)
        self.mode.setEnabled(not busy)
        self.project_box.setVisible(self.mode.currentData() == 'code')
        self.project_box.setEnabled(editable and not busy)
        code = self.mode.currentData() == 'code'
        for widget in (self.project_picker, self.project_refresh):
            widget.setVisible(code)
        self.attach_button.setEnabled(editable and not busy)
        self.selection_button.setEnabled(editable and code and not busy)
        self.model.setEnabled(not busy)
        self.settings_box.setEnabled(editable and not busy)
        self.composer.setEnabled(editable)
        self.composer.setPlaceholderText('Enter Message')
        self.send_button.setEnabled(busy or editable)
        action = 'Stop generation / connection check' if busy else 'Send message'
        self.send_button.setIcon(chat_icon('stop' if busy else 'send'))
        self.send_button.setToolTip(action)
        self.send_button.setAccessibleName(action)
        self.transcript.set_retry_enabled(editable and not busy)
        self.auth_toggle.setEnabled(not busy)
        selected = self.list.currentItem()
        selected_conversation = (selected is not None and self.data is not None and
            selected.data(0, qt.Qt.ItemDataRole.UserRole) == self.data['id'])
        for widget in (self.rename_button, self.delete_button):
            widget.setEnabled(editable and not busy and selected_conversation)
        self.move_button.setEnabled(editable and not busy)
        self.move_button.setToolTip('Move the open conversation to another folder')
        self.export_button.setEnabled(self.data is not None)
        self.pin_action.setEnabled(editable and not busy)
        self.pin_action.setText('Unpin conversation' if self.data and self.data.get('pinned') else 'Pin conversation')
        self.fork_action.setEnabled(editable and not busy)
        for action in getattr(self, 'draft_actions', ()):
            action.setEnabled(editable)
        for action in getattr(self, 'idle_menu_actions', ()):
            action.setEnabled(not busy)





    def can_close(self):
        if self.discard_approved or self.persist():
            return True
        answer = qt.QMessageBox.question(self, 'Conversation could not be saved',
            'The current conversation has unsaved changes. Cancel to export or retry saving, or discard them and close.',
            qt.QMessageBox.StandardButton.Discard | qt.QMessageBox.StandardButton.Cancel,
            qt.QMessageBox.StandardButton.Cancel)
        self.discard_approved = answer == qt.QMessageBox.StandardButton.Discard
        return self.discard_approved

    def prepare_close(self):
        self.closing = True
        self.save_timer.stop()
        if self.client.busy:
            self.client.cancel()
        if self.client.busy:
            return False
        if not self.discard_approved and not self.persist():
            return False
        self.release_lease()
        self.update_controls()
        return True
