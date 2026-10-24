"""Resolve a library edit before returning to the retained note browser."""


def attach_return(app, library, owner):
    if owner is None:
        return
    workflow = owner._provider_markdown
    if workflow is None:
        return
    path = library.path
    destination = library.destination

    async def return_to_library():
        from mobile.document_dialogs import DocumentDialog
        if not library.valid() or owner.session.id not in app.workspace.sessions:
            return
        try:
            await workflow.flush()
        except ValueError as error:
            owner.crypt_title.text = str(error)
            return
        if owner.private_dirty():
            choice = await app.main_window.dialog(DocumentDialog(
                'Save changes before returning?', 'Save this note or discard its unsaved changes.',
                discard_label='Discard changes'))
            if not library.valid() or owner.session.id not in app.workspace.sessions:
                return
            if choice == 'save':
                await owner.save_crypt()
                if owner.private_dirty():
                    return
            elif choice != 'discard':
                return
        if not app.private_sessions.close(owner.session.id, discard=True):
            return
        library.present(destination=destination)
        await library.open_note(path, remember=False)

    workflow.action_items = [item for item in workflow.action_items if item[0] != 'Return to Notes Library']
    workflow.action_items.insert(0, ('Return to Notes Library', return_to_library))
    workflow.menu_state = None
    workflow.refresh_controls()
