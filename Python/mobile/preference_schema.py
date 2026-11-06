"""Serialized mobile preference defaults and validation, independent of INI I/O.

Feature-specific value rules stay with their owners. Preferences re-exports
DEFAULTS and exposes validate() for existing callers.
"""
import json

from .magnifier import LEVELS, RANGE_ERROR
from features.books.mobile.typography import DEFAULTS as READING_DEFAULTS, FONT_SIZES, validate as validate_reading
from features.images.mobile.burst_camera import DEFAULTS as CAMERA_DEFAULTS, validate_preferences as validate_camera

DEFAULTS = {
    'notebook_paper_preview': 'true',
    'notes_library_migrated': 'true',
    'seasonal_snow': 'true',
    'android_eink': 'false',
    'font_size': '16',
    'markdown_font_size': '16',
    'text_font_size': '16',
    'epub_font_size': '16',
    'restore_last_document': 'true',
    'last_document': '',
    'accent_hue': '221',
    'accent_saturation': '83',
    'workspace_local_group': 'Others',
    'document_card_overview': 'false',
    'show_legacy': 'false',
    'disabled_features': '[]',
    'markdown_justify': 'false',
    'clear_unmodified_documents_on_restart': 'true',
    'session_speech_when_locked': 'false',
    'session_trusted_wifi': 'false',
    'trusted_wifi_networks': '[]',
    'approved_bluetooth_devices': '[]',
    'speech_voice': '',
    'magnifier_zoom': '190',
    'epub_volume_pages': 'false',
    'comic_volume_pages': 'false',
    'epub_outer_cover': 'false',
    'comic_outer_cover': 'false',
    'comic_layout': 'auto',
    'comic_split_wide': 'true',
    'reading_margin': '16',
    'reading_theme': 'system',
    'remote_packages': '[]',
    **READING_DEFAULTS,
    **CAMERA_DEFAULTS,
}


def validate(values):
    from services.mobile_features import disabled_features
    if values.keys() != DEFAULTS.keys():
        raise ValueError('Unknown mobile preference.')
    from .palette import validate_accent
    validate_accent(values['accent_hue'], values['accent_saturation'])
    disabled_features(values['disabled_features'])
    if values['notes_library_migrated'] != 'true':
        raise ValueError('Invalid Notes Library migration state.')
    from services.audio_output import approvals
    approvals(values['approved_bluetooth_devices'])
    if not isinstance(values['speech_voice'], str) or len(values['speech_voice']) > 1024 or any(c in values['speech_voice'] for c in '\r\n\x00'):
        raise ValueError('Invalid read-aloud voice.')
    from .trusted_wifi import network_names
    network_names(values['trusted_wifi_networks'])
    if values['session_trusted_wifi'] not in {'true', 'false'}:
        raise ValueError('Invalid trusted Wi-Fi session preference.')
    if values['session_speech_when_locked'] not in {'true', 'false'}:
        raise ValueError('Invalid session speech lock-screen preference.')
    if values['notebook_paper_preview'] not in {'true', 'false'}:
        raise ValueError('Invalid notebook preview preference.')
    if values['seasonal_snow'] not in {'true', 'false'}:
        raise ValueError('Invalid seasonal snow preference.')
    if values['android_eink'] not in {'true', 'false'}:
        raise ValueError('Invalid Android E Ink preference.')
    if values['markdown_justify'] not in {'true', 'false'}:
        raise ValueError('Invalid Markdown justification preference.')
    if any(values[key] not in FONT_SIZES for key in ('font_size', 'markdown_font_size', 'text_font_size', 'epub_font_size')):
        raise ValueError('Choose a supported font size.')
    if values['restore_last_document'] not in {'true', 'false'}:
        raise ValueError('Invalid document restore preference.')
    if values['workspace_local_group'] not in {'Rclone', 'Others'}:
        raise ValueError('Invalid local workspace tab.')
    if values['show_legacy'] not in {'true', 'false'}:
        raise ValueError('Invalid legacy folder preference.')
    if values['document_card_overview'] != 'false':
        raise ValueError('Invalid document overview preference.')
    if values['clear_unmodified_documents_on_restart'] not in {'true', 'false'}:
        raise ValueError('Invalid document clearing preference.')
    if values['reading_margin'] not in {'8', '16', '24', '32'} or values['reading_theme'] not in {'system', 'light', 'dark', 'sepia', 'slate'}:
        raise ValueError('Invalid reader appearance preference.')
    validate_reading(values)
    validate_camera(values)
    if values['magnifier_zoom'] not in {str(value) for value in LEVELS}:
        raise ValueError(RANGE_ERROR)
    for key in ('epub_volume_pages', 'comic_volume_pages'):
        if values[key] not in {'true', 'false'}:
            raise ValueError('Invalid volume-button page preference.')
    if any(values[key] not in {'true', 'false'} for key in ('epub_outer_cover', 'comic_outer_cover')):
        raise ValueError('Invalid outer-display cover preference.')
    if values['comic_split_wide'] not in {'true', 'false'}:
        raise ValueError('Invalid wide comic page preference.')
    if values['comic_layout'] not in {'single', 'auto', 'double'}:
        raise ValueError('Invalid comic page layout.')
    packages = json.loads(values['remote_packages'])
    if (not isinstance(packages, list) or len(packages) > 32 or any(
            not isinstance(item, dict) or set(item) != {'zip', 'remotes', 'session_only'}
            or not isinstance(item['zip'], str) or not 0 < len(item['zip']) <= 255
            or type(item['session_only']) is not bool or not isinstance(item['remotes'], list)
            or len(item['remotes']) > 256 or any(not isinstance(name, str) or not 0 < len(name) <= 80 for name in item['remotes'])
            for item in packages)):
        raise ValueError('Invalid remote credential associations.')
    key = values['last_document']
    if key and (len(key) != 32 or any(c not in '0123456789abcdef' for c in key)):
        raise ValueError('Invalid last-document identity.')
