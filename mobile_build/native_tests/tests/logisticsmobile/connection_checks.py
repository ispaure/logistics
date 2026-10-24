"""Native remote previews, transfer workflows and retained credential lifecycle."""
import base64
from commonUtils.runtime.resources.documents import LocalDocuments


async def exercise_connections(app, fixtures, background_comic, passed):
    from features.rclone.mobile.cloud import CloudClient
    from .fixtures import AES_CREDENTIALS
    from unittest.mock import AsyncMock, patch
    app.cloud_client = CloudClient()
    app.show_cloud()
    if hasattr(app, 'cloud_restore_task'):
        await app.cloud_restore_task
    await app.probe_cloud()
    assert 'offline read check passed' in app.cloud_status.value, app.cloud_status.value
    credentials = fixtures / 'credentials.zip'
    credentials.write_bytes(base64.b64decode(AES_CREDENTIALS))
    assert app.cloud_import.text == 'Unlock' and not app.cloud_import.enabled
    with patch('mobile.pickers.pick_document', new=AsyncMock(return_value=(LocalDocuments(), credentials))):
        await app.choose_cloud_package()
        assert app.cloud_import.enabled and 'credentials.zip' in app.cloud_selected_zip.text
        app.cloud_password.value = 'synthetic-fixture-password'
        await app.import_cloud_package()
    assert app.cloud_password.value == ''
    assert app.cloud_pending_zip is None and 'Browse folder' in app.cloud_import_message.text.replace('\n', ' ')
    assert app.cloud_remote.value == 'Fixture' and len(app.cloud_remote.items) == 1, app.cloud_status.value
    await app.browse_cloud()
    row = next(row for row in app.cloud_rows.values() if row['path'] == 'logistics-native-check')
    assert await app.browser_cloud_folder(row)
    row = next(row for row in app.cloud_rows.values() if row['path'].endswith('fixture.txt'))
    assert await app.open_remote_document(row), app.cloud_status.value
    owner = app.provider_sessions().active
    assert owner is not None and owner.crypt_text.readonly
    assert owner.crypt_text.value == 'Native rclone fixture\n'
    assert app.provider_sessions().close(owner.session.id, discard=True)
    assert not hasattr(app, 'download_cloud') and not hasattr(app, 'choose_cloud_copy')
    assert not app.downloads.items()
    passed.append('native_remote_preview_only')
    from .files_checks import exercise_files
    await exercise_files(app, passed)
    from .mirror_checks import exercise_mirrors
    await exercise_mirrors(app, background_comic)
    passed.append('native_background_local_pull_push')
    app.show_cloud()
    await app.clear_cloud()
    assert not list(app.cloud_remote.items)
    assert not app.downloads.items()
    passed.append('native_rclone_files')
    from features.rclone.mobile.credential_vault import ProtectedVault
    vault = ProtectedVault.for_app(app)
    app.cloud_client.vault = vault
    app.cloud_remember.value = True
    app.cloud_password.value = 'synthetic-fixture-password'
    with patch('mobile.pickers.pick_document', new=AsyncMock(return_value=(LocalDocuments(), credentials))):
        await app.import_cloud_package()
    assert vault.ciphertext.is_file(), app.cloud_status.value
    encrypted = vault.ciphertext.read_bytes()
    assert b'Fixture' not in encrypted and b'credentials.zip' not in encrypted
    assert b'synthetic-fixture-password' not in vault.record.read_bytes()
    app.cloud_client.request('clear')  # Shutdown/detach without erasing saved keys.
    app.cloud_client = CloudClient(vault=ProtectedVault.for_app(app))
    await app.restore_cloud()
    assert app.cloud_remote.value == 'Fixture', app.cloud_status.value
    assert 'credentials.zip' in app.cloud_package.text
    # A session-only unlock must leave the saved ciphertext untouched.
    app.cloud_remember.value = False
    app.cloud_password.value = 'synthetic-fixture-password'
    with patch('mobile.pickers.pick_document', new=AsyncMock(return_value=(LocalDocuments(), credentials))):
        await app.import_cloud_package()
    assert vault.ciphertext.read_bytes() == encrypted
    cache = app.retained_packages()
    matches = cache.matching('Fixture')
    assert len(matches) == 1, app.cloud_import_message.text
    retained_key = matches[0][0]
    await app.lock_cloud()
    assert await app.refresh_folder_hub()
    locked_choice = app.folder_choices().get('Fixture', {})
    assert any(copy['source'] == 'Remote' for copy in locked_choice.get('copies', ()))
    assert not await app.require_remote_credentials_async('Fixture')
    assert app.routes.screens['files'][-1][0] == 'unlock-credential'
    assert not app.loaded_remote_names()
    app.show_cloud_connections()
    assert app.native_host.state.destination == 'settings'
    app.cloud_retained_buttons[retained_key].on_press()
    assert app.routes.screens['settings'][-1][0] == 'unlock-credential'
    app.credential_unlock_password.value = 'incorrect-fixture-password'
    await app.credential_unlock_button.on_press()
    assert not app.loaded_remote_names()
    assert app.credential_unlock_password.value == ''
    app.credential_unlock_password.value = 'synthetic-fixture-password'
    await app.credential_unlock_button.on_press()
    assert app.loaded_remote_names() == ['Fixture'], app.credential_unlock_status.text
    assert await app.refresh_folder_hub()
    assert any(copy['source'] == 'Remote' for copy in app.folder_choices()['Fixture']['copies'])
    assert cache.path(retained_key).is_file()
    assert vault.ciphertext.read_bytes() == encrypted
    # Key loss must not regenerate a key or overwrite the saved ciphertext.
    app.cloud_client.request('clear')
    vault.keys.delete(vault.metadata()['id'])
    app.cloud_client = CloudClient(vault=ProtectedVault.for_app(app))
    await app.restore_cloud()
    assert 'unavailable' in app.cloud_status.value, app.cloud_status.value
    assert vault.ciphertext.read_bytes() == encrypted
    await app.clear_cloud()
    assert not vault.ciphertext.exists() and not vault.record.exists(), app.cloud_status.value
    assert vault.unlock() is None
    passed.append('native_secure_credentials')
    passed.append('native_credential_visibility')
