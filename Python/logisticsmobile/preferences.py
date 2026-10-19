"""Mobile-owned INI preferences in an explicitly supplied private directory."""
from configparser import Error
import json
from pathlib import Path

from commonUtils.formats.iniType import INIFile
from commonUtils.persistence import atomic_write_bytes

from features.books.mobile.typography import DEFAULTS as READING_DEFAULTS, FONT_SIZES, validate as validate_reading

DEFAULTS = {'android_eink': 'false', 'font_size': '16', 'restore_last_document': 'true', 'last_document': '',
            'document_card_overview': 'false', 'show_legacy': 'false',
            'clear_unmodified_documents_on_restart': 'true', 'session_speech_when_locked': 'false',
            'speech_voice': '', 'magnifier_zoom': '190', 'comic_layout': 'auto', 'reading_margin': '16', 'reading_theme': 'system', 'remote_packages': '[]', **READING_DEFAULTS}


class Preferences:
    def __init__(self, root):
        root = Path(root)
        if not root.is_absolute():
            raise ValueError('Preferences require an absolute app-private directory.')
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = root / 'preferences.ini'
        self.reload()

    def reload(self):
        self.error = ''
        self.original = None
        self.text = ''
        self.values = dict(DEFAULTS)
        try:
            if self.path.is_symlink():
                raise ValueError('Preferences cannot be a symbolic link.')
            if self.path.exists():
                with self.path.open('rb') as stream:
                    self.original = stream.read(65537)
                if len(self.original) > 65536:
                    raise ValueError('Preferences exceed the size limit.')
                self.text = self.original.decode('utf-8-sig')
                parser = INIFile.parse(self.text)
                for key in DEFAULTS:
                    if key not in {'show_legacy', 'document_card_overview'} and parser.has_option('Mobile', key):
                        self.values[key] = parser['Mobile'][key]
                self.validate(self.values)
                # Older session-only imports persisted package/remote labels.
                # Remove those associations as part of the privacy migration.
                packages = json.loads(self.values['remote_packages'])
                retained = [item for item in packages if not item['session_only']]
                if retained != packages:
                    self.save(remote_packages=json.dumps(retained))
        except (OSError, ValueError, UnicodeError, Error) as error:
            self.error = 'Preferences were preserved; using defaults. ' + str(error)
            self.values = dict(DEFAULTS)
        return self.values

    @staticmethod
    def validate(values):
        if values.keys() != DEFAULTS.keys():
            raise ValueError('Unknown mobile preference.')
        if not isinstance(values['speech_voice'], str) or len(values['speech_voice']) > 1024 or any(c in values['speech_voice'] for c in '\r\n\x00'):
            raise ValueError('Invalid read-aloud voice.')
        if values['session_speech_when_locked'] not in {'true', 'false'}:
            raise ValueError('Invalid session speech lock-screen preference.')
        if values['android_eink'] not in {'true', 'false'}:
            raise ValueError('Invalid Android E Ink preference.')
        if values['font_size'] not in FONT_SIZES:
            raise ValueError('Choose a supported font size.')
        if values['restore_last_document'] not in {'true', 'false'}:
            raise ValueError('Invalid document restore preference.')
        if values['show_legacy'] not in {'true', 'false'}:
            raise ValueError('Invalid legacy folder preference.')
        if values['document_card_overview'] != 'false':
            raise ValueError('Invalid document overview preference.')
        if values['clear_unmodified_documents_on_restart'] not in {'true', 'false'}:
            raise ValueError('Invalid document clearing preference.')
        if values['reading_margin'] not in {'8', '16', '24', '32'} or values['reading_theme'] not in {'system', 'light', 'dark', 'sepia', 'slate'}:
            raise ValueError('Invalid reader appearance preference.')
        validate_reading(values)
        if values['magnifier_zoom'] not in {str(value) for value in range(150, 251, 20)}:
            raise ValueError('Choose magnifier zoom from 150–250%, in 20% steps.')
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

    def save(self, **changes):
        if self.error:
            raise ValueError('Repair or move the preserved preferences file before saving settings.')
        # Retain retired keys for INI compatibility, but keep cards and the saved legacy toggle off.
        changes = dict(changes, show_legacy='false', document_card_overview='false')
        values = dict(self.values, **changes)
        self.validate(values)
        # Session-only associations must never reach disk, including through autosave.
        packages = json.loads(values['remote_packages'])
        retained = [item for item in packages if not item['session_only']]
        if retained != packages:
            values['remote_packages'] = changes['remote_packages'] = json.dumps(retained)
        text = INIFile.updated_text(self.text, {('Mobile', key): value for key, value in changes.items()})
        def check():
            if self.path.is_symlink():
                raise ValueError('Preferences cannot be a symbolic link.')
            current = None
            if self.path.exists():
                with self.path.open('rb') as stream:
                    current = stream.read(65537)
            if current != self.original:
                raise OSError('Preferences changed on disk; reload before saving.')
        data = (b'\xef\xbb\xbf' if self.original and self.original.startswith(b'\xef\xbb\xbf') else b'') + text.encode('utf-8')
        if len(data) > 65536:
            raise ValueError('Preferences exceed the size limit.')
        # Atomic replace works in Android sandboxes which forbid hard links.
        atomic_write_bytes(self.path, data, validate=check)
        self.original, self.text, self.values = data, text, values

