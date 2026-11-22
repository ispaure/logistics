"""Bounded rmdoc archives, opaque-member preservation and notebook page operations."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from copy import deepcopy
from dataclasses import dataclass, field
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import time
from tempfile import TemporaryDirectory
from uuid import uuid4
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED, BadZipFile

from .ink import InkPage
from commonUtils.runtime.operations import check_cancelled
from commonUtils.runtime.streams import iter_chunks

# Android and some Android Python builds identify themselves differently.
IS_ANDROID = sys.platform == 'android' or hasattr(sys, 'getandroidapilevel')
MAX_ARCHIVE = (256 if IS_ANDROID else 512) * 1024 * 1024
STREAMED_PDF_THRESHOLD = 256 * 1024 * 1024
STREAMED_PDF_MAX_ARCHIVE = 512 * 1024 * 1024
STREAMED_PDF_SIDECAR_LIMIT = 64 * 1024 * 1024
TABLET_MAX_ARCHIVE = 128 * 1024 * 1024
DESKTOP_MAX_ARCHIVE = 2 * 1024 * 1024 * 1024
MAX_EXPANDED = 256 * 1024 * 1024
MAX_MEMBERS = 65536


class StreamedPDFUnavailable(ValueError):
    """A valid archive may require the ordinary in-memory editor path."""


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


def read_archive(data, *, max_bytes=MAX_ARCHIVE):
    if len(data) > max_bytes:
        raise ValueError(f'RMDOC imports are limited to {max_bytes // (1024 * 1024)} MiB compressed.')
    return _read_zip_members(BytesIO(data), max_bytes)


def _read_zip_members(stream, max_bytes, *, pdf_path=None):
    members = {}
    seen = set()
    try:
        with ZipFile(stream) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_MEMBERS or sum(i.file_size for i in infos) > max(MAX_EXPANDED, max_bytes):
                raise ValueError('RMDOC archive exceeds the expanded size/member limit.')
            pdf_name = None
            if pdf_path is not None:
                roots = [info.filename[:-8] for info in infos if '/' not in info.filename
                         and info.filename.endswith('.content')]
                if len(roots) != 1:
                    raise ValueError('Choose an archive containing exactly one reMarkable document.')
                pdf_name = roots[0] + '.pdf'
                if not any(info.filename == pdf_name and not info.is_dir() for info in infos):
                    raise StreamedPDFUnavailable('Streaming requires an embedded PDF.')
                if sum(info.file_size for info in infos if info.filename != pdf_name) > STREAMED_PDF_SIDECAR_LIMIT:
                    raise StreamedPDFUnavailable('Streamed PDF notebooks allow up to 64 MiB of other expanded data.')
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
                    if name == pdf_name:
                        with archive.open(info) as source, pdf_path.open('xb') as output:
                            for chunk in iter_chunks(source):
                                output.write(chunk)
                        members[name] = pdf_path
                    else:
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
    recovered_ink: bytes | None = None


class Notebook:
    def __init__(self, members, doc_id, content, metadata, pages, *, max_bytes=MAX_ARCHIVE):
        self.max_bytes = max_bytes
        self.members, self.id = members, doc_id
        self.content, self.metadata, self.pages = content, metadata, pages
        self.structure_dirty = False
        self.metadata_dirty = False
        self._pdf_workspace = None

    @property
    def large_pdf_view(self):
        return self._pdf_workspace is not None

    def close_large_pdf(self):
        if self._pdf_workspace is not None:
            self._pdf_workspace.cleanup()

    @classmethod
    def new(cls, name='Notebook', *, template=None, paper_format='pro', max_bytes=MAX_ARCHIVE):
        identity = str(uuid4())
        result = cls({}, identity,
            dict(fileType='notebook', formatVersion=1, pageCount=1, pages=[],
                 lineHeight=-1, margins=100, textScale=1, orientation='portrait'),
            dict(visibleName=name, type='DocumentType', parent='', version=1,
                 deleted=False, pinned=False, synced=False, modified=True, lastOpenedPage=0), [], max_bytes=max_bytes)
        result.add_page()
        result.metadata_dirty = True
        if template is not None:
            from .templates import select
            select(result, 0, template, paper_format, True, lock_size=True)
        return result

    @classmethod
    def read(cls, data, *, max_bytes=MAX_ARCHIVE):
        return cls._from_members(read_archive(data, max_bytes=max_bytes), max_bytes=max_bytes)

    @classmethod
    def read_large_pdf(cls, stream, directory):
        """Extract the dominant PDF member of a local archive in bounded reads."""
        if stream.seek(0, 2) > STREAMED_PDF_MAX_ARCHIVE:
            raise ValueError('Streamed PDF notebooks are limited to 512 MiB compressed.')
        stream.seek(0)
        workspace = TemporaryDirectory(prefix='notebook-pdf-', dir=directory)
        try:
            target = Path(workspace.name) / 'background.pdf'
            members = _read_zip_members(stream, STREAMED_PDF_MAX_ARCHIVE, pdf_path=target)
            book = cls._from_members(members, max_bytes=STREAMED_PDF_MAX_ARCHIVE)
            if book.content.get('fileType') != 'pdf':
                raise StreamedPDFUnavailable('Streaming requires a PDF-backed notebook.')
            from pypdf import PdfReader
            with target.open('rb') as source:
                if PdfReader(source).is_encrypted:
                    raise StreamedPDFUnavailable('Password-protected PDFs require the ordinary notebook editor.')
            book._pdf_workspace = workspace
            return book
        except BaseException:
            workspace.cleanup()
            raise

    @classmethod
    def _from_members(cls, members, *, max_bytes):
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
            if not records:
                raise ValueError('Notebooks must contain at least one page with an explicit page ID.')
            pages = [Page(identifier(r['id']), deepcopy(r),
                r.get('template', {}).get('value', templates[i] if i < len(templates) else 'Blank'))
                for i, r in enumerate(records)]
            if any(not isinstance(p.template, str) or len(p.template) > 512
                   or any(ord(c) < 32 or c in '\x85\u2028\u2029' for c in p.template) for p in pages):
                raise ValueError('Invalid notebook page template reference.')
            if len({p.id for p in pages}) != len(pages):
                raise ValueError('Duplicate notebook page identifiers.')
        except (KeyError, TypeError, AttributeError, UnicodeError, json.JSONDecodeError) as error:
            raise ValueError('Malformed RMDOC page metadata.') from error
        return cls(members, identity, content, metadata, pages, max_bytes=max_bytes)

    @property
    def name(self):
        return self.metadata.get('visibleName', 'Notebook')

    def page(self, index):
        page = self.pages[index]
        if page.ink is None:
            raw = self.unloaded_ink(page)
            page.ink = InkPage.read(raw) if raw is not None else InkPage.blank()
        return page.ink

    def unloaded_ink(self, page):
        if page.recovered_ink is not None:
            return page.recovered_ink
        return self.members.get(f'{self.id}/{page.id}.rm')

    def add_page(self, at=None):
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
        # Original custom template artwork is document-level, unlike page sidecars.
        artwork = original.template + '.template'
        from .templates import same_artwork
        if (artwork in source.members and artwork in self.members
                and not same_artwork(self.members[artwork], source.members[artwork])):
            raise ValueError('This template name has different artwork in the destination notebook.')
        self.members.update(staged)
        if artwork in source.members and artwork not in self.members:
            self.members[artwork] = source.members[artwork]
        page = Page(identity, record, original.template)
        self.pages.insert(at, page)
        self.structure_dirty = True
        return page

    def _archive_members(self):
        members = dict(self.members)
        content, metadata = deepcopy(self.content), deepcopy(self.metadata)
        changed = self.structure_dirty or self.metadata_dirty
        for page in self.pages:
            raw = page.ink.to_bytes() if page.ink is not None else page.recovered_ink
            if raw is not None:
                path = f'{self.id}/{page.id}.rm'
                if members.get(path) != raw:
                    members[path] = raw
                    changed = True
        if self.structure_dirty:
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
        expanded = sum(data.stat().st_size if isinstance(data, Path) else len(data) for data in members.values())
        if len(members) > MAX_MEMBERS or expanded > max(MAX_EXPANDED, self.max_bytes):
            raise ValueError('Notebook exceeds the archive size/member limit.')
        return members

    def to_bytes(self):
        if self.large_pdf_view:
            raise ValueError('Use Save to write a streamed PDF notebook.')
        output = BytesIO()
        with ZipFile(output, 'w', compression=ZIP_DEFLATED) as archive:
            for name, data in self._archive_members().items():
                archive.writestr(name, data)
        data = output.getvalue()
        if len(data) > self.max_bytes:
            raise ValueError(f'Export exceeds the {self.max_bytes // (1024 * 1024)} MiB compressed limit.')
        return data

    def write_large_archive(self, stream, *, cancelled=lambda: False):
        """Write and verify a staged ZIP while keeping its PDF file-backed."""
        if not self.large_pdf_view:
            raise ValueError('This notebook does not have a streamed PDF.')
        members = self._archive_members()
        if sum(len(data) for data in members.values() if not isinstance(data, Path)) > STREAMED_PDF_SIDECAR_LIMIT:
            raise ValueError('Streamed PDF notebooks allow up to 64 MiB of other expanded data.')
        pdf_hash = sha256()
        with ZipFile(stream, 'w', compression=ZIP_DEFLATED) as archive:
            for name, data in members.items():
                check_cancelled(cancelled)
                if isinstance(data, Path):
                    # PDF streams are usually compressed already. Store the
                    # backing file so saving ink does not recompress it.
                    with data.open('rb') as source, archive.open(ZipInfo(name), 'w') as target:
                        for chunk in iter_chunks(source, cancelled=cancelled):
                            pdf_hash.update(chunk)
                            target.write(chunk)
                else:
                    archive.writestr(name, data)
        if stream.tell() > self.max_bytes:
            raise ValueError(f'Export exceeds the {self.max_bytes // (1024 * 1024)} MiB compressed limit.')
        with ZipFile(stream) as archive:
            if archive.namelist() != list(members):
                raise ValueError('Notebook archive members did not verify.')
            for name, expected in members.items():
                check_cancelled(cancelled)
                if isinstance(expected, Path):
                    received = sha256()
                    with archive.open(name) as source:
                        for chunk in iter_chunks(source, cancelled=cancelled):
                            received.update(chunk)
                    matches = received.digest() == pdf_hash.digest()
                else:
                    matches = archive.read(name) == expected
                if not matches:
                    raise ValueError('Notebook archive contents did not verify.')
