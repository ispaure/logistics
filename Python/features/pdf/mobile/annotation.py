"""Mobile PDF overflow command over the retained document provider."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import asyncio
import toga
from features.pdf.annotation import duplicate_pdf, LABEL
from features.notebooks.notebook import MAX_ARCHIVE
from services.documents.storage import DocumentResource


async def annotate_pdf(owner, reader):
    app = getattr(owner, 'app', owner)
    if not owner.active_host or owner.cloud_busy:
        return False
    generation = app.navigation_generation
    source = reader.source
    owner.set_cloud_busy(True)
    resource = None
    try:
        def create():
            source.check()
            return duplicate_pdf(source.provider, source.path)
        destination = await asyncio.to_thread(create)
        if not owner.active_host or app.navigation_generation != generation:
            return False
        resource = DocumentResource(source.provider, destination, max_bytes=MAX_ARCHIVE)
        from services.documents.mobile_notebooks import open_notebook
        transferred, resource = resource, None
        return await open_notebook(app, resource=transferred)
    except Exception as error:
        if owner.active_host:
            await app.main_window.dialog(toga.ErrorDialog(LABEL, str(error)))
        return False
    finally:
        if resource is not None:
            resource.close()
        owner.set_cloud_busy(False)
