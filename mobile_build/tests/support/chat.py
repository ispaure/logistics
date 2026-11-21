"""Bounded waits for real deferred chat publications in host tests."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import asyncio


async def wait_for_chat_writes(store):
    """Wait through debounce and executor publication without changing either."""
    async with asyncio.timeout(3):
        while store._pending or store._writes:
            await asyncio.sleep(.005)


def create_chat_app(case, *, root=None):
    """Register chat cleanup before callers initialize or exercise its UI."""
    from mobile_build.tests.support.app import create_app
    app = create_app(case, root=root)

    def dispose_menu():
        controller = app.__dict__.get('_chat_controller')
        menu = getattr(controller, 'chat_actions', None)
        if menu is not None:
            menu.dispose()

    case.addCleanup(dispose_menu)
    return app
