"""
Generic dispatcher for feature-contributed UI workflows.
"""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from features.application import registry


def open_workflow(workflow_id: str, data=None, parent=None):
    """Open one workflow contributed by an enabled feature."""

    registered = registry.get_workflow(workflow_id)
    return registered.contribution.handler(data, parent)
