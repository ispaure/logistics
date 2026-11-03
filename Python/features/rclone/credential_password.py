"""Verified credential ZIP re-encryption with no plaintext staging files."""
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import pyzipper
from commonUtils.persistence import atomic_write_bytes
from commonUtils.runtime.operations import check_cancelled
from . import session


def _migrate_catalogs(root, old_identity, old_password, cipher):
    from services.documents.catalog import DocumentCatalog, _lock
    from services.documents.state_migration import _desktop_open
    class PreviousCipher:
        identity = old_identity
        def transform(self, data, decode=False):
            if not decode:
                raise ValueError('Previous password is read-only.')
            return _desktop_open(data, old_password, 'state.json')
    with _lock:
        for recent in (False, True):
            store = DocumentCatalog(root, recent=recent)
            old_path = store.path(PreviousCipher())
            if not old_path.exists():
                continue
            previous = store.read(PreviousCipher())
            current = store.read(cipher)
            merged = {}
            for field, maximum in (('favourites', 100), ('recent', 10)):
                rows = sorted([*current[field], *previous[field]], key=lambda row: row['updated'], reverse=True)
                unique = {}
                for row in rows:
                    unique.setdefault(row['id'], row)
                merged[field] = list(unique.values())[:maximum]
            store.save(merged, cipher)
            if store.read(cipher) != merged:
                raise ValueError('Document history migration could not be verified.')
            if old_path != store.path(cipher):
                old_path.unlink()


def change_password(package, context, new_password, *, current_password=None, cancelled=lambda: False):
    package, context = Path(package), Path(context)
    if not new_password:
        raise ValueError('Enter a non-empty new password.')
    if package.is_symlink() or not package.is_file() or package.stat().st_nlink != 1:
        raise ValueError('Choose an independent credential ZIP file.')
    from .desktop_service import service
    grant = service.credentials.capture(context)
    state = session.registry.state_credentials(context)
    if current_password is None:
        if state is None:
            raise ValueError('Enter the current ZIP password.')
        try:
            current_password = bytes(state[1]).decode()
        finally:
            state[1][:] = b'\0' * len(state[1])
    elif state is not None:
        state[1][:] = b'\0' * len(state[1])
    with package.open('rb') as stream:
        original = stream.read(1024 * 1024 + 1)
    if len(original) > 1024 * 1024:
        raise ValueError('Credential ZIPs are limited to 1 MiB.')
    old_identity = sha256(original).hexdigest()
    # Authenticate and validate the existing format before attempting a rewrite.
    expected = session.read_package(package, current_password)
    loaded = session.credentials(context)
    if loaded is None and context.suffix == '.conf':
        from configparser import ConfigParser
        parser = ConfigParser(interpolation=None)
        parser.read(context, encoding='utf-8')
        loaded = {name: dict(parser[name]) for name in parser.sections()}
    if loaded != expected:
        raise ValueError('Loaded credentials differ from this ZIP. Reload the package before changing its password.')
    output = BytesIO()
    members = []
    with pyzipper.AESZipFile(BytesIO(original)) as archive:
        archive.setpassword(current_password.encode())
        for member in archive.infolist():
            check_cancelled(cancelled)
            members.append((member.filename, archive.read(member.filename)))
    with pyzipper.AESZipFile(output, 'w', encryption=pyzipper.WZ_AES,
                             compression=pyzipper.ZIP_DEFLATED) as archive:
        archive.setpassword(new_password.encode())
        for name, data in members:
            archive.writestr(name, data)
    encrypted = output.getvalue()
    if len(encrypted) > 1024 * 1024:
        raise ValueError('Re-encrypted credential ZIP exceeds 1 MiB; original preserved.')
    with pyzipper.AESZipFile(BytesIO(encrypted)) as archive:
        archive.setpassword(new_password.encode())
        if [(member.filename, archive.read(member.filename)) for member in archive.infolist()] != members:
            raise ValueError('Credential ZIP verification failed; original preserved.')
    def validate():
        check_cancelled(cancelled)
        grant.check()
        if (package.is_symlink() or package.stat().st_nlink != 1 or package.stat().st_size > 1024 * 1024
                or sha256(package.read_bytes()).hexdigest() != old_identity):
            raise ValueError('Credential ZIP changed; original preserved.')
    validate()
    atomic_write_bytes(package, encrypted, validate=validate)
    # Credential settings stay identical; republishing retires old reader grants.
    from .desktop_credentials import DesktopCredentialLoad
    session_context = context.with_suffix('.session')
    had_session = session.names(session_context) is not None
    from .credential_loading import CredentialContext
    admission = CredentialContext(cancelled=cancelled, valid=lambda: not grant.revoked())
    try:
        if had_session:
            service.credentials.load(DesktopCredentialLoad(package, session_context, False), new_password, admission)
        if context.suffix == '.conf':
            service.credentials.load(DesktopCredentialLoad(package, context, True), new_password, admission)
    except Exception:
        return ('Credential ZIP password changed. Unlock it with the new password to resume. '
                'Protected history was preserved under the previous password.')
    warning = ''
    if had_session:
        from commonUtils.filesystem.storage import cache_directory
        from services.documents.credential_state import DesktopCredentialCipher
        from types import SimpleNamespace
        from services.documents.state_migration import migrate
        root = cache_directory(create=False)
        cipher = DesktopCredentialCipher(SimpleNamespace(context=session_context))
        try:
            _migrate_catalogs(root, old_identity, current_password, cipher)
            migrate(root, current_password)
        except (OSError, ValueError, PermissionError, RuntimeError):
            warning = ' Some protected history was preserved under its previous password; use Reader history migration if needed.'
    for settings in expected.values():
        settings.clear()
    expected.clear()
    members.clear()
    return 'Credential ZIP password changed.' + warning
