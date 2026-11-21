"""Folder discovery/detail request state and worker preparation, without Qt."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path

from commonUtils.runtime.operations import check_cancelled
from features.contributions import FolderFeatureContribution, RegisteredContribution
from models.folder_entry import FolderEntry


@dataclass(frozen=True, eq=False)
class FolderDetailRequest:
    """The selected workspace root, tools and credential generation for one check."""

    entry: FolderEntry
    features: tuple[RegisteredContribution[FolderFeatureContribution], ...]
    credentials_revoked: Callable[[], bool] | None

    def revoked(self):
        return self.credentials_revoked is not None and self.credentials_revoked()

    def detect(self, _report, cancelled):
        check_cancelled(cancelled)
        if self.revoked():
            return []
        found = []
        for registered in self.features:
            check_cancelled(cancelled)
            contribution = registered.contribution
            # A private path names ciphertext; only backend-aware tools may inspect it.
            if getattr(self.entry.local, 'private', False) and not contribution.supports_private_folders:
                continue
            if contribution.is_available(self.entry):
                actions = None if contribution.create_widget else contribution.get_actions(self.entry)
                found.append((contribution, actions))
        check_cancelled(cancelled)
        return found


@dataclass
class FolderController:
    refresh_generation: int = 0
    refresh_pending: bool = False
    _selected_detail: FolderDetailRequest | None = field(default=None, init=False)
    _running_detail: FolderDetailRequest | None = field(default=None, init=False)

    def discovery_work(self, remotes, locals_, discover):
        generation = self.refresh_generation
        def work(report, cancelled):
            return generation, discover(remote_providers=remotes, local_providers=locals_, cancelled=cancelled)
        return work

    def select_detail(self, entry, features, *, scope, unlock_target):
        self.clear_detail()
        config = (entry.local.connection.context if getattr(entry.local, 'private', False) else
                  entry.remote_context if entry.remote_source == 'rclone' else None)
        config = Path(config) if config is not None else None
        revoked = None
        if config is not None and config.suffix == '.session':
            from features.rclone import session
            revoked = session.revocation_check(config)
        target = unlock_target(entry)
        missing_credentials = scope == 'remote' and entry.remote_source == 'rclone' and entry.remote_context is None
        if target is None and not missing_credentials:
            self._selected_detail = FolderDetailRequest(replace(entry, storage_scope=scope), tuple(features), revoked)
        return target, missing_credentials

    def clear_detail(self):
        self._selected_detail = None

    def start_detail(self):
        if self._running_detail is not None:
            return None
        self._running_detail = self._selected_detail
        return self._running_detail

    def complete_detail(self, unlock_target):
        """Retire the worker and admit a completion only for the selected request."""
        request, self._running_detail = self._running_detail, None
        if request is None or request is not self._selected_detail:
            return None, False
        self.clear_detail()
        return request, request.revoked() or unlock_target(request.entry) is not None
