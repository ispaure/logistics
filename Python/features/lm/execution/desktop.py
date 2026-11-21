"""Optional desktop project-tool capability; portable generation never imports it."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"


def project_tools(project, buffers, *, allow_edits=False, edit_dispatch=None):
    from ..project_tools import ProjectTools
    tools = ProjectTools(project, buffers, allow_edits=allow_edits, edit_dispatch=edit_dispatch)
    return tools, tools.specs
