"""Collect notices from resolved native artifacts; no downloads or cache guessing."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
from zipfile import is_zipfile


def inventory_module():
    # This file is also copied beside license_inventory.py in generated projects.
    local = Path(__file__).with_name('license_inventory.py')
    path = local if local.is_file() else Path(__file__).resolve().parents[2] / 'Python/services/license_inventory.py'
    spec = importlib.util.spec_from_file_location('logistics_license_inventory', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def collect_android(inventory, resources):
    reader = inventory_module()
    resources = Path(resources)
    known = {item['module']: item for item in json.loads((resources / 'native.json').read_text()) if 'module' in item}
    supplements = resources / 'android.json'
    supplements = json.loads(supplements.read_text()) if supplements.is_file() else {}
    result = []
    for artifact in inventory['artifacts']:
        path = Path(artifact['file'])
        module, version = artifact['module'], artifact['version']
        published = reader.pom_information(artifact['pom'], inventory.get('poms')) if artifact.get('pom') else {}
        texts = reader.archive_notices(path) if is_zipfile(path) else {}
        fallback = known.get(module, {})
        supplement = supplements.get(module, {})
        supplement = supplement if supplement.get('version') == version else {}
        license_names = [item['name'] for item in published.get('licenses', ())]
        # A POM declaration is kept separate from a complete publisher notice.
        declarations = '\n'.join(' · '.join(filter(None, (item['name'], item['url'])))
                                 for item in published.get('licenses', ()))
        files = []
        if not texts:
            files = list(fallback.get('files', ()))
            if any('apache' in name.lower() for name in license_names) and not files:
                files.append('Apache-2.0.txt')
            if any('android software development kit' in name.lower() for name in license_names):
                files.append('Google-Android-SDK-Terms.txt')
            if any('ml kit' in name.lower() for name in license_names):
                files.extend(('Google-MLKit-Terms.txt', 'Google-APIs-Terms.txt', 'Google-MLKit-GenAI-Terms.txt'))
            if any(name.lower() == 'cc0' for name in license_names):
                files.append('CC0-1.0.txt')
        files.extend(supplement.get('files', ()))
        for name in files:
            texts[name] = (resources / name).read_text(encoding='utf-8')
        sections = [f'{name}\n\n{text}' for name, text in sorted(texts.items())]
        if published.get('organization'):
            sections.insert(0, 'Publisher: ' + published['organization'])
        if declarations:
            sections.insert(0, 'Publisher license declaration:\n' + declarations)
        if fallback.get('note'):
            sections.append(fallback['note'])
        if supplement.get('note'):
            sections.append(supplement['note'])
        missing_notice = not bool(texts) or supplement.get('notice_complete') is False
        if missing_notice:
            sections.append('The published artifact did not supply a complete license notice.')
        source = supplement.get('source') or published.get('source') or fallback.get('source', '')
        if fallback.get('version') and not supplement.get('source') and not published.get('source'):
            source = source.replace('/' + fallback['version'] + '/', '/' + version + '/').replace('-' + fallback['version'] + '.', '-' + version + '.')
        result.append(dict(module=module, name=supplement.get('name') or fallback.get('name') or published.get('name') or module,
            version=version, license=supplement.get('license') or ' / '.join(license_names) or fallback.get('license', ''),
            source=source, text='\n\n'.join(sections),
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(), missing_notice=missing_notice))
    merged = {}
    for item in result:
        identity = item['module'], item['version']
        if identity not in merged:
            merged[identity] = item
            item['artifact_sha256'] = [item.pop('sha256')]
        else:
            previous = merged[identity]
            if item['sha256'] not in previous['artifact_sha256']:
                previous['artifact_sha256'].append(item['sha256'])
            if item['text'] != previous['text']:
                previous['text'] += '\n\nAdditional artifact notices:\n\n' + item['text']
            previous['missing_notice'] &= item['missing_notice']
    return dict(schema=1, platform='android', components=sorted(merged.values(), key=lambda item: item['module']),
                missing_pom_metadata=len(inventory.get('pomFailures', ())))


def configure_android(project, python):
    project = Path(project)
    destination = project / 'app/logistics-license-tools'
    destination.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[2]
    for source in (Path(__file__), root / 'Python/services/license_inventory.py',
                   Path(__file__).with_name('android_licenses.gradle')):
        shutil.copyfile(source, destination / source.name)
    shutil.copytree(root / 'Python/services/licenses', destination / 'licenses', dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('python.json', 'qt*-notices.json', 'qt-source-index.json',
                                                 'rclone-dependency-notices.json'))
    (destination / 'python.txt').write_text(str(python), encoding='utf-8')
    gradle = project / 'app/build.gradle'
    text = gradle.read_text()
    line = 'apply from: "logistics-license-tools/android_licenses.gradle"'
    if line not in text:
        gradle.write_text(text.rstrip() + '\n' + line + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--resources', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    data = collect_android(json.loads(args.inventory.read_text()), args.resources)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
