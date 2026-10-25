"""Compatibility entry for host-owned notebook document composition."""
from services.documents.mobile_notebooks import (
    repository, panels, open_notebook, present, close_notebook, retarget_notebook,
    adopt_notebook_document, retire_stale_notebooks, prepare_notebook_lock,
)
