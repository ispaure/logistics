"""Compatibility entry for host-owned notebook document composition."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from services.documents.mobile_notebooks import (
    repository, panels, open_notebook, present, close_notebook, retarget_notebook,
    adopt_notebook_document, retire_stale_notebooks, prepare_notebook_lock,
)
