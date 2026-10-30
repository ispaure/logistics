"""Ask document providers for resume proof without inspecting credential storage."""
from .protection import TemporaryResumeAuthorization, document_protections


def resume_authorization(provider):
    protections = tuple(document_protections(provider))
    if not protections:
        return TemporaryResumeAuthorization()
    # All wrapped sources must authorize; none may hide an inner restriction.
    authorizations = tuple(protection.resume_authorization() for protection in protections)
    if len(authorizations) == 1:
        return authorizations[0]
    return CombinedResumeAuthorization(authorizations)


class CombinedResumeAuthorization:
    def __init__(self, authorizations):
        self.authorizations = authorizations
        gates = tuple(proof.password_gate for proof in authorizations if proof.password_gate is not None)
        self.password_gate = next((gate for gate in gates if gate.proof is None), gates[0] if gates else None)

    def verify(self, secret):
        pending, established = [], []
        for proof in self.authorizations:
            gate = proof.password_gate
            (pending if gate is not None and gate.proof is None else established).append(proof)
        # Configuration is a side effect. A wrong existing credential must not
        # set a new temporary password and prevent the next valid attempt.
        return (all(proof.verify(secret) for proof in established)
                and all(proof.verify(secret) for proof in pending))
