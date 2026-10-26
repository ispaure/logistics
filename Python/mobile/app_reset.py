"""Fresh-launch iOS erasure and Android's own clear-app-data operation."""
import json
from pathlib import Path
import shutil

from commonUtils.persistence import atomic_write_json
from services.documents.locations import _unlinked

RESET_MARKER = 'erase-app-data-on-launch.json'


def schedule_reset(private_root):
    atomic_write_json(_unlinked(Path(private_root) / RESET_MARKER),
                      {'schema': 1}, durable_directory=True)


def erase_contents(root, *, keep):
    """Unlink contained links; never visit their targets. Keep the retry marker."""
    root = _unlinked(root)
    if not root.exists():
        return
    for child in root.iterdir():
        if child == keep:
            continue
        if child.is_symlink() or not child.is_dir():
            child.unlink()
        elif keep.is_relative_to(child):
            erase_contents(child, keep=keep)
        else:
            shutil.rmtree(child)


def finish_pending_reset(private_root, roots, *, erase_keys):
    """Run before migration/services. Interrupted erasure retries next launch."""
    marker = _unlinked(Path(private_root) / RESET_MARKER)
    if not marker.exists():
        return False
    if marker.stat().st_size > 128 or json.loads(marker.read_text()) != {'schema': 1}:
        raise ValueError('Invalid app reset request; no data was erased.')
    roots = list(dict.fromkeys(_unlinked(Path(root)) for root in (*roots, private_root)))
    erase_keys()  # A locked Keychain must fail before deleting credential records.
    for root in roots:
        erase_contents(root, keep=marker)
    marker.unlink()
    return True


def erase_ios_keys():
    # Restrict deletion to the two Logistics services, including orphaned keys
    # whose metadata was damaged. Never issue an unscoped Keychain deletion.
    from commonUtils.runtime.protected_keys import IOSKeys, KeyStoreUnavailable
    for service in ('io.github.ispaure.logisticsmobile.credentials',
                    'io.github.ispaure.logisticsmobile.packages'):
        keys = IOSKeys(service=service, label='', label_prefix='')
        cf = keys.cf
        name = cf.CFStringCreateWithCString(None, service.encode(), 0x08000100)
        query = cf.CFDictionaryCreateMutable(None, 0, None, None)
        try:
            cf.CFDictionarySetValue(query, keys.constant('kSecClass'), keys.constant('kSecClassGenericPassword'))
            cf.CFDictionarySetValue(query, keys.constant('kSecAttrService'), name)
            status = keys.security.SecItemDelete(query)
            if status not in (0, -25300):
                raise KeyStoreUnavailable('Unlock the device and reopen Logistics to finish erasing app data.')
        finally:
            cf.CFRelease(query)
            cf.CFRelease(name)


def finish_ios_reset(app, private_root):
    from rubicon.objc import ObjCClass
    from .screen_privacy import native_value
    library = Path(app.paths.config).parent.parent

    def erase_keys():
        erase_ios_keys()
        bundle = native_value(native_value(ObjCClass('NSBundle'), 'mainBundle'), 'bundleIdentifier')
        native_value(ObjCClass('NSUserDefaults'), 'standardUserDefaults').removePersistentDomainForName(bundle)

    shared_intake = []
    if (Path(private_root) / RESET_MARKER).exists():
        group = ObjCClass('NSFileManager').defaultManager.containerURLForSecurityApplicationGroupIdentifier(
            'group.io.github.ispaure.logisticsmobile')
        if group is not None:
            shared_intake.append(Path(str(group.path)) / 'Incoming')
    return finish_pending_reset(private_root,
        (*shared_intake, Path(app.paths.data), Path(app.paths.config).parent, Path(app.paths.cache),
         library / 'WebKit', library / 'Cookies', library / 'Saved Application State',
         library.parent / 'tmp'), erase_keys=erase_keys)


def reset_android(app):
    from java import jclass
    manager = app._impl.native.getSystemService(jclass('android.content.Context').ACTIVITY_SERVICE)
    if not manager.clearApplicationUserData():
        raise OSError('Android could not erase app data. Use Android Settings → Apps → Logistics → Storage → Clear storage.')
