"""Logistics help entry points; rendering and hierarchy remain in commonUtils."""
from pathlib import Path


def feature_guide(owner):
    """Prefer the owned wiki, preserving separately installed legacy features."""
    owner = Path(owner)
    guide = owner / 'docs/user/user.md'
    if guide.is_file():
        return guide, owner / 'docs'
    guide = owner / 'user_docs/index.md'
    if {p.name for p in guide.parent.glob('*.md')} == {'index.md', 'README.md'}:
        guide = guide.parent / 'README.md'
    return guide, guide.parent


def open_guide(path, *, directory=None, **kwargs):
    from commonUtils.formats.markdown.wiki import documentation_root
    from commonUtils.ui.markdown import open_markdown
    return open_markdown(path, directory=directory or documentation_root(path), **kwargs)
