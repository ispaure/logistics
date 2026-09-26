"""
Debug UI contributions exposed by Images.
"""

from features.contributions import DebugActionContribution, FeatureContributions, WorkflowContribution

def _open_compress(data=None, parent=None):
    from features.images.ui.dialogs import ImageCompressDialog

    dialog = ImageCompressDialog(initial_path=data, parent=parent)
    return dialog.exec()


def _open_exif_comments(data=None, parent=None):
    from features.images.ui.dialogs import ExifCommentsDialog

    dialog = ExifCommentsDialog(initial_path=data, parent=parent)
    return dialog.exec()


def get_contributions() -> FeatureContributions:
    return FeatureContributions(
        debug_actions=[
            DebugActionContribution(
                name='Batch Compress Images...',
                workflow_id='debug_images_compress',
                destructive=True,
                order=10
            ),
            DebugActionContribution(
                name='JPG EXIF - Set Comments...',
                workflow_id='debug_images_exif_comments',
                destructive=True,
                order=20
            ),
        ],
        workflows=[
            WorkflowContribution('debug_images_compress', _open_compress),
            WorkflowContribution('debug_images_exif_comments', _open_exif_comments),
        ]
    )
