"""Logistics help entry points; rendering and hierarchy remain in commonUtils."""
from pathlib import Path


def feature_guide(owner):
    """Open built-in guides in the root wiki; preserve external feature help."""
    owner = Path(owner)
    root = Path(__file__).resolve().parents[2]
    if owner.parent == root / 'Python/features' and not owner.is_symlink():
        guide = root / 'docs/features' / owner.name / 'user/user.md'
    elif owner == root / 'Python/desktop/bulk_rename':
        guide = root / 'docs/features/bulk_rename/user/user.md'
    else:
        guide = owner / 'docs/user/user.md'
    if guide.is_file() and guide.is_relative_to(root / 'docs'):
        return guide, root / 'docs'
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
