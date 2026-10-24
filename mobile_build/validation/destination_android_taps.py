"""Native taps/checkpoints for the separately installed disposable Destination QA app."""
import argparse
import json,re,subprocess,time
from pathlib import Path
from xml.etree import ElementTree as E
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--serial', required=True)
parser.add_argument('--output', type=Path, required=True)
args=parser.parse_args()
root=args.output
root.mkdir(parents=True, exist_ok=True)
serial=args.serial
package='io.github.ispaure.logisticsdestinationqa'
def adb(*args,check=True):
 return subprocess.run(['adb','-s',serial,*args],check=check,capture_output=True,timeout=20)
def state():
 return json.loads(adb('shell','run-as',package,'cat','cache/destination-state.json').stdout)
def nodes():
 adb('shell','uiautomator','dump','/sdcard/destination-ui.xml')
 text=adb('shell','cat','/sdcard/destination-ui.xml').stdout
 (root/'android-ui.xml').write_bytes(text)
 return list(E.fromstring(text).iter('node'))
def click(label=None,kind=None,contains=None):
 for n in nodes():
  if label is not None and label not in (n.get('text'),n.get('content-desc')):continue
  if kind is not None and not n.get('class','').endswith(kind):continue
  if contains is not None and contains not in n.get('text',''):continue
  if n.get('enabled')!='true':continue
  x1,y1,x2,y2=map(int,re.findall(r'\d+',n.get('bounds')))
  print('Tap', label or kind, flush=True)
  adb('shell','input','tap',str((x1+x2)//2),str((y1+y2)//2));return
 raise RuntimeError('Control absent '+str(label))
def wait_phase(phase):
 for _ in range(100):
  s=state()
  if s['phase']==phase:return
  if s['phase']=='complete':raise RuntimeError(s)
  time.sleep(.1)
 raise RuntimeError(state())
for _ in range(100):
 try:
  current=state();break
 except (subprocess.CalledProcessError,json.JSONDecodeError):time.sleep(.2)
else:raise RuntimeError('QA app did not become ready')
print(current,flush=True)
if current['phase']=='save-ui':
 # A fresh launch starts with the untouched picker.
 click('New folder',kind='Button')
 time.sleep(.6)
 click('New folder name',kind='EditText')
 adb('shell','input','text','Native%sfolder')
 adb('shell','input','keyevent','4')
 click('Create',kind='Button')
 time.sleep(.4)
 click('Source.md',kind='EditText')
 adb('shell','input','keyevent','KEYCODE_MOVE_END')
 for _ in range(9):adb('shell','input','keyevent','KEYCODE_DEL')
 adb('shell','input','text','Native%ssaved')
 adb('shell','input','keyevent','4')
 click('Save here',kind='Button')
 wait_phase('move-ui');click('Move here',kind='Button')
for phase in ('hidden-light','hidden-tiles','hidden-dark'):
 wait_phase(phase)
 if phase=='hidden-dark':
  adb('shell','cmd','uimode','night','yes');time.sleep(.5)
 (root/('android-'+phase+'.png')).write_bytes(adb('exec-out','screencap','-p').stdout)
 adb('shell','run-as',package,'touch','cache/destination-command')
for _ in range(100):
 if state()['phase']=='complete':break
 time.sleep(.1)
result=json.loads(adb('shell','run-as',package,'cat','cache/destination-result.json').stdout)
(root/'android-result.json').write_text(json.dumps(result,indent=2))
for phase in ('light','tiles','dark','search'):
 (root/('android-hidden-'+phase+'.png')).write_bytes(adb('exec-out','run-as',package,'cat','cache/hidden-'+phase+'.png').stdout)
print(result,flush=True)
adb('shell','cmd','uimode','night','no')
assert result['success']
