"""Image file navigation through the existing mobile document-session manager."""
import asyncio
from features.images.document import adjacent_image


def install(owner, view):
    from mobile.control_icons import icon_button
    store = view._crypt_reader_store
    provider = getattr(store, 'provider', None) or getattr(store, 'resource', None)
    reader = view.crypt_reader
    buttons = []

    busy = False

    async def move(direction):
        nonlocal busy
        if busy:
            return
        busy = True
        enabled = [button.enabled for button in buttons]
        for button in buttons:
            button.enabled = False
        try:
            await switch(direction)
        finally:
            busy = False
            for button, available in zip(buttons, enabled):
                button.enabled = available

    async def switch(direction):
        if owner.cloud_busy or owner.crypt_reader is not reader or provider is None:
            return
        token = owner.workspace.token(owner.session.id)
        try:
            rows = await asyncio.to_thread(provider.list, reader.key.rpartition('/')[0])
            if (not owner.active_host or owner.crypt_reader is not reader
                    or not owner.workspace.accepts(token) or owner.manager.active is not owner):
                return
            target = adjacent_image(rows, reader.key, direction)
            if target is not None and await owner.manager.open(store, target, destination=owner.presentation_destination):
                active = owner.manager.active
                if (active is not None and active is not owner and active.crypt_reader is not None
                        and active.session.resource == owner.manager.identity(store, target)):
                    owner.manager.close(owner.session.id)
        except Exception as error:
            if owner.crypt_reader is reader:
                owner.crypt_title.text = 'Cannot open neighboring image: ' + str(error)[:200]

    async def previous(widget=None, **kwargs):
        await move(-1)

    async def following(widget=None, **kwargs):
        await move(1)

    buttons.extend([icon_button('back', 'Previous image', on_press=previous),
                    icon_button('forward', 'Next image', on_press=following)])
    for button in buttons:
        button.enabled = False
    return buttons


async def refresh(owner):
    reader = owner.crypt_reader
    store = owner._crypt_reader_store
    provider = getattr(store, 'provider', None) or getattr(store, 'resource', None)
    if provider is None:
        return
    token = owner.workspace.token(owner.session.id)
    try:
        rows = await asyncio.to_thread(provider.list, reader.key.rpartition('/')[0])
    except Exception:
        return
    if owner.active_host and owner.crypt_reader is reader and owner.workspace.accepts(token):
        for button, direction in zip(owner.image_file_buttons, (-1, 1)):
            button.enabled = adjacent_image(rows, reader.key, direction) is not None
