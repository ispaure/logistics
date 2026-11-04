"""Native UIKit Notes interaction checks shared by functional and timing probes."""
import asyncio
from unittest.mock import patch

from rubicon.objc import ObjCClass, objc_property
from commonUtils.testing.stages import TestStage
from .notes_tree_helpers import activate_entry, native_row_control

TEST_STAGE = TestStage.EXTENDED


class NotesDragSession(ObjCClass('NSObject')):
    localContext = objc_property(object)
    localDragSession = objc_property(object)


async def check_tree_interactions(owner, report):
    rows = owner.rows
    path = 'Library/Folder/Child 0'
    await activate_entry(owner, path)
    assert owner.path == path + '/Child 0.md'
    owner.sidebar.show_sidebar()
    await activate_entry(owner, path, expand=True)
    assert any(row.path == path + '/Child 0.md' for row in rows.children)
    await activate_entry(owner, path, expand=True)
    assert not any(row.path == path + '/Child 0.md' for row in rows.children)
    title = await native_row_control(owner, path)
    assert title.attributedText is not None
    choices = []

    async def cancel(dialog):
        choices.extend(value for _, value, _ in dialog.choices)
        return 'cancel'

    before = owner.path
    action = await native_row_control(owner, 'Library/Folder/Note 00.md', 'actions')
    with patch.object(owner.view.window, 'dialog', new=cancel):
        action.sendActionsForControlEvents(1 << 6)
        await asyncio.sleep(0)
        await asyncio.gather(*tuple(rows.tasks))
    assert {'rename', 'move', 'copy', 'delete'}.issubset(choices), choices
    assert owner.path == before
    icon = await native_row_control(owner, 'Library/Folder/Note 00.md', 'icon')
    # Resolve the native delegate installed on the visible image. This tests
    # its opaque authorization payload, not a physical drag/drop gesture.
    from toga_iOS.libs import NSIndexPath
    row = next(row for row in rows.children if row.path.endswith('/Note 00.md'))
    table = rows.native_list._impl.native
    cell = table.cellForRowAtIndexPath(NSIndexPath.indexPathForRow(row.index, inSection=0))
    interaction, delegate = cell.tree_drag
    session = NotesDragSession.alloc().init()
    items = delegate.dragInteraction_itemsForBeginningSession_(interaction, session)
    assert len(list(items)) == 1 and str(session.localContext) == owner.file_drag.token
    assert owner.file_drag.source == row.path
    folder_row = next(row for row in rows.children if row.path == path)
    await native_row_control(owner, path)
    folder_cell = table.cellForRowAtIndexPath(NSIndexPath.indexPathForRow(folder_row.index, inSection=0))
    drop_interaction, drop_delegate = folder_cell.tree_drop
    session.localDragSession = session
    try:
        assert drop_delegate.dropInteraction_canHandleSession_(drop_interaction, session)
        proposal = drop_delegate.dropInteraction_sessionDidUpdate_(drop_interaction, session)
        assert int(proposal.operation) == 3
        # Verify the native delegate's authorization/dispatch without changing
        # the fixture between renderer variants or later functional cases.
        with patch.object(rows, 'drop', return_value=True) as dropped:
            drop_delegate.dropInteraction_performDrop_(drop_interaction, session)
            dropped.assert_called_once_with(folder_row)
        session.localContext = 'another-library-token'
        assert not drop_delegate.dropInteraction_canHandleSession_(drop_interaction, session)
    finally:
        session.localDragSession = None
    delegate.dragInteraction_session_didEndWithOperation_(interaction, session, 0)
    assert owner.file_drag.source is None
    assert icon.userInteractionEnabled
    table.scrollToRowAtIndexPath(NSIndexPath.indexPathForRow(44, inSection=0),
                                atScrollPosition=2, animated=False)
    last = await native_row_control(owner, 'Library/Folder/Note 39.md')
    assert str(last.text) == 'Note 39.md' and last.attributedText is None
    owner.dispose()
    assert str(last.text) == '' and last.attributedText is None
    assert not rows.children and rows.closed
    report['cases'].append('uikit_tree_interactions_and_retirement_' + report['interaction_storage'])
