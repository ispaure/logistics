"""Check staged/tracked source for ignored paths and recognizable private keys.

Report paths and categories only, never matching values. This supplements careful
review; arbitrary provider tokens cannot all be identified from their syntax.
"""
from pathlib import Path
import re
import subprocess

PATTERNS = {
    'private key': re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH |ENCRYPTED )?PRIVATE KEY-----'),
    'GitHub token': re.compile(rb'gh[pousr]_[A-Za-z0-9]{30,}'),
    'AWS access key': re.compile(rb'AKIA[0-9A-Z]{16}'),
}
TEXT = {'.py', '.md', '.json', '.toml', '.yaml', '.yml', '.ini', '.txt', '.in',
        '.sh', '.bat', '.cmd', '.command', '.go', '.java'}


def categories(data):
    return [name for name, pattern in PATTERNS.items() if pattern.search(data)]


def check(root):
    root = Path(root)
    names = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root)
    ignored = subprocess.run(['git', 'check-ignore', '--no-index', '-z', '--stdin'],
                             cwd=root, input=names, capture_output=True)
    if ignored.returncode not in (0, 1):
        print('Could not inspect Git ignore rules.')
        return 1
    errors = [f'Ignored path is tracked: {name.decode(errors="replace")}'
              for name in ignored.stdout.split(b'\0') if name]
    records = subprocess.check_output(['git', 'ls-files', '--stage', '-z'], cwd=root)
    selected = []
    for record in records.split(b'\0'):
        if not record:
            continue
        metadata, name = record.split(b'\t', 1)
        mode, oid, stage = metadata.split()
        if stage != b'0':
            errors.append('Unmerged path: ' + name.decode(errors='replace'))
        elif mode in (b'100644', b'100755') and Path(name.decode()).suffix.lower() in TEXT:
            selected.append((oid, name))
    result = subprocess.run(['git', 'cat-file', '--batch'], cwd=root,
                            input=b''.join(oid + b'\n' for oid, _ in selected), capture_output=True, check=True)
    offset = 0
    for _, name in selected:
        end = result.stdout.index(b'\n', offset)
        _, kind, size = result.stdout[offset:end].split()
        if kind != b'blob':
            raise ValueError('Expected a source blob')
        offset = end + 1
        data = result.stdout[offset:offset + int(size)]
        offset += int(size) + 1
        for category in categories(data):
            errors.append(f'{category} detected in staged source: {name.decode(errors="replace")}')
    for error in errors:
        print(error)
    print(f'Source hygiene: {len(selected)} indexed text files; {len(errors)} violations.')
    return int(bool(errors))
