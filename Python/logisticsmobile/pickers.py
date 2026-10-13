"""Native document selection for the pinned Toga 0.5.7 mobile backends."""
import asyncio
from commonUtils.runtime.platform import get_os, OS
from .access import AndroidDocuments, IOSDocuments, LocalDocuments

_ios_future = _ios_delegate_class = _ios_delegate = _ios_picker = None


async def pick_document(app):
    current = get_os()
    if current is OS.ANDROID:
        from java import jclass
        Intent = jclass('android.content.Intent')
        Activity = jclass('android.app.Activity')
        intent = Intent(Intent.ACTION_OPEN_DOCUMENT)
        intent.addCategory(Intent.CATEGORY_OPENABLE)
        intent.setType('*/*')
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        future = asyncio.get_running_loop().create_future()
        def complete(code, data):
            if not future.done():
                future.set_result(data.getData() if code == Activity.RESULT_OK and data else None)
        app._impl.start_activity(intent, on_complete=complete)
        uri = await future
        return (AndroidDocuments(app._impl.native.getContentResolver()), uri) if uri else None
    if current is OS.IOS:
        return await pick_ios(app)
    import toga
    path = await app.main_window.dialog(toga.OpenFileDialog('Import text document'))
    return (LocalDocuments(), path) if path else None


async def pick_ios(app):
    global _ios_future, _ios_delegate_class, _ios_delegate, _ios_picker
    from rubicon.objc import ObjCClass, ObjCProtocol, objc_method
    if _ios_future is not None:
        raise RuntimeError('A document picker is already open.')
    if _ios_delegate_class is None:
        NSObject = ObjCClass('NSObject')
        class LogisticsDocumentPickerDelegate(NSObject, protocols=(ObjCProtocol('UIDocumentPickerDelegate'),)):
            @objc_method
            def documentPicker_didPickDocumentsAtURLs_(self, picker, urls) -> None:
                if _ios_future is not None and not _ios_future.done():
                    _ios_future.set_result(urls[0] if len(urls) else None)

            @objc_method
            def documentPickerWasCancelled_(self, picker) -> None:
                if _ios_future is not None and not _ios_future.done():
                    _ios_future.set_result(None)
        _ios_delegate_class = LogisticsDocumentPickerDelegate
    # Open mode returns a scoped source URL. The adapter copies its bytes into
    # private storage while access is held, so no permission/bookmark is retained.
    _ios_picker = ObjCClass('UIDocumentPickerViewController').alloc().initWithDocumentTypes(
        ['public.data'], inMode=1)
    _ios_delegate = _ios_delegate_class.alloc().init()
    _ios_picker.delegate = _ios_delegate
    _ios_picker.allowsMultipleSelection = False
    _ios_future = asyncio.get_running_loop().create_future()
    try:
        controller = app.main_window._impl.native.rootViewController
        while controller.presentedViewController:
            controller = controller.presentedViewController
        controller.presentViewController(_ios_picker, animated=True, completion=None)
        url = await _ios_future
        return (IOSDocuments(), url) if url is not None else None
    finally:
        _ios_future = _ios_delegate = _ios_picker = None
