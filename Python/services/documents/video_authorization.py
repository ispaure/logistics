"""Compose document sources with the owning credential resume-proof service."""
from pathlib import Path
from features.rclone.desktop_credentials import SessionResumeProof, session_package
from .storage import document_sources


def credential_package(provider):
    for source in document_sources(provider):
        connection = getattr(source, 'connection', None)
        if connection is not None and getattr(connection, 'package', None):
            return Path(connection.package)
        key = getattr(source, 'config_path', None) or getattr(source, 'context', None)
        if key is not None:
            package = session_package(key)
            if package is not None:
                return Path(package)
    return None


def resume_authorization(package):
    return SessionResumeProof(package)
