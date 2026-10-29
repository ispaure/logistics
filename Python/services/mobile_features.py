"""Portable mobile feature catalogue and all-enabled preference baseline.

Mobile ships selected feature modules rather than desktop registration/UI hooks.
These device-local choices control admission, not packaging or stored data.
"""
from features.video.formats import VIDEO_EXTENSIONS
from dataclasses import dataclass
from pathlib import PurePosixPath
import json


@dataclass(frozen=True)
class MobileFeature:
    name: str
    label: str
    description: str
    members: tuple[str, ...] = ()

    @property
    def names(self):
        return self.members or (self.name,)


FEATURES = (
    MobileFeature('text_editor', 'Text Editor', 'Create, read and edit text, Markdown and source files.'),
    MobileFeature('notebooks', 'Notebooks', 'Create and draw in reMarkable (.rmdoc) notebooks.'),
    MobileFeature('books', 'Books & Comics', 'Read EPUB books and comic archives and browse their libraries.', ('books', 'comics')),
    MobileFeature('pdf', 'PDF Reader', 'Read PDF documents.'),
    MobileFeature('images', 'Image Tools', 'View images and use Burst camera on supported devices.'),
    MobileFeature('video', 'Video Player', 'Play Local, LocalCrypt and remote/crypt video, including MP4, MKV and AVI.'),
    MobileFeature('lm', 'LM Chat', 'Conversations with your configured language-model server.'),
    MobileFeature('rclone', 'rclone', 'Cloud connections, network shares, encrypted storage and transfers. Local files remain available.'),
)
BY_NAME = {name: feature for feature in FEATURES for name in feature.names}
KIND_FEATURES = {'text': 'text_editor', 'markdown': 'text_editor', 'epub': 'books',
                 'comic': 'comics', 'pdf': 'pdf', 'notebook': 'notebooks', 'image': 'images', 'video': 'video'}


def disabled_features(value):
    names = json.loads(value)
    if isinstance(names, list):
        names = ['video' if name == 'media' else name for name in names]
    if (not isinstance(names, list) or any(not isinstance(name, str) or name not in BY_NAME for name in names)
            or len(names) != len(set(names))):
        raise ValueError('Invalid mobile feature selection.')
    return set(names)


def selection_preferences(preferences):
    """Scene windows share feature selection while retaining their other settings."""
    return getattr(preferences, 'feature_preferences', preferences)


def enabled(preferences, name):
    if name not in BY_NAME:
        raise ValueError('Unknown mobile feature: ' + name)
    return name not in disabled_features(selection_preferences(preferences).values.get('disabled_features', '[]'))


def group_enabled(preferences, name):
    return all(enabled(preferences, member) for member in BY_NAME[name].names)


def document_feature(name='', kind=None):
    suffix = PurePosixPath(str(name)).suffix.lower()
    if suffix in VIDEO_EXTENSIONS:
        return 'video'
    if suffix == '.rmdoc':
        return 'notebooks'
    if suffix == '.epub':
        return 'books'
    if suffix in ('.cbz', '.zip', '.cbr', '.cb7', '.cbt'):
        return 'comics'
    if suffix == '.pdf':
        return 'pdf'
    if suffix in ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp', '.tiff', '.heic'):
        return 'images'
    if kind in KIND_FEATURES:
        return KIND_FEATURES[kind]
    from commonUtils.formats.code_syntax import SOURCE_EXTENSIONS
    return 'text_editor' if suffix in SOURCE_EXTENSIONS else None


def session_enabled(preferences, session):
    feature = document_feature(session.title, session.kind)
    if feature is not None and not enabled(preferences, feature):
        return False
    source = (getattr(session, 'source', None) or getattr(session, 'history_source', None)
              or getattr(session, 'cache_source', None))
    return not (source and source.get('type') != 'local' and not enabled(preferences, 'rclone'))
