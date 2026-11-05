"""Capture existing browser tools and require them only for full mobile releases.

Inspection reads Node/Playwright metadata and executable availability. It never
installs software, launches a browser, accesses accounts or changes user settings.
"""
import argparse
from dataclasses import replace
import json
import os
from pathlib import Path
import shutil
import subprocess
from uuid import uuid4

PROBE_SECONDS=10
MAX_OUTPUT=16384
PROBE="""const path=require('path'),fs=require('fs');
const selected=require.resolve(path.join(process.env.NODE_PATH,'playwright'));
for(const directory of JSON.parse(process.env.LOGISTICS_BROWSER_FIXTURE_DIRS||'[]')){
 const actual=require.resolve('playwright',{paths:[directory]});
 if(fs.realpathSync(actual)!==fs.realpathSync(selected))throw Error('Playwright package is shadowed');
}
const p=require(selected);
process.stdout.write(JSON.stringify({node:process.versions.node,
browser:p.chromium.executablePath()}));"""
REMEDY=('Open project settings and select tools.node and tools.node_modules (the directory containing Playwright). '
        'Select tools.chrome for an existing browser, or install the matching Playwright Chromium explicitly. '
        'This check never downloads tools or browsers.')


def probe(node, environment):
    result=subprocess.run([node,'-e',PROBE],env=environment,capture_output=True,text=True,timeout=PROBE_SECONDS)
    if result.returncode or len(result.stdout.encode())+len(result.stderr.encode())>MAX_OUTPUT:
        raise ValueError('Node could not inspect the selected Playwright package.')
    value=json.loads(result.stdout)
    if not isinstance(value.get('node'),str) or not isinstance(value.get('browser'),str):
        raise ValueError('Invalid browser metadata.')
    return value


def environment(values, *, inherited=None, root=None):
    """Freeze even auto-selected browser paths before isolated test caches change."""
    inherited=dict(os.environ if inherited is None else inherited)
    absolute=lambda value: str(Path(value).expanduser().absolute()) if value else ''
    node=absolute(values.get('tools.node') or shutil.which('node',path=inherited.get('PATH','')))
    modules=absolute(values.get('tools.node_modules'))
    chrome=absolute(values.get('tools.chrome'))
    root=Path.cwd() if root is None else Path(root)
    result={'LOGISTICS_NODE':node,'NODE_PATH':modules,'LOGISTICS_CHROME':chrome,
            'LOGISTICS_BROWSER_FIXTURE_DIRS':json.dumps([str(root/'mobile_build/tests'/owner) for owner in ('chat','reading')])}
    if node:
        result['PATH']=str(Path(node).parent)+os.pathsep+inherited.get('PATH','')
    if inherited.get('PLAYWRIGHT_BROWSERS_PATH'):
        result['PLAYWRIGHT_BROWSERS_PATH']=inherited['PLAYWRIGHT_BROWSERS_PATH']
    if not chrome and node and Path(node).is_file() and Path(modules,'playwright/package.json').is_file():
        try:
            result['LOGISTICS_CHROME']=probe(node,dict(inherited,**result))['browser']
        except (OSError,ValueError,subprocess.SubprocessError):
            # Preparation remains reviewable. The explicit release prerequisite
            # below fails before tests rather than silently skipping optional cases.
            pass
    return result


def inspect(*, selected=None):
    selected=dict(os.environ if selected is None else selected)
    node=selected.get('LOGISTICS_NODE','');modules=selected.get('NODE_PATH','');browser=selected.get('LOGISTICS_CHROME','')
    checks=[]
    for key,path,valid in (('node',node,Path(node).is_file() if node else False),
            ('playwright',modules,Path(modules,'playwright/package.json').is_file() if modules else False),
            ('browser',browser,Path(browser).is_file() if browser else False)):
        checks.append(dict(tool=key,path=path,ready=valid))
    if all(row['ready'] for row in checks):
        try:
            metadata=probe(node,selected)
            checks[0]['version']=metadata['node']
        except (OSError,ValueError,subprocess.SubprocessError):
            checks[0].update(ready=False,error='Selected Node/Playwright metadata inspection failed.')
    ready=all(row['ready'] for row in checks)
    return dict(schema=1,ready=ready,scope='Existing tool metadata and files; browser runtime is tested by DOM cases.',
                message='Browser tools are ready.' if ready else REMEDY,tools=checks)


def require_release_browser(hosts, subject, python, workspace):
    """Only owning release host gates opt in; ordinary developer suites may skip."""
    from build_manager import Phase
    output=Path(workspace)/('mobile-browser-prerequisites-'+uuid4().hex+'.json')
    gate=Phase('mobile-browser-prerequisites',(str(python),'-m','logistics_build.browser_tooling','--output',str(output)),
        subject.cwd,timeout=30,environment=dict(subject.environment),kind='setup',effect='inspect',
        artifacts=(str(output),),dependencies=('test-structure',) if any(p.id == 'test-structure' for p in hosts) else (),
        label='Check release browser tools',
        description='Require existing Node, Playwright and browser for all mobile DOM checks; no installation.')
    return (*(p for p in hosts if p.id == 'test-structure'),gate,
        *(replace(phase,dependencies=tuple(dict.fromkeys((*phase.dependencies,gate.id)))) for phase in hosts if phase.id != 'test-structure'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();value=inspect()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(value,indent=2)+'\n')
    print(value['message'],flush=True)
    return int(not value['ready'])


if __name__=='__main__':raise SystemExit(main())
