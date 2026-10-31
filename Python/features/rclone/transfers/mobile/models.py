"""Validated copy identity and named transfer outcomes; JSON stays at the boundary."""

from collections.abc import Mapping, Iterator
from dataclasses import dataclass, fields, asdict
from typing import NamedTuple

from commonUtils.runtime.resources.paths import resource_path
from services.identifiers import uuid, digest

MAX_COPIES = 16


@dataclass(frozen=True)
class CopyMapping(Mapping[str, object]):
    id: str
    remote: str
    # Connection identity binds a copy to the account and remote configuration.
    identity: str
    # Cipher identity binds encoded paths to the crypt settings, not the account.
    cipher_identity: str
    crypt: bool
    prefix: str
    target: str

    def __post_init__(self):
        if not uuid(self.id):
            raise ValueError("Invalid local copy identifier.")
        if (
            not isinstance(self.remote, str)
            or not 0 < len(self.remote) <= 80
            or any(ord(char) < 32 for char in self.remote)
        ):
            raise ValueError("Invalid local copy remote name.")
        if not digest(self.identity):
            raise ValueError("Invalid local copy connection identity.")
        if type(self.crypt) is not bool:
            raise ValueError("Invalid local copy storage kind.")
        if not (
            digest(self.cipher_identity) if self.crypt else self.cipher_identity == ""
        ):
            raise ValueError("Invalid local copy cipher identity.")
        if (
            not isinstance(self.prefix, str)
            or resource_path(self.prefix) != self.prefix
        ):
            raise ValueError("Invalid local copy prefix.")
        if (
            not isinstance(self.target, str)
            or not self.target
            or "/" in self.target
            or resource_path(self.target) != self.target
        ):
            raise ValueError("Invalid local copy target.")

    @classmethod
    def from_record(cls, value):
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping) or set(value) != {
            field.name for field in fields(cls)
        }:
            raise ValueError("Invalid local copy mapping fields.")
        return cls(**value)

    def to_record(self) -> dict:
        return asdict(self)

    def __getitem__(self, key):
        if key not in self.__dataclass_fields__:
            raise KeyError(key)
        return getattr(self, key)

    def __iter__(self) -> Iterator[str]:
        return iter(self.__dataclass_fields__)

    def __len__(self):
        return len(self.__dataclass_fields__)


class PullResult(NamedTuple):
    status: str
    details: object = None


class CreatedCopy(NamedTuple):
    mapping: dict
    result: PullResult


@dataclass(frozen=True)
class TransferOutcome:
    """Uniform result used by reviewed execution and its presentation."""

    operation: str
    files: int | None = None
    status: str = "updated"

    def __post_init__(self):
        if self.operation == "push":
            if (
                type(self.files) is not int
                or self.files < 0
                or self.status != "updated"
            ):
                raise ValueError("Invalid Push outcome.")
        elif self.operation in ("pull", "create", "download"):
            if self.files is not None or self.status not in (
                "updated",
                "complete",
                "conflict",
            ):
                raise ValueError("Invalid Pull outcome.")
        else:
            raise ValueError("Invalid transfer operation.")

    @classmethod
    def from_result(cls, operation, result):
        if isinstance(result, cls):
            if result.operation != operation:
                raise ValueError(
                    "Transfer result direction does not match its request."
                )
            return result
        if operation == "push":
            if type(result) is not int or result < 0:
                raise ValueError("Invalid Push file count.")
            return cls(operation, files=result)
        if operation == "create":
            if (
                not isinstance(result, (tuple, list))
                or len(result) != 2
                or not isinstance(result[0], Mapping)
            ):
                raise ValueError("Invalid created-copy result.")
            _, result = result
        elif operation != "pull":
            raise ValueError("Invalid transfer operation.")
        if not isinstance(result, (tuple, list)) or len(result) != 2:
            raise ValueError("Invalid Pull result.")
        status, _ = result
        if status not in ("updated", "complete", "conflict"):
            raise ValueError("Invalid Pull result status.")
        return cls(operation, status=status)
