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

    def refresh_retained_credentials(self):
        cloud = self.cloud
        if not getattr(cloud, '_cloud_connections_opened', False):
            return
        for child in list(cloud.cloud_retained_box.children):
            cloud.cloud_retained_box.remove(child)
        try:
            cache = cloud.retained_packages()
            rows = sorted(getattr(cache, 'items', {}).items(), key=lambda row: row[1]['zip'].casefold())
            rows = [(key, item) for key, item in rows if cloud.legacy_name_visible(item['zip'], prefix='legacy')]
        except (OSError, ValueError):
            cloud.cloud_retained_box.add(toga.Label('Retained ZIPs are unavailable. Unlock the device and try again.'))
            return
        cloud.cloud_retained_buttons = {}
        records = {item['package_name']: item for item in getattr(cloud.cloud_client, 'package_records', ())
                   if item['package_name'] not in ('Network shares', 'Session network shares')
                   and cloud.legacy_name_visible(item['package_name'], prefix='legacy')}
        if not records and cloud.cloud_client is not None and cloud.loaded_remote_names():
            name = getattr(cloud.cloud_client, 'package_name', '')
            if name and name not in ('Network shares', 'Session network shares'):
                records[name] = dict(remotes=cloud.loaded_remote_names(), saved=False)
        ui = cloud.rclone_ui
        for name, record in records.items():
            def browse(widget=None, **kwargs):
                cloud.show_locations()
            names = cloud.visible_remote_names(record['remotes'])
            row = ui.settings.group([
                toga.Label(import_hint(name), style=Pack(font_weight='bold', margin_top=8)),
                ui.settings.note(f'{len(names)} remotes · ' + ('saved on this device' if record.get('saved') else 'session only')),
                toga.Button('Browse remote files', on_press=browse, enabled=not cloud.cloud_busy, style=Pack(height=48))])
            cloud.cloud_retained_box.add(row)
        for key, item in rows:
            if item['zip'] in records:
                continue
            def unlock(widget=None, selected=key, **kwargs):
                if not cloud.cloud_busy:
                    cloud.show_retained_unlock(selected, destination='settings', resume=cloud.show_locations)
            button = toga.Button('Unlock ' + item['zip'], on_press=unlock,
                                 enabled=not cloud.cloud_busy, style=Pack(height=44))
            cloud.cloud_retained_buttons[key] = button
            cloud.cloud_retained_box.add(ui.settings.group([
                toga.Label(import_hint(item['zip']), style=Pack(font_weight='bold', margin_top=8)),
                ui.settings.note('Locked · retained on this device'), button]))
        if not rows and not records:
            cloud.cloud_retained_box.add(ui.settings.note('No credential packages yet. Import a ZIP to get started.'))
        if hasattr(cloud, 'cloud_connections_status'):
            cloud.cloud_connections_status.text = cloud.cloud_status.value
        if hasattr(cloud.cloud_connections_view, 'reflow'):
            cloud.cloud_connections_view.reflow()

    async def _load_crypt_remote_names(self):
        cloud = self.cloud
        client = cloud.cloud_client
        generation = getattr(client, 'generation', 0)
        # Alternate client adapters may not expose crypt support.
        kinds = getattr(cloud.cloud_client, 'crypt_remotes', lambda: ())
        records = getattr(cloud.cloud_client, 'package_records', ())
        if records and all('crypt_identities' in record for record in records):
            cloud.cloud_crypt_remotes = {remote for record in records for remote in record['crypt_identities']}
        else:
            cloud.cloud_crypt_remotes = set(await asyncio.to_thread(kinds))
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
        try:
            await cloud.refresh_hub_crypt_locations()
        except (OSError, ValueError) as error:
            cloud.folder_hub_error = str(error)[:300]
        cloud.refresh_cloud_remote_help()

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
        packages = [item for item in previous if item['zip'] != name and not item['session_only']]
        association = dict(zip=name, remotes=list(remotes), session_only=session_only)
        sessions = [item for item in getattr(cloud, 'session_credential_packages', ()) if item['zip'] != name]
        cloud.session_credential_packages = [*sessions, association] if session_only else sessions
        if session_only:
            return
        packages.append(association)
        if packages[-32:] != previous:
            cloud.preferences.save(remote_packages=json.dumps(packages[-32:]))

    def visible_remote_names(self, names):
        cloud = self.cloud
        exclusions = cloud.rclone_ui.exclusions
        from services.folders.policy import visible_name
        original = {alias: name for item in getattr(cloud.cloud_client, 'package_records', ())
                    for name, alias in item.get('aliases', {}).items()}
        rules = exclusions()
        return sorted((name for name in names if visible_name(original.get(name, name), rules, remote=True)), key=str.casefold)

    def package_remote_names(self, label, fallback):
        cloud = self.cloud
        method = getattr(cloud.cloud_client, 'package_remotes', None)
        return method(label, fallback) if method else fallback

    def remember_loaded_packages(self, label, names, *, session_only):
        cloud = self.cloud
        visible_remotes = cloud.rclone_ui.visible_remotes
        records = getattr(cloud.cloud_client, 'package_records', ())
        if records:
            for item in records:
                cloud.remember_credential_association(item['package_name'], cloud.visible_remote_names(item['remotes']), session_only=not item['saved'])
        else:
            cloud.remember_credential_association(label, cloud.visible_remote_names(names), session_only=session_only)

    def loaded_package_label(self):
        cloud = self.cloud
        records = getattr(cloud.cloud_client, 'package_records', ())
        if not records:
            return 'Credential package: ' + (getattr(cloud.cloud_client, 'package_name', '') or 'none')
        return 'Loaded:\n' + '\n'.join(item['package_name'] + (' (saved)' if item['saved'] else ' (session only)') for item in records)

    def credential_groups(self, choices=None):
        cloud = self.cloud
        import json
        from pathlib import Path
        groups = {'All': None}
        associations = {item['zip']: item for item in json.loads(cloud.preferences.values['remote_packages'])
                        + cloud.retained_credential_associations() + getattr(cloud, 'session_credential_packages', [])}
        loaded = set()
        for item in getattr(getattr(cloud, 'cloud_client', None), 'package_records', ()):
            loaded.add(item['package_name'])
            associations[item['package_name']] = dict(zip=item['package_name'], remotes=item['remotes'])
        available = {copy['remote'] for entry in (cloud.folder_choices() if choices is None else choices).values()
                     for copy in entry.get('copies', ()) if copy.get('remote')}
        if choices is None:
            # Loaded packages are authoritative while folder discovery is still
            # pending. An explicit choices snapshot still scopes its own rows.
            available.update(cloud.loaded_remote_names())
        for item in associations.values():
            if item['zip'] in ('Network shares', 'Session network shares'):
                continue
            if not cloud.legacy_name_visible(Path(item['zip']).name, prefix='legacy'):
                continue
            remotes = set(item['remotes']) & available
            if not remotes and item['zip'] not in loaded:
                continue
            name = Path(item['zip']).name
            base = name[:-4] if name.lower().endswith('.zip') else name
            title = base
            number = 2
            while title in groups:
                title = f'{base} ({number})'
                number += 1
            from services.folders.catalog import CredentialScope
            groups[title] = CredentialScope(remotes, item['zip'])
        return groups

    def home_unlock_candidates(self):
        cloud = self.cloud
        """Inspect retained metadata/files only; never restore or decode credentials."""
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
        if remote in cloud.loaded_remote_names() and identity is None:
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
        cloud = self.cloud
        """Return immediately when loaded; otherwise present the matching ZIP unlock."""
        if identity is not None and hasattr(cloud.cloud_client, 'resolve_remote'):
            remote = cloud.cloud_client.resolve_remote(remote, identity)
        loaded = cloud.loaded_remote_names()
        if remote in loaded and identity is None:
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

    def show_retained_unlock(self, key, remote=None, *, identity=None, resume=None, destination='files', choices=None):
        cloud = self.cloud
        cache = cloud.retained_packages()
        password = cloud.credential_unlock_password = PasswordInput(placeholder='ZIP password', style=Pack(height=44))
        status = cloud.credential_unlock_status = toga.Label('')
        selector = None
        if choices:
            labels = {item['zip']: candidate for candidate, item in choices}
            selector = toga.Selection(items=list(labels), style=Pack(height=44))
            selector.on_change = lambda widget, **kw: setattr(password, 'value', '')
        async def unlock(widget=None, **kwargs):
            selected = labels[selector.value] if selector is not None else key
            if cloud.cloud_busy or getattr(cloud, 'transfer_busy', False):
                return
            secret = password.value
            password.value = ''
            cloud.set_cloud_busy(True)
            ready = False
            try:
                if not cloud.clear_private_reader():
                    raise ValueError('Save or discard private edits before unlocking another credential.')
                cloud.clear_private_catalog()
                client, origin = cloud.cloud_client, cloud.navigation_generation
                current = lambda: cloud.active_host and cloud.cloud_client is client and cloud.navigation_generation == origin
                result = await run_credentials(native_service(client).credentials.load,
                    NativeCredentialLoad(cache, selected, remember=False), secret, valid=current)
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
                cloud.remember_loaded_packages(cache.items[selected]['zip'], names, session_only=True)
                cloud.cloud_package.text = cloud.loaded_package_label()
                cloud.app.credential_document_lists.refresh()
                cloud.cloud_status.value = 'Credential ZIP unlocked for this app session. Its open and recent file lists are restored.'
                ready = True
            except (OSError, ValueError) as error:
                status.text = import_hint('Unlock failed: ' + str(error)[:160])
            finally:
                secret = None
                cloud.set_cloud_busy(False)
            if ready:
                cloud.routes.back()
                if resume is not None:
                    import inspect
                    result = resume()
                    if inspect.isawaitable(result):
                        await result
        visible_remotes = cloud.rclone_ui.visible_remotes
        password.on_confirm = unlock
        cloud.credential_unlock_button = toga.Button('Unlock', on_press=unlock, style=Pack(height=44))
        box = toga.Box(children=[toga.Label('Choose credential' if choices else import_hint('Unlock ' + cache.items[key]['zip']), style=Pack(font_size=18)),
            *([selector] if selector is not None else []),
            toga.Label(import_hint('Its ZIP is retained on this device. The password is needed for this session and is never saved.')),
            password, cloud.credential_unlock_button, status,
            toga.Button('Cancel', on_press=lambda widget, **kw: cloud.routes.back(), style=Pack(height=44))],
            style=Pack(direction=COLUMN, margin=16))
        cloud.show_view(box, destination=destination, route='unlock-credential', title='Unlock credential')

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
                valid=lambda: cloud.active_host and cloud.cloud_client is client)
            names = list(result.remotes)
            if not cloud.active_host or cloud.cloud_client is not client:
                return
            await cloud._load_crypt_remote_names()
            visible_remotes = cloud.rclone_ui.visible_remotes
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
            cloud.cloud_import_message.text = import_hint('Enter the ZIP password, then tap Load remotes (or Return).\nLeave it blank for an unencrypted ZIP.')
        except Exception as error:
            cloud.cloud_import_message.text = import_hint('Could not select ZIP: ' + str(error)[:150])
        finally:
            cloud.set_cloud_busy(False)

    async def import_cloud_package(self, widget=None, **kwargs):
        cloud = self.cloud
        if cloud.cloud_busy or cloud.cloud_client is None:
            return
        # Retain the direct-call API for native validation clients; the visible
        # Load remotes button is enabled only after Choose ZIP succeeds.
        if cloud.cloud_pending_zip is None:
            if widget is not None:
                cloud.cloud_import_message.text = import_hint('Tap Choose credential ZIP first, then enter its password and tap Load remotes.')
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
            if not cloud.clear_private_reader():
                cloud.cloud_import_message.text = import_hint('Save or discard your private edits before loading another package.')
                return
            cloud.clear_private_catalog()
            remember = cloud.cloud_remember.value
            client, origin = cloud.cloud_client, cloud.navigation_generation
            current = lambda: cloud.active_host and cloud.cloud_client is client and cloud.navigation_generation == origin
            result = await run_credentials(native_service(client).credentials.load,
                NativeCredentialLoad(selected, None, remember=remember), password, valid=current)
            if not current():
                return
            names = list(result.remotes)
            loaded_generation = result.generation
            await cloud._load_crypt_remote_names()
            if not current():
                return
            visible_remotes = cloud.rclone_ui.visible_remotes
            cloud.remember_loaded_packages(selected.name, names, session_only=not remember)
            cache_error = ''
            if not remember:
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
            cloud.cloud_selected_zip.text = import_hint('Loaded ZIP: ' + selected.name)
            cloud.cloud_import_message.text = import_hint(f'{len(names)} total remote(s) available. Open Workspaces or Browse remote files to choose a remote, then tap Browse folder.' + cache_error)
            cloud.app.credential_document_lists.refresh()
            cloud.cloud_status.value = f'{selected.name} loaded ({"saved" if remember else "session only"}). {len(names)} total remote(s) available. Open Workspaces to browse. No connection has been made yet.'
        except CredentialBusyError as error:
            cloud.cloud_status.value = str(error)
            cloud.cloud_import_message.text = import_hint(str(error))
        except Exception as error:
            cloud.cloud_status.value = 'Import failed: ' + str(error)[:300]
            cloud.cloud_import_message.text = import_hint('Could not load ZIP. Check the password and tap Load remotes again.\n' + str(error)[:150])
        finally:
            password = None
            cloud.set_cloud_busy(False)

