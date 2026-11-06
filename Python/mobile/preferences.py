"""Mobile-owned INI preferences in an explicitly supplied private directory."""
from configparser import Error
import json
from pathlib import Path

from commonUtils.formats.iniType import INIFile
from commonUtils.persistence import atomic_write_bytes
from .preference_schema import DEFAULTS, validate as validate_preferences


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
                # Seed each new category from the old shared size only when absent.
                for key in ('markdown_font_size', 'text_font_size', 'epub_font_size'):
                    if not parser.has_option('Mobile', key):
                        self.values[key] = self.values['font_size']
                self.validate(self.values)
                if not parser.has_option('Mobile', 'notes_library_migrated'):
                    disabled = set(json.loads(self.values['disabled_features']))
                    if 'text_editor' in disabled:
                        disabled.add('notes_library')
                    self.save(disabled_features=json.dumps(sorted(disabled)), notes_library_migrated='true')
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
        validate_preferences(values)

    def save(self, **changes):
        if self.error:
            raise ValueError('Repair or move the preserved preferences file before saving settings.')
        # Retain retired keys for INI compatibility, but keep cards and the saved legacy toggle off.
        changes = dict(changes, show_legacy='false', document_card_overview='false', notes_library_migrated='true')
        for key in ('markdown_font_size', 'text_font_size', 'epub_font_size'):
            changes.setdefault(key, self.values[key])
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

