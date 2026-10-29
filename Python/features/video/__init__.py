"""Video playback feature; decoder imports stay in presentation factories."""
FEATURE_NAME = 'video'
FEATURE_LABEL = 'Video Player'
FEATURE_DESCRIPTION = 'Play Local, LocalCrypt and remote/crypt MP4, MKV, AVI and other common video containers.'


def _open(context):
    from .ui.player import open_video
    return open_video(context.path, context.host or context.browser)


def _launch(parent):
    from .ui.player import launch
    return launch(parent)


def register():
    from features.contributions import Feature, DocumentLauncherContribution
    from commonUtils.ui.features import FileType, BrowserExtension, FileActivation
    from .formats import VIDEO_EXTENSIONS
    return Feature(id='video', label=FEATURE_LABEL,
        file_types=[FileType('features.video.file_type:VideoFile', extensions=tuple(sorted(suffix[1:] for suffix in VIDEO_EXTENSIONS)))],
        document_launchers=[DocumentLauncherContribution('video', 'Video Player', _launch, 'tools', 47,
            description=FEATURE_DESCRIPTION)],
        browser=BrowserExtension(activation=[FileActivation('features.video.file_type:VideoFile', _open)]))
