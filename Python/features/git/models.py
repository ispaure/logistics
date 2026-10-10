"""Qt-independent structured Git output. Paths retain their exact spelling."""
from dataclasses import dataclass, field
import os


@dataclass(frozen=True)
class Change:
    path: str
    index: str
    worktree: str
    original_path: str | None = None
    submodule: str = 'N...'
    conflict: bool = False

    @property
    def staged(self):
        return self.index not in ('.', '?') and not self.conflict

    @property
    def unstaged(self):
        return self.worktree != '.' or self.index == '?' or self.conflict


@dataclass
class Status:
    branch: str = ''
    oid: str = ''
    upstream: str = ''
    ahead: int = 0
    behind: int = 0
    changes: list[Change] = field(default_factory=list)


def parse_status(data: bytes) -> Status:
    status = Status()
    records = iter(data.split(b'\0'))
    for record in records:
        if not record:
            continue
        if record.startswith(b'# '):
            key, _, value = record[2:].partition(b' ')
            text = value.decode('utf-8', 'replace')
            if key == b'branch.head': status.branch = text
            elif key == b'branch.oid': status.oid = text
            elif key == b'branch.upstream': status.upstream = text
            elif key == b'branch.ab':
                ahead, behind = text.split()
                status.ahead, status.behind = int(ahead), abs(int(behind))
            continue
        kind = record[:1]
        if kind in (b'1', b'2', b'u'):
            fields = record.split(b' ', {b'1': 8, b'2': 9, b'u': 10}[kind])
            xy = fields[1].decode('ascii')
            old = os.fsdecode(next(records)) if kind == b'2' else None
            status.changes.append(Change(os.fsdecode(fields[-1]), xy[0], xy[1], old,
                                         fields[2].decode('ascii'), kind == b'u'))
        elif kind == b'?':
            status.changes.append(Change(os.fsdecode(record[2:]), '?', '?'))
    return status


@dataclass(frozen=True)
class Commit:
    oid: str
    parents: tuple[str, ...]
    author: str
    date: str
    subject: str
    decorations: str = ''


def parse_log(data: bytes) -> list[Commit]:
    # Each field is NUL-delimited; Git adds a newline between formatted records.
    fields = data.split(b'\0')
    commits = []
    for offset in range(0, len(fields) - 6, 7):
        oid, parents, author, date, subject, decorations = fields[offset:offset + 6]
        commits.append(Commit(oid.strip().decode('ascii'), tuple(parents.decode('ascii').split()),
                              author.decode('utf-8', 'replace'), date.decode('ascii'),
                              subject.decode('utf-8', 'replace'), decorations.decode('utf-8', 'replace')))
    return commits


@dataclass(frozen=True)
class Ref:
    name: str
    oid: str
    upstream: str = ''
    current: bool = False


def parse_refs(data: bytes) -> list[Ref]:
    refs = []
    for record in data.splitlines():
        if not record: continue
        name, oid, upstream, head = record.split(b'\0')
        refs.append(Ref(name.decode('utf-8', 'replace'), oid.decode('ascii'),
                        upstream.decode('utf-8', 'replace'), head == b'*'))
    return refs


@dataclass(frozen=True)
class TreeEntry:
    mode: str
    kind: str
    oid: str
    path: str


def parse_tree(data: bytes) -> list[TreeEntry]:
    entries = []
    for record in data.split(b'\0'):
        if record:
            metadata, path = record.split(b'\t', 1)
            mode, kind, oid = metadata.decode('ascii').split()
            entries.append(TreeEntry(mode, kind, oid, os.fsdecode(path)))
    return entries
