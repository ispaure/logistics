"""Bounded copy-record migration, optimistic concurrency and atomic persistence."""

import json
import os
from pathlib import Path
from commonUtils.persistence import atomic_write_bytes
from .models import CopyMapping, MAX_COPIES

MAX_RECORD_BYTES = 4 * 1024 * 1024


class CopyRecords:
    def __init__(self, root, guard):
        self.root = Path(root)
        if not self.root.is_absolute() or self.root.is_symlink():
            raise ValueError("Transfers require private storage.")
        self.path = self.root / "mirror-jobs.json"
        self.jobs, self.error = {}, ""
        self.original = None
        self.guard = guard
        try:
            if self.path.exists():
                if (
                    self.path.is_symlink()
                    or self.path.stat().st_size > MAX_RECORD_BYTES
                ):
                    raise ValueError("Invalid transfer records.")
                with self.path.open("rb") as stream:
                    self.original = stream.read(MAX_RECORD_BYTES + 1)
                if len(self.original) > MAX_RECORD_BYTES:
                    raise ValueError("Invalid transfer records.")
                value = json.loads(self.original)
                if not isinstance(value, dict) or value.get("schema") not in (3, 4):
                    raise ValueError("Invalid transfer records.")
                if set(value) != {"schema", "jobs"}:
                    raise ValueError("Invalid transfer records.")
                if (
                    not isinstance(value["jobs"], list)
                    or len(value["jobs"]) > MAX_COPIES
                ):
                    raise ValueError("Invalid transfer records.")
                for job in value["jobs"]:
                    job = dict(job)
                    if value["schema"] == 3:
                        job.pop("baseline", None)
                    job = CopyMapping.from_record(job).to_record()
                    if job["id"] in self.jobs:
                        raise ValueError("Duplicate local copy.")
                    self.jobs[job["id"]] = job
        except (OSError, ValueError, TypeError, KeyError):
            self.jobs = {}
            self.error = "Transfer records could not be restored; the original file was preserved."

    def save(self):
        if self.error or self.path.is_symlink():
            raise ValueError(self.error or "Transfer records cannot be linked.")
        if len(self.jobs) > MAX_COPIES:
            raise ValueError(
                f"Transfer records exceed the local copy limit ({MAX_COPIES})."
            )
        jobs = []
        for key, record in self.jobs.items():
            mapping = CopyMapping.from_record(record)
            if key != mapping.id:
                raise ValueError("Local copy record key does not match its identifier.")
            jobs.append(mapping.to_record())
        data = json.dumps(
            {"schema": 4, "jobs": jobs}, ensure_ascii=False, allow_nan=False
        ).encode("utf-8")
        if len(data) > MAX_RECORD_BYTES:
            raise ValueError("Transfer records exceed the size limit.")
        atomic_write_bytes(self.path, data, validate=self.check_records)
        self.original = data
        descriptor = os.open(self.path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def check_records(self):
        self.guard(self.path)
        current = None
        if self.path.exists():
            with self.path.open("rb") as stream:
                current = stream.read(MAX_RECORD_BYTES + 1)
        if current != self.original:
            raise OSError(
                "Local copy records changed; reopen Logistics before transferring again."
            )
