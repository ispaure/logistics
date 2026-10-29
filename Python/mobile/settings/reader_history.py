"""Separate application-wide actions; encrypted state is erasable while locked."""

import asyncio
import toga
from toga.style import Pack


def controls(app, box):
    async def clear(positions):
        title = "Clear all saved positions?" if positions else "Clear all recent files?"
        detail = (
            "Resets saved reading and video positions across all sources and windows. "
            "Open readers will not save their old position again until reopened. Files and bookmarks are kept."
            if positions
            else "Clears recent files for all sources and windows, including locked credentials. "
            "Legacy encrypted reopen references are also removed. Open documents and positions are kept."
        )
        if not await app.main_window.dialog(toga.ConfirmDialog(title, detail)):
            return
        from services.documents.history_controls import (
            clear_saved_positions,
            clear_recent_files,
        )

        try:
            await asyncio.to_thread(
                clear_saved_positions if positions else clear_recent_files,
                app.private_root,
                mobile=True,
            )
            for destination in ("home", "documents"):
                app.refresh_hub(destination)
        except (OSError, ValueError) as error:
            await app.main_window.dialog(
                toga.InfoDialog("Could not finish clearing history", str(error))
            )

    async def positions(widget, **kwargs):
        await clear(True)

    async def recent(widget, **kwargs):
        await clear(False)

    box.add(
        toga.Button(
            "Clear all saved positions…", on_press=positions, style=Pack(height=48)
        )
    )
    box.add(
        toga.Button("Clear all recent files…", on_press=recent, style=Pack(height=48))
    )
    from commonUtils.ui.native.password_input import PasswordInput

    password = PasswordInput(
        placeholder="Previous credential ZIP password", style=Pack(height=48)
    )
    migration = toga.Box(style=Pack(direction="column"))

    async def restore(widget, **kwargs):
        secret = password.value
        password.value = ""
        try:
            from services.documents.state_migration import migrate

            result = await asyncio.to_thread(migrate, app.private_root, secret, app=app)
            manager = getattr(app, "credential_document_lists", None)
            if manager is not None:
                manager.forget_memory()
                manager.refresh()
            await app.main_window.dialog(
                toga.InfoDialog(
                    "Reader history migration",
                    f"Migrated {result['migrated']} records. Preserved {result['preserved']} records that could not be migrated. "
                    "Reopen affected readers to restore their saved positions.",
                )
            )
        except (OSError, ValueError) as error:
            await app.main_window.dialog(
                toga.InfoDialog("History was preserved", str(error))
            )
        finally:
            secret = None

    migration.add(
        toga.Label(
            "After changing the ZIP password: unlock the updated ZIP, then enter its previous password. "
            "Unmatched or unreadable records are preserved.",
            style=Pack(font_size=12),
        )
    )
    migration.add(password)
    migration.add(
        toga.Button(
            "Migrate protected reader history…", on_press=restore, style=Pack(height=48)
        )
    )
    box.add(migration)
