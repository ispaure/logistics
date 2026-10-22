"""Generate public standalone encrypted-comic fixtures, without remote credentials."""
import base64
from io import BytesIO
import importlib.util
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from commonUtils.archives.zip_access import open_archive


def generate(destination):
    password = 'synthetic-comic-password'
    spec = importlib.util.spec_from_file_location('native_comic_fixtures',
        Path(__file__).parent / 'native_tests/tests/logisticsmobile/fixtures.py')
    fixtures = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixtures)
    image = fixtures.png_page()
    metadata = b'<ComicInfo><Title>Standalone encrypted comic</Title><Manga>YesAndRightToLeft</Manga></ComicInfo>'
    members = {'page10.png': image, 'page2.png': image, 'ComicInfo.xml': metadata}
    encrypted = BytesIO()
    with open_archive(encrypted, 'w', password=password) as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    with TemporaryDirectory() as folder:
        root = Path(folder)
        for name, data in members.items():
            (root / name).write_bytes(data)
        subprocess.run(['zip', '-q', '-P', password, 'legacy.cbz', *members], cwd=root, check=True)
        legacy = (root / 'legacy.cbz').read_bytes()
    destination.write_text(json.dumps(dict(password=password, page=base64.b64encode(image).decode(),
        aes=base64.b64encode(encrypted.getvalue()).decode(), legacy=base64.b64encode(legacy).decode()), indent=2)+'\n')


if __name__ == '__main__':
    generate(Path(__file__).parent / 'native_tests/tests/logisticsmobile/comic_fixture.json')
