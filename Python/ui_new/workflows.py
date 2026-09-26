"""
Generic dispatcher for feature-contributed UI workflows.
"""

from features import registry


def open_workflow(workflow_id: str, data=None, parent=None):
    """Open one workflow contributed by an enabled feature."""

    registered = registry.get_workflow(workflow_id)
    return registered.contribution.handler(data, parent)
