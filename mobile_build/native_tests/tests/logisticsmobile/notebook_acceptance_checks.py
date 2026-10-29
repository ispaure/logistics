"""Synthetic export/recovery acceptance shared by desktop and installed runtimes."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import errno
from hashlib import sha256
import json
from pathlib import Path
import time
import tracemalloc
from unittest.mock import patch

from features.notebooks.notebook import Notebook, MAX_ARCHIVE, json_bytes, page_order_key
from features.notebooks.ink import TOOLS
from features.notebooks.editor import Editor
from features.notebooks.recovery import Repository
from features.notebooks.storage import NotebookDocument
from services.documents.storage import DocumentResource, local_document_resource
from commonUtils.runtime.resources.local import LocalFiles


def signature(book):
    return [dict(id=page.id, ink=sha256(book.page(i).to_bytes()).hexdigest())
            for i, page in enumerate(book.pages)]


def exercise_storage(root):
    """Fault injection reaches real temporary-file publication, never user data."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    book = Notebook.new('Synthetic hardware acceptance')
    tools = list(TOOLS.values())
    for index in range(36):
        if index:
            book.add_page()
        ink = book.page(index)
        ink.add_layer('Details')
        for stroke in range(12):
            ink.add([[40 + p * 3, 60 + stroke * 80 + p % 7, .2 + p % 4 * .2]
                     for p in range(80)], tool=tools[stroke % len(tools)], color=6,
                    width=1 + stroke % 3, layer=ink.layers[stroke % 2][0])
    tracemalloc.start()
    started = time.monotonic()
    data = book.to_bytes()
    elapsed = time.monotonic() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    book = Notebook.read(data)
    assert len(book.pages) == 36
    assert all(len(book.page(i).strokes) == 12 for i in range(36))
    archive = root / 'acceptance.rmdoc'
    archive.write_bytes(data)
    provider = LocalFiles(root)
    resource = local_document_resource(archive, max_bytes=MAX_ARCHIVE)
    resource.read()
    repository = Repository(root / 'recovery')
    document = NotebookDocument(book, resource=resource, recovery=repository)
    editor = Editor(book, document.checkpoint)
    editor.apply(dict(op='stroke', points=[[900, 1400, .25], [1000, 1450, .8]]))
    edited = signature(book)
    failures = []
    try:
        for code in (errno.ENOSPC, errno.EACCES):
            entries = set(root.iterdir())
            def fail(stream, output, **kwargs):
                output.write(stream.read(32))
                raise OSError(code, 'Synthetic publication failure')
            with patch('commonUtils.runtime.resources.local.copy_stream', side_effect=fail):
                try:
                    document.save()
                except OSError as error:
                    assert error.errno == code
                else:
                    raise AssertionError('Faulted save succeeded')
            assert document.dirty and archive.read_bytes() == data and signature(book) == edited
            assert set(root.iterdir()) == entries, 'Publication left a temporary file'
            failures.append(code)
        try:
            document.save(cancelled=lambda: True)
        except Exception as error:
            from commonUtils.runtime.operations import OperationCancelled
            assert isinstance(error, OperationCancelled), repr(error)
        else:
            raise AssertionError('Cancelled save succeeded')
        assert archive.read_bytes() == data and document.dirty
        try:
            DocumentResource.publish(provider, archive.name, data, max_bytes=MAX_ARCHIVE)
        except FileExistsError:
            pass
        else:
            raise AssertionError('Duplicate destination silently overwritten')
        assert signature(Repository(repository.root).open(document.key)) == edited
        # A failed checkpoint must leave both the in-memory edit and durable
        # manifest at the last successfully acknowledged stroke.
        with patch('features.notebooks.recovery.atomic_write_json', side_effect=OSError(errno.ENOSPC, 'Synthetic manifest failure')):
            try:
                editor.apply(dict(op='erase', ids=[book.page(0).strokes[0].id]))
            except OSError:
                pass
            else:
                raise AssertionError('Faulted checkpoint succeeded')
        assert signature(book) == edited
        assert signature(Repository(repository.root).open(document.key)) == edited
        document.save()
        assert not document.dirty and signature(Notebook.read(archive.read_bytes())) == edited
        modern = Notebook.read(archive.read_bytes())
        modern.content.pop('pages', None)
        modern.content['cPages'] = dict(pages=[dict(id=p.id,
            idx=dict(timestamp='1:1', value=page_order_key(i))) for i, p in enumerate(modern.pages)])
        modern.members[modern.id + '.content'] = json_bytes(modern.content)
        modern.move_page(0, 35)
        modern.copy_page(modern, 0)
        modern.delete_page(1)
        modern_data = modern.to_bytes()
        reread = Notebook.read(modern_data)
        assert [p.id for p in reread.pages] == [p.id for p in modern.pages]
        assert len(reread.pages) == 36 and len(reread.content['cPages']['pages']) == 37
        (root / 'modern.rmdoc').write_bytes(modern_data)
        # Preserve fresh native output for the independent host reader.
        return dict(pages=36, strokes=433, points=34562, export_seconds=elapsed,
                    export_peak_python_bytes=peak, archive_bytes=archive.stat().st_size,
                    archive_sha256=sha256(archive.read_bytes()).hexdigest(),
                    partial_write_errors=failures, cancellation=True, duplicate_refused=True,
                    modern_reorder_copy_delete=True, layers=2, tools=len(tools),
                    recovery_after_failed_checkpoint=True, retry=True,
                    key=document.key, signature=edited)
    finally:
        document.close()


async def exercise_mobile(panel):
    """Run native canvas export commands against failed/cancelled destinations."""
    import asyncio
    from unittest.mock import AsyncMock
    before = signature(panel.editor.notebook)
    document, canvas = panel.document, panel.web
    errors = []
    for failure in (None, OSError(errno.ENOSPC, 'Synthetic full storage'),
                    PermissionError(errno.EACCES, 'Synthetic denied destination')):
        export = AsyncMock(return_value=False, side_effect=failure)
        with patch('commonUtils.ui.native.documents.export_stream', export):
            await panel.perform(dict(op='export'))
        export.assert_awaited_once()
        assert not panel.busy and panel.web is canvas and panel.document is document
        assert signature(panel.editor.notebook) == before
        errors.append('cancelled' if failure is None else failure.errno)
    # A successful separate copy must include every queued model stroke.
    captured = []
    async def destination(app, name, open_source):
        with open_source() as stream:
            captured.append(Notebook.read(stream.read()))
        return True
    with patch('commonUtils.ui.native.documents.export_stream', destination):
        await panel.perform(dict(op='export'))
    assert signature(captured[0]) == before
    await panel.perform(dict(op='stroke', points=[[50, 1500, .3], [75, 1520, .7]]))
    assert len(panel.editor.notebook.page(panel.editor.index).strokes) > 0
    await asyncio.sleep(.1)
    return dict(failures=errors, copy_matches=True, drawing_after_failure=True)


def write_report(path, value):
    Path(path).write_text(json.dumps(value, indent=2))
