"""Optional desktop project-tool capability; portable generation never imports it."""


def project_tools(project, buffers):
    from ..project_tools import ProjectTools, TOOLS
    return ProjectTools(project, buffers), TOOLS
