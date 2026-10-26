"""
Debug UI contributions exposed by Images.
"""

from features.contributions import DebugActionContribution, DocumentLauncherContribution, Feature, WorkflowContribution
from commonUtils.ui.features import BrowserExtension, SelectionAction, FileType, FileActivation
from commonUtils.filesystem.directories import Directory

def _open_compress(context):
    from features.images.ui.dialogs import ImageCompressDialog
    dialog = ImageCompressDialog(initial_path=context.paths, parent=context.host or context.browser)
    try:
        return dialog.exec()
    finally:
        dialog.deleteLater()
        context.browser.refresh()


def _open_exif_comments(data=None, parent=None):
    from features.images.ui.dialogs import ExifCommentsDialog

    dialog = ExifCommentsDialog(initial_path=data, parent=parent)
    return dialog.exec()


def _open_image(context):
    from .ui.viewer import open_image
    return open_image(context.path, context.host or context.browser)


def _launch_image(parent):
    from .ui.viewer import launch
    return launch(parent)


def get_contributions() -> Feature:
    return Feature(id='images', label='Image Tools',
        file_types=[FileType('features.images.file_type:ImageFile', extensions=('png', 'jpg', 'jpeg', 'webp'))],
        document_launchers=[DocumentLauncherContribution('images', 'Image Viewer', _launch_image, 'image', 46,
            description='View images and navigate neighboring files in the same folder.')],
        browser=BrowserExtension(activation=[FileActivation('features.images.file_type:ImageFile', _open_image)], actions=[SelectionAction('compress_webp', 'Batch Compress Images to WEBP…', Directory, _open_compress, order=60)]),
        debug_actions=[
            DebugActionContribution(
                name='JPG EXIF - Set Comments...',
                workflow_id='debug_images_exif_comments',
                destructive=True,
                order=20
            ),
        ],
        workflows=[
            WorkflowContribution('debug_images_exif_comments', _open_exif_comments),
        ]
    )
