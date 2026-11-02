"""Read notice inventories without importing platform libraries or using the network."""
from io import BytesIO
from pathlib import Path
import re
from zipfile import ZipFile
import xml.etree.ElementTree as ET


def is_notice(path):
    name = Path(str(path)).name.upper()
    in_license_folder = any(part.upper() in ('LICENSES', 'LICENCES') for part in Path(str(path)).parts[:-1])
    return ((in_license_folder or name.startswith(('LICENSE', 'LICENCE', 'COPYING', 'NOTICE', 'COPYRIGHT', 'UNLICENSE', 'AUTHORS', 'PATENTS')))
            and not name.endswith(('.PY', '.PYC', '.GO', '.JAVA', '.C', '.H', '.CLASS', '.SO', '.DLL')))


def archive_notices(path):
    """Keep artifact notices, including the JARs nested inside Android AARs."""
    texts = {}
    def read(archive, prefix='', depth=0):
        for item in archive.infolist():
            if item.is_dir():
                continue
            if is_notice(item.filename):
                texts[prefix + item.filename] = archive.read(item).decode('utf-8', errors='replace').strip()
            elif item.filename.endswith(('.jar', '.zip', '.imy')) and depth < 2:
                with ZipFile(BytesIO(archive.read(item))) as child:
                    read(child, prefix + item.filename + '!/', depth + 1)
    with ZipFile(path) as archive:
        read(archive)
    return texts


def pom_information(path, parents=None, seen=None):
    """Keep publisher license declarations and attribution without inferring permission."""
    root = ET.parse(path).getroot()
    for element in root.iter():
        element.tag = element.tag.rsplit('}', 1)[-1]
    result = dict(name=root.findtext('name') or '', source=root.findtext('url') or root.findtext('scm/url') or '',
                licenses=[dict(name=item.findtext('name') or '', url=item.findtext('url') or '')
                          for item in root.findall('licenses/license')],
                organization=root.findtext('organization/name') or '')
    parent = root.find('parent')
    if parent is not None and parents:
        identity = ':'.join(parent.findtext(field) or '' for field in ('groupId', 'artifactId', 'version'))
        seen = set() if seen is None else seen
        if identity in parents and identity not in seen:
            seen.add(identity)
            inherited = pom_information(parents[identity], parents, seen)
            for field in ('source', 'licenses', 'organization'):
                result[field] = result[field] or inherited[field]
    return result


def package_notice_paths(module_root, package_directories, embedded=()):
    """Include package-local and ancestor notices, plus module-wide LICENSES trees."""
    root = Path(module_root).resolve()
    directories = {root}
    for directory in package_directories:
        directory = Path(directory).resolve()
        if directory.is_relative_to(root):
            directories.add(directory)
            directories.update(parent for parent in directory.parents if parent.is_relative_to(root))
    files = {path for directory in directories for path in directory.iterdir()
             if path.is_file() and not path.is_symlink() and is_notice(path)}
    for name in ('LICENSES', 'licenses', 'LICENCES', 'licences'):
        directory = root / name
        if directory.is_dir():
            files.update(path for path in directory.rglob('*') if path.is_file() and not path.is_symlink())
    files.update(Path(path) for path in embedded if Path(path).is_file()
                 and Path(path).resolve().is_relative_to(root) and is_notice(path))
    return sorted(files)


def full_license(text):
    """An SPDX expression or metadata label is not a complete license."""
    return bool(re.search(r'permission is hereby granted|redistribution and use|terms and conditions|'
                          r'gnu (?:lesser )?general public license|this is free and unencumbered software',
                          text, re.IGNORECASE)) and len(text) > 300
