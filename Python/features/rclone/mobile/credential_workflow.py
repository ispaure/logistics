"""Credential workflow capabilities, independent of widgets and application state."""

import asyncio
from typing import Protocol
from .credential_loading import run_credentials
from .service import native_service


class CredentialPresentation(Protocol):
    """Only the host effects needed to publish and display a credential load."""

    def current(self, client, *, navigation=None, generation=None) -> bool: ...
    async def refresh_kinds(self) -> None: ...
    def remotes_loaded(self, names: list[str]) -> None: ...
    def loaded(self, package: str, names: list[str], *, remember: bool) -> None: ...


class CredentialLoadWorkflow:
    """Run loading and refresh stages while retaining the captured host binding."""

    def __init__(self, view: CredentialPresentation):
        self.view = view

    async def load(self, client, request, password, *, generation, current):
        """Run the service against the caller's captured publication scope."""
        result = await run_credentials(
            native_service(client).credentials.load, request, password,
            valid=lambda: current(generation),
        )
        return result if current(result.generation) else None

    async def unlock(
        self,
        client,
        request,
        password,
        *,
        package: str,
        navigation,
        generation,
        remote=None,
        identity=None,
    ):
        """Load a retained package, verify its requested connection, then display it."""
        def current(generation):
            return self.view.current(client, navigation=navigation, generation=generation)

        result = await self.load(
            client, request, password, generation=generation, current=current
        )
        if result is None:
            return None
        await self.view.refresh_kinds()
        if not current(result.generation):
            return None
        names = list(result.remotes)
        # Publication is already committed. Reflect the actual loaded remotes
        # even when this package cannot resume the requested folder connection.
        self.view.remotes_loaded(names)
        if not current(result.generation):
            return None
        if (
            remote is not None
            and identity is not None
            and hasattr(client, "resolve_remote")
        ):
            remote = client.resolve_remote(remote, identity)
        if remote is not None and (
            remote not in names
            or (
                identity is not None
                and await asyncio.to_thread(client.connection_identity, remote)
                != identity
            )
        ):
            raise ValueError("This ZIP does not match the folder connection.")
        if not current(result.generation):
            return None
        self.view.loaded(package, names, remember=request.remember)
        return result
