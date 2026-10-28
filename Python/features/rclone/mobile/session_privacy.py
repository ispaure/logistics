"""Bind remote views to their owning credential resume challenge."""

def remote_privacy_gate(client, remote, identity=None, *, cipher=False):
    """Bind private views to their owning package, never the first loaded account.

    The caller retains this gate for the view's lifetime, including unsaved drafts
    after credential revocation. Older isolated test clients have only one gate.
    """
    state = getattr(client, 'credential_state', None)
    if state is None:
        return getattr(client, 'session_privacy', None)
    with state.lock:
        remote = state.resolve_remote(remote, identity, cipher=cipher)
        field = 'crypt_identities' if cipher else 'identities'
        for record in state.package_records:
            if (remote in record.get('remotes', ())
                    and (identity is None or record.get(field, {}).get(remote) == identity)):
                if record.get('saved'):
                    return None
                gate = state.package_privacy.get(record['package_name'])
                if gate is None:
                    raise ValueError('This credential session has no password gate. Lock and reload its package.')
                return gate
    raise ValueError('The credential package is no longer available. Unlock it again.')
