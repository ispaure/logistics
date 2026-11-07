"""Open local documents against their original folder-backed resource."""
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
