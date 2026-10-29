"""Provider-bound Markdown image rendering for ordinary and encrypted folders."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import base64
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import Image
from commonUtils.runtime.resources.local import LocalFiles
from mobile.preview import folder_image_source, markdown_preview, reader_image_source
from features.text_editor.mobile.markdown_editor import editor_blocks, editor_html


class MarkdownImageTests(unittest.TestCase):
    def image(self, kind):
        data = BytesIO()
        Image.new('RGB', (16, 12), 'blue').save(data, kind)
        return data.getvalue()

    def test_local_images_and_wiki_embeds_resolve_relative_to_markdown(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'notes').mkdir()
            (root / 'assets').mkdir()
            for extension, kind, mime in [('webp', 'WEBP', 'webp'), ('png', 'PNG', 'png'), ('jpg', 'JPEG', 'jpeg'), ('gif', 'GIF', 'gif')]:
                data = self.image(kind)
                (root / 'assets' / ('photo.' + extension)).write_bytes(data)
                text = f'![Picture](../assets/photo.{extension})\n\n![[../assets/photo.{extension}]]'
                html = markdown_preview(text, image_source=folder_image_source(LocalFiles(root), 'notes/read.md'))
                self.assertEqual(html.count(f'<img src="data:image/{mime};base64,'), 2)
                self.assertIn(base64.b64encode(data).decode(), html)
                self.assertIn('img-src data:', html)
                self.assertNotIn('file://', html)
                self.assertNotIn('<img', markdown_preview(text))
                self.assertNotIn('<img', markdown_preview('`![[../assets/photo.webp]]`',
                    image_source=folder_image_source(LocalFiles(root), 'notes/read.md')))

    def test_images_cannot_fetch_network_or_escape_provider_root(self):
        with TemporaryDirectory() as directory:
            provider = LocalFiles(directory)
            load = folder_image_source(provider, 'note.md')
            with patch.object(provider, 'open', side_effect=AssertionError('must not open')):
                for path in ('https://example.org/a.webp', '//host/a.png', '/a.jpg', '../a.webp',
                             '%2e%2e/a.webp', 'file:///a.png', 'data:image/png;base64,abc', 'a.svg', 'a\\b.png'):
                    self.assertIsNone(load(path), path)
            html = markdown_preview('![Missing](missing.webp)', image_source=load)
            self.assertNotIn('<img', html)
            self.assertIn('Missing', html)
            (Path(directory) / 'link.webp').symlink_to('/tmp/not-a-markdown-image')
            self.assertNotIn('<img', markdown_preview('![Linked](link.webp)', image_source=load))

    def test_localcrypt_reads_decrypted_bytes_only_through_provider(self):
        for kind, extension, mime in [('WEBP', 'webp', 'webp'), ('GIF', 'gif', 'gif')]:
            with self.subTest(kind=kind):
                self.check_localcrypt_image(kind, extension, mime)

    def check_localcrypt_image(self, kind, extension, mime):
        from features.rclone.localcrypt.mobile.resources import CryptFiles
        data = self.image(kind)
        calls = []
        class Client:
            generation = 1
            supports_streaming = False
            def request(self, action, **values):
                calls.append(action)
                if action == 'crypt_path':
                    path = '/'.join('enc-' + part for part in values['path'].split('/') if part)
                    return dict(path=path, identity='a' * 64)
                if action == 'crypt_raw_read':
                    return dict(data=base64.b64encode(data).decode())
                raise AssertionError(action)
        with TemporaryDirectory() as directory:
            provider = CryptFiles(directory, Client(), 'Secret')
            (provider.root / 'enc-notes').mkdir()
            ciphertext = provider.root / 'enc-notes' / ('enc-photo.' + extension)
            ciphertext.write_bytes(b'ciphertext-only')
            copies = SimpleNamespace(provider=provider)
            reader = SimpleNamespace(key='notes/read.md')
            html = markdown_preview(f'![Secret](photo.{extension})', image_source=reader_image_source(copies, reader))
            self.assertIn(f'<img src="data:image/{mime};base64,', html)
            self.assertIn('crypt_raw_read', calls)
            self.assertEqual(ciphertext.read_bytes(), b'ciphertext-only')
            self.assertEqual([p for p in Path(directory).rglob('*') if p.is_file()], [ciphertext])
            provider.client.request = lambda *a, **kw: (_ for _ in ()).throw(ValueError('Locked'))
            self.assertNotIn('<img', markdown_preview(f'![Secret](photo.{extension})',
                image_source=reader_image_source(copies, reader)))

    def test_formatted_images_preserve_markdown_source(self):
        data = self.image('WEBP')
        load = lambda target: ('image/webp', data)
        text = '![Caption](photo.webp)\n\n![[photo.webp]]\n'
        blocks = editor_blocks(text, image_source=load)
        self.assertEqual(''.join(block['source'] for block in blocks), text)
        self.assertTrue(all('<img' in block['html'] for block in blocks if block['source'].strip()))
        html = editor_html(text, 'logistics-editor://test/', image_source=load)
        self.assertIn('img-src data:', html)
        self.assertIn('data:image/webp;base64,', html)

    def test_animated_gif_bytes_survive_mobile_preview_and_formatted_source(self):
        data = BytesIO()
        Image.new('RGB', (16, 12), 'red').save(data, 'GIF', save_all=True,
            append_images=[Image.new('RGB', (16, 12), 'blue')], duration=100, loop=0)
        raw = data.getvalue()
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'two colors #1.GIF').write_bytes(raw)
            provider = LocalFiles(root)
            factory = lambda: folder_image_source(provider, 'read.md')
            text = 'Before ![Animation](two%20colors%20%231.GIF) after.\r\n'
            html = markdown_preview(text, image_source=factory())
            self.assertIn('data:image/gif;base64,' + base64.b64encode(raw).decode(), html)
            blocks = editor_blocks(text, image_source=factory())
            self.assertEqual(''.join(block['source'] for block in blocks), text)
            self.assertIn('contenteditable="false"', blocks[0]['html'])
            self.assertIn('data-markdown="![Animation](two%20colors%20%231.GIF)"', blocks[0]['html'])
            self.assertIn('data:image/gif;base64,' + base64.b64encode(raw).decode(),
                editor_html(text, 'logistics-editor://gif/', image_source=factory()))
            self.assertEqual((root / 'two colors #1.GIF').read_bytes(), raw)

    def test_remote_reader_resources_supply_preview_images(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'photo.png').write_bytes(self.image('PNG'))
            provider = LocalFiles(root)
            provider.remote_storage = True
            copies = SimpleNamespace(resource=SimpleNamespace(entry=lambda path: (_ for _ in ()).throw(ValueError('Browser closed'))))
            reader = SimpleNamespace(key='read.md', source=SimpleNamespace(resource=provider))
            html = markdown_preview('![[photo.png|900x600]]', image_source=reader_image_source(copies, reader))
            self.assertIn('data:image/png;base64,', html)
            self.assertIn('max-width:100%;height:auto', html)
            self.assertIn('vertical-align:middle', html)
            self.assertIn('aspect-ratio:900/600', html)

    def test_sized_wiki_embeds_keep_the_exact_spelling_in_formatted_dom(self):
        for extension, kind in (('png', 'PNG'), ('jpeg', 'JPEG'), ('webp', 'WEBP'), ('gif', 'GIF')):
            source = f'![[ photo #1.{extension}|900x600 ]]\n'
            data = self.image(kind)
            blocks = editor_blocks(source, image_source=lambda target: ('image/' + ('jpeg' if kind == 'JPEG' else extension), data))
            self.assertEqual(''.join(block['source'] for block in blocks), source)
            self.assertIn('data-markdown="' + source.strip() + '"', blocks[0]['html'])
            self.assertIn('max-width:100%;height:auto', blocks[0]['html'])
            self.assertIn('vertical-align:middle', blocks[0]['html'])
