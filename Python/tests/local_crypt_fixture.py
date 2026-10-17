"""Synthetic local rclone cloud/crypt fixture: never uses user accounts."""
from contextlib import contextmanager, ExitStack
from io import BytesIO
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image
from commonUtils.archives.zip_access import open_archive
from commonUtils.integrations.wrappers.cmdShellWrapper.binary import run_bytes
from features.rclone import session
from features.rclone.localcrypt import backend as local_crypt
from features.rclone import actions
from features.rclone.transfers import sync
from features.rclone import storage


@contextmanager
def crypt_fixture(root, binary, *, crypt_settings=None):
    root = Path(root).resolve()
    plain, cloud = root / 'plain', root / 'cloud'
    plain.mkdir()
    cloud.mkdir()
    original = b'# Private fixture\n\nOriginal note.\n\n![page](page.png)\n'
    (plain / 'note.md').write_bytes(original)
    (plain / 'remoteConfig.ini').write_text('[LogisticsZIP]\narchive_password=synthetic-archive-password\n')
    image = BytesIO()
    Image.new('RGB', (24, 32), 'red').save(image, 'PNG')
    (plain / 'page.png').write_bytes(image.getvalue())
    for name, password in [('plain.cbz', None), ('encrypted.cbz', 'synthetic-archive-password')]:
        with open_archive(plain / name, 'w', password=password) as archive:
            archive.writestr('page.png', image.getvalue())
    obscured = run_bytes([str(binary), 'obscure', 'synthetic-crypt-password']).decode().strip()
    package = root / 'Accounts.zip'
    with open_archive(package, 'w', password='synthetic-package-password') as archive:
        archive.writestr('Cloud.txt', '[Cloud]\ntype=local\n')
        extra = ''.join(f'{key}={value}\n' for key, value in (crypt_settings or {}).items())
        archive.writestr('Secret.txt', f'[Secret]\ntype=crypt\nremote=Cloud:{cloud}\npassword={obscured}\n' + extra)
    context = root / 'Accounts.session'
    session.remember(context, session.read_package(package, 'synthetic-package-password'), package_path=package)
    environment, source, destination = session.launch(context, plain, 'Secret:')
    run_bytes([str(binary), '--config', session.NULL_CONFIG, 'copy', str(source), str(destination)], environment=environment, max_output=0)
    actual_sync = sync.rclone_sync
    def transfer(source, destination, **options):
        return actual_sync(source, destination, **options, wait_for_output=True, executable_path=binary)
    with ExitStack() as patches:
        patches.enter_context(patch.object(local_crypt.configuration, 'get_credential_config_path', return_value=root / 'Accounts.conf'))
        patches.enter_context(patch.object(storage, 'application_root', return_value=root / 'Application Support/Logistics'))
        patches.enter_context(patch.object(actions.config, 'LogisticsConfig', return_value=SimpleNamespace(server_path=root / 'Server', path_remote_local=root / 'Server/Local')))
        patches.enter_context(patch.object(sync, 'rclone_sync', side_effect=transfer))
        assert actions.pull_encrypted_copy('Secret', context)
        item = local_crypt.connection(context, 'Secret')
        provider = local_crypt.CryptResources(item, binary=binary)
        try:
            yield SimpleNamespace(root=root, plain=plain, cloud=cloud, package=package, context=context,
                                  item=item, provider=provider, original=original, image=image.getvalue())
        finally:
            provider.close()
            session.forget(context)
