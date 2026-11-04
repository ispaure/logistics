"""Execute the production Android touch method against a small host JVM fixture.

This checks event policy and parent interception, not Android framework behavior.
The production method is extracted unchanged; fixtures supply only platform APIs.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from logistics_build.build_retention import scratch
from mobile_build.deployment import manager_settings

FIXTURE = r'''
public class TapHarness {
  static class MotionEvent {
    static final int ACTION_DOWN=0,ACTION_UP=1,ACTION_MOVE=2,ACTION_CANCEL=3,TOOL_TYPE_FINGER=1,FLAG_CANCELED=32;
    int action,tool,count,flags;float x,y;long time;
    MotionEvent(int a,float px,float py,int t,int c,int f,long ms){action=a;x=px;y=py;tool=t;count=c;flags=f;time=ms;}
    int getActionMasked(){return action;} int getToolType(int i){return tool;} int getPointerCount(){return count;}
    int getFlags(){return flags;} float getX(){return x;} float getY(){return y;}
    long getEventTime(){return time;} long getDownTime(){return 0;}
  }
  static class Matrix {boolean invert(Matrix m){return true;} void mapPoints(float[] p){} void postTranslate(float x,float y){} }
  static class Drawable {int getIntrinsicWidth(){return 400;}int getIntrinsicHeight(){return 800;}}
  static class Display {float density=1;}
  static class Resources {Display getDisplayMetrics(){return new Display();}}
  static class ViewConfiguration {static ViewConfiguration get(Object c){return new ViewConfiguration();}float getScaledTouchSlop(){return 8;}}
  static class Detector {int events;void onTouchEvent(MotionEvent e){events++;}boolean isInProgress(){return false;}}
  static class Parent {boolean everDisallowed;void requestDisallowInterceptTouchEvent(boolean value){everDisallowed|=value;}}
  static class Listener {boolean enabled=true;int taps,pages,toggles;float x,y;
    boolean imageTaps(){return enabled;}void tap(float px,float py){taps++;x=px;y=py;}
    void page(int direction){pages+=direction;}void toggleControls(){toggles++;}}
  static class Canvas {
    Listener listener=new Listener();Matrix matrix=new Matrix();Detector detector=new Detector();Parent parent=new Parent();
    float zoom=1,startX,startY,lastX,lastY;boolean finger,moved,multiplePointers,verticalPaging=true;
    boolean magnifierEnabled,lensActive,lensConsumed,touchActive,edgeContact,lensControlUpdatePending;
    Runnable hold,lensControlUpdate;int scheduledHolds;
    Resources getResources(){return new Resources();}Object getContext(){return null;}Parent getParent(){return parent;}
    int getWidth(){return 400;}int getHeight(){return 800;}int getPaddingLeft(){return 0;}int getPaddingTop(){return 0;}
    Drawable getDrawable(){return new Drawable();}void dismissMagnifier(){lensActive=false;}
    void postDelayed(Runnable r,int ms){scheduledHolds++;}void removeCallbacks(Runnable r){}void postOnAnimation(Runnable r){}void postInvalidateOnAnimation(){}
    void constrain(){}boolean performClick(){listener.toggleControls();return true;}
    __METHOD__
  }
  static int checks=0;
  static void check(boolean value,String label){if(!value)throw new AssertionError(label);checks++;}
  static boolean event(Canvas c,int action,float x,float y,int tool,int count,int flags,long time){return c.onTouchEvent(new MotionEvent(action,x,y,tool,count,flags,time));}
  static void finger(Canvas c,int action,float x,float y,long time){event(c,action,x,y,1,1,0,time);}
  public static void main(String[] args){
    for(float edge:new float[]{8,392}){
      Canvas c=new Canvas();c.magnifierEnabled=true;
      check(event(c,0,edge,200,1,1,0,0),"edge finger DOWN must be admitted for link taps");
      finger(c,1,edge,200,80);
      check(c.listener.taps==1,"edge tap callback");check(Math.abs(c.listener.x-edge/400)<.0001,"inverse image x");
      check(!c.parent.everDisallowed,"edge contact must leave parent interception enabled");check(c.detector.events==0,"edge tap must not start pinch recognition");
      check(c.listener.pages==0,"edge tap must not page");check(c.scheduledHolds==0,"edge does not schedule hold magnifier");
      System.out.println("TRACE edge="+edge+" tap="+c.listener.taps+" parentDisallowed="+c.parent.everDisallowed+" detectorEvents="+c.detector.events+" scheduledHolds="+c.scheduledHolds);
    }
    Canvas c=new Canvas();c.listener.enabled=false;check(!event(c,0,8,200,1,1,0,0),"legacy edge rejection");
    System.out.println("TRACE legacy edgeDown=false parentDisallowed="+c.parent.everDisallowed);
    c=new Canvas();check(!event(c,0,8,200,2,1,0,0),"edge stylus rejection");
    for(String kind:new String[]{"move_back","swipe","multi","cancel","flag","hold"}){
      c=new Canvas();finger(c,0,8,400,0);
      if(kind.equals("move_back")){finger(c,2,40,400,20);finger(c,1,8,400,80);}
      if(kind.equals("swipe")){finger(c,2,8,200,20);finger(c,1,8,200,80);}
      if(kind.equals("multi")){event(c,2,8,400,1,2,0,20);finger(c,1,8,400,80);}
      if(kind.equals("cancel")){finger(c,3,8,400,80);finger(c,1,8,400,100);}
      if(kind.equals("flag"))event(c,1,8,400,1,1,32,80);
      if(kind.equals("hold"))finger(c,1,8,400,800);
      check(c.listener.taps==0,"edge no tap: "+kind);check(c.listener.pages==0,"edge no page: "+kind);
      check(c.listener.toggles==0,"edge no fallback click: "+kind);check(!c.parent.everDisallowed,"parent remains eligible: "+kind);
    }
    c=new Canvas();c.magnifierEnabled=true;finger(c,0,200,400,0);check(c.scheduledHolds==1,"ordinary hold schedule retained");finger(c,1,200,400,80);
    check(c.listener.taps==1&&c.parent.everDisallowed,"ordinary center tap retained");
    c=new Canvas();finger(c,0,200,400,0);finger(c,2,200,200,20);finger(c,1,200,200,80);
    check(c.listener.pages==1,"ordinary PDF swipe retained");
    c=new Canvas();c.zoom=2;finger(c,0,8,400,0);finger(c,2,40,400,20);finger(c,1,40,400,80);
    check(c.detector.events>0&&c.parent.everDisallowed,"zoomed edge pan remains ordinary pan");
    c=new Canvas();c.listener=null;check(!event(c,0,8,200,1,1,0,0),"retired listener rejects edge");
    System.out.println("PASS "+checks);
  }
}
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--expect-red',action='store_true')
    parser.add_argument('--source-revision', help='Optional commonUtils commit for an immutable baseline')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[3]
    path=root/'Python/commonUtils/ui/native/android/io/github/ispaure/commonutils/ImageCanvasView.java'
    text=(subprocess.check_output(['git','-C',str(root/'Python/commonUtils'),'show',args.source_revision+':ui/native/android/io/github/ispaure/commonutils/ImageCanvasView.java'],text=True)
          if args.source_revision else path.read_text())
    start=text.index('@Override public boolean onTouchEvent(')
    pos=text.index('{',start);depth=1;end=pos+1
    while depth:
        depth+=(text[end]=='{')-(text[end]=='}');end+=1
    method=text[start:end].replace('@Override ','',1)
    options,_=manager_settings.settings(root/'mobile_build')
    jdk=Path(options['tools.java'])/'bin'
    with scratch(root) as work:
        (work/'TapHarness.java').write_text(FIXTURE.replace('__METHOD__',method))
        compiled=subprocess.run([str(jdk/'javac'),str(work/'TapHarness.java')],capture_output=True,text=True,timeout=15)
        if compiled.returncode:
            raise RuntimeError(compiled.stderr)
        result=subprocess.run([str(jdk/'java'),'-cp',str(work),'TapHarness'],capture_output=True,text=True,timeout=15)
    expected=(result.returncode!=0 and 'edge finger DOWN must be admitted' in result.stderr) if args.expect_red else result.returncode==0
    report=dict(expected_result=expected,expect_red=args.expect_red,exit_code=result.returncode,
        stdout=result.stdout,stderr=result.stderr,source_sha256=sha256(text.encode()).hexdigest(),
        method_sha256=sha256(method.encode()).hexdigest(),workspace_removed=not work.exists(),android_framework_tested=False)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
    raise SystemExit(0 if expected else 1)


if __name__=='__main__':
    main()
