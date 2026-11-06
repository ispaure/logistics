// TEST_STAGE = TestStage.EXTENDED
// Silent, app-local playback drives real system activity; no network or user media.
#import <UIKit/UIKit.h>
#import <AVFoundation/AVFoundation.h>
#import <MediaPlayer/MediaPlayer.h>
@interface MediaQA : UIResponder <UIApplicationDelegate, UIWindowSceneDelegate>
@property(nonatomic, strong) UIWindow *window;
@property(nonatomic, strong) AVAudioPlayer *player;
@end
@implementation MediaQA
- (BOOL)application:(UIApplication *)app didFinishLaunchingWithOptions:(NSDictionary *)options {
    return YES;
}
- (void)scene:(UIScene *)scene willConnectToSession:(UISceneSession *)session options:(UISceneConnectionOptions *)options {
    self.window = [[UIWindow alloc] initWithWindowScene:(UIWindowScene *)scene];
    self.window.rootViewController = [UIViewController new];
    [self.window makeKeyAndVisible];
    NSError *error;
    [AVAudioSession.sharedInstance setCategory:AVAudioSessionCategoryPlayback error:&error];
    [AVAudioSession.sharedInstance setActive:YES error:&error];
    self.player = [[AVAudioPlayer alloc] initWithContentsOfURL:[NSBundle.mainBundle URLForResource:@"silence" withExtension:@"wav"] error:&error];
    self.player.numberOfLoops = -1;
    BOOL playing = [self.player play];
    [UIApplication.sharedApplication beginReceivingRemoteControlEvents];
    MPRemoteCommandCenter *commands = MPRemoteCommandCenter.sharedCommandCenter;
    [commands.playCommand addTargetWithHandler:^MPRemoteCommandHandlerStatus(MPRemoteCommandEvent *event) { return MPRemoteCommandHandlerStatusSuccess; }];
    [commands.pauseCommand addTargetWithHandler:^MPRemoteCommandHandlerStatus(MPRemoteCommandEvent *event) { return MPRemoteCommandHandlerStatusSuccess; }];
    MPNowPlayingInfoCenter.defaultCenter.nowPlayingInfo = @{MPMediaItemPropertyTitle:@"Silent QA audio", MPMediaItemPropertyArtist:@"Disposable test", MPMediaItemPropertyPlaybackDuration:@600, MPNowPlayingInfoPropertyElapsedPlaybackTime:@1, MPNowPlayingInfoPropertyPlaybackRate:@1};
    MPNowPlayingInfoCenter.defaultCenter.playbackState = MPNowPlayingPlaybackStatePlaying;
    NSString *directory = [NSHomeDirectory() stringByAppendingPathComponent:@"Documents"];
    [NSFileManager.defaultManager createDirectoryAtPath:directory withIntermediateDirectories:YES attributes:nil error:nil];
    NSDictionary *state = @{@"playing":@(playing), @"error":error.localizedDescription ?: @""};
    [[NSJSONSerialization dataWithJSONObject:state options:0 error:nil] writeToFile:[directory stringByAppendingPathComponent:@"media-ready.json"] atomically:YES];
}
@end
int main(int argc, char **argv) { @autoreleasepool { return UIApplicationMain(argc, argv, nil, NSStringFromClass(MediaQA.class)); } }
