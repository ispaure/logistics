"""Logistics release names; suggestions do not create or publish tags."""
import re
import subprocess
import tomllib


def suggest_tag(root, version, channel='alpha'):
    if not re.fullmatch(r'\d+\.\d+\.\d+', version) or channel not in {'alpha','beta','main'}:
        raise ValueError('A supported app version and release channel are required.')
    prefix=f'v{version}-{channel}.'
    tags=subprocess.check_output(['git','tag','--list',prefix+'*'],cwd=root,text=True,timeout=10).splitlines()
    numbers=[int(tag[len(prefix):]) for tag in tags if tag[len(prefix):].isdigit()]
    return prefix+str(max(numbers,default=0)+1)


def source_version(root, commit):
    """Source releases follow the selected desktop project, not mobile marketing versions."""
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('A resolved source commit is required for release naming.')
    metadata = subprocess.check_output(['git', 'show', commit + ':Python/pyproject.toml'],
                                       cwd=root, text=True, timeout=10)
    version = tomllib.loads(metadata)['project']['version']
    if not isinstance(version, str) or not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('The selected source needs a supported project version.')
    return version
