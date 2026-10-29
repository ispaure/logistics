"""Desktop launch modes and outcomes, separate from legacy boolean APIs."""

from dataclasses import dataclass
from enum import Enum


class LaunchMode(Enum):
    PREVIEW = "preview"
    WAIT = "wait"
    INTEGRATED = "integrated"
    TERMINAL = "terminal"

    @classmethod
    def from_legacy(cls, *, query, wait_for_output, integrated):
        if query:
            return cls.PREVIEW
        if wait_for_output:
            return cls.WAIT
        return cls.INTEGRATED if integrated else cls.TERMINAL


class SyncState(Enum):
    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PREVIEW = "preview"


@dataclass(frozen=True)
class SyncOutcome:
    state: SyncState
    preview: dict | None = None

    def legacy_value(self):
        """Historical callers treat an accepted asynchronous launch as True."""
        if self.state is SyncState.PREVIEW:
            return self.preview
        return self.state in (SyncState.STARTED, SyncState.SUCCEEDED)


def transfer_concurrency(source_path) -> int:
    """Preserve the historical single-transfer policy for paths containing -VM.

    This is a source-path naming convention, including parent directories. Keep it
    explicit here so a future configurable policy does not silently change it.
    """
    return 1 if "-VM" in str(source_path) else 10
