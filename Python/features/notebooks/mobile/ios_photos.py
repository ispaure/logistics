"""Bridge the iOS system photo pickers to the active notebook canvas."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import asyncio

from commonUtils.ui.native.text_size import native_backend


def _picker(web):
    if getattr(web, '_impl', None) is None or not native_backend(web).startswith('toga_iOS.'):
        return None
    try:
        from rubicon.objc import ObjCClass

        return ObjCClass('LogisticsNotebookPhotoPicker')
    except (ImportError, NameError, ValueError, RuntimeError):
        return None


def photo_sources(web):
    picker = _picker(web)
    if picker is None:
        return []
    return ['photos', 'camera'] if picker.cameraAvailable() else ['photos']


async def choose_photo(web, source):
    picker = _picker(web)
    if picker is None or (source == 'camera' and not picker.cameraAvailable()):
        raise ValueError('This photo source is unavailable.')
    from commonUtils.ui.native.keyboard import native_value
    from rubicon.objc import Block, ObjCInstance, objc_id
    from toga_iOS.images import nsdata_to_bytes

    window = native_value(web._impl.native.window)
    presenter = native_value(window.rootViewController) if window is not None else None
    if presenter is None:
        raise ValueError('Reopen the notebook before choosing a photo.')
    while presented := native_value(presenter.presentedViewController):
        presenter = presented
    future = asyncio.get_running_loop().create_future()

    def completed(data, error):
        if future.done():
            return
        try:
            if error:
                raise ValueError(str(ObjCInstance(error)))
            future.set_result(nsdata_to_bytes(ObjCInstance(data)) if data else None)
        except Exception as failure:
            future.set_exception(failure)

    completion = Block(completed, None, objc_id, objc_id)
    if not picker.showFrom(presenter, camera=source == 'camera', completion=completion):
        raise ValueError('Could not open the photo picker.')
    return await future
