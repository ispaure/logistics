"""Install pre-sized launcher artwork; Pillow is needed only to regenerate it."""
import argparse
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1] / 'resources/icons'
DENSITIES = {'mdpi': 1, 'hdpi': 1.5, 'xhdpi': 2, 'xxhdpi': 3, 'xxxhdpi': 4}


def configure_ios(project):
    project = Path(project)
    destination = project / 'LogisticsMobile/Images.xcassets'
    if not destination.is_dir():
        raise ValueError('Expected the generated iOS image catalog.')
    shutil.copytree(ROOT / 'ios', destination / 'AppIcon.appiconset', dirs_exist_ok=True)
    # Briefcase uses the app icon for launch artwork too. Keep its scale metadata.
    splash = destination / 'Splash.imageset'
    metadata = json.loads((splash / 'Contents.json').read_text())
    for entry in metadata['images']:
        if entry.get('filename'):
            shutil.copyfile(ROOT / 'ios/icon-1024.png', splash / entry['filename'])


def configure_android(project):
    destination = Path(project) / 'app/src/main/res'
    if not destination.is_dir():
        raise ValueError('Expected the generated Android resource directory.')
    shutil.copytree(ROOT / 'android', destination, dirs_exist_ok=True)


def generate(light, dark, monochrome):
    """Resize complete artwork without cropping, retouching or changing its colors.

    iOS requires opaque icons. Android themed icons consume alpha rather than RGB,
    so their separate mask encodes the supplied grayscale shading as opacity.
    """
    from PIL import Image, ImageChops, ImageOps

    images = {}
    for name, path in [('light', light), ('dark', dark), ('monochrome', monochrome)]:
        with Image.open(path) as source:
            if source.width != source.height or source.width < 1024:
                raise ValueError('Supply square artwork at least 1024 pixels wide.')
            images[name] = source.convert('RGBA')

    def save(image, path, size, background=None, inset=False):
        path.parent.mkdir(parents=True, exist_ok=True)
        edge = round(size * 2 / 3) if inset else size
        result = image.resize((edge, edge), Image.Resampling.LANCZOS)
        if inset:
            canvas = Image.new('RGBA', (size, size))
            canvas.paste(result, ((size - edge) // 2, (size - edge) // 2))
            result = canvas
        if background:
            canvas = Image.new('RGBA', result.size, background)
            result = Image.alpha_composite(canvas, result).convert('RGB')
        result.save(path, optimize=True)

    ios = ROOT / 'ios'
    entries = []
    # Retain legacy slots for the iOS 15 minimum, plus modern appearance slots.
    for idiom, sizes, scales in [('iphone', [20, 29, 40, 60], [2, 3]),
                                 ('ipad', [20, 29, 40, 76], [1, 2])]:
        for size in sizes:
            for scale in scales:
                pixels = size * scale
                save(images['light'], ios / f'icon-{pixels}.png', pixels, '#ffffff')
                entries.append(dict(idiom=idiom, size=f'{size}x{size}', scale=f'{scale}x',
                                    filename=f'icon-{pixels}.png'))
    save(images['light'], ios / 'icon-167.png', 167, '#ffffff')
    entries.append(dict(idiom='ipad', size='83.5x83.5', scale='2x', filename='icon-167.png'))
    entries.append(dict(idiom='ios-marketing', size='1024x1024', scale='1x', filename='icon-1024.png'))
    for name, appearance, background in [('light', None, '#ffffff'),
                                          ('dark', 'dark', '#03152f'),
                                          ('monochrome', 'tinted', '#ffffff')]:
        filename = 'icon-1024.png' if name == 'light' else f'icon-{name}-1024.png'
        save(images[name], ios / filename, 1024, background)
        entry = dict(idiom='universal', platform='ios', size='1024x1024', filename=filename)
        if appearance:
            entry['appearances'] = [dict(appearance='luminosity', value=appearance)]
        entries.append(entry)
    (ios / 'Contents.json').write_text(json.dumps(dict(images=entries, info=dict(version=1, author='xcode')), indent=2) + '\n')

    android = ROOT / 'android'
    mask = images['monochrome'].copy()
    mask.putalpha(ImageChops.multiply(ImageOps.invert(mask.convert('L')), mask.getchannel('A')))
    for density, factor in DENSITIES.items():
        for name, qualifier in [('light', ''), ('dark', '-night')]:
            folder = android / f'mipmap{qualifier}-{density}'
            for filename in ['ic_launcher.png', 'ic_launcher_round.png']:
                save(images[name], folder / filename, round(48 * factor))
            save(images[name], folder / 'ic_launcher_foreground.png', round(108 * factor), inset=True)
            save(images[name], folder / 'splash.png', round(48 * factor))
        save(mask, android / f'mipmap-{density}/ic_launcher_monochrome.png', round(108 * factor), inset=True)
    for qualifier, color in [('', '#ffffff'), ('-night', '#03152f')]:
        path = android / f'values{qualifier}/launcher_colors.xml'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f'<resources><color name="logisticsIconBackground">{color}</color></resources>\n')
    for version in [26, 33]:
        folder = android / f'mipmap-anydpi-v{version}'
        folder.mkdir(parents=True, exist_ok=True)
        mono = '\n    <monochrome android:drawable="@mipmap/ic_launcher_monochrome"/>' if version == 33 else ''
        xml = ('<?xml version="1.0" encoding="utf-8"?>\n'
               '<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">\n'
               '    <background android:drawable="@color/logisticsIconBackground"/>\n'
               '    <foreground android:drawable="@mipmap/ic_launcher_foreground"/>'
               + mono + '\n</adaptive-icon>\n')
        for filename in ['ic_launcher.xml', 'ic_launcher_round.xml']:
            (folder / filename).write_text(xml)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('light', type=Path)
    parser.add_argument('dark', type=Path)
    parser.add_argument('monochrome', type=Path)
    args = parser.parse_args()
    generate(args.light, args.dark, args.monochrome)
