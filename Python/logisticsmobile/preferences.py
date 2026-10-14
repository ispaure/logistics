"""Mobile-owned INI preferences in an explicitly supplied private directory."""
from configparser import Error
from pathlib import Path

from commonUtils.formats.iniType import INIFile
from commonUtils.persistence import atomic_write_bytes

DEFAULTS = {'font_size': '16', 'restore_last_document': 'true', 'last_document': '',
            'reading_margin': '16', 'reading_theme': 'system'}


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
                    if parser.has_option('Mobile', key):
                        self.values[key] = parser['Mobile'][key]
                self.validate(self.values)
        except (OSError, ValueError, UnicodeError, Error) as error:
            self.error = 'Preferences were preserved; using defaults. ' + str(error)
            self.values = dict(DEFAULTS)
        return self.values

    @staticmethod
    def validate(values):
        if values.keys() != DEFAULTS.keys():
            raise ValueError('Unknown mobile preference.')
        if values['font_size'] not in {'12', '14', '16', '18', '20', '24', '28', '32'}:
            raise ValueError('Choose a supported font size.')
        if values['restore_last_document'] not in {'true', 'false'}:
            raise ValueError('Invalid document restore preference.')
        if values['reading_margin'] not in {'8', '16', '24', '32'} or values['reading_theme'] not in {'system', 'light', 'dark'}:
            raise ValueError('Invalid reader appearance preference.')
        key = values['last_document']
        if key and (len(key) != 32 or any(c not in '0123456789abcdef' for c in key)):
            raise ValueError('Invalid last-document identity.')

    def save(self, **changes):
        if self.error:
            raise ValueError('Repair or move the preserved preferences file before saving settings.')
        values = dict(self.values, **changes)
        self.validate(values)
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

