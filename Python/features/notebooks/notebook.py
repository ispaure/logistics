"""Bounded rmdoc archives, opaque-member preservation and notebook page operations."""
from copy import deepcopy
from dataclasses import dataclass, field
from io import BytesIO
import json
from pathlib import PurePosixPath
import re
import stat
import time
from uuid import uuid4
from zipfile import ZipFile, ZIP_DEFLATED, BadZipFile

from .ink import InkPage

MAX_ARCHIVE = 32 * 1024 * 1024
MAX_EXPANDED = 128 * 1024 * 1024
MAX_MEMBERS = 4096
MAX_PAGES = 1000


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', value):
        raise ValueError('Invalid document or page identifier.')
    return value


def page_order_key(index):
    """Sequential fractional-index integer keys: ba … bz, caa … czz."""
    digits = 1
    while index >= 26 ** digits:
        index -= 26 ** digits
        digits += 1
    encoded = ''
    for _ in range(digits):
        encoded = chr(97 + index % 26) + encoded
        index //= 26
    return chr(97 + digits) + encoded


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2).encode('utf-8')


def page_index(index, count, *, insertion=False):
    if type(index) is not int or not 0 <= index < count + int(insertion):
        raise ValueError('Page destination is out of range.')
    return index


def read_archive(data):
    if len(data) > MAX_ARCHIVE:
        raise ValueError('RMDOC imports are limited to 32 MiB compressed.')
    members = {}
    seen = set()
    try:
        with ZipFile(BytesIO(data)) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_MEMBERS or sum(i.file_size for i in infos) > MAX_EXPANDED:
                raise ValueError('RMDOC archive exceeds the expanded size/member limit.')
            for info in infos:
                # ZipInfo.filename normalizes Windows separators and truncates
                # NULs; validate the original entry before that transformation.
                name = info.orig_filename
                path = PurePosixPath(name)
                mode = info.external_attr >> 16
                if (name in seen or '\\' in name or ':' in name or '\x00' in name
                        or path.is_absolute() or '..' in path.parts or path.as_posix() != name.rstrip('/')
                        or stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR))
                        or info.flag_bits & 1):
                    raise ValueError('Unsafe, duplicate or encrypted RMDOC archive entry.')
                seen.add(name)
                if info.compress_type not in (0, 8):
                    raise ValueError('RMDOC archives must use stored or deflated ZIP entries.')
                if not info.is_dir():
                    members[name] = archive.read(info)
    except (BadZipFile, RuntimeError, EOFError) as error:
        raise ValueError('Invalid RMDOC ZIP archive.') from error
    return members


@dataclass
class Page:
    id: str
    record: dict = field(default_factory=dict)
    template: str = 'Blank'
    ink: InkPage | None = None


