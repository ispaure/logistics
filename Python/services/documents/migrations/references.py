"""Upgrade saved ordinary references while their original storage is active."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

def upgrade_local_references(root):
    from services.documents.mobile_locations import enabled
    if not enabled(root):
        return
    from services.documents.catalog import DocumentCatalog
    from services.documents.progress_identity import normalize_local_reference
    from mobile.locations import Locations
    Locations(root)  # Upgrade saved local pins while the original drive is selected.
    catalog = DocumentCatalog(root, normalize=lambda source, opener: normalize_local_reference(root, source, opener))
    try:
        catalog.upgrade_local_references()
    except (OSError, ValueError, TypeError):
        pass  # The favourites view can still report the original read error.
