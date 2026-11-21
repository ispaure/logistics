"""Stage one selected file for the platform share sheet."""
import asyncio
from ctypes import c_bool
from dataclasses import replace
from functools import partial
import mimetypes
from pathlib import Path
import shutil
from tempfile import mkdtemp
from threading import Event
import time

from commonUtils.runtime.operations import check_cancelled, OperationCancelled
from commonUtils.runtime.platform import get_os, OS
from commonUtils.runtime.streams import copy_stream
from services.documents.mobile_storage import confirm_export
from services.documents.storage import DocumentPolicy, document_display_name, document_operation

SEND = 'Send to App…'
SHARE_LIFETIME = 15 * 60
STAGING_FOLDER = 'OutgoingShares'
_ANDROID_PROVIDER = 'io.github.ispaure.logisticsmobile.OutgoingFiles'


def supported():
    return get_os() in (OS.ANDROID, OS.IOS)


def _root(app):
    if get_os() is OS.ANDROID:
        cache = Path(str(app._impl.native.getCacheDir().getAbsolutePath()))
    else:
        cache = Path(app.paths.cache)
    return cache / STAGING_FOLDER


def prune(root):
    cutoff = time.time() - SHARE_LIFETIME
    for directory in root.glob('share-*'):
        try:
            if not directory.is_symlink() and directory.is_dir() and directory.stat().st_mtime < cutoff:
                shutil.rmtree(directory, ignore_errors=True)
        except FileNotFoundError:
            pass


def prune_for_app(app):
    if supported():
        try:
            prune(_root(app))
        except OSError:
            pass


def stage(item, directory, cancelled):
    """Copy stored bytes, rejecting replacements and revocation during the read."""
    with document_operation(item.provider, cancelled):
        before = item.validate()
        name = document_display_name(item.provider, item.path)
        if name in ('', '.', '..') or Path(name).name != name or '\x00' in name:
            raise ValueError('This file has an invalid name.')
        payload = directory / 'payload'
        payload.mkdir(mode=0o700)
        path = payload / name
        with item.provider.open(item.path) as source, path.open('xb') as output:
            copy_stream(source, output, cancelled=cancelled)
            size = output.tell()
        after = item.validate()
        if before.get('revision') != after.get('revision') or size != before['size']:
            raise ValueError('The selected file changed while preparing it.')
        check_cancelled(cancelled)
        directory.touch()
        return path


async def send(app, item, *, anchor=None):
    import toga
    from types import SimpleNamespace
    if not supported() or not app.active_host or getattr(app, '_sending_file', False):
        return False
    app._sending_file = True
    location = getattr(app, 'navigation_generation', None)
    directory = None
    defer_cleanup = False
    cancelled = Event()
    app._outbound_share_cancellation = cancelled
    try:
        provider = item.provider
        policy = DocumentPolicy.for_provider(provider)
        row = await asyncio.to_thread(item.validate)
        item = replace(item, revision=row.get('revision'))
        access_check = item.access_check()

        def validate():
            check_cancelled(cancelled.is_set)
            if not app.active_host or getattr(app, 'navigation_generation', None) != location:
                raise OperationCancelled()
            access_check()

        validate()
        if not policy.persistent and type(app._impl).__module__.startswith('toga_iOS.'):
            await _ios_presenter(app, validate)
        if not await confirm_export(app, SimpleNamespace(policy=policy)):
            return False
        validate()
        root = _root(app)
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if get_os() is OS.ANDROID:
            prune(root)
        directory = Path(mkdtemp(prefix='share-', dir=root))
        worker = asyncio.create_task(asyncio.to_thread(stage, item, directory, cancelled.is_set))
        try:
            path = await asyncio.shield(worker)
        except asyncio.CancelledError:
            # The worker can still hold a storage stream after the caller retires.
            # Delete its copy after it has stopped, even if the coroutine is gone.
            cancelled.set()
            worker.add_done_callback(partial(_discard_worker, directory))
            defer_cleanup = True
            raise

        validate()
        if get_os() is OS.ANDROID:
            _send_android(app, path)
            defer_cleanup = True
            return True
        return await _send_ios(app, path, validate, anchor)
    except OperationCancelled:
        return False
    except (OSError, ValueError, RuntimeError) as error:
        if app.active_host:
            await app.main_window.dialog(toga.InfoDialog(SEND, str(error)))
        return False
    finally:
        app._sending_file = False
        app._outbound_share_cancellation = None
        if directory is not None and not defer_cleanup:
            shutil.rmtree(directory, ignore_errors=True)


def _discard_worker(directory, worker):
    if not worker.cancelled():
        worker.exception()
    shutil.rmtree(directory, ignore_errors=True)


