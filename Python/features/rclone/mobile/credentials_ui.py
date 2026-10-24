"""Credential package selection, retention, unlock and restoration presentation."""
import asyncio
from contextlib import contextmanager
from dataclasses import dataclass, field
from io import BytesIO
from typing import Any
import toga
from toga.style import Pack
from toga.style.pack import COLUMN
from commonUtils.ui.native.password_input import PasswordInput
from .cloud import PACKAGE_LIMIT, download_name
from features.rclone.credential_loading import CredentialBusyError
from .messages import import_hint
from .credential_catalog import CredentialCatalog, remember_association
from .service import native_service
from .credential_loading import NativeCredentialLoad, run_credentials


class SelectedCredentialZIP:
    """Consume picker access immediately; retain only bounded ZIP bytes in memory."""
    def __init__(self, access, reference):
        with access.open(reference) as (name, source):
            self.data = source.read(PACKAGE_LIMIT + 1)
        if len(self.data) > PACKAGE_LIMIT:
            raise ValueError('Credential ZIPs are limited to 1 MiB.')
        self.name = download_name(name)

    @contextmanager
    def open(self, reference=None):
        with BytesIO(self.data) as stream:
            yield self.name, stream



@dataclass
class CredentialState:
    credential_packages: Any = field(init=False, repr=False)
    session_credential_packages: Any = field(init=False, repr=False)
    cloud_pending_zip: Any = field(init=False, repr=False)


