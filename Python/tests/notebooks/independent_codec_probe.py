"""Cross-check synthetic exports with the independent pinned Go reader."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

from Scripts.build_retention import scratch
from features.notebooks.notebook import Notebook
from features.notebooks.ink import TOOLS
from features.notebooks.workspace import Editor


def main(output, go):
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with scratch() as workspace:
        (workspace/'go.mod').write_text('module logistics-ink-proof\n\ngo 1.26.0\n\nrequire github.com/go-go-golems/remarquee v0.0.14\n')
        shutil.copyfile(Path(__file__).with_name('independent_scene_check.go'),workspace/'main.go')
        env = dict(os.environ,GOMODCACHE=str(workspace/'modules'),GOCACHE=str(workspace/'cache'),
                   GOPATH=str(workspace/'go'),GOTOOLCHAIN='local',GOFLAGS='-mod=mod -modcacherw')
        book=Notebook.new('Synthetic native brush proof')
        for tool in TOOLS.values():
            book.page(0).add([[120,160,.2],[180,210,.5],[240,160,.8]],tool=tool,color=6,width=4)
        book.add_page()
        book.page(1).add([[100,100,.6],[400,100,.6]],tool=17,width=2)
        archive=workspace/'proof.rmdoc';archive.write_bytes(book.to_bytes())
        command=[str(Path(go).resolve()),'run','.',str(archive)]
        first=subprocess.run(command,cwd=workspace,env=env,text=True,capture_output=True,timeout=600)
        if first.returncode:
            raise RuntimeError(first.stderr[-4000:])
        created=json.loads(first.stdout)
        assert created['stroke_counts']==[8,1],created['stroke_counts']
        assert [s['Tool'] for s in created['strokes'][:8]]==list(TOOLS.values())
        book=Notebook.read(archive.read_bytes())
        editor=Editor(book)
        editor.apply(dict(op='erase',ids=[book.page(0).strokes[0].id]))
        archive.write_bytes(book.to_bytes())
        second=subprocess.run(command,cwd=workspace,env=env,text=True,capture_output=True,timeout=120)
        if second.returncode:
            raise RuntimeError(second.stderr[-4000:])
        edited=json.loads(second.stdout)
        assert edited['stroke_counts']==[7,1],edited['stroke_counts']
        output.write_text(json.dumps(dict(status='passed',created=created,erased=edited),indent=2)+'\n')
        print('Independent native scene reader accepted multi-page brush exports and erased-stroke tombstones.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--go',type=Path,required=True)
    args=parser.parse_args();main(args.output,args.go)