def _send_android(app, path):
    from java import jclass
    native = app._impl.native
    helper = jclass(_ANDROID_PROVIDER)
    mime = mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
    uri = helper.getUriForFile(native, native.getPackageName() + '.outgoing-files',
                               jclass('java.io.File')(str(path)))
    chooser = helper.chooser(native, uri, mime)
    loop = asyncio.get_running_loop()
    directory = path.parent.parent

    def retire():
        native.revokeUriPermission(uri, jclass('android.content.Intent').FLAG_GRANT_READ_URI_PERMISSION)
        shutil.rmtree(directory, ignore_errors=True)

    def cancelled():
        if not (directory / '.target-chosen').exists():
            retire()

    def completed(_code, _data):
        # Chooser selection is reported independently from its activity result.
        # Allow its pending broadcast to arrive before treating Back as cancel.
        loop.call_later(2, cancelled)

    app._impl.start_activity(chooser, on_complete=completed)
    loop.call_later(SHARE_LIFETIME, retire)


async def _ios_presenter(app, validate):
    from rubicon.objc import ObjCClass
    window = app.main_window._impl.native
    presenter = window.rootViewController
    # A browser action sheet dismisses itself after the row action is pressed.
    while presenter.presentedViewController:
        previous = presenter.presentedViewController
        if previous.isKindOfClass(ObjCClass('UIAlertController')):
            for _ in range(30):
                await asyncio.sleep(0.05)
                validate()
                if presenter.presentedViewController != previous:
                    break
            else:
                raise RuntimeError('Close the current dialog and try sharing again.')
        else:
            presenter = previous
    validate()
    return window, presenter


def _ios_file_provider(path):
    from rubicon.objc import Block, ObjCBlock, ObjCClass, objc_block, objc_id

    url = ObjCClass('NSURL').fileURLWithPath(str(path))
    UTType = ObjCClass('UTType')
    data = UTType.typeWithIdentifier('public.data')
    suffix = path.suffix[1:]
    # For an unregistered extension, declare a dynamic type that still
    # conforms to file data so document receivers can load its contents.
    content = UTType.typeWithFilenameExtension(suffix, conformingToType=data) if suffix else None
    provider = ObjCClass('NSItemProvider').alloc().init()
    provider.suggestedName = path.name
    provider.preferredPresentationStyle = 2  # UIPreferredPresentationStyleAttachment

    def load(completion):
        ObjCBlock(completion, None, objc_id, c_bool, objc_id)(url, False, None)
        return None

    provider.registerFileRepresentationForTypeIdentifier((content or data).identifier,
        fileOptions=0, visibility=0, loadHandler=Block(load, objc_id, objc_block))
    # iOS uses the file URL to match extensions that accept files. Keep the
    # byte representation first so the receiver can load the attachment.
    provider.registerObject(url, visibility=0)
    return provider


async def _send_ios(app, path, validate, anchor):
    from rubicon.objc import Block, CGRect, ObjCClass, objc_id
    window, presenter = await _ios_presenter(app, validate)
    provider = _ios_file_provider(path)
    configuration = ObjCClass('UIActivityItemsConfiguration').alloc().initWithItemProviders([provider])
    sheet = ObjCClass('UIActivityViewController').alloc().initWithActivityItemsConfiguration(configuration)
    popover = sheet.popoverPresentationController
    if popover is not None:
        native = getattr(getattr(anchor, '_impl', None), 'native', None)
        if native is not None and native.window == window:
            popover.sourceView, popover.sourceRect = native, native.bounds
        else:
            view = presenter.view
            size = view.bounds.size
            popover.sourceView = view
            popover.sourceRect = CGRect((float(size.width) / 2, float(size.height) / 2), (1, 1))
            popover.permittedArrowDirections = 0

    future = asyncio.get_running_loop().create_future()

    def completed(_activity, accepted, _items, error):
        if not future.done():
            if error:
                future.set_exception(OSError('The selected sharing app could not receive the file.'))
            else:
                future.set_result(bool(accepted))

    completion = Block(completed, None, objc_id, c_bool, objc_id, objc_id)
    sheet.completionWithItemsHandler = completion
    app._outbound_share_sheet = sheet, future
    try:
        presenter.presentViewController(sheet, animated=True, completion=None)
        return await future
    finally:
        app._outbound_share_sheet = None
        sheet.completionWithItemsHandler = None


def cancel(app):
    staging = getattr(app, '_outbound_share_cancellation', None)
    if staging is not None:
        staging.set()
    active = getattr(app, '_outbound_share_sheet', None)
    if active:
        sheet, future = active
        sheet.dismissViewControllerAnimated(False, completion=None)
        if not future.done():
            future.set_result(False)
