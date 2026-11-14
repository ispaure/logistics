"""Offline batch receipts for an explicitly captured, stable-ID tablet snapshot.

The caller supplies retrieval and editor checks. This module has no connection
options and never overwrites an export, including unverified interrupted output.
"""
from collections import Counter
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from tempfile import NamedTemporaryFile

from features.notebooks.notebook import MAX_ARCHIVE, Notebook, read_archive
from features.notebooks.remarkable_ssh import UUID
from features.notebooks.remarkable_store import ROOT, UNFILED


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def checkpoint(path, report):
    if 'items' in report:
        report['totals'] = totals(report)
    if path.is_symlink():
        raise ValueError('Receipt files must not be links.')
    with NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        json.dump(report, stream, indent=2, ensure_ascii=False)
        stream.write('\n')
    temporary.replace(path)


def page_sample(count):
    return sorted({0, count // 2, count - 1}) if count else []


def totals(report):
    documents = [row for row in report['items'] if not row['directory']]
    outcomes = dict(Counter(row['outcome'] for row in documents))
    observed = report['metadata_inventory']
    excluded = [row for row in observed if not row['visible']]
    return dict(inventory=len(observed), visible_inventory=len(report['inventory']),
                excluded=len(excluded), exclusions=dict(Counter(row['reason'] for row in excluded)),
                metadata_occurrences=sum(row['occurrences'] for row in observed),
                unidentified_records=report['unidentified_records'],
                folders=len(report['items']) - len(documents),
                documents=len(documents), selected_documents=len(report['document_ids']), outcomes=outcomes,
                reconciled=sum(outcomes.values()) == len(documents) and len(observed) == len(report['items']) + len(excluded))


def run_batch(snapshot, workspace, retrieve, inspect_editor, *, document_ids=()):
    """Process only explicitly selected IDs; an empty selection acquires nothing.

    inspect_editor(path, sampled_pages, receipt) must open a disposable copy and
    record editor_open, page_render and save_reopen separately. Exceptions retain
    earlier phase receipts. Interrupts propagate after the last checkpoint.
    Selection is not authorization to connect: callers own the injected transport.
    """
    document_ids = tuple(document_ids)
    eligible = {key for key, entry in snapshot.entries.items() if not entry.directory}
    if len(set(document_ids)) != len(document_ids) or not set(document_ids) <= eligible:
        raise ValueError('Select distinct visible document IDs from the captured inventory.')
    document_ids = sorted(document_ids)
    workspace = Path(workspace)
    if workspace.is_symlink():
        raise ValueError('Receipt workspace must not be a link.')
    workspace.mkdir(mode=0o700, parents=True, exist_ok=True)
    workspace.chmod(0o700)
    exports = workspace / 'exports'
    if exports.is_symlink():
        raise ValueError('Export directory must not be a link.')
    exports.mkdir(mode=0o700, exist_ok=True)
    entries = [asdict(entry) for key, entry in sorted(snapshot.entries.items()) if key not in (ROOT, UNFILED)]
    for entry in entries:
        if not UUID.fullmatch(entry['id']):
            raise ValueError('Invalid stable document ID.')
    observations = json.loads(json.dumps([asdict(row) for _, row in sorted(snapshot.inventory.items())]))
    if {row['id'] for row in observations if row['visible']} != {row['id'] for row in entries}:
        raise ValueError('Snapshot requires complete per-ID inventory diagnostics.')
    path = workspace / 'manifest.json'
    if path.is_symlink():
        raise ValueError('Receipt must not be a link.')
    if path.exists():
        report = json.loads(path.read_text())
        if (report.get('schema') != 3 or report['inventory'] != entries
                or report['document_ids'] != document_ids
                or report['metadata_inventory'] != observations
                or report['unidentified_records'] != snapshot.unidentified_records):
            raise ValueError('Resume requires the same captured inventory.')
        if [{key: row.get(key) for key in entry} for row, entry in zip(report['items'], entries)] != entries or len(report['items']) != len(entries):
            raise ValueError('Receipt item identity differs from captured inventory.')
    else:
        report = dict(schema=3, inventory=entries, metadata_inventory=observations, document_ids=document_ids,
            unidentified_records=snapshot.unidentified_records,
            items=[dict(entry, outcome='folder' if entry['directory'] else 'untested') for entry in entries],
            scope='Received metadata records; unidentified occurrences cannot be mapped to eligible documents.',
            tablet_acceptance=False, native_picker_acceptance=False)
    for row in report['items']:
        if not row['directory']:
            for key in ('archive', 'editor_open', 'page_render', 'save_reopen', 'error_type', 'original_unchanged', 'page_count', 'file_type', 'sampled_pages'):
                row.pop(key, None)
            row['outcome'] = 'untested' if row['id'] in document_ids else 'not_selected'
    report['totals'] = totals(report)
    checkpoint(path, report)
    for row in report['items']:
        if row['directory'] or row['id'] not in document_ids:
            continue
        target = exports / (row['id'] + '.rmdoc')
        phase = 'retrieval'
        try:
            previous = row.get('retrieval', {})
            if target.is_symlink():
                raise ValueError('Export must not be a link.')
            if target.exists():
                if previous.get('status') != 'passed' or digest(target) != previous.get('sha256'):
                    raise ValueError('Unverified or changed export; preserve it and use a new workspace.')
                row['retrieval'] = dict(previous, reused=True)
            else:
                if previous.get('status') == 'passed':
                    raise ValueError('Previously verified export is missing; use a new workspace.')
                retrieve(row['id'], target)
                target.chmod(0o600)
                row['retrieval'] = dict(status='passed', sha256=digest(target), bytes=target.stat().st_size, reused=False)
            checkpoint(path, report)
            phase = 'archive'
            if target.stat().st_size > MAX_ARCHIVE:
                raise ValueError('Archive exceeds editor import limit.')
            data = target.read_bytes()
            members = read_archive(data)
            row['archive'] = dict(status='passed', members=len(members))
            phase = 'editor_open'
            book = Notebook.read(data)
            row['page_count'] = len(book.pages)
            row['file_type'] = book.content.get('fileType')
            row['sampled_pages'] = page_sample(len(book.pages))
            checkpoint(path, report)
            inspect_editor(target, row['sampled_pages'], row)
            for phase in ('editor_open', 'page_render', 'save_reopen'):
                if row.get(phase, {}).get('status') != 'passed':
                    break
            else:
                phase = 'passed'
            row['outcome'] = phase if phase == 'passed' else phase + '_' + row.get(phase, {}).get('status', 'untested')
        except Exception as error:
            if phase == 'editor_open':
                phase = next((name for name in ('editor_open', 'page_render', 'save_reopen')
                              if row.get(name, {}).get('status') != 'passed'), phase)
            # Raw messages may contain titles, paths or remote details. Retain
            # the exception class only; deeper diagnosis is a private session.
            row['outcome'] = phase + '_failed'
            row['error_type'] = type(error).__name__
            if row.get(phase, {}).get('status') != 'passed':
                row[phase] = dict(status='failed')
            # This is the current reader's explicit unsupported-backing gate.
            # Other ValueErrors (corruption, invalid mappings, etc.) stay failed.
            if (phase == 'editor_open' and isinstance(error, ValueError)
                    and str(error) == 'EPUB-backed RMDOC editing is not supported yet; the original was not changed.'):
                row['editor_open'] = dict(status='unsupported', reason='unsupported_backing_type')
                row['page_render'] = row['save_reopen'] = dict(status='untested', reason='editor_open_unsupported')
                row['outcome'] = 'editor_open_unsupported'
        except BaseException:
            row['outcome'] = 'interrupted'
            checkpoint(path, report)
            raise
        if row.get('retrieval', {}).get('status') == 'passed':
            try:
                row['original_unchanged'] = not target.is_symlink() and target.is_file() and digest(target) == row['retrieval']['sha256']
            except OSError:
                row['original_unchanged'] = False
            if not row['original_unchanged']:
                row['outcome'] = 'source_changed'
        report['totals'] = totals(report)
        checkpoint(path, report)
    return report
