"""Canvas command shapes and host-independent notebook responses.

The bridge consumes an ordered envelope. Hosts validate its action inside their
error/acknowledgement boundary so a malformed action cannot strand the JS queue.
Model validation remains authoritative for page bounds and native ink values.
"""
import json
import math

MODEL_COMMANDS = frozenset({
    'page', 'stroke', 'add-layer', 'layer-visible', 'transform', 'erase',
    'add-page', 'duplicate-page', 'delete-page', 'move-page', 'rename', 'undo', 'redo',
})
HOST_COMMANDS = frozenset({
    'save', 'save-as', 'export', 'transfer', 'library', 'show-in-folder', 'delete-file',
})


def validate_action(action):
    """Reject malformed commands before mutation or a native action begins."""
    if not isinstance(action, dict) or not isinstance(action.get('op'), str):
        raise ValueError('Invalid notebook command.')
    op = action['op']
    if op not in MODEL_COMMANDS | HOST_COMMANDS:
        raise ValueError('Unknown notebook command.')
    required = {
        'page': {'index': int}, 'move-page': {'index': int},
        'stroke': {'points': list}, 'add-layer': {'name': str},
        'rename': {'name': str}, 'layer-visible': {'layer': str, 'visible': bool},
        'erase': {'ids': list}, 'transform': {'ids': list},
    }.get(op, {})
    if any(type(action.get(key)) is not kind for key, kind in required.items()):
        raise ValueError('Invalid ' + op + ' command fields.')
    if op in {'erase', 'transform'}:
        ids = action['ids']
        if len(ids) > 100_000 or any(not isinstance(value, str) for value in ids):
            raise ValueError('Invalid stroke selection.')
    if op == 'transform':
        if any(type(action.get(key)) not in (int, float) or not math.isfinite(action[key])
               for key in ('dx', 'dy')):
            raise ValueError('Invalid stroke movement.')
    return op


def save_status(document):
    if document is None:
        return 'Saved on this device. Export a copy to share.'
    if document.dirty:
        return 'Unsaved changes'
    if document.resource is None and document.recovery is None:
        return 'Not saved yet'
    return 'Saved'


def document_state(editor, document):
    state = editor.state()
    state.update(save_status=save_status(document),
                 read_only=bool(document and not document.writable),
                 has_source=bool(document and document.resource))
    state['can_delete'] = document is not None and not state['read_only']
    return state


def update_script(state, error=''):
    return 'window.notebookUpdate(' + json.dumps(state, allow_nan=False) + ',' + json.dumps(error) + ')'


def stroke_script(editor, document):
    stroke = editor.notebook.page(editor.index).strokes[-1].payload()
    return ('window.notebookStrokeUpdate(' + json.dumps(stroke, allow_nan=False)
            + ',' + json.dumps(save_status(document)) + ')')
