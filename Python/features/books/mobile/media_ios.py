"""iOS background audio and system remote commands for live speech only."""
import ctypes


class AppleMedia:
    def __init__(self, loop, command):
        from rubicon.objc import ObjCClass, Block, objc_id, ns_from_py
        self.library = ctypes.CDLL('/System/Library/Frameworks/MediaPlayer.framework/MediaPlayer')
        self.closed, self.targets = False, []
        self.state, self.timer_text = 'paused', ''
        self.title = 'Read aloud'
        self.observer = self.interruption_block = None
        def value(owner, name):
            result = getattr(owner, name)
            return result() if callable(result) else result
        self.audio = value(ObjCClass('AVAudioSession'), 'sharedInstance')
        if not self.audio.setCategory('AVAudioSessionCategoryPlayback', mode='AVAudioSessionModeSpokenAudio', options=0, error=None):
            raise RuntimeError('Background speech audio session unavailable.')
        if not self.audio.setActive(True, error=None):
            raise RuntimeError('Could not activate speech audio.')
        self.center = value(ObjCClass('MPRemoteCommandCenter'), 'sharedCommandCenter')
        self.info = value(ObjCClass('MPNowPlayingInfoCenter'), 'defaultCenter')
        self.notifications = value(ObjCClass('NSNotificationCenter'), 'defaultCenter')
        self.interruption_block = Block(lambda note: loop.call_soon_threadsafe(
            lambda: None if self.closed else command('pause')), None, objc_id)
        self.observer = self.notifications.addObserverForName('AVAudioSessionInterruptionNotification',
            object=self.audio, queue=None, usingBlock=self.interruption_block)
        for name, action in [('playCommand', 'play'), ('pauseCommand', 'pause'),
                ('togglePlayPauseCommand', 'toggle'), ('skipBackwardCommand', 'back'),
                ('skipForwardCommand', 'forward'), ('stopCommand', 'stop')]:
            remote = getattr(self.center, name)
            if action in {'back', 'forward'}:
                remote.preferredIntervals = ns_from_py([15])
            remote.enabled = True
            def invoke(event, action=action):
                if self.closed:
                    return 100  # MPRemoteCommandHandlerStatusNoSuchContent
                loop.call_soon_threadsafe(lambda: None if self.closed else command(action))
                return 0
            block = Block(invoke, ctypes.c_long, objc_id)
            target = remote.addTargetWithHandler(block)
            self.targets.append((remote, target, block))

    def update(self, state, *, timer_text=''):
        if self.closed:
            return
        self.state, self.timer_text = state, timer_text
        self._publish_info()
        if state == 'speaking':
            self.audio.setActive(True, error=None)
        self.info.playbackState = 1 if state == 'speaking' else 2

    def _key(self, name):
        from rubicon.objc import ObjCInstance
        return str(ObjCInstance(ctypes.c_void_p.in_dll(self.library, name).value))

    def _publish_info(self):
        from rubicon.objc import ns_from_py
        key = self._key
        subtitle = self.timer_text or 'Logisticks'
        self.info.nowPlayingInfo = ns_from_py({key('MPMediaItemPropertyTitle'): self.title,
            key('MPMediaItemPropertyArtist'): subtitle,
            key('MPNowPlayingInfoPropertyPlaybackRate'): 1.0 if self.state == 'speaking' else 0.0,
            key('MPNowPlayingInfoPropertyIsLiveStream'): False})

    def update_timer(self, text):
        if not self.closed:
            self.timer_text = text
            self._publish_info()

    def update_content(self, title):
        if not self.closed:
            self.title = title
            self._publish_info()

    def close(self):
        if not self.closed:
            self.closed = True
            for remote, target, block in self.targets:
                remote.removeTarget(target)
                remote.enabled = False
            self.targets.clear()
            if self.observer is not None:
                self.notifications.removeObserver(self.observer)
                self.observer = self.interruption_block = None
            if hasattr(self, 'info'):
                self.info.nowPlayingInfo = None
                self.info.playbackState = 0
            if hasattr(self, 'audio'):
                self.audio.setActive(False, withOptions=1, error=None)
