"""Logistics release names; suggestions do not create or publish tags."""
import re
import subprocess


def suggest_tag(root, version, channel='alpha'):
    if not re.fullmatch(r'\d+\.\d+\.\d+', version) or channel not in {'alpha','beta','main'}:
        raise ValueError('A supported app version and release channel are required.')
    prefix=f'v{version}-{channel}.'
    tags=subprocess.check_output(['git','tag','--list',prefix+'*'],cwd=root,text=True,timeout=10).splitlines()
    numbers=[int(tag[len(prefix):]) for tag in tags if tag[len(prefix):].isdigit()]
    return prefix+str(max(numbers,default=0)+1)
