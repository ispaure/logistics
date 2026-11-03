"""Refresh pinned Qt source attributions; downloaded trees use managed scratch storage."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html.parser import HTMLParser
from html import unescape
import json
from pathlib import Path, PurePosixPath
import posixpath
import os
import subprocess
from urllib.request import urlopen
from urllib.parse import urljoin

from .build_retention import scratch

ROOT = Path(__file__).resolve().parents[1]
QT_MODULES = ('qtbase', 'qtimageformats', 'qtsvg', 'qtdeclarative', 'qt3d', 'qtcharts',
              'qtdatavis3d', 'qtgraphs', 'qthttpserver', 'qtlocation', 'qtlottie', 'qtmultimedia',
              'qtnetworkauth', 'qtpositioning', 'qtquick3d', 'qtquick3dphysics', 'qtquicktimeline',
              'qtremoteobjects', 'qtscxml', 'qtsensors', 'qtserialbus', 'qtserialport', 'qtshadertools',
              'qtspeech', 'qttools', 'qtvirtualkeyboard', 'qtwebchannel', 'qtwebengine',
              'qtwebsockets', 'qtwebview')


def fetch(url):
    with urlopen(url, timeout=45) as response:
        return response.read()


class QtNoticePage(HTMLParser):
    """Extract the license blocks, not the surrounding Qt documentation/navigation."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.pre, self.h1, self.title_tag = False, False, False
        self.blocks, self.name, self.title, self.links = [], [], [], set()

    def handle_starttag(self, tag, attrs):
        if tag == 'pre':
            self.pre = True
            self.blocks.append([])
        if tag == 'h1':
            self.h1 = True
        if tag == 'title':
            self.title_tag = True
        if tag == 'a':
            href = dict(attrs).get('href', '')
            if href.startswith('qtwebengine-3rdparty-') and href.endswith('.html'):
                self.links.add(href)

    def handle_endtag(self, tag):
        if tag == 'pre':
            self.pre = False
        if tag == 'h1':
            self.h1 = False
        if tag == 'title':
            self.title_tag = False

    def handle_data(self, text):
        if self.pre:
            self.blocks[-1].append(text)
        if self.h1:
            self.name.append(text)
        if self.title_tag:
            self.title.append(text)


