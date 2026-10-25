"""Optional desktop project-tool capability; portable generation never imports it."""


def project_tools(project, buffers, *, allow_edits=False, edit_dispatch=None):
    from ..project_tools import ProjectTools
    tools = ProjectTools(project, buffers, allow_edits=allow_edits, edit_dispatch=edit_dispatch)
    return tools, tools.specs
