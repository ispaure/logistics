"""Open local documents against their original folder-backed resource."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from pathlib import Path


async def open_local_document(app, path, *, destination=None):
    if path is None:
        return False
    from commonUtils.runtime.resources.local import LocalFiles
    from services.documents.mobile_storage import open_provider_document
    selected = Path(path)
    destination = destination or app.native_host.state.destination
    return await open_provider_document(app, LocalFiles(selected.parent), selected.name,
                                        destination=destination)
