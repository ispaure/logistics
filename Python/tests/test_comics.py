"""Run with: PYTHONPATH=Python python3 -m unittest discover -s Python/tests -v."""

from contextlib import redirect_stdout
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO, StringIO
from pathlib import Path
import stat
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile
from xml.etree import ElementTree

from PIL import Image
from commonUtils import fileUtils
from features.comics import actions, archive_io, cbz, conversion, metadata


COMICINFO = '''<?xml version="1.0" encoding="utf-8"?>
<ComicInfo>
  <Writer>Old</Writer>
  <Series>Old</Series>
  <PageCount>99</PageCount>
  <Pages>
    <Page Image="0" Type="FrontCover" />
  </Pages>
</ComicInfo>'''


def image_bytes(mode='RGB', size=(64, 80), color='white', format='PNG'):
    output = BytesIO()
    Image.new(mode, size, color).save(output, format=format)
    return output.getvalue()


def multiframe_bytes(format):
    output = BytesIO()
    first = Image.new('RGB', (64, 80), 'red')
    second = Image.new('RGB', (64, 80), 'blue')
    first.save(output, format=format, save_all=True, append_images=[second])
    return output.getvalue()


class ComicsTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = StringIO()
        self.redirect = redirect_stdout(self.output)
        self.redirect.__enter__()
        self.addCleanup(self.redirect.__exit__, None, None, None)

    def archive(self, entries=None, name='comic.cbz'):
        path = self.root / name
        with zipfile.ZipFile(path, 'w') as archive:
            for key, data in (entries or {'01.png': image_bytes()}).items():
                archive.writestr(key, data)
        return path

    def assert_compression_rejected(self, entries):
        path = self.archive(entries)
        before = path.read_bytes()
        self.assertFalse(cbz.CBZFile(path).compress_to_webp(True))
        self.assertEqual(path.read_bytes(), before)

    def test_real_compression_updates_pages_in_existing_order(self):
        path = self.archive({'2.png': image_bytes('L', color=120),
                             '1.png': image_bytes(size=(120, 2500)),
                             'ComicInfo.xml': COMICINFO, 'Thumbs.db': b'junk',
                             '__MACOSX/._1.png': b'junk', 'notes.txt': b'junk'})
        comic = cbz.CBZFile(path)
        self.assertTrue(comic.compress_to_webp(True), self.output.getvalue())
        with zipfile.ZipFile(path) as archive:
            self.assertEqual(set(archive.namelist()), {'01.webp', '02.webp', 'ComicInfo.xml', 'CompressionLog.txt'})
            xml = ElementTree.fromstring(archive.read('ComicInfo.xml'))
            self.assertEqual(xml.findtext('PageCount'), '2')
            pages = xml.findall('./Pages/Page')
            self.assertEqual([page.get('Image') for page in pages], ['0', '1'])
            self.assertEqual(pages[0].get('Type'), 'FrontCover')
            self.assertIsNone(pages[1].get('Type'))
            with Image.open(BytesIO(archive.read('01.webp'))) as cover:
                self.assertEqual(cover.size, (115, 2400))
            self.assertEqual(pages[0].get('ImageHeight'), '2400')
            self.assertEqual(pages[0].get('ImageSize'), str(len(archive.read('01.webp'))))
            self.assertIn('||Compression Statistics||', archive.read('CompressionLog.txt').decode())
        self.assertTrue(comic.is_already_compressed())
        self.assertEqual(comic.compression_stats.kept_images_compressed_cnt, 2)

    def test_threshold_is_strict_and_override_is_preserved(self):
        for size, override, expected in [(74, False, '01.webp'), (75, False, '01.png'),
                                        (76, False, '01.png'), (76, True, '01.webp')]:
            with self.subTest(size=size, override=override):
                path = self.archive(name=f'{size}-{override}.cbz')
                def compress(image, dest_path, **settings):
                    self.assertEqual(settings, dict(quality_grayscale=35, quality_color=60,
                                                   max_long_edge=None, max_height=2400,
                                                   preserve_alpha=False))
                    Image.new('RGB', (64, 80), 'white').save(dest_path, 'WEBP')
                    image.compressed_image = cbz.CBZImageFile(dest_path)
                    image.size = 100
                    image.compressed_image.size = size
                    return True
                with patch.object(cbz.CBZImageFile, 'compress', compress):
                    self.assertTrue(cbz.CBZFile(path).compress_to_webp(override), self.output.getvalue())
                with zipfile.ZipFile(path) as archive:
                    self.assertEqual(set(archive.namelist()), {expected, 'CompressionLog.txt'})

    def test_retained_original_is_byte_identical(self):
        original = image_bytes(size=(1, 1), format='WEBP')
        path = self.archive({'01.webp': original})
        self.assertTrue(cbz.CBZFile(path).compress_to_webp())
        with zipfile.ZipFile(path) as archive:
            self.assertEqual(archive.read('01.webp'), original)

    def test_compress_selection_deduplicates_and_preserves_batch_failure_policy(self):
        good = self.archive(name='good.cbz')
        marked = self.archive({'CompressionLog.txt': b'done'}, 'marked.cbz')
        bad = self.root / 'bad.cbz'
        bad.write_bytes(b'not a zip')
        original = marked.read_bytes()
        stats = cbz.compress_selected_cbz([good, self.root, good])
        self.assertEqual((stats.total_file_count, stats.compressed_file_count,
                          stats.already_compressed_file_count, stats.error_during_compression), (3, 1, 1, 1))
        self.assertEqual(marked.read_bytes(), original)
        self.assertEqual(bad.read_bytes(), b'not a zip')

    def test_nonrecursive_selection_includes_explicit_nested_files(self):
        from features.comics.selection import selected_comics
        top = self.archive(name='top.cbz')
        (self.root / 'nested').mkdir()
        nested = self.archive(name='nested/child.cbz')
        sibling = self.archive(name='nested/other.cbz')
        self.assertEqual(selected_comics([self.root], recursive=False), (top,))
        self.assertEqual(set(selected_comics([self.root, nested], recursive=False)), {top, nested})
        self.assertEqual(set(selected_comics([self.root, nested])), {top, nested, sibling})

    def test_empty_batch(self):
        stats = cbz.batch_compress_cbz(self.root)
        self.assertEqual(stats.total_file_count, 0)

    def test_batch_continues_after_bad_archive_and_skips_marked(self):
        (self.root / 'bad.cbz').write_bytes(b'not a zip')
        good = self.archive(name='good.cbz')
        marked = self.archive({'CompressionLog.txt': b'done'}, 'marked.cbz')
        original = marked.read_bytes()
        stats = cbz.batch_compress_cbz(self.root, always_keep_compressed=True)
        self.assertEqual((stats.total_file_count, stats.compressed_file_count,
                          stats.already_compressed_file_count, stats.error_during_compression), (3, 1, 1, 1))
        self.assertTrue(cbz.CBZFile(good).is_already_compressed())
        self.assertEqual(marked.read_bytes(), original)

    def test_missing_xml_is_allowed(self):
        path = self.archive()
        comic = cbz.CBZFile(path)
        self.assertTrue(comic.compress_to_webp(True))
        self.assertFalse(comic.compression_stats.has_comicinfo_xml)

    def test_xml_update_failure_preserves_original(self):
        self.assert_compression_rejected({'01.png': image_bytes(),
                                         'ComicInfo.xml': '<ComicInfo><Pages/><Pages/></ComicInfo>'})

    def test_xml_formatting_variations_rebuild_pages_and_preserve_metadata(self):
        variants = [
            '<ComicInfo><Title>A &amp; B</Title><PageCount>99</PageCount>'
            '<Pages><!-- stale page comment --><?stale page?>'
            '<Page Image="98" ImageSize="999999" ImageWidth="999" ImageHeight="888" '
            'Bookmark="Old" DoublePage="True" Type="Deleted" Custom="obsolete">'
            '<OldMetadata>obsolete</OldMetadata></Page></Pages></ComicInfo>',
            '<ComicInfo>\n\t<Title>A &amp; B</Title>\n<PageCount>99</PageCount>\n'
            '\t<Pages>\n<Page Image="98"/>\n</Pages>\n</ComicInfo>',
            '<ComicInfo><Title>A &amp; B</Title><PageCount>99</PageCount><Pages/></ComicInfo>',
            '<ComicInfo><Title>A &amp; B</Title></ComicInfo>',
        ]
        for xml in variants:
            with self.subTest(xml=xml):
                path = self.archive({'01.png': image_bytes(), '02.png': image_bytes(),
                                     'ComicInfo.xml': xml})
                self.assertTrue(cbz.CBZFile(path).compress_to_webp(True), self.output.getvalue())
                with zipfile.ZipFile(path) as archive:
                    serialized = archive.read('ComicInfo.xml')
                    root = ElementTree.fromstring(serialized)
                    self.assertEqual(root.findtext('Title'), 'A & B')
                    self.assertEqual(root.findtext('PageCount'), '2')
                    pages = root.findall('./Pages/Page')
                    self.assertEqual([page.get('Image') for page in pages], ['0', '1'])
                    self.assertEqual(pages[0].get('Type'), 'FrontCover')
                    self.assertIsNone(pages[1].get('Type'))
                    self.assertTrue(all('Bookmark' not in page.attrib and 'DoublePage' not in page.attrib
                                        for page in pages))
                    for index, page in enumerate(pages):
                        payload = archive.read(f'{index + 1:02}.webp')
                        with Image.open(BytesIO(payload)) as image:
                            expected = dict(Image=str(index), ImageSize=str(len(payload)),
                                            ImageWidth=str(image.width), ImageHeight=str(image.height))
                        if index == 0:
                            expected['Type'] = 'FrontCover'
                        self.assertEqual(page.attrib, expected)
                        self.assertEqual(list(page), [])
                    self.assertNotIn(b'stale page', serialized)
                    self.assertNotIn(b'obsolete', serialized)
                    self.assertIn(b'\n  <PageCount>2</PageCount>', serialized)

    def test_xml_namespaces_comments_and_metadata_content_are_preserved(self):
        xml = ('<?xml version="1.0"?><ComicInfo xmlns="urn:comicinfo" '
               'xmlns:extra="urn:extra" extra:flag="yes"><!-- Keep this comment -->'
               '<?keep processing?><Title>Été &amp; comics</Title>'
               '<Notes> First line\n Second line </Notes>'
               '<extra:Data extra:value="a &amp; b">Custom text</extra:Data>'
               '<PageCount>99</PageCount><Pages><Page Image="98" /></Pages></ComicInfo>')
        path = self.archive({'01.png': image_bytes(), 'ComicInfo.xml': xml})
        self.assertTrue(cbz.CBZFile(path).compress_to_webp(True), self.output.getvalue())
        with zipfile.ZipFile(path) as archive:
            serialized = archive.read('ComicInfo.xml')
            root = ElementTree.fromstring(serialized)
            self.assertEqual(root.get('{urn:extra}flag'), 'yes')
            self.assertEqual(root.findtext('{urn:comicinfo}Title'), 'Été & comics')
            self.assertEqual(root.findtext('{urn:comicinfo}Notes'), ' First line\n Second line ')
            custom = root.find('{urn:extra}Data')
            self.assertEqual(custom.text, 'Custom text')
            self.assertEqual(custom.get('{urn:extra}value'), 'a & b')
            self.assertEqual(root.findtext('{urn:comicinfo}PageCount'), '1')
            self.assertEqual(len(root.findall('{urn:comicinfo}Pages/{urn:comicinfo}Page')), 1)
            self.assertIn(b'<!-- Keep this comment -->', serialized)
            self.assertIn(b'<?keep processing?>', serialized)

    def test_ambiguous_or_wrong_root_xml_preserves_original(self):
        for xml in ('<ComicInfo><PageCount>1</PageCount><PageCount>2</PageCount><Pages/></ComicInfo>',
                    '<Other><PageCount>1</PageCount><Pages/></Other>',
                    '<ComicInfo><PageCount><Count>1</Count></PageCount><Pages/></ComicInfo>'):
            with self.subTest(xml=xml):
                self.assert_compression_rejected({'01.png': image_bytes(), 'ComicInfo.xml': xml})

    def test_xml_character_references_and_unicode_separators_survive_repeated_updates(self):
        xml = ('<ComicInfo><Summary>A &#13; B &#x85; C &#x2028; D &#x2029; E</Summary>'
               '<Notes>Literal \u0085 / \u2028 / \u2029 separators</Notes><Pages/></ComicInfo>')
        expected = ElementTree.fromstring(xml)
        path = self.archive({'01.png': image_bytes(), 'ComicInfo.xml': xml})
        for iteration in range(2):
            with self.subTest(iteration=iteration):
                self.assertTrue(cbz.CBZFile(path).compress_to_webp(True), self.output.getvalue())
                with zipfile.ZipFile(path) as archive:
                    result = ElementTree.fromstring(archive.read('ComicInfo.xml'))
                    self.assertEqual(result.findtext('Summary'), expected.findtext('Summary'))
                    self.assertEqual(result.findtext('Notes'), expected.findtext('Notes'))

    def test_malformed_xml_preserves_original(self):
        self.assert_compression_rejected({'01.png': image_bytes(), 'ComicInfo.xml': '<broken>'})

    def test_no_images_preserves_original(self):
        self.assert_compression_rejected({'ComicInfo.xml': COMICINFO})

    def test_unknown_file_preserves_original(self):
        self.assert_compression_rejected({'01.png': image_bytes(), 'unexpected.pdf': b'unknown'})

    def test_unreadable_image_preserves_original(self):
        self.assert_compression_rejected({'01.png': b'not an image'})

    def test_nested_two_level_wrapper_is_flattened(self):
        path = self.archive({'outer/inner/01.png': image_bytes()})
        self.assertTrue(cbz.CBZFile(path).compress_to_webp(True))
        with zipfile.ZipFile(path) as archive:
            self.assertEqual(set(archive.namelist()), {'01.webp', 'CompressionLog.txt'})

    def test_multiple_subfolders_are_preserved(self):
        path = self.archive({'a/01.png': image_bytes(), 'b/01.png': image_bytes()})
        self.assertTrue(cbz.CBZFile(path).compress_to_webp(True))
        with zipfile.ZipFile(path) as archive:
            self.assertEqual({key for key in archive.namelist() if not key.endswith('/')},
                             {'a/01.webp', 'b/01.webp', 'CompressionLog.txt'})

    def test_flattening_metadata_collision_preserves_original(self):
        self.assert_compression_rejected({'ComicInfo.xml': COMICINFO,
                                         'inner/ComicInfo.xml': COMICINFO, 'inner/01.png': image_bytes()})

    def test_webp_stem_collision_preserves_original(self):
        self.assert_compression_rejected({'01.png': image_bytes(), '01.jpg': image_bytes(format='JPEG')})

    def test_padding_collision_preserves_original(self):
        self.assert_compression_rejected({'1.png': image_bytes(), '01.png': image_bytes()})

    def test_padding_mixed_names_preserves_original(self):
        self.assert_compression_rejected({'1.png': image_bytes(), 'cover.png': image_bytes()})

    def test_copy_failure_preserves_original(self):
        path = self.archive()
        before = path.read_bytes()
        with patch.object(cbz.fileUtils.File, 'copy_file', side_effect=OSError('copy failed')):
            self.assertFalse(cbz.CBZFile(path).compress_to_webp(True))
        self.assertEqual(path.read_bytes(), before)

    def test_encoder_failure_preserves_original(self):
        path = self.archive()
        before = path.read_bytes()
        with patch.object(cbz.CBZImageFile, 'compress', return_value=False):
            self.assertFalse(cbz.CBZFile(path).compress_to_webp(True))
        self.assertEqual(path.read_bytes(), before)

    def test_archive_build_failure_preserves_original(self):
        path = self.archive()
        before = path.read_bytes()
        with patch.object(archive_io.zipUtils, 'zip_file', side_effect=OSError('disk full')):
            self.assertFalse(cbz.CBZFile(path).compress_to_webp(True))
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse(list(self.root.glob('.logistics-comic-*')))

    def test_archive_verification_rejects_incomplete_output(self):
        path = self.archive()
        before = path.read_bytes()
        def incomplete(source, destination, **kwargs):
            with zipfile.ZipFile(destination, 'w') as archive:
                archive.writestr('wrong.txt', b'wrong')
        with patch.object(archive_io.zipUtils, 'zip_file', incomplete):
            self.assertFalse(cbz.CBZFile(path).compress_to_webp(True))
        self.assertEqual(path.read_bytes(), before)

    def test_archive_verification_rejects_different_content(self):
        path = self.archive()
        before = path.read_bytes()
        def wrong_content(source, destination, **kwargs):
            with zipfile.ZipFile(destination, 'w') as archive:
                for page in source.rglob('*'):
                    if page.is_file():
                        archive.writestr(page.relative_to(source).as_posix(), b'x' * page.stat().st_size)
        with patch.object(archive_io.zipUtils, 'zip_file', wrong_content):
            self.assertFalse(cbz.CBZFile(path).compress_to_webp(True))
        self.assertEqual(path.read_bytes(), before)

    def test_atomic_replace_failure_preserves_original(self):
        path = self.archive()
        before = path.read_bytes()
        actual_replace = archive_io.os.replace
        def fail_final_replace(source, destination):
            if Path(destination) == path:
                raise OSError('replace failed')
            return actual_replace(source, destination)
        with patch.object(archive_io.os, 'replace', fail_final_replace):
            self.assertFalse(cbz.CBZFile(path).compress_to_webp(True))
        self.assertEqual(path.read_bytes(), before)

    def test_unsafe_directory_entry_preserves_original(self):
        self.assert_compression_rejected({'../escaped/': b'', '01.png': image_bytes()})
        self.assertFalse((self.root.parent / 'escaped').exists())

    def test_duplicate_member_preserves_original(self):
        path = self.archive({'01.png': image_bytes()})
        with zipfile.ZipFile(path, 'a') as archive:
            with self.assertWarns(UserWarning):
                archive.writestr('01.png', image_bytes())
        before = path.read_bytes()
        self.assertFalse(cbz.CBZFile(path).compress_to_webp(True))
        self.assertEqual(path.read_bytes(), before)

    def test_case_collision_preserves_original(self):
        self.assert_compression_rejected({'01.png': image_bytes(), '01.PNG': image_bytes()})

    def test_destination_mode_is_preserved(self):
        path = self.archive()
        path.chmod(0o640)
        expected_mode = stat.S_IMODE(path.stat().st_mode)
        self.assertTrue(cbz.CBZFile(path).compress_to_webp(True))
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), expected_mode)

    def test_changed_original_is_not_overwritten(self):
        path = self.archive()
        replacement = b'concurrent change'
        actual_compress = cbz.CBZImageFile.compress
        def changing(image, *args, **kwargs):
            path.write_bytes(replacement)
            return actual_compress(image, *args, **kwargs)
        with patch.object(cbz.CBZImageFile, 'compress', changing):
            self.assertFalse(cbz.CBZFile(path).compress_to_webp(True))
        self.assertEqual(path.read_bytes(), replacement)

    def test_metadata_edits_escape_values_and_keep_page_bytes(self):
        parent = self.root / 'A & B'
        parent.mkdir()
        path = self.archive({'01.png': image_bytes(), 'ComicInfo.xml': COMICINFO})
        destination = parent / path.name
        path.rename(destination)
        self.assertTrue(metadata.comic_info_xml_replace_author(destination, 'Old'))
        self.assertTrue(metadata.comic_info_xml_replace_series(destination, 'Old', 'Prefix '))
        with zipfile.ZipFile(destination) as archive:
            root = ElementTree.fromstring(archive.read('ComicInfo.xml'))
            self.assertEqual(root.findtext('Writer'), 'A & B')
            self.assertEqual(root.findtext('Series'), 'Prefix A & B')
            self.assertEqual(archive.read('01.png'), image_bytes())

    def test_metadata_failure_preserves_original(self):
        path = self.archive({'01.png': image_bytes(), 'ComicInfo.xml': COMICINFO})
        before = path.read_bytes()
        with patch.object(metadata.zipUtils, 'unzip_file', return_value=False):
            self.assertFalse(metadata.comic_info_xml_replace_author(path, 'Old'))
        self.assertEqual(path.read_bytes(), before)

    def test_metadata_no_match_does_not_rebuild(self):
        path = self.archive({'01.png': image_bytes(), 'ComicInfo.xml': COMICINFO})
        before = path.read_bytes()
        self.assertTrue(metadata.comic_info_xml_replace_author(path, 'No match'))
        self.assertEqual(path.read_bytes(), before)

    def test_conversion_failure_never_deletes_source_or_existing_output(self):
        source = self.root / 'comic.cbr'
        source.write_bytes(b'cbr original')
        existing = self.archive()
        before = existing.read_bytes()
        self.assertFalse(conversion.convert_cbr_to_cbz(source))
        self.assertEqual(existing.read_bytes(), before)
        self.assertEqual(source.read_bytes(), b'cbr original')

    def test_conversion_extract_failure_preserves_source(self):
        source = self.root / 'comic.cbr'
        source.write_bytes(b'cbr original')
        settings = SimpleNamespace(path_logistics_software_win=self.root)
        with patch.object(conversion.config, 'LogisticsConfig', return_value=settings), \
                patch.object(conversion.zipUtils, 'unrar_file', return_value=False):
            self.assertFalse(conversion.convert_cbr_to_cbz(source))
        self.assertEqual(source.read_bytes(), b'cbr original')
        self.assertFalse(source.with_suffix('.cbz').exists())

    def test_conversion_deletes_source_only_after_verified_cbz(self):
        source = self.root / 'comic.cbr'
        source.write_bytes(b'cbr original')
        settings = SimpleNamespace(path_logistics_software_win=self.root)
        def extract(source, destination, **kwargs):
            (destination / '01.png').write_bytes(image_bytes())
        with patch.object(conversion.config, 'LogisticsConfig', return_value=settings), \
                patch.object(conversion.zipUtils, 'unrar_file', extract):
            self.assertTrue(conversion.convert_cbr_to_cbz(source), self.output.getvalue())
        self.assertFalse(source.exists())
        with zipfile.ZipFile(source.with_suffix('.cbz')) as archive:
            self.assertEqual(archive.read('01.png'), image_bytes())

    def test_padding_width_cutoffs_are_preserved(self):
        for count, width in [(89, 2), (90, 3), (949, 3), (950, 5)]:
            with self.subTest(count=count):
                directory = self.root / str(count)
                directory.mkdir()
                files = []
                for index in range(1, count + 1):
                    path = directory / f'{index}.png'
                    path.write_bytes(b'page')
                    files.append(fileUtils.File(path))
                comic = cbz.CBZFile(self.archive(name=f'{count}.cbz'))
                self.assertTrue(comic.repair_padding(files))
                self.assertTrue((directory / f'{1:0{width}d}.png').is_file())
                self.assertEqual(len(list(directory.iterdir())), count)

    def test_nested_xml_is_not_silently_discarded(self):
        self.assert_compression_rejected({'a/01.png': image_bytes(), 'a/ComicInfo.xml': COMICINFO,
                                         'b/01.png': image_bytes()})

    def test_compressions_do_not_share_or_wipe_workspaces(self):
        first = self.archive(name='first.cbz')
        second = self.archive(name='second.cbz')
        legacy_workspace = self.root / 'legacy-workspace'
        legacy_workspace.mkdir()
        sentinel = legacy_workspace / 'unrelated.txt'
        sentinel.write_text('keep')
        with patch.object(cbz, 'temp_compression_path', legacy_workspace):
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(cbz.CBZFile(path).compress_to_webp, True) for path in (first, second)]
                self.assertTrue(all(future.result() for future in futures), self.output.getvalue())
        self.assertEqual(sentinel.read_text(), 'keep')
        self.assertTrue(cbz.CBZFile(first).is_already_compressed())
        self.assertTrue(cbz.CBZFile(second).is_already_compressed())

    def test_existing_sibling_zip_is_untouched(self):
        path = self.archive()
        sibling = path.with_suffix('.zip')
        sibling.write_bytes(b'unrelated zip')
        self.assertTrue(cbz.CBZFile(path).compress_to_webp(True))
        self.assertEqual(sibling.read_bytes(), b'unrelated zip')

    def test_empty_pages_xml_is_rebuilt(self):
        xml = COMICINFO.replace('  <Pages>\n    <Page Image="0" Type="FrontCover" />\n  </Pages>', '  <Pages />')
        path = self.archive({'01.png': image_bytes(), 'ComicInfo.xml': xml})
        self.assertTrue(cbz.CBZFile(path).compress_to_webp(True))
        with zipfile.ZipFile(path) as archive:
            root = ElementTree.fromstring(archive.read('ComicInfo.xml'))
            self.assertEqual(root.findtext('PageCount'), '1')
            self.assertEqual(len(root.findall('./Pages/Page')), 1)

    def test_padding_preflight_does_not_partially_rename(self):
        first = self.root / '1.png'
        second = self.root / 'cover.png'
        first.write_bytes(b'page'); second.write_bytes(b'page')
        comic = cbz.CBZFile(self.archive())
        self.assertFalse(comic.repair_padding([fileUtils.File(first), fileUtils.File(second)]))
        self.assertTrue(first.exists())
        self.assertFalse((self.root / '01.png').exists())

    def test_symlink_archive_member_is_rejected(self):
        path = self.archive()
        info = zipfile.ZipInfo('02.png')
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        with zipfile.ZipFile(path, 'a') as archive:
            archive.writestr(info, '01.png')
        before = path.read_bytes()
        self.assertFalse(cbz.CBZFile(path).compress_to_webp(True))
        self.assertEqual(path.read_bytes(), before)

    def test_individual_folder_move_refuses_existing_destination(self):
        path = self.archive()
        folder = self.root / path.stem
        folder.mkdir()
        destination = folder / path.name
        destination.write_bytes(b'existing comic')
        before = path.read_bytes()
        self.assertFalse(actions.move_cbz_to_individual_folders(self.root))
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(destination.read_bytes(), b'existing comic')

    def test_individual_folder_move_copy_failure_keeps_original(self):
        path = self.archive()
        before = path.read_bytes()
        with patch.object(actions.fileUtils.File, 'copy_file', side_effect=OSError('copy failed')):
            self.assertFalse(actions.move_cbz_to_individual_folders(self.root))
        self.assertEqual(path.read_bytes(), before)

    def test_individual_folder_move_preserves_bytes(self):
        path = self.archive()
        before = path.read_bytes()
        destination = self.root / path.stem / path.name
        self.assertTrue(actions.move_cbz_to_individual_folders(self.root))
        self.assertFalse(path.exists())
        self.assertEqual(destination.read_bytes(), before)

    def test_preservation_keeps_all_frames_and_original_bytes(self):
        for format, extension in [('GIF', 'gif'), ('TIFF', 'tiff'), ('WEBP', 'webp'), ('PNG', 'png')]:
            with self.subTest(format=format):
                original = multiframe_bytes(format)
                name = f'01.{extension}'
                path = self.archive({name: original}, name=f'{extension}.cbz')
                comic = cbz.CBZFile(path)
                with patch.object(cbz.CBZImageFile, 'compress', side_effect=AssertionError('Must not encode preserved pages')):
                    self.assertTrue(comic.compress_to_webp(preserve_animated_and_multipage_originals=True),
                                    self.output.getvalue())
                with zipfile.ZipFile(path) as archive:
                    self.assertEqual(archive.read(name), original)
                    with Image.open(BytesIO(archive.read(name))) as image:
                        self.assertEqual(image.n_frames, 2)
                self.assertEqual(comic.compression_stats.kept_images_original_cnt, 1)
                self.assertEqual(comic.compression_stats.kept_images_compressed_cnt, 0)

    def test_preservation_does_not_prevent_static_page_compression(self):
        original = multiframe_bytes('GIF')
        path = self.archive({'01.gif': original, '02.png': image_bytes(size=(64, 80))})
        self.assertTrue(cbz.CBZFile(path).compress_to_webp(preserve_animated_and_multipage_originals=True))
        with zipfile.ZipFile(path) as archive:
            self.assertEqual(archive.read('01.gif'), original)
            self.assertIn('02.webp', archive.namelist())

    def test_conflicting_flags_log_error_before_processing_single_archive(self):
        path = self.archive()
        before = path.read_bytes()
        comic = cbz.CBZFile(path)
        with patch.object(cbz, 'log') as log, patch.object(comic, '_compress_to_webp') as compress:
            self.assertFalse(comic.compress_to_webp(True, True))
            compress.assert_not_called()
            self.assertEqual(log.call_args.args[0], cbz.Severity.ERROR)
        self.assertEqual(path.read_bytes(), before)

    def test_conflicting_batch_flags_log_error_before_scanning(self):
        with patch.object(cbz, 'log') as log, patch.object(cbz.dirUtils.Directory, 'list_files') as scan:
            self.assertIsNone(cbz.batch_compress_cbz(self.root, always_keep_compressed=True,
                                                  preserve_animated_and_multipage_originals=True))
            scan.assert_not_called()
            self.assertEqual(log.call_args.args[0], cbz.Severity.ERROR)

    def test_batch_passes_preservation_option(self):
        original = multiframe_bytes('TIFF')
        path = self.archive({'01.tiff': original})
        stats = cbz.batch_compress_cbz(self.root, preserve_animated_and_multipage_originals=True)
        self.assertEqual(stats.compressed_file_count, 1)
        with zipfile.ZipFile(path) as archive:
            self.assertEqual(archive.read('01.tiff'), original)

    def test_forced_compression_without_preservation_flattens_animation(self):
        path = self.archive({'01.gif': multiframe_bytes('GIF')})
        self.assertTrue(cbz.CBZFile(path).compress_to_webp(always_keep_compressed=True))
        with zipfile.ZipFile(path) as archive:
            self.assertNotIn('01.gif', archive.namelist())
            with Image.open(BytesIO(archive.read('01.webp'))) as image:
                self.assertEqual(getattr(image, 'n_frames', 1), 1)

    def test_cbz_encoding_uses_shared_dot_stage_with_normal_final_names(self):
        path = self.archive()
        actual_save = Image.Image.save
        destinations = []
        def observe_save(image, destination, *args, **kwargs):
            destinations.append(Path(destination))
            return actual_save(image, destination, *args, **kwargs)
        with patch.object(Image.Image, 'save', observe_save):
            self.assertTrue(cbz.CBZFile(path).compress_to_webp(True))
        self.assertEqual(len(destinations), 1)
        self.assertEqual(destinations[0].name, '.01.webp')
        self.assertEqual(destinations[0].parent.name, '2_Compressed_Images')
        with zipfile.ZipFile(path) as archive:
            self.assertEqual(set(archive.namelist()), {'01.webp', 'CompressionLog.txt'})


if __name__ == '__main__':
    unittest.main()
