"""Folder discovery/detail request state and worker preparation, without Qt."""
from dataclasses import dataclass
from typing import Any
from commonUtils.runtime.operations import check_cancelled


@dataclass
class FolderController:
    refresh_generation: int = 0
    refresh_pending: bool = False
    detail_generation: int = 0
    detail_pending: Any = None

    def discovery_work(self, remotes, locals_, discover):
        generation = self.refresh_generation
        def work(report, cancelled):
            return generation, discover(remote_providers=remotes, local_providers=locals_, cancelled=cancelled)
        return work

    def detail_work(self, entry, features):
        generation = self.detail_generation
        features = tuple(features)
        def work(report, cancelled):
            found = []
            for registered in features:
                check_cancelled(cancelled)
                contribution = registered.contribution
                # A private path names ciphertext; only backend-aware tools may inspect it.
                if getattr(entry.local, 'private', False) and not contribution.supports_private_folders:
                    continue
                if contribution.is_available(entry):
                    actions = None if contribution.create_widget else contribution.get_actions(entry)
                    found.append((contribution, actions))
            check_cancelled(cancelled)
            return generation, entry, found
        return work
