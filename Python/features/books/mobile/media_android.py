"""Android foreground media-service adapter; commands carry no source text."""
class AndroidMedia:
    def __init__(self, loop, command):
        from java import dynamic_proxy
        from org.beeware.android import MainActivity
        from io.github.ispaure.logistics.books import SpeechMediaService
        self.service, self.context = SpeechMediaService, MainActivity.singletonThis
        self.closed = False
        owner = self
        class Listener(dynamic_proxy(SpeechMediaService.Listener)):
            def command(self, action):
                loop.call_soon_threadsafe(lambda: None if owner.closed else command(str(action)))
        self.listener = Listener()
        SpeechMediaService.attach(self.context, self.listener)

    def update(self, state):
        if not self.closed:
            self.service.update(self.context, state == 'speaking')

    def close(self):
        if not self.closed:
            self.closed = True
            self.service.detach(self.context, self.listener)
