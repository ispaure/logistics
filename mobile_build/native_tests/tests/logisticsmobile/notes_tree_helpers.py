"""Native Notes tree controls across recycled Android and existing UIKit rows."""
import asyncio
import inspect

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION


def row_paths(owner):
    if getattr(owner.rows, 'recycled', False):
        return {row.path for row in owner.rows.children}
    return {child.vault_path for row in owner.rows.children for child in row.children
            if hasattr(child, 'vault_path')}


def legacy_row(owner, path):
    return next(row for row in owner.rows.children
                if any(getattr(child, 'vault_path', None) == path for child in row.children))


def landing_row(owner, path):
    if getattr(owner.rows, 'recycled', False):
        return next(row.tree_landing for row in owner.rows.children if row.path == path)
    return legacy_row(owner, path).children[1].browser_entry_kind == 'folder_document'


async def native_row_control(owner, path, control='title'):
    rows = owner.rows
    if not getattr(rows, 'recycled', False):
        row = legacy_row(owner, path)
        button = (row.children[-1] if control == 'actions' else row.children[2] if control == 'disclosure'
                  else next(child for child in row.children if hasattr(child, 'vault_path')))
        return button._impl.native
    names = dict(title='getRowTitleView', actions='getRowActionView', disclosure='getRowDisclosureView',
                 icon='getRowIconView')
    native = rows.native_list._impl.native
    for _ in range(500):
        row = next(row for row in rows.children if row.path == path)
        generation = rows.native_list._impl.generation
        view = getattr(native, names[control])(row.index, generation)
        if (view is not None and view.isAttachedToWindow() and view.isShown()
                and view.getWidth() > 0 and view.getHeight() > 0):
            return view
        native.setSelection(row.index)
        await asyncio.sleep(.02)
    raise AssertionError('Native Notes control did not become visible: ' + path + ' / ' + control)


async def activate_entry(owner, path, *, expand=False):
    rows = owner.rows
    if getattr(rows, 'recycled', False):
        control = await native_row_control(owner, path, 'disclosure' if expand else 'title')
        if expand:
            assert control.performClick()
        else:
            row = next(row for row in rows.children if row.path == path)
            native = rows.native_list._impl.native
            assert native.performItemClick(native.getChildAt(row.index - native.getFirstVisiblePosition()),
                                           row.index, native.getItemIdAtPosition(row.index))
        await asyncio.gather(*tuple(rows.tasks))
    else:
        row = legacy_row(owner, path)
        button = row.children[2] if expand else next(child for child in row.children if hasattr(child, 'vault_path'))
        result = button.on_press()
        if inspect.isawaitable(result):
            await result
    task = getattr(owner, 'tree_task', None)
    if task is not None:
        await task
