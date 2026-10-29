"""Version-one native bridge actions and response envelope validation.

Request fields and action examples are documented beside the owning feature.
Changing these names requires updating the Python/Go contract fixtures together.
"""

import json
from typing import Protocol, TypedDict, Required

ACTIONS = frozenset(
    (
        "add_smb",
        "cancel",
        "clear",
        "connection_identity",
        "crypt_archive",
        "crypt_decode",
        "crypt_describe",
        "crypt_encode",
        "crypt_write_buffer",
        "crypt_manifest",
        "crypt_metadata",
        "crypt_path",
        "crypt_paths",
        "crypt_range",
        "crypt_raw_read",
        "crypt_raw_write",
        "crypt_remotes",
        "crypt_stat",
        "crypt_thumbnail",
        "document_lists_open",
        "document_lists_seal",
        "file_archive",
        "file_thumbnail",
        "forget_package",
        "image_thumbnail",
        "import",
        "list",
        "mirror_info",
        "mirror_progress",
        "mirror_review",
        "mirror_review_clear",
        "mirror_review_progress",
        "mirror_sync",
        "mirror_validate",
        "probe",
        "protect_package",
        "remote_archive",
        "remote_cache_archive",
        "remote_cache_close",
        "remote_cache_open",
        "remote_cache_status",
        "remote_range",
        "remote_stat",
        "remote_thumbnail",
        "unprotect_package",
        "vault_info",
        "vault_open",
    )
)


def decode_envelope(data):
    reply = json.loads(data)
    if not isinstance(reply, dict) or type(reply.get("ok")) is not bool:
        raise ValueError(
            "The native rclone bridge returned an invalid response envelope."
        )
    return reply


# Python limits bound the encoded JSON, before crossing ctypes. Native review
# decoding intentionally has no cap; Python callers still use the general cap.
PACKAGE_LIMIT = 1024 * 1024


def request_limit_bytes(action):
    return PACKAGE_LIMIT * {"crypt_write_buffer": 45, "image_thumbnail": 24}.get(
        action, 2
    )


def validate_result(action, value):
    """Reject malformed native results before callers use fields or file counts."""
    from services.identifiers import digest

    def invalid():
        raise ValueError("Invalid native result for " + action + ".")

    if action == "mirror_info":
        if (
            not isinstance(value, dict)
            or type(value.get("crypt")) is not bool
            or not digest(value.get("identity"))
            or not isinstance(value.get("prefix"), str)
        ):
            invalid()
        cipher = value.get("cipher_identity")
        if not (digest(cipher) if value["crypt"] else cipher == ""):
            invalid()
    elif action == "crypt_path":
        if not isinstance(value, dict) or not isinstance(value.get("path"), str):
            invalid()
    elif action == "mirror_progress":
        if (
            not isinstance(value, dict)
            or not isinstance(value.get("phase"), str)
            or not {"done", "total"} <= value.keys()
        ):
            invalid()
        for field in (
            "done",
            "total",
            "files",
            "total_files",
            "checks",
            "listed",
            "active",
            "attempt",
            "max_attempts",
        ):
            if field in value and (type(value[field]) is not int or value[field] < 0):
                invalid()
        if "retrying" in value and type(value["retrying"]) is not bool:
            invalid()
    elif action == "mirror_sync":
        if type(value) is not int or value < 0:
            invalid()
    return value


class BridgeClient(Protocol):
    def request(self, action: str, **values): ...


class MirrorInfo(TypedDict):
    identity: str
    cipher_identity: str
    crypt: bool
    prefix: str


class MirrorProgress(TypedDict, total=False):
    phase: Required[str]
    done: Required[int]
    total: Required[int]
    files: int
    total_files: int
    checks: int
    listed: int
    active: int
    attempt: int
    max_attempts: int
    retrying: bool


def mirror_info(
    client: BridgeClient, remote: str, path: str, *, decrypted=False
) -> MirrorInfo:
    return validate_result(
        "mirror_info",
        client.request("mirror_info", remote=remote, path=path, decrypted=decrypted),
    )


def mirror_progress(client: BridgeClient, run: str) -> MirrorProgress:
    return validate_result(
        "mirror_progress", client.request("mirror_progress", run=run)
    )


def crypt_path(
    client: BridgeClient, *, remote: str, path: str, identity: str, directory=False
) -> str:
    result = client.request(
        "crypt_path",
        remote=remote,
        path=path,
        identity=identity,
        directory=directory,
        decode=True,
    )
    return validate_result("crypt_path", result)["path"]
