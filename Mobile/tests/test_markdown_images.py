"""Provider-bound Markdown image rendering for ordinary and encrypted folders."""
import base64
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import Image
from commonUtils.runtime.local_files import LocalFiles
from logisticsmobile.preview import folder_image_source, markdown_preview, reader_image_source
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
            for extension, kind, mime in [('webp', 'WEBP', 'webp'), ('png', 'PNG', 'png'), ('jpg', 'JPEG', 'jpeg')]:
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
        from features.rclone.localcrypt.mobile.resources import CryptFiles
        data = self.image('WEBP')
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
            ciphertext = provider.root / 'enc-notes' / 'enc-photo.webp'
            ciphertext.write_bytes(b'ciphertext-only')
            copies = SimpleNamespace(provider=provider)
            reader = SimpleNamespace(key='notes/read.md')
            html = markdown_preview('![Secret](photo.webp)', image_source=reader_image_source(copies, reader))
            self.assertIn('<img src="data:image/webp;base64,', html)
            self.assertIn('crypt_raw_read', calls)
            self.assertEqual(ciphertext.read_bytes(), b'ciphertext-only')
            self.assertEqual([p for p in Path(directory).rglob('*') if p.is_file()], [ciphertext])
            provider.client.request = lambda *a, **kw: (_ for _ in ()).throw(ValueError('Locked'))
            self.assertNotIn('<img', markdown_preview('![Secret](photo.webp)',
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
