"""
Resolver for feature-contributed standalone UI pages.

Features contribute stable page IDs without importing ui_new. The frontend
resolves those IDs by convention:

    page_id='smart_home'
        -> ui_new.pages.smart_home
        -> SmartHomePage
"""

import importlib


def create_page(page_id: str, parent=None):
    """Create the frontend page associated with one contributed page ID."""

    if not page_id or any(not part.isidentifier() for part in page_id.split('_')):
        raise ValueError(f'Invalid page ID: {page_id!r}')

    module_name = f'ui_new.pages.{page_id}'
    class_name = ''.join(
        part[:1].upper() + part[1:]
        for part in page_id.split('_')
    ) + 'Page'

    module = importlib.import_module(module_name)
    page_type = getattr(module, class_name, None)

    if page_type is None:
        raise ValueError(
            f'Page "{page_id}" must expose {class_name} in {module_name}.'
        )

    return page_type(parent=parent)
