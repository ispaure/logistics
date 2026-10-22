"""Documentation ownership and navigation contracts for migrated manuals."""
from pathlib import Path
import re
import unittest
from urllib.parse import unquote, urlsplit

from commonUtils.formats.markdown import split_frontmatter
from commonUtils.formats.markdown_wiki import MarkdownWiki, documentation_root
from services.documentation import feature_guide

ROOT = Path(__file__).resolve().parents[2]
SCOPES = [ROOT / 'docs', ROOT / 'Python/desktop/bulk_rename/docs'] + [
    owner / 'docs' for owner in (ROOT / 'Python/features').iterdir()
    if owner.is_dir() and not owner.is_symlink() and (owner / 'docs').is_dir()]


def links(text):
    # Examples inside code are not navigation destinations.
    text = re.sub(r'^```.*?^```[^\n]*', '', text, flags=re.M | re.S)
    text = re.sub(r'`[^`\n]*`', '', text)
    return re.findall(r'\[[^\]\n]*\]\(([^\s)]+)', text)


class DocumentationLayoutTests(unittest.TestCase):
    def test_landing_h1_and_parent_mentions(self):
        for scope in SCOPES:
            catalog = MarkdownWiki(scope)
            self.assertFalse(catalog.errors)
            for page, text in catalog.pages.items():
                with self.subTest(page=page.relative_to(ROOT)):
                    self.assertTrue(split_frontmatter(text).body.lstrip().startswith('# '))
                    self.assertNotIn('emulation', page.relative_to(ROOT).parts)
                    self.assertNotIn('commonUtils', page.relative_to(ROOT).parts)
            for folder in [scope, *[p for p in scope.rglob('*') if p.is_dir()]]:
                landing = folder / (folder.name + '.md')
                self.assertTrue(landing.is_file(), str(landing))
                destinations = {(landing.parent / unquote(urlsplit(u).path)).resolve()
                                for u in links(landing.read_text())}
                for child in folder.iterdir():
                    target = child / (child.name + '.md') if child.is_dir() else child
                    if target != landing and target.suffix == '.md':
                        self.assertIn(target.resolve(), destinations, str(landing))

    def test_relative_document_and_asset_links(self):
        for scope in SCOPES:
            for page in scope.rglob('*.md'):
                for url in links(page.read_text()):
                    parsed = urlsplit(url)
                    if parsed.scheme or parsed.netloc or not parsed.path:
                        continue
                    with self.subTest(page=page.relative_to(ROOT), url=url):
                        target = page.parent / unquote(parsed.path)
                        self.assertFalse(target.resolve().is_relative_to(ROOT / 'test-results'),
                                         'Public docs link to a local test artifact')
                        self.assertFalse(target.resolve().is_relative_to(
                            ROOT / 'docs/development/mobile-evidence'),
                            'Public docs link to the legacy local evidence archive')
                        self.assertTrue(target.exists())
                        if parsed.fragment and target.suffix == '.md':
                            headings = re.findall(r'^#{1,6} (.+)', target.read_text(), re.M)
                            anchors = {re.sub(r'[^\w\- ]', '', h.lower()).replace(' ', '-')
                                       for h in headings}
                            self.assertIn(unquote(parsed.fragment), anchors)

    def test_feature_guide_scope_and_compatibility_links(self):
        for scope in SCOPES[1:]:
            page, directory = feature_guide(scope.parent)
            self.assertEqual(page, scope / 'user/user.md')
            self.assertEqual(directory, scope)
            self.assertTrue(page.is_file())
            index = scope.parent / 'user_docs/index.md'
            if index.is_file():
                destinations = [(index.parent / urlsplit(u).path).resolve() for u in links(index.read_text())]
                self.assertIn(page, destinations)
            self.assertEqual(documentation_root(page), scope)

    def test_mobile_owners_and_systemic_hub_have_separate_scopes(self):
        for owner in ('books', 'comics', 'lm', 'rclone', 'text_editor'):
            scope = ROOT / 'Python/features' / owner / 'docs'
            self.assertTrue((scope / 'user_mobile/user_mobile.md').is_file())
        guide = ROOT / 'docs/user_mobile/user_mobile.md'
        self.assertIn('## Workspaces and Local / LocalCrypt sync', guide.read_text())
        self.assertEqual(documentation_root(guide), ROOT / 'docs')

    def test_external_acknowledgement_remains_single_sentence(self):
        text = (ROOT / 'README.md').read_text()
        self.assertEqual(text.count('ally-tools'), 1)
        self.assertIn('Additional emulator tools are available on request through ispaure’s **ally-tools**.', text)
