import json
from pathlib import Path
import struct
from tempfile import TemporaryDirectory
import unittest
import xml.etree.ElementTree as ET

from mobile_build.build_support import icon_build


def png_header(path):
    data = path.read_bytes()
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise AssertionError('Invalid PNG: ' + str(path))
    return (*struct.unpack('>II', data[16:24]), data[25])


class IconBuildTests(unittest.TestCase):
    def test_ios_catalog_has_opaque_sized_artwork_and_all_appearances(self):
        root = icon_build.ROOT / 'ios'
        catalog = json.loads((root / 'Contents.json').read_text())
        appearances = set()
        for entry in catalog['images']:
            width, height, color_type = png_header(root / entry['filename'])
            pixels = round(float(entry['size'].split('x')[0]) * float(entry.get('scale', '1x')[:-1]))
            self.assertEqual((width, height, color_type), (pixels, pixels, 2))
            if entry['idiom'] == 'universal':
                appearances.add(entry.get('appearances', [{'value': 'light'}])[0]['value'])
        self.assertEqual(appearances, {'light', 'dark', 'tinted'})

    def test_android_density_night_and_themed_resources_resolve(self):
        root = icon_build.ROOT / 'android'
        for density, factor in icon_build.DENSITIES.items():
            for qualifier in ['', '-night']:
                folder = root / f'mipmap{qualifier}-{density}'
                for name, dp in [('ic_launcher', 48), ('ic_launcher_round', 48),
                                 ('ic_launcher_foreground', 108), ('splash', 48)]:
                    self.assertEqual(png_header(folder / (name + '.png'))[:2], (round(dp * factor),) * 2)
            mask = root / f'mipmap-{density}/ic_launcher_monochrome.png'
            self.assertEqual(png_header(mask), (round(108 * factor), round(108 * factor), 6))
        key = '{http://schemas.android.com/apk/res/android}drawable'
        for version in [26, 33]:
            for name in ['ic_launcher', 'ic_launcher_round']:
                tree = ET.parse(root / f'mipmap-anydpi-v{version}/{name}.xml').getroot()
                self.assertEqual(tree.find('foreground').get(key), '@mipmap/ic_launcher_foreground')
                self.assertEqual(tree.find('background').get(key), '@color/logisticsIconBackground')
                if version == 33:
                    self.assertEqual(tree.find('monochrome').get(key), '@mipmap/ic_launcher_monochrome')
                else:
                    self.assertIsNone(tree.find('monochrome'))

    def test_generated_projects_receive_icons_on_repeated_updates(self):
        with TemporaryDirectory() as directory:
            project = Path(directory)
            catalog = project / 'LogisticsMobile/Images.xcassets'
            splash = catalog / 'Splash.imageset'
            splash.mkdir(parents=True)
            (splash / 'Contents.json').write_text(json.dumps({'images': [{'filename': 'splash.png'}]}))
            (project / 'app/src/main/res').mkdir(parents=True)
            for _ in range(2):
                icon_build.configure_ios(project)
                icon_build.configure_android(project)
            self.assertEqual((splash / 'splash.png').read_bytes(), (icon_build.ROOT / 'ios/icon-1024.png').read_bytes())
            self.assertTrue((catalog / 'AppIcon.appiconset/icon-dark-1024.png').is_file())
            self.assertTrue((project / 'app/src/main/res/mipmap-anydpi-v33/ic_launcher.xml').is_file())


if __name__ == '__main__':
    unittest.main()
