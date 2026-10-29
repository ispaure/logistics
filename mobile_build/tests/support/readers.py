"""Reusable Logistics readers fixtures; no test cases or discovery side effects."""
import base64
from io import BytesIO
from zipfile import ZipFile


def assert_preview_only_ui(test, owner):
    """Check visible controls and overflow tools, including disabled widgets."""
    def labels(widget):
        yield str(getattr(widget, 'text', ''))
        children = getattr(widget, 'children', ())
        for child in children:
            yield from labels(child)
        content = getattr(widget, 'content', None)
        if content is not None:
            yield from labels(content)
    text = '\n'.join([*labels(owner.crypt_view), *labels(owner.crypt_tools_view),
                      *(label for label, _ in owner.crypt_actions_menu.actions)]).lower()
    for forbidden in ('save', 'download', 'edit metadata', 'discard changes', 'previous comic', 'next comic'):
        test.assertNotIn(forbidden, text)
    actions = {label for label, _ in owner.crypt_actions_menu.actions}
    if owner.crypt_reader.editable:
        expected = {'All documents', 'Show in folder'}
        if owner.crypt_reader.kind in {'.md', '.markdown'}:
            reading = getattr(owner, '_text_menu_state', (False, False))[1]
            expected.add('View source text' if reading else 'View Markdown')
            if reading:
                expected.add('Read aloud…')
                expected.add('Find in this page…')
        if owner.app.adaptive.width() >= 640:
            expected.add('Open beside another document')
        test.assertEqual(actions, expected)
    elif getattr(owner.crypt_reader, 'image_document', False):
        test.assertEqual(actions, {'Fit image', 'All documents', 'Show in folder'})

class RemoteClient:
    supports_streaming = True
    generation = 1

    def __init__(self):
        self.calls = []
        self.text = b'REMOTE_MEMORY_SENTINEL'
        self.files = {'note.txt': self.text}
        self.cached = {}

    def connection_identity(self, remote):
        return 'a' * 64

    def entries(self, remote, path=''):
        self.calls.append(('list', path))
        return [dict(path='note.txt', directory=False, size=len(self.text)),
                dict(path='movie.mp4', directory=False, size=200),
                dict(path='folder', directory=True, size=0)]

    def request(self, action, **values):
        self.calls.append((action, values.get('path')))
        if action == 'remote_cache_close':
            self.cached.pop(values['run'], None)
            return {}
        if action == 'remote_cache_status':
            data = self.cached.get(values['run'], b'')
            return dict(done=len(data), total=len(data), ready=bool(data))
        data = self.cached[values['run']] if action == 'remote_cache_archive' else self.files[values['path']]
        if action == 'remote_cache_open':
            self.cached[values['run']] = data
            return dict(size=len(data), revision='one')
        if action == 'remote_cache_archive':
            data = self.cached[values['run']]
        if action == 'remote_stat':
            return dict(size=len(data), revision='one')
        if action == 'remote_range':
            start = values['offset']
            return dict(data=base64.b64encode(data[start:start+values['count']]).decode())
        if action in {'remote_archive', 'remote_cache_archive'}:
            with ZipFile(BytesIO(data)) as archive:
                if values.get('member'):
                    return dict(data=base64.b64encode(archive.read(values['member'])).decode())
                return [dict(name=row.filename, size=row.file_size, crc=row.CRC, flags=0,
                             directory=row.is_dir()) for row in archive.infolist()]
        raise AssertionError('Unexpected request: ' + action)

    def cancel(self):
        pass
