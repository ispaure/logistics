"""
Debug UI contributions exposed by Images.
"""

from features.contributions import DebugActionContribution, Feature, WorkflowContribution
from commonUtils.features import BrowserExtension, SelectionAction
from commonUtils.dirUtils import Directory

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


def get_contributions() -> Feature:
    return Feature(id='images', label='Images',
        browser=BrowserExtension(actions=[SelectionAction('compress_webp', 'Batch Compress Images to WEBP…', Directory, _open_compress, order=60)]),
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
