"""UI-independent shared/mixed values and explicit pending metadata patches."""

from dataclasses import dataclass


@dataclass
class FieldEdit:
    originals: tuple[str, ...]
    baseline: str
    pending: str | None = None

    @property
    def mixed(self):
        return any(value != self.originals[0] for value in self.originals[1:])

    @property
    def changed(self):
        return self.pending is not None and (self.mixed or self.pending != self.baseline)

    def edit(self, value):
        self.pending = value if self.mixed or value != self.baseline else None


class MetadataEditState:
    def __init__(self):
        self.fields: dict[str, FieldEdit] = {}

    def reset(self, documents, fields):
        if not documents:
            raise ValueError('No comic metadata to edit')
        entries = {}
        for field in fields:
            originals = tuple(values[field] for values in documents)
            shared = all(value == originals[0] for value in originals)
            entries[field] = FieldEdit(originals, originals[0] if shared else '')
        self.fields = entries

    def changes(self):
        return {name: entry.pending for name, entry in self.fields.items() if entry.changed}

    def revert(self, field):
        self.fields[field].pending = None
