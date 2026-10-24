"""Version-one native bridge actions and response envelope validation.

Request fields and action examples are documented beside the owning feature.
Changing these names requires updating the Python/Go contract fixtures together.
"""
import json

ACTIONS = frozenset(('add_smb', 'cancel', 'clear', 'connection_identity', 'crypt_archive', 'crypt_decode', 'crypt_describe', 'crypt_encode', 'crypt_manifest', 'crypt_metadata', 'crypt_path', 'crypt_paths', 'crypt_range', 'crypt_raw_read', 'crypt_raw_write', 'crypt_remotes', 'crypt_stat', 'crypt_thumbnail', 'document_lists_open', 'document_lists_seal', 'file_archive', 'file_thumbnail', 'forget_package', 'image_thumbnail', 'import', 'list', 'mirror_info', 'mirror_progress', 'mirror_review', 'mirror_review_clear', 'mirror_review_progress', 'mirror_sync', 'mirror_validate', 'probe', 'protect_package', 'remote_archive', 'remote_cache_archive', 'remote_cache_close', 'remote_cache_open', 'remote_cache_status', 'remote_range', 'remote_stat', 'remote_thumbnail', 'unprotect_package', 'vault_info', 'vault_open'))


def decode_envelope(data):
    reply = json.loads(data)
    if not isinstance(reply, dict) or type(reply.get('ok')) is not bool:
        raise ValueError('The native rclone bridge returned an invalid response envelope.')
    return reply