class CredentialWorkflow:
    def __init__(self, cloud):
        self.cloud = cloud

    def _current(self, client, *, navigation=None, generation=None):
        """Check the captured host/client and, after publication, its generation."""
        cloud = self.cloud
        return (cloud.active_host and cloud.cloud_client is client
                and (navigation is None or cloud.navigation_generation == navigation)
                and (generation is None or getattr(client, 'generation', 0) == generation))

    @staticmethod
    def package_title(name):
        from pathlib import PurePosixPath
        name = PurePosixPath(name).name
        return name[:-4] if name.lower().endswith('.zip') else name

    def package_rows(self):
        cloud = self.cloud
        records = {item['package_name']: item for item in getattr(cloud.cloud_client, 'package_records', ())}
        cache = cloud.retained_packages()
        retained = {item['zip']: key for key, item in getattr(cache, 'items', {}).items()}
        import json
        # Another scene can forget saved material while this scene retains its
        # Settings view. Do not resurrect its package label from cached prefs.
        saved = {item['zip'] for item in json.loads(cloud.preferences.reload()['remote_packages'])}
        names = set(records) | set(retained) | saved
        fallback = getattr(cloud.cloud_client, 'package_name', '')
        if not records and fallback and cloud.loaded_remote_names():
            records[fallback] = dict(remotes=cloud.loaded_remote_names(), saved=False)
            names.add(fallback)
        return [(name, records.get(name), retained.get(name)) for name in sorted(names, key=str.casefold)
                if name not in ('Network shares', 'Session network shares')
                and cloud.legacy_name_visible(name, prefix='legacy')]

    def refresh_retained_credentials(self):
        cloud = self.cloud
        if not getattr(cloud, '_cloud_connections_opened', False):
            return
        for child in list(cloud.cloud_retained_box.children):
            cloud.cloud_retained_box.remove(child)
        ui = cloud.rclone_ui
        cloud.cloud_retained_buttons = {}
        try:
            rows = self.package_rows()
        except (OSError, ValueError):
            cloud.cloud_retained_box.add(ui.settings.note('Credential packages are unavailable. Unlock the device and try again.'))
            return
        buttons = []
        for name, record, key in rows:
            status = ('Persistent save' if record.get('saved') else 'Session-Only') if record else 'Locked'
            def open_package(widget=None, selected=name, **kwargs):
                if not cloud.cloud_busy:
                    self.show_credential_package(selected)
            button = ui.settings.package_row(self.package_title(name), status, open_package)
            button.enabled = not cloud.cloud_busy
            cloud.cloud_retained_buttons[key or name] = button
            buttons.append(button)
        cloud.cloud_retained_box.add(ui.settings.group(buttons) if buttons else
            ui.settings.note('No credential packages yet. Import a ZIP to get started.'))
        self.refresh_package_remotes()
        if hasattr(cloud, 'cloud_connections_status'):
            cloud.cloud_connections_status.text = cloud.cloud_status.value
        if hasattr(cloud.cloud_connections_view, 'reflow'):
            cloud.cloud_connections_view.reflow()

    def refresh_package_remotes(self):
        cloud = self.cloud
        name = getattr(self, 'package_name', None)
        if name is None or not hasattr(self, 'package_remotes_box'):
            return
        record = next((item for item in getattr(cloud.cloud_client, 'package_records', ())
                       if item['package_name'] == name), None)
        self.package_status.text = ('Persistent save' if record.get('saved') else 'Session-Only') if record else 'Locked'
        box = self.package_remotes_box
        for child in list(box.children):
            box.remove(child)
        names = cloud.visible_remote_names(record['remotes']) if record else []
        for remote in names:
            async def browse(widget=None, selected=remote, **kwargs):
                if cloud.cloud_busy:
                    return
                cloud.cloud_remote.value = selected
                cloud.cloud_location.value = ''
                if await cloud.browse_cloud():
                    cloud.show_cloud()
            box.add(toga.Button(remote, on_press=browse, enabled=not cloud.cloud_busy, style=Pack(height=48)))
        if not names:
            box.add(cloud.rclone_ui.settings.note('Unlock this package to load its remotes.'))
        for control in (cloud.credential_unlock_password, cloud.credential_unlock_button, self.package_forget):
            control.enabled = not cloud.cloud_busy
        if hasattr(self, 'package_view'):
            self.package_view.reflow()

    def show_credential_package(self, name):
        rows = {label: key for label, record, key in self.package_rows()}
        if name not in rows:
            cloud = self.cloud
            cloud.show_cloud_connections()
            return
        return self.show_retained_unlock(rows[name], destination='settings', package_name=name)

    async def choose_credential_storage(self, name):
        from .credential_dialog import CredentialStorageDialog
        cloud = self.cloud
        import json
        saved = (any(item['zip'] == name for item in json.loads(cloud.preferences.values['remote_packages']))
                 or any(item['package_name'] == name and item.get('saved')
                        for item in getattr(cloud.cloud_client, 'package_records', ())))
        return await cloud.main_window.dialog(CredentialStorageDialog(
            self.package_title(name), saved=saved, content_factory=cloud.rclone_ui.settings.storage_content))

    async def forget_package(self, name):
        cloud = self.cloud
        if cloud.cloud_busy or cloud.cloud_client is None:
            return
        client, origin = cloud.cloud_client, cloud.navigation_generation
        generation = getattr(client, 'generation', 0)
        warning = (f'Remove {self.package_title(name)} and all its saved and session credentials from this device? '
                   'Every remote supplied by this package will disappear from Cloud. '
                   'Its retained ZIP and encrypted open/recent lists will also be removed. '
                   'You must import the package again to reconnect. This cannot be undone.\n\n'
                   'Cloud files and local folders will not be deleted.')
        if not await cloud.main_window.dialog(toga.ConfirmDialog('Forget this credential package?', warning)):
            return
        if cloud.cloud_busy or not self._current(client, navigation=origin, generation=generation):
            return
        cloud.set_cloud_busy(True)
        try:
            if not cloud.clear_private_reader():
                return
            cloud.clear_private_catalog()
            from .credential_retention import NativeCredentialForget
            await run_credentials(native_service(client).credentials.forget,
                NativeCredentialForget(lambda: cloud.retained_packages(), cloud.app.credential_document_lists.root, name))
            import json
            saved = [item for item in json.loads(cloud.preferences.values['remote_packages']) if item['zip'] != name]
            cloud.preferences.save(remote_packages=json.dumps(saved))
            cloud.session_credential_packages = [item for item in getattr(cloud, 'session_credential_packages', ())
                                                 if item['zip'] != name]
            cloud.set_loaded_remote_names(cloud.loaded_remote_names())
            cloud.cloud_password.value = cloud.credential_unlock_password.value = ''
            cloud.cloud_pending_zip = None
            cloud.cloud_crypt_remotes.intersection_update(cloud.loaded_remote_names())
            cloud.cloud_rows = {}
            cloud.cloud_entries.items = []
            cloud.cloud_open_remote = None
            cloud.cloud_location.value = cloud.cloud_path = ''
            cloud.cloud_package.text = cloud.loaded_package_label()
            cloud.app.folder_controller().discovery.invalidate()
            if hasattr(cloud.app, 'folder_list'):
                cloud.app.update_folder_list(cloud.app.folder_choices())
            self.package_name = None
            cloud.cloud_status.value = 'Credential package and its remotes forgotten. Local folders were kept.'
            cloud.show_cloud_connections()
        except Exception:
            cloud.cloud_status.value = 'Some package cleanup failed. Access may already be removed. Unlock the device and retry forgetting.'
            if hasattr(cloud, 'credential_unlock_status'):
                cloud.credential_unlock_status.text = cloud.cloud_status.value
        finally:
            cloud.set_cloud_busy(False)

    async def _load_crypt_remote_names(self):
        cloud = self.cloud
        client = cloud.cloud_client
        generation = getattr(client, 'generation', 0)
        # Alternate client adapters may not expose crypt support.
        kinds = getattr(cloud.cloud_client, 'crypt_remotes', lambda: ())
        records = getattr(cloud.cloud_client, 'package_records', ())
        if records and all('crypt_identities' in record for record in records):
            crypt_remotes = {remote for record in records for remote in record['crypt_identities']}
        else:
            crypt_remotes = set(await asyncio.to_thread(kinds))
        if not self._current(client, generation=generation):
            return False
        cloud.cloud_crypt_remotes = crypt_remotes
        try:
            cache = cloud.retained_packages()
            update = getattr(cache, 'update_crypt_remotes', None)
            if update is not None:
                records = {item['package_name']: item for item in getattr(cloud.cloud_client, 'package_records', ())}
                for key, item in tuple(cache.items.items()):
                    record = records.get(item['zip'])
                    if record is not None and record.get('document_cache_id') != key:
                        continue
                    if record is not None or item['zip'] == getattr(cloud.cloud_client, 'package_name', ''):
                        from .credential_retention import NativeCredentialMetadata
                        await run_credentials(native_service(client).credentials.retain,
                            NativeCredentialMetadata(cache, key, generation, tuple(cloud.cloud_crypt_remotes),
                                record.get('aliases', {}) if record else {}),
                            valid=lambda: cloud.active_host and cloud.cloud_client is client)
        except (OSError, ValueError) as error:
            cloud.folder_hub_error = 'Could not save folder type metadata: ' + str(error)[:200]
        if not self._current(client, generation=generation):
            return False
        try:
            await cloud.refresh_hub_crypt_locations()
        except (OSError, ValueError) as error:
            cloud.folder_hub_error = str(error)[:300]
        if not self._current(client, generation=generation):
            return False
        cloud.refresh_cloud_remote_help()
        return True

    def retained_packages(self, *, for_forget=False):
        cloud = self.cloud
        if getattr(getattr(cloud, 'cloud_client', None), 'vault', None) is None:
            return None
        if (for_forget or not hasattr(cloud, 'credential_packages')
                or cloud.credential_packages.client is not cloud.cloud_client):
            from features.rclone.mobile.credential_packages import CredentialPackages
            from features.rclone.mobile.credential_vault import ProtectedVault
            cloud.credential_packages = CredentialPackages(ProtectedVault.for_app(cloud.app, packages=True), cloud.cloud_client,
                document_cache_root=cloud.app.credential_document_lists.root, load=not for_forget)
        return cloud.credential_packages

    def remember_credential_association(self, name, remotes, *, session_only):
        cloud = self.cloud
        import json
        previous = json.loads(cloud.preferences.values['remote_packages'])
        update = remember_association(previous, getattr(cloud, 'session_credential_packages', ()),
                                      name, remotes, session_only=session_only)
        cloud.session_credential_packages = update.sessions
        if not session_only and update.saved != previous:
            cloud.preferences.save(remote_packages=json.dumps(update.saved))

    def visible_remote_names(self, names):
        cloud = self.cloud
        catalog = CredentialCatalog(getattr(cloud.cloud_client, 'package_records', ()))
        return catalog.visible_remotes(names, cloud.rclone_ui.exclusions())

    def package_remote_names(self, label, fallback):
        cloud = self.cloud
        method = getattr(cloud.cloud_client, 'package_remotes', None)
        return method(label, fallback) if method else fallback

    def remember_loaded_packages(self, label, names, *, session_only):
        cloud = self.cloud
        records = getattr(cloud.cloud_client, 'package_records', ())
        if records:
            for item in records:
                cloud.remember_credential_association(item['package_name'], cloud.visible_remote_names(item['remotes']), session_only=not item['saved'])
        else:
            cloud.remember_credential_association(label, cloud.visible_remote_names(names), session_only=session_only)

    def loaded_package_label(self):
        cloud = self.cloud
        catalog = CredentialCatalog(getattr(cloud.cloud_client, 'package_records', ()))
        return catalog.label(getattr(cloud.cloud_client, 'package_name', ''))

    def credential_groups(self, choices=None, *, loaded_remotes=None):
        cloud = self.cloud
        loaded = set(cloud.loaded_remote_names() if loaded_remotes is None else loaded_remotes)
        records = getattr(cloud.cloud_client, 'package_records', ())
        if not hasattr(cloud.cloud_client, 'package_records'):
            name = getattr(cloud.cloud_client, 'package_name', '')
            records = [dict(package_name=name, remotes=loaded)] if name and loaded else []
        catalog = CredentialCatalog(records)
        folders = cloud.folder_choices() if choices is None else choices
        available = {copy['remote'] for entry in folders.values()
                     for copy in entry.get('copies', ()) if copy.get('remote')}
        if choices is None:
            available.update(loaded)
        available.intersection_update(loaded)
        return catalog.groups(available,
                              visible=lambda name: cloud.legacy_name_visible(name, prefix='legacy'))

    def home_unlock_candidates(self):
        """Inspect retained metadata/files only; never restore or decode credentials."""
        cloud = self.cloud
        try:
            cache = cloud.retained_packages()
            loaded = {item['package_name'] for item in
                      getattr(getattr(cloud, 'cloud_client', None), 'package_records', ())}
            return sorted(((key, item) for key, item in getattr(cache, 'items', {}).items()
                           if item['zip'] not in loaded
                           and cloud.legacy_name_visible(item['zip'], prefix='legacy')
                           and cache.path(key).is_file()), key=lambda row: row[1]['zip'].casefold())
        except (OSError, ValueError):
            return []

    def show_home_unlock(self, widget=None, **kwargs):
        cloud = self.cloud
        if not cloud.app.checkpoint():
            return
        cloud.show_cloud(present=False)
        choices = cloud.home_unlock_candidates()
        if choices:
            cloud.show_retained_unlock(choices[0][0], destination='home',
                                      resume=cloud.app.show_home, choices=choices)
        else:
            cloud.app.show_home()

    def retained_credential_associations(self):
        cloud = self.cloud
        try:
            cache = cloud.retained_packages()
            return [dict(zip=item['zip'], remotes=list(item['remotes']), identities=dict(item['remotes']), session_only=True,
                         crypt_remotes=list(item.get('crypt_remotes', ())))
                    for item in getattr(cache, 'items', {}).values()] if cache is not None else []
        except (OSError, ValueError):
            return []

    def _connection_is_loaded(self, remote, identity):
        cloud = self.cloud
        if identity is None:
            return remote in cloud.loaded_remote_names()
        # Native publication already resolves identities for every loaded package,
        # including saved packages when the newest import is session-only. A
        # second bridge probe can fail transiently; that is not a credential lock.
        return any(record.get('identities', {}).get(remote) == identity
                   for record in getattr(cloud.cloud_client, 'package_records', ()))

    async def require_remote_credentials_async(self, remote, *, identity=None, resume=None):
        cloud = self.cloud
        origin = cloud.navigation_generation
        restore = getattr(cloud, 'cloud_restore_task', None)
        if restore is not None:
            await asyncio.shield(restore)
            if not cloud.active_host or cloud.navigation_generation != origin:
                return False
        if identity is not None and hasattr(cloud.cloud_client, 'resolve_remote'):
            remote = cloud.cloud_client.resolve_remote(remote, identity)
        if self._connection_is_loaded(remote, identity):
            return True
        client, generation = cloud.cloud_client, getattr(cloud.cloud_client, 'generation', None)
        try:
            current = await asyncio.to_thread(client.connection_identity, remote)
        except (OSError, ValueError, AttributeError):
            current = None
        if (not cloud.active_host or cloud.navigation_generation != origin or client is not cloud.cloud_client
                or generation != getattr(client, 'generation', None)):
            return False
        if current is not None and (identity is None or current == identity):
            return True
        return cloud.require_remote_credentials(remote, identity=identity, resume=resume, checked=True)

    def require_remote_credentials(self, remote, *, identity=None, resume=None, checked=False):
        """Return immediately when loaded; otherwise present the matching ZIP unlock."""
        cloud = self.cloud
        if identity is not None and hasattr(cloud.cloud_client, 'resolve_remote'):
            remote = cloud.cloud_client.resolve_remote(remote, identity)
        if self._connection_is_loaded(remote, identity):
            return True
        if not checked:
            try:
                current = cloud.cloud_client.connection_identity(remote)
                if identity is None or current == identity:
                    return True
            except (OSError, ValueError, AttributeError):
                pass
        try:
            cache = cloud.retained_packages()
            matches = [(key, item) for key, item in cache.matching(remote, identity)
                       if cloud.legacy_name_visible(item['zip'], prefix='legacy')] if cache else []
        except (OSError, ValueError) as error:
            cloud.cloud_status.value = str(error)
            matches = []
        if len(matches) == 1:
            cloud.show_retained_unlock(matches[0][0], remote, identity=identity, resume=resume)
        elif matches:
            box = toga.Box(style=Pack(direction=COLUMN, margin=16))
            box.add(toga.Label('Choose credential ZIP'))
            for key, item in matches:
                def choose(widget=None, selected=key, **kwargs):
                    cloud.show_retained_unlock(selected, remote, identity=identity, resume=resume)
                box.add(toga.Button(item['zip'], on_press=choose, style=Pack(height=44)))
            cloud.show_view(box, destination='files', route='choose-credential', title='Unlock connection')
        else:
            cloud.show_cloud_connections()
            cloud.cloud_import_message.text = import_hint('Load the credential ZIP for ' + remote + '. Retained password-protected ZIPs need their ZIP password to unlock again.')
        return False

    def show_retained_unlock(self, key, remote=None, *, identity=None, resume=None, destination='files', choices=None, package_name=None):
        cloud = self.cloud
        cache = cloud.retained_packages()
        password = cloud.credential_unlock_password = PasswordInput(placeholder='ZIP password', style=Pack(height=44))
        status = cloud.credential_unlock_status = toga.Label('')
        name = package_name or cache.items[key]['zip']
        selected_note = cloud.rclone_ui.settings.note(self.package_title(name))
        selector = None
        if choices:
            labels = {item['zip']: candidate for candidate, item in choices}
            selector = toga.Selection(items=list(labels), style=Pack(height=44))
            def changed(widget, **kwargs):
                password.value = ''
                status.text = ''
                selected_note.text = self.package_title(selector.value)
            selector.on_change = changed
        async def unlock(widget=None, **kwargs):
            selected = labels[selector.value] if selector is not None else key
            if selected is None:
                cloud.show_cloud_import()
                await cloud.choose_cloud_package()
                return
            if cloud.cloud_busy or getattr(cloud, 'transfer_busy', False):
                return
            if selected not in getattr(cache, 'items', {}):
                password.value = ''
                status.text = 'This package is no longer retained. Return to Credential Packages and import it again.'
                return
            secret = password.value
            password.value = ''
            client, origin = cloud.cloud_client, cloud.navigation_generation
            generation = getattr(client, 'generation', 0)
            cloud.set_cloud_busy(True)
            ready = False
            try:
                remember = await self.choose_credential_storage(cache.items[selected]['zip'])
                if remember is None:
                    status.text = 'Unlock cancelled.'
                    return
                if not self._current(client, navigation=origin, generation=generation):
                    status.text = 'Credentials changed. Return to Credential Packages and try again.'
                    return
                if not cloud.clear_private_reader():
                    raise ValueError('Save or discard private edits before unlocking another credential.')
                cloud.clear_private_catalog()
                client, origin = cloud.cloud_client, cloud.navigation_generation
                current = lambda: self._current(client, navigation=origin, generation=generation)
                result = await run_credentials(native_service(client).credentials.load,
                    NativeCredentialLoad(cache, selected, remember=remember), secret, valid=current)
                current = lambda: self._current(client, navigation=origin, generation=result.generation)
                if not current():
                    return
                names = list(result.remotes)
                await cloud._load_crypt_remote_names()
                if not current():
                    return
                cloud.set_loaded_remote_names(cloud.visible_remote_names(names))
                checked_remote = cloud.cloud_client.resolve_remote(remote, identity) if remote is not None and identity is not None and hasattr(cloud.cloud_client, 'resolve_remote') else remote
                if checked_remote is not None and (checked_remote not in names or (identity is not None
                        and await asyncio.to_thread(cloud.cloud_client.connection_identity, checked_remote) != identity)):
                    raise ValueError('This ZIP does not match the folder connection.')
                if not current():
                    return
                cloud.remember_loaded_packages(cache.items[selected]['zip'], names, session_only=not remember)
                cloud.cloud_package.text = cloud.loaded_package_label()
                cloud.app.credential_document_lists.refresh()
                cloud.cloud_status.value = 'Credential ZIP unlocked (' + ('Persistent save' if remember else 'Session-Only') + ').'
                ready = True
            except (OSError, ValueError) as error:
                status.text = import_hint('Unlock failed: ' + str(error)[:160])
            finally:
                secret = None
                cloud.set_cloud_busy(False)
            if ready:
                if package_name is not None:
                    self.refresh_package_remotes()
                    return
                cloud.routes.back()
                if resume is not None:
                    import inspect
                    result = resume()
                    if inspect.isawaitable(result):
                        await result
        password.on_confirm = unlock
        cloud.credential_unlock_button = toga.Button('Unlock', on_press=unlock, style=Pack(height=44))
        ui = cloud.rclone_ui
        if package_name is not None:
            self.package_name = name
            self.package_status = ui.settings.note('')
            self.package_remotes_box = toga.Box(style=Pack(direction=COLUMN))
            async def forget(widget=None, **kwargs):
                await self.forget_package(name)
            self.package_forget = toga.Button('Forget this credential package', on_press=forget, style=Pack(height=48))
            box = self.package_view = ui.settings.page('', '', [
                self.package_status, ui.settings.field('Package password', password),
                cloud.credential_unlock_button, status,
                ui.settings.heading('Loaded remotes'), self.package_remotes_box,
                ui.settings.heading('Credential removal'),
                ui.settings.group([self.package_forget]), ui.settings.note('Removes this package and all its remotes from Cloud on this device.')])
            if key is None:
                status.text = 'Select the original credential ZIP to unlock this package again.'
            self.refresh_package_remotes()
            cloud.show_view(box, destination=destination, route='credential-package', title=self.package_title(name))
        else:
            box = ui.settings.page('Unlock credential ZIP', 'Your ZIP password is never saved.', [
                *([selector] if selector is not None else []),
                selected_note, password, cloud.credential_unlock_button, status,
                toga.Button('Cancel', on_press=lambda widget, **kw: cloud.routes.back(), style=Pack(height=44))])
            if cloud.show_view(box, destination=destination, route='unlock-credential', title='Unlock credential'):
                password.focus()

    async def restore_cloud(self, widget=None, *, initial=False, **kwargs):
        cloud = self.cloud
        if (cloud.cloud_busy and not initial) or cloud.cloud_client is None:
            return
        if not initial and not cloud.clear_private_reader():
            return
        if not initial:
            cloud.set_cloud_busy(True)
        cloud._cloud_restore_error = ''
        try:
            # Initial restore has no old credential state to retire. Home and
            # ordinary local browsers may already be in use while it runs.
            if not initial:
                cloud.clear_private_catalog()
            client = cloud.cloud_client
            result = await run_credentials(native_service(client).credentials.restore,
                valid=lambda: self._current(client))
            names = list(result.remotes)
            if not self._current(client, generation=result.generation):
                return
            await cloud._load_crypt_remote_names()
            if not self._current(client, generation=result.generation):
                return
            cloud.set_loaded_remote_names(cloud.visible_remote_names(names))
            if names and cloud.cloud_client.package_name:
                cloud.remember_loaded_packages(cloud.cloud_client.package_name, names, session_only=False)
            cloud._cloud_restored = True
            cloud._publish_restored_connections(names)
        except Exception:
            cloud._cloud_restore_error = 'Saved credentials are unavailable. Unlock the device and reload, or forget saved credentials to import again.'
            if hasattr(cloud, 'cloud_status'):
                cloud.cloud_status.value = cloud._cloud_restore_error
        finally:
            cloud.set_cloud_busy(False)

    def _publish_restored_connections(self, names):
        cloud = self.cloud
        if not hasattr(cloud, 'cloud_view'):
            return
        cloud.cloud_entries.items = []
        cloud.cloud_rows = {}
        cloud.cloud_open_remote = None
        cloud.cloud_location.value = cloud.cloud_path = ''
        cloud.cloud_package.text = cloud.loaded_package_label()
        if cloud.cloud_pending_zip is None and names:
            saved = [item['package_name'] for item in getattr(cloud.cloud_client, 'package_records', ()) if item['saved']]
            cloud.cloud_selected_zip.text = import_hint('Saved packages: ' + ', '.join(saved) if saved else 'Loaded ZIP: ' + (cloud.cloud_client.package_name or 'saved package'))
            cloud.cloud_import_message.text = import_hint('Loaded remotes are ready. Open Workspaces or Browse remote files to choose a remote, then tap Browse folder.\nChoose another ZIP to add another credential package.')
        cloud.cloud_status.value = (f'{len(names)} total remote(s) available. Saved packages reloaded; active session-only packages were kept.'
                                   if names else 'No saved credential package. Import a ZIP to get started.')

    async def choose_cloud_package(self, widget=None, **kwargs):
        cloud = self.cloud
        pick_document = cloud.rclone_ui.pick_document
        if cloud.cloud_busy or cloud.cloud_client is None:
            return
        cloud.set_cloud_busy(True)
        try:
            selected = await pick_document(cloud)
            if selected is None:
                cloud.cloud_import_message.text = import_hint('ZIP selection cancelled. Your loaded remotes are unchanged.')
                return
            package = await asyncio.to_thread(SelectedCredentialZIP, *selected)
            cloud.cloud_pending_zip = package
            cloud.cloud_selected_zip.text = import_hint('Selected ZIP: ' + package.name)
            cloud.cloud_import_message.text = import_hint('Enter the ZIP password, then tap Unlock (or Return).\nLeave it blank for an unencrypted ZIP.')
        except Exception as error:
            cloud.cloud_import_message.text = import_hint('Could not select ZIP: ' + str(error)[:150])
        finally:
            cloud.set_cloud_busy(False)

    async def import_cloud_package(self, widget=None, **kwargs):
        cloud = self.cloud
        if cloud.cloud_busy or cloud.cloud_client is None:
            return
        # Retain the direct-call API for native validation clients; the visible
        # Unlock button is enabled only after Choose ZIP succeeds.
        if cloud.cloud_pending_zip is None:
            if widget is not None:
                cloud.cloud_import_message.text = import_hint('Tap Choose credential ZIP first, then enter its password and tap Unlock.')
                return
            await cloud.choose_cloud_package()
            if cloud.cloud_pending_zip is None:
                return
        password = cloud.cloud_password.value
        cloud.cloud_password.value = ''
        selected = cloud.cloud_pending_zip
        cloud.set_cloud_busy(True)
        cloud.cloud_import_message.text = 'Loading remotes…'
        try:
            client, origin = cloud.cloud_client, cloud.navigation_generation
            generation = getattr(client, 'generation', 0)
            remember = (await self.choose_credential_storage(selected.name) if widget is not None
                        else cloud.cloud_remember.value)
            if remember is None:
                cloud.cloud_import_message.text = 'Unlock cancelled. Enter the ZIP password to retry.'
                return
            if not self._current(client, navigation=origin, generation=generation):
                cloud.cloud_import_message.text = 'Credentials changed. Try unlocking this package again.'
                return
            if not cloud.clear_private_reader():
                cloud.cloud_import_message.text = import_hint('Save or discard your private edits before loading another package.')
                return
            cloud.clear_private_catalog()
            current = lambda: self._current(client, navigation=origin, generation=generation)
            result = await run_credentials(native_service(client).credentials.load,
                NativeCredentialLoad(selected, None, remember=remember), password, valid=current)
            current = lambda: self._current(client, navigation=origin, generation=result.generation)
            if not current():
                return
            names = list(result.remotes)
            loaded_generation = result.generation
            await cloud._load_crypt_remote_names()
            if not current():
                return
            cloud.remember_loaded_packages(selected.name, names, session_only=not remember)
            cache_error = ''
            try:
                cache = cloud.retained_packages()
                if cache is not None:
                    from .credential_retention import NativeCredentialRetention
                    remotes = tuple(cloud.visible_remote_names(cloud.package_remote_names(selected.name, names)))
                    await run_credentials(native_service(client).credentials.retain,
                        NativeCredentialRetention(cache, selected, remotes, loaded_generation, tuple(cloud.cloud_crypt_remotes)),
                        valid=current)
            except (OSError, ValueError) as error:
                cache_error = ' ZIP not retained; select it again next time. ' + str(error)[:120]
            if not current():
                return
            cloud.set_loaded_remote_names(cloud.visible_remote_names(names))
            cloud.cloud_package.text = cloud.loaded_package_label()
            cloud.cloud_location.value = cloud.cloud_path = ''
            cloud.cloud_open_remote = None
            cloud.cloud_rows = {}
            cloud.cloud_entries.items = []
            cloud.cloud_pending_zip = None
            cloud.cloud_rows = {}
            cloud.cloud_entries.items = []
            cloud.cloud_open_remote = None
            cloud.cloud_location.value = cloud.cloud_path = ''
            cloud.cloud_selected_zip.text = import_hint('Loaded ZIP: ' + selected.name)
            cloud.cloud_import_message.text = import_hint(f'{len(names)} total remote(s) available. Open Workspaces or Browse remote files to choose a remote, then tap Browse folder.' + cache_error)
            cloud.app.credential_document_lists.refresh()
            cloud.cloud_status.value = f'{selected.name} loaded ({"Persistent save" if remember else "Session-Only"}). {len(names)} total remote(s) available. Open Workspaces to browse. No connection has been made yet.'
        except CredentialBusyError as error:
            cloud.cloud_status.value = str(error)
            cloud.cloud_import_message.text = import_hint(str(error))
        except Exception as error:
            cloud.cloud_status.value = 'Import failed: ' + str(error)[:300]
            cloud.cloud_import_message.text = import_hint('Could not load ZIP. Check the password and tap Unlock again.\n' + str(error)[:150])
        finally:
            password = None
            cloud.set_cloud_busy(False)