def refresh_webengine(version, resources, url):
    retrieved = datetime.now(timezone.utc).date().isoformat()
    def page(url):
        parser = QtNoticePage()
        parser.feed(fetch(url).decode('utf-8'))
        if version not in ''.join(parser.title):
            raise ValueError('Upstream WebEngine documentation version changed: ' + url)
        return parser
    index = page(url)
    def component(link):
        source = urljoin(url, link)
        data = page(source)
        texts = [unescape(''.join(block).strip()) for block in data.blocks]
        return dict(name=''.join(data.name).strip(), source=source, version='', license='',
                    text='\n\n'.join(filter(None, texts)), missing_notice=not any(texts),
                    scope=f'Upstream Qt WebEngine {version} source notices, retrieved {retrieved}; optional components may not be in this binary.')
    with ThreadPoolExecutor(max_workers=6) as pool:
        components = list(pool.map(component, sorted(index.links)))
    if not components:
        raise ValueError('No WebEngine attribution links found')
    result = dict(schema=1, version=version, source=url, components=components)
    (Path(resources) / 'qtwebengine-source-notices.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return result


def refresh_rclone(version, resources, go):
    from mobile_build.build_support.license_build import inventory_module
    reader = inventory_module()
    downloaded = json.loads(subprocess.check_output([str(go), 'mod', 'download', '-json',
        'github.com/rclone/rclone@v' + version], cwd=ROOT / 'mobile_build/rclone_bridge', text=True))
    source = Path(downloaded['Dir']).resolve()
    modules, packages = {}, {}
    decoder = json.JSONDecoder()
    for platform in ('darwin', 'windows', 'linux'):
        for arch in ('arm64', 'amd64'):
            env = dict(os.environ, GOOS=platform, GOARCH=arch, CGO_ENABLED='1', GOTOOLCHAIN='local')
            raw = subprocess.check_output([str(go), 'list', '-mod=readonly', '-tags', 'cmount', '-deps', '-json', '.'],
                                          cwd=source, text=True, env=env)
            while raw.strip():
                item, end = decoder.raw_decode(raw.lstrip())
                raw = raw.lstrip()[end:]
                module = item.get('Module', {})
                if module.get('Dir'):
                    key = module['Path']
                    modules[key] = module
                    packages.setdefault(key, set()).add(Path(item['Dir']))
    components = []
    for name, module in sorted(modules.items()):
        directory = Path(module['Dir']).resolve()
        files = reader.package_notice_paths(directory, packages[name])
        if not files:
            raise ValueError('No rclone dependency notice: ' + name)
        components.append(dict(name=name, version=module.get('Version', 'v' + version),
            source='https://' + name, license='',
            text='\n\n'.join(path.relative_to(directory).as_posix() + '\n\n' + path.read_text(encoding='utf-8', errors='replace')
                             for path in files),
            scope='Pinned rclone source dependency notices, union of desktop OS/architecture graphs including cmount support.'))
    goroot = Path(subprocess.check_output([str(go), 'env', 'GOROOT'], text=True).strip())
    components.append(dict(name='Go runtime', version='', license='BSD-3-Clause', source='https://go.dev',
        text=(goroot / 'LICENSE').read_text(), scope='Go runtime license accompanying the rclone source dependency collection.'))
    result = dict(schema=1, version=version, components=components)
    (Path(resources) / 'rclone-dependency-notices.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return result


def refresh_qt(version, resources, modules=QT_MODULES):
    resources = Path(resources)
    index_path = resources / 'qt-source-index.json'
    index = json.loads(index_path.read_text()) if index_path.is_file() else None
    if index and index['version'] == version:
        revisions = {name: value['revision'] for name, value in index['modules'].items()}
        modules = tuple(revisions)
        missing_modules = index['unavailable_modules']
    else:
        release = json.loads(fetch(f'https://api.github.com/repos/qt/qt5/git/trees/v{version}'))
        revisions = {item['path']: item['sha'] for item in release['tree'] if item['mode'] == '160000'}
        missing_modules = [name for name in modules if name not in revisions]
        modules = tuple(name for name in modules if name in revisions)
    def source(module, path):
        return f'https://raw.githubusercontent.com/qt/{module}/{revisions[module]}/{path}'
    with scratch() as temporary:
        def tree(module):
            data = fetch(f'https://api.github.com/repos/qt/{module}/git/trees/{revisions[module]}?recursive=1')
            (temporary / (module + '.json')).write_bytes(data)
            value = json.loads(data)
            if value.get('truncated'):
                raise ValueError('Incomplete upstream source tree: ' + module)
            return module, value['tree']
        if index and index['version'] == version:
            paths = [(name, path) for name, value in index['modules'].items() for path in value['attributions']]
        else:
            with ThreadPoolExecutor(max_workers=4) as pool:
                trees = dict(pool.map(tree, modules))
            paths = [(module, item['path']) for module, entries in trees.items() for item in entries
                     if item['path'].startswith('src/') and item['path'].endswith('qt_attribution.json')]
        def attribution(item):
            module, path = item
            data = json.loads(fetch(source(module, path)), strict=False)
            return [(module, path, entry) for entry in (data if isinstance(data, list) else [data])]
        with ThreadPoolExecutor(max_workers=6) as pool:
            records = [entry for entries in pool.map(attribution, paths) for entry in entries]
        requested, attributed = set(), []
        for module, path, entry in records:
            files = entry.get('LicenseFile', entry.get('LicenseFiles', []))
            files = [files] if isinstance(files, str) else list(files)
            if entry.get('CopyrightFile'):
                files.append(entry['CopyrightFile'])
            urls = [source(module, posixpath.normpath(str(PurePosixPath(path).parent / name))) for name in files]
            if not urls:
                identifier = entry.get('LicenseId', '')
                if identifier and not any(char in identifier for char in ' ()'):
                    urls = [source('qtbase', 'LICENSES/' + identifier + '.txt')]
            requested.update(urls)
            attributed.append((module, path, entry, urls))
        def license_text(url):
            return url, fetch(url).decode('utf-8', errors='replace').strip()
        with ThreadPoolExecutor(max_workers=6) as pool:
            texts = dict(pool.map(license_text, sorted(requested)))
        components = []
        for module, path, entry, urls in attributed:
            copyright = entry.get('Copyright', '')
            if isinstance(copyright, list):
                copyright = '\n'.join(copyright)
            components.append(dict(name=entry.get('Name') or entry['Id'], version=entry.get('Version', ''),
                license=entry.get('License', ''), source=entry.get('Homepage', ''),
                text='\n\n'.join(filter(None, [copyright, *(texts[url] for url in urls)])),
                provenance=source(module, path), license_sources=urls,
                scope=f'Upstream Qt {version} source notices; optional and platform-specific components may not be in this binary.',
                missing_notice=not bool(urls)))
        result = dict(schema=1, version=version, modules=list(modules), unavailable_modules=missing_modules,
                      components=sorted(components, key=lambda item: item['name'].casefold()))
        resources = Path(resources)
        resources.mkdir(parents=True, exist_ok=True)
        (resources / 'qt-source-notices.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qt-version')
    parser.add_argument('--webengine-version')
    parser.add_argument('--webengine-url', default='https://doc-snapshots.qt.io/qtwebengine/qtwebengine-licensing.html')
    parser.add_argument('--rclone-version')
    parser.add_argument('--go', type=Path, default=ROOT / 'mobile_build/.tools/go/bin/go')
    args = parser.parse_args()
    if not any((args.qt_version, args.webengine_version, args.rclone_version)):
        parser.error('Select a pinned component to refresh.')
    if args.qt_version:
        result = refresh_qt(args.qt_version, ROOT / 'Python/services/licenses')
        print(f"Collected {len(result['components'])} Qt source attributions from {len(result['modules'])} modules.")
        print('Modules absent from the Qt release:', result['unavailable_modules'])
    if args.webengine_version:
        engine = refresh_webengine(args.webengine_version, ROOT / 'Python/services/licenses', args.webengine_url)
        print('Collected WebEngine source notices:', len(engine['components']))
    if args.rclone_version:
        rclone = refresh_rclone(args.rclone_version, ROOT / 'Python/services/licenses', args.go)
        print('Collected rclone source dependency notices:', len(rclone['components']))


if __name__ == '__main__':
    main()
