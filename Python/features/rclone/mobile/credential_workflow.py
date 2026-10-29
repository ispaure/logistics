"""Credential workflow capabilities, independent of widgets and application state."""

import asyncio
from typing import Protocol
from .credential_loading import run_credentials
from .service import native_service


class CredentialPresentation(Protocol):
    """Only the host effects needed to publish and display a credential load."""

    def current(self, client, *, navigation=None, generation=None) -> bool: ...
    def prepare_publication(self) -> bool: ...
    async def refresh_kinds(self) -> None: ...
    def remotes_loaded(self, names: list[str]) -> None: ...
    def loaded(self, package: str, names: list[str], *, remember: bool) -> None: ...


class CredentialLoadWorkflow:
    """Run loading and refresh stages while retaining the captured host binding."""

    def __init__(self, view: CredentialPresentation):
        self.view = view

    async def load(self, client, request, password, *, navigation, generation):
        def current():
            return self.view.current(
                client, navigation=navigation, generation=generation
            )

        result = await run_credentials(
            native_service(client).credentials.load, request, password, valid=current
        )
        generation = result.generation
        if not current():
            return None
        await self.view.refresh_kinds()
        if not current():
            return None
        return result

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
        result = await self.load(
            client, request, password, navigation=navigation, generation=generation
        )
        if result is None:
            return None
        names = list(result.remotes)
        # Publication is already committed. Reflect the actual loaded remotes
        # even when this package cannot resume the requested folder connection.
        self.view.remotes_loaded(names)
        if not self.view.current(
            client, navigation=navigation, generation=result.generation
        ):
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
        if not self.view.current(
            client, navigation=navigation, generation=result.generation
        ):
            return None
        self.view.loaded(package, names, remember=request.remember)
        return result
