"""Executable-backed Git workspace; no UI or executable probing at import time."""


def create_page(parent=None):
    from .ui.page import GitPage
    return GitPage(parent)


def register():
    from features.contributions import Feature, PageContribution
    return Feature(id='git', label='Git', pages=[
        PageContribution('Git', 'git.workspace', create_page, order=15, navigation_icon='git'),
    ])
