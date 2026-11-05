"""Compile exact native Pencil producer + synthetic UIKit fixtures, owned Simulator only.

This is transport/ABI evidence, never a physical Pencil or Logistics release pass.
No existing simulator is selected, no personal device is queried, no package is
installed outside the newly created SDK-owned disposable Simulator.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import shutil
import subprocess
import time
from uuid import uuid4

from build_manager.apple_simulators import AppleSimulators
from logistics_build.build_retention import scratch

BUNDLE = 'io.github.ispaure.logisticsnotebooknativeqa'
MAIN = r'''
#import "producer.m"
#import "checks.m"
#include <fcntl.h>
#include <unistd.h>
#include <string.h>
static void LGStage(const char *stage) {
    fprintf(stderr,"LG_NATIVE_QA_STAGE=%s\n",stage); fflush(stderr);
    const char *path=getenv("LOGISTICS_NATIVE_QA_STAGE_PATH");
    if(path){int fd=open(path,O_WRONLY|O_CREAT|O_APPEND,0600);if(fd>=0){write(fd,stage,strlen(stage));write(fd,"\n",1);close(fd);}}
}
static void LGException(NSException *exception) {
    fprintf(stderr,"LG_NATIVE_QA_EXCEPTION=%s: %s\n",exception.name.UTF8String,exception.reason.UTF8String);fflush(stderr);
}
@interface LGNotebookNativeQAScene : UIResponder <UIWindowSceneDelegate>
@property(nonatomic,strong) UIWindow *window;
@end
@implementation LGNotebookNativeQAScene
- (void)scene:(UIScene *)scene willConnectToSession:(UISceneSession *)session options:(UISceneConnectionOptions *)options {
    LGStage("scene-connect-enter");
    self.window=[[LogisticsNotebookInputWindow alloc] initWithFrame:((UIWindowScene *)scene).coordinateSpace.bounds];
    self.window.windowScene=(UIWindowScene *)scene;
    LGNotebookRequire([self.window isKindOfClass:LogisticsNotebookInputWindow.class] &&
        ((LogisticsNotebookInputWindow *)self.window).notebookBindings!=nil,@"Producer initializer did not create binding registry");
    LGStage("native-window-created");
    self.window.rootViewController=[UIViewController new];
    [self.window makeKeyAndVisible];
    LGStage("native-window-visible");
    dispatch_async(dispatch_get_main_queue(), ^{
        LGStage("fixture-enter");
        NSDictionary *result=[LogisticsNotebookNativeChecks runOnWindow:self.window];
        LGStage("fixture-returned");
        NSString *cache=NSSearchPathForDirectoriesInDomains(NSCachesDirectory,NSUserDomainMask,YES).firstObject;
        NSData *data=[NSJSONSerialization dataWithJSONObject:result options:0 error:NULL];
        BOOL written=[data writeToFile:[cache stringByAppendingPathComponent:@"native-pencil-result.json"] atomically:YES];
        LGStage(written ? "result-published" : "result-write-failed");
    });
}
@end
@interface LGNotebookNativeQADelegate : UIResponder <UIApplicationDelegate>
@end
@implementation LGNotebookNativeQADelegate
- (BOOL)application:(UIApplication *)application didFinishLaunchingWithOptions:(NSDictionary *)options {
    LGStage("application-finished-launching"); return YES;
}
@end
int main(int argc,char **argv) {
    @autoreleasepool {
        LGStage("main-enter");NSSetUncaughtExceptionHandler(LGException);
        return UIApplicationMain(argc,argv,nil,NSStringFromClass(LGNotebookNativeQADelegate.class));
    }
}
'''


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root',type=Path,required=True)
    parser.add_argument('--producer',type=Path,required=True)
    parser.add_argument('--producer-sha256',required=True)
    parser.add_argument('--fixture-sha256',required=True)
    parser.add_argument('--developer-dir',type=Path,required=True)
    parser.add_argument('--device-type',required=True)
    parser.add_argument('--runtime',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    fixture=Path(__file__).with_name('fixtures')/'notebook_native_pen_checks.m'
    if sha(args.producer)!=args.producer_sha256 or sha(fixture)!=args.fixture_sha256:
        raise ValueError('Reviewed native source/fixture bytes changed before preparation')
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    env=dict(os.environ,DEVELOPER_DIR=str(args.developer_dir.resolve()))
    result=dict(success=False,diagnostic_only=True,physical_pencil_tested=False,
                native_transport_only=True,source_sha256=args.producer_sha256,
                fixture_sha256=args.fixture_sha256,bundle=BUNDLE)
    client=AppleSimulators(env);device=None;name='Build Manager Native Pencil QA '+uuid4().hex
    def run(argv,timeout=120):
        completed=subprocess.run(argv,env=env,capture_output=True,text=True,timeout=timeout)
        with (output/'native-build.log').open('a') as log:
            log.write(completed.stdout);log.write(completed.stderr)
        completed.check_returncode();return completed.stdout.strip()
    def stage(name):
        with (output/'driver-stages.jsonl').open('a') as stream:
            stream.write(json.dumps(dict(stage=name,monotonic=time.monotonic()))+'\n')
    try:
        stage('scratch-enter')
        with scratch(args.project_root.resolve()) as work:
            shutil.copyfile(args.producer,work/'producer.m');shutil.copyfile(fixture,work/'checks.m')
            if sha(work/'producer.m')!=args.producer_sha256 or sha(work/'checks.m')!=args.fixture_sha256:
                raise ValueError('Native source copy changed')
            (work/'main.m').write_text(MAIN)
            app=work/'NativePencilQA.app';app.mkdir()
            sdk=run(['xcrun','--sdk','iphonesimulator','--show-sdk-path'],timeout=30)
            architecture={'arm64':'arm64','x86_64':'x86_64'}.get(platform.machine())
            if architecture is None:raise ValueError('Unsupported host Simulator architecture')
            run(['xcrun','--sdk','iphonesimulator','clang','-fobjc-arc','-arch',architecture,
                 '-isysroot',sdk,'-mios-simulator-version-min=15.0',str(work/'main.m'),
                 '-framework','Foundation','-framework','UIKit','-framework','WebKit',
                 '-framework','JavaScriptCore','-o',str(app/'NativePencilQA')])
            (app/'Info.plist').write_bytes(plistlib.dumps(dict(CFBundleIdentifier=BUNDLE,
                CFBundleExecutable='NativePencilQA',CFBundleName='NativePencilQA',
                CFBundlePackageType='APPL',CFBundleVersion='1',CFBundleShortVersionString='1.0',
                LSRequiresIPhoneOS=True,UIDeviceFamily=[1,2],UILaunchScreen={},
                UIApplicationSceneManifest=dict(UIApplicationSupportsMultipleScenes=False,
                    UISceneConfigurations={'UIWindowSceneSessionRoleApplication':[dict(
                        UISceneConfigurationName='Native Pencil QA',
                        UISceneDelegateClassName='LGNotebookNativeQAScene')]}))))
            run(['codesign','--force','--sign','-',str(app)],timeout=30)
            result.update(binary_sha256=sha(app/'NativePencilQA'),architecture=architecture,
                          toolchain=client.toolchain())
            stage('compile-codesign-complete')
            device=client.create(name,args.device_type,args.runtime)
            (output/'owned-simulator.json').write_text(json.dumps(dict(device=device,name=name,
                runtime=args.runtime,model=args.device_type,owned=True),indent=2)+'\n')
            stage('simulator-created')
            client.boot(device,name=name)
            stage('simulator-booted')
            client.invoke('install',device,str(app),timeout=120)
            stage('app-installed')
            container=Path(client.invoke('get_app_container',device,BUNDLE,'data',timeout=30))
            client.environment['SIMCTL_CHILD_LOGISTICS_NATIVE_QA_STAGE_PATH']=str(container/'Library/Caches/native-pencil-stages.log')
            launched=client.invoke('launch','--stdout='+str(output/'app-stdout.log'),
                '--stderr='+str(output/'app-stderr.log'),device,BUNDLE,timeout=60)
            (output/'launch-receipt.txt').write_text(launched+'\n')
            stage('app-launched')
            result['launch_receipt']=launched
            pid_text=launched.rsplit(':',1)[-1].strip()
            pid=int(pid_text) if pid_text.isdecimal() else None
            result['original_pid']=pid
            observed_stages=''
            stage_path=container/'Library/Caches/native-pencil-stages.log'
            report=container/'Library/Caches/native-pencil-result.json'
            deadline=time.monotonic()+120
            while time.monotonic()<deadline:
                if stage_path.is_file():
                    observed_stages=stage_path.read_bytes()[:16384].decode('utf-8',errors='replace')
                    (output/'app-stages.log').write_text(observed_stages)
                if report.is_file():
                    raw=report.read_bytes()
                    if len(raw)>65536:raise ValueError('Native QA report exceeds bounded contract')
                    try:value=json.loads(raw)
                    except json.JSONDecodeError:
                        time.sleep(.1);continue
                    result['native']=value
                    result['success']=value.get('success') is True and value.get('native_transport_only') is True
                    break
                if pid is not None:
                    try:os.kill(pid,0)
                    except ProcessLookupError:
                        result['original_process_dead']=True
                        raise RuntimeError('Original QA process exited before result; inspect launch console/stages and matching IPS')
                time.sleep(.2)
            else:raise TimeoutError('Native QA app did not publish its bounded result; inspect app-stages.log and launch console')
            if not result['success']:raise RuntimeError('Native Pencil fixture reported failure')
    except Exception as error:
        result['error']=str(error)
        stage('failed-before-cleanup')
        pid=result.get('original_pid')
        result['matching_crash_reports']=[]
        try:
            if type(pid) is int:
                for path in sorted((Path.home()/'Library/Logs/DiagnosticReports').glob('NativePencilQA-*.ips'),reverse=True)[:12]:
                    if path.stat().st_size>4*1024*1024:continue
                    raw=path.read_bytes()
                    if re.search(rb'"pid"\s*:\s*'+str(pid).encode()+rb'\b',raw):
                        target=output/path.name;target.write_bytes(raw)
                        result['matching_crash_reports'].append(target.name)
        except Exception as diagnostic_error:
            result['crash_capture_error']=str(diagnostic_error)
        raise
    finally:
        try:
            if device is not None:
                stage('cleanup-enter')
                client.remove(device,name)
                result['cleanup_verified']=client.matching(device,name,timeout=5) is None
                if not result['cleanup_verified']:raise RuntimeError('Owned native QA simulator remained')
            else:result['cleanup_verified']=True
        finally:
            (output/'native-pencil-proof.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(success=result['success'],cleanup_verified=result['cleanup_verified'],
                         cases=result['native']['cases'],diagnostic_only=True)))


if __name__=='__main__':main()
