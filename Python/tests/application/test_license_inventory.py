"""Notices carried inside packages and archives must survive collection."""
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

from services.license_inventory import archive_notices, full_license, package_notice_paths, pom_information


class LicenseInventoryTests(unittest.TestCase):
    def test_desktop_vlc_keeps_extensionless_and_same_named_notices(self):
        from services.video_runtime import extract
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / 'runtime.nupkg'
            with ZipFile(archive, 'w') as package:
                package.writestr('build/libvlc.dll', b'runtime')
                package.writestr('COPYING', 'Main license')
                package.writestr('third-party/a/LICENSE', 'Codec A license')
                package.writestr('third-party/b/LICENSE', 'Codec B license')
            destination = root / 'installed'
            extract(archive, destination, 'build/')
            self.assertEqual((destination / 'notices/COPYING').read_text(), 'Main license')
            self.assertEqual((destination / 'notices/third-party/a/LICENSE').read_text(), 'Codec A license')
            self.assertEqual((destination / 'notices/third-party/b/LICENSE').read_text(), 'Codec B license')

    def test_nested_jar_copyright_and_notice_are_preserved(self):
        with TemporaryDirectory() as temporary:
            child = BytesIO()
            with ZipFile(child, 'w') as jar:
                jar.writestr('META-INF/COPYRIGHT', 'Nested copyright')
                jar.writestr('META-INF/NOTICE', 'Nested attribution')
                jar.writestr('Copyright.class', b'not license text')
            path = Path(temporary) / 'library.aar'
            with ZipFile(path, 'w') as archive:
                archive.writestr('LICENSE', 'Outer license')
                archive.writestr('classes.jar', child.getvalue())
            texts = archive_notices(path)
            self.assertEqual(set(texts), {'LICENSE', 'classes.jar!/META-INF/COPYRIGHT', 'classes.jar!/META-INF/NOTICE'})
            self.assertEqual(texts['classes.jar!/META-INF/COPYRIGHT'], 'Nested copyright')

    def test_used_go_packages_include_ancestor_and_nested_notices(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            package = root / 'internal/third_party/codec'
            package.mkdir(parents=True)
            (root / 'LICENSE').write_text('Root license')
            (package.parent / 'COPYRIGHT').write_text('Parent notice')
            (package / 'LICENSE').write_text('Codec license')
            unused = root / 'tests/unused'
            unused.mkdir(parents=True)
            (unused / 'LICENSE').write_text('Uncompiled test notice')
            paths = {path.relative_to(root).as_posix() for path in package_notice_paths(root, [package])}
            self.assertEqual(paths, {'LICENSE', 'internal/third_party/COPYRIGHT', 'internal/third_party/codec/LICENSE'})

    def test_maven_parent_license_is_inherited_but_child_override_wins(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            parent = root / 'parent.pom'
            parent.write_text('<project><licenses><license><name>Apache-2.0</name><url>https://example.org/license</url></license></licenses></project>')
            child = root / 'child.pom'
            prefix = '<project xmlns="http://maven.apache.org/POM/4.0.0"><parent><groupId>example</groupId><artifactId>parent</artifactId><version>1</version></parent>'
            child.write_text(prefix + '</project>')
            self.assertEqual(pom_information(child, {'example:parent:1': parent})['licenses'][0]['name'], 'Apache-2.0')
            child.write_text(prefix + '<licenses><license><name>MIT</name></license></licenses></project>')
            self.assertEqual(pom_information(child, {'example:parent:1': parent})['licenses'][0]['name'], 'MIT')

    def test_spdx_expression_does_not_pass_as_complete_license(self):
        self.assertFalse(full_license(' OR '.join(['LicenseRef-Example'] * 20)))
        self.assertTrue(full_license('Permission is hereby granted, free of charge. ' * 10))
