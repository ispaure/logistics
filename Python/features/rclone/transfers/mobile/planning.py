"""Resolve copy proposals without modifying mappings or creating destinations."""

from uuid import uuid4
from services.documents.locations import collection_path
from features.rclone.transfers.scope import pull_name, push_scope
from .models import CopyMapping, MAX_COPIES
from features.rclone.mobile.bridge_protocol import mirror_info


class CopyPlanner:
    def __init__(self, root, jobs, check_name, guard):
        self.root = root
        self.jobs = jobs
        self.check_name = check_name
        self.guard = guard

    def pull(self, client, remote, folder="", *, storage=None) -> CopyMapping:
        """Resolve a proposed copy without writing records or creating a folder."""
        if storage not in (None, "Local", "LocalCrypt"):
            raise ValueError("Choose Local or LocalCrypt.")
        info = mirror_info(client, remote, folder, decrypted=storage == "Local")
        if storage == "LocalCrypt" and not info["crypt"]:
            raise ValueError("LocalCrypt requires a crypt remote with encryption keys.")
        existing = next(
            (
                job
                for job in self.jobs.values()
                if job["remote"] == remote
                and job["identity"] == info["identity"]
                and job["prefix"] == info["prefix"]
                and job["crypt"] == info["crypt"]
            ),
            None,
        )
        if existing is not None:
            return CopyMapping.from_record(existing)
        if len(self.jobs) >= MAX_COPIES:
            raise ValueError(
                f"Remove a local copy mapping before adding another (limit: {MAX_COPIES})."
            )
        target = pull_name(remote, folder, crypt=info["crypt"])
        self.check_name(target, info["crypt"], adopt=True)
        job = CopyMapping(
            id=uuid4().hex,
            remote=remote,
            identity=info["identity"],
            cipher_identity=info["cipher_identity"],
            crypt=info["crypt"],
            prefix=info["prefix"],
            target=target,
        )
        return job

    def push(self, client, local_folder, *, remote=None, specific=False) -> CopyMapping:
        """Infer a new ordinary Push from its local name; mappings retain ownership."""
        target = self.guard(collection_path(self.root) / local_folder)
        if not target.is_dir():
            raise ValueError("Choose an existing local folder.")
        remote, prefix = push_scope(local_folder, remote, specific=specific)
        info = mirror_info(client, remote, prefix, decrypted=True)
        existing = next(
            (
                job
                for job in self.jobs.values()
                if not job["crypt"]
                and job["target"].casefold() == local_folder.casefold()
            ),
            None,
        )
        if existing is not None:
            if (
                existing["remote"] != remote
                or existing["identity"] != info["identity"]
                or existing["prefix"] != info["prefix"]
            ):
                raise ValueError("This local folder belongs to another copy.")
            return CopyMapping.from_record(existing)
        if len(self.jobs) >= MAX_COPIES:
            raise ValueError(
                f"Remove a local copy mapping before adding another (limit: {MAX_COPIES})."
            )
        self.check_name(local_folder, False, adopt=True)
        job = CopyMapping(
            id=uuid4().hex,
            remote=remote,
            identity=info["identity"],
            cipher_identity="",
            crypt=False,
            prefix=info["prefix"],
            target=local_folder,
        )
        return job