class Notebook:
    def __init__(self, members, doc_id, content, metadata, pages):
        self.members, self.id = members, doc_id
        self.content, self.metadata, self.pages = content, metadata, pages
        self.structure_dirty = False
        self.metadata_dirty = False

    @classmethod
    def new(cls, name='Notebook'):
        identity = str(uuid4())
        result = cls({}, identity,
            dict(fileType='notebook', formatVersion=1, pageCount=1, pages=[],
                 lineHeight=-1, margins=100, textScale=1, orientation='portrait'),
            dict(visibleName=name, type='DocumentType', parent='', version=1,
                 deleted=False, pinned=False, synced=False, modified=True, lastOpenedPage=0), [])
        result.add_page()
        result.metadata_dirty = True
        return result

    @classmethod
    def read(cls, data):
        members = read_archive(data)
        roots = [name[:-8] for name in members if '/' not in name and name.endswith('.content')]
        if len(roots) != 1:
            raise ValueError('Choose an archive containing exactly one reMarkable document.')
        identity = identifier(roots[0])
        try:
            content = json.loads(members[identity + '.content'])
            metadata = json.loads(members[identity + '.metadata'])
            if not isinstance(content, dict) or not isinstance(metadata, dict):
                raise ValueError('Invalid notebook metadata.')
            title = metadata.get('visibleName', 'Notebook')
            if not isinstance(title, str) or len(title) > 512:
                raise ValueError('Invalid or oversized notebook title.')
            if content.get('fileType', '') not in ('', 'notebook', 'pdf'):
                raise ValueError('EPUB-backed RMDOC editing is not supported yet; the original was not changed.')
            if content.get('fileType') == 'pdf' and identity + '.pdf' not in members:
                raise ValueError('The PDF-backed notebook is missing its embedded PDF.')
            templates = members.get(identity + '.pagedata', b'').decode('utf-8').splitlines()
            if 'cPages' in content:
                records = content['cPages']['pages']
                records = [r for r in records if r.get('deleted', {}).get('value', 0) != 1]
                records = sorted(records, key=lambda r: r.get('idx', {}).get('value', ''))
            else:
                records = [dict(id=p) for p in content.get('pages', [])]
                if content.get('fileType') == 'pdf':
                    redirects = content.get('redirectionPageMap')
                    if redirects is None:
                        redirects = list(range(len(records)))
                    if not isinstance(redirects, list) or len(redirects) != len(records):
                        raise ValueError('Invalid PDF page mapping.')
                    for record, redirect in zip(records, redirects):
                        record['redir'] = dict(value=redirect)
            if content.get('fileType') == 'pdf':
                for record in records:
                    redirect = record.get('redir', {}).get('value', -1)
                    if type(redirect) is not int or not -1 <= redirect < 10000:
                        raise ValueError('Invalid PDF page mapping.')
            if not 1 <= len(records) <= MAX_PAGES:
                raise ValueError('Notebooks must contain 1–1000 pages with explicit page IDs.')
            pages = [Page(identifier(r['id']), deepcopy(r),
                r.get('template', {}).get('value', templates[i] if i < len(templates) else 'Blank'))
                for i, r in enumerate(records)]
            if len({p.id for p in pages}) != len(pages):
                raise ValueError('Duplicate notebook page identifiers.')
        except (KeyError, TypeError, AttributeError, UnicodeError, json.JSONDecodeError) as error:
            raise ValueError('Malformed RMDOC page metadata.') from error
        return cls(members, identity, content, metadata, pages)

    @property
    def name(self):
        return self.metadata.get('visibleName', 'Notebook')

    def page(self, index):
        page = self.pages[index]
        if page.ink is None:
            raw = self.members.get(f'{self.id}/{page.id}.rm')
            page.ink = InkPage.read(raw) if raw is not None else InkPage.blank()
        return page.ink

    def add_page(self, at=None):
        if len(self.pages) >= MAX_PAGES:
            raise ValueError('A notebook is limited to 1000 pages.')
        at = len(self.pages) if at is None else page_index(at, len(self.pages), insertion=True)
        page = Page(str(uuid4()), ink=InkPage.blank())
        if self.content.get('fileType') == 'pdf':
            page.record['redir'] = dict(value=-1)
        self.pages.insert(at, page)
        self.structure_dirty = True
        return page

    def delete_page(self, index):
        page_index(index, len(self.pages))
        if len(self.pages) <= 1:
            raise ValueError('Keep at least one page in a notebook.')
        self.structure_dirty = True
        return self.pages.pop(index)

    def move_page(self, index, target):
        page_index(index, len(self.pages))
        page_index(target, len(self.pages))
        self.pages.insert(target, self.pages.pop(index))
        self.structure_dirty = True

    def copy_page(self, source, index, at=None):
        """Copy opaque page data with a fresh ID. Never remove the source first."""
        if len(self.pages) >= MAX_PAGES:
            raise ValueError('A notebook is limited to 1000 pages.')
        page_index(index, len(source.pages))
        at = len(self.pages) if at is None else page_index(at, len(self.pages), insertion=True)
        original = source.pages[index]
        if source is not self and source.content.get('fileType') == 'pdf' and original.record.get('redir', {}).get('value', -1) >= 0:
            raise ValueError('PDF-backed pages can only be duplicated within their notebook.')
        if source is not self and source.page(index).warning:
            raise ValueError('This page contains unsupported objects; cross-notebook copy is disabled to preserve referenced assets.')
        identity = str(uuid4())
        prefix = f'{source.id}/{original.id}'
        staged = {}
        for name, data in source.members.items():
            if name.startswith(prefix + '.') or name.startswith(prefix + '/'):
                staged[f'{self.id}/{identity}' + name[len(prefix):]] = data
        staged[f'{self.id}/{identity}.rm'] = source.page(index).to_bytes()
        record = deepcopy(original.record)
        record['id'] = identity
        # A copied page is inserted in the target, not a redirect into another document.
        if source is not self:
            record.pop('redir', None)
            if self.content.get('fileType') == 'pdf':
                record['redir'] = dict(value=-1)
        record.pop('deleted', None)
        for name, data in source.members.items():
            parts = PurePosixPath(name).parts
            if len(parts) == 2 and parts[0].startswith(source.id + '.') and (parts[1] == original.id or parts[1].startswith(original.id + '.')):
                staged[self.id + parts[0][len(source.id):] + '/' + identity + parts[1][len(original.id):]] = data
        self.members.update(staged)
        page = Page(identity, record, original.template)
        self.pages.insert(at, page)
        self.structure_dirty = True
        return page

    def to_bytes(self):
        members = dict(self.members)
        content, metadata = deepcopy(self.content), deepcopy(self.metadata)
        changed = self.structure_dirty or self.metadata_dirty
        for index, page in enumerate(self.pages):
            if page.ink is not None:
                raw = page.ink.to_bytes()
                path = f'{self.id}/{page.id}.rm'
                if members.get(path) != raw:
                    members[path] = raw
                    changed = True
        baseline = ([r['id'] for r in sorted(content.get('cPages', {}).get('pages', []), key=lambda r: r.get('idx', {}).get('value', '')) if r.get('deleted', {}).get('value', 0) != 1]
                    if 'cPages' in content else content.get('pages', []))
        if self.structure_dirty and baseline != [p.id for p in self.pages]:
            content['pageCount'] = len(self.pages)
            if 'cPages' in content:
                # Keep page records and deleted records; publish fresh ordered indices.
                stamp = '1:' + str(int(time.time() * 1000))
                records = []
                for index, page in enumerate(self.pages):
                    record = deepcopy(page.record)
                    record.update(id=page.id, idx=dict(timestamp=stamp, value=page_order_key(index)))
                    record['template'] = dict(timestamp=stamp, value=page.template)
                    records.append(record)
                active = {p.id for p in self.pages}
                for old in content['cPages']['pages']:
                    if old['id'] not in active:
                        old['deleted'] = dict(timestamp=stamp, value=1)
                        records.append(old)
                content['cPages']['pages'] = records
                content['cPages']['lastOpened'] = dict(timestamp=stamp, value=self.pages[0].id)
            else:
                content['pages'] = [page.id for page in self.pages]
                if content.get('fileType') == 'pdf':
                    content['redirectionPageMap'] = [p.record.get('redir', {}).get('value', -1) for p in self.pages]
            members[self.id + '.pagedata'] = ('\n'.join(p.template for p in self.pages) + '\n').encode()
            members[self.id + '.content'] = json_bytes(content)
        if changed:
            metadata.update(lastModified=str(int(time.time() * 1000)), modified=True, synced=False,
                            version=int(metadata.get('version', 0)) + 1,
                            lastOpenedPage=min(int(metadata.get('lastOpenedPage', 0)), len(self.pages) - 1))
            members[self.id + '.metadata'] = json_bytes(metadata)
        if len(members) > MAX_MEMBERS or sum(map(len, members.values())) > MAX_EXPANDED:
            raise ValueError('Notebook exceeds the archive size/member limit.')
        output = BytesIO()
        with ZipFile(output, 'w', compression=ZIP_DEFLATED) as archive:
            for name, data in members.items():
                archive.writestr(name, data)
        data = output.getvalue()
        if len(data) > MAX_ARCHIVE:
            raise ValueError('Export exceeds the 32 MiB compressed limit.')
        return data
