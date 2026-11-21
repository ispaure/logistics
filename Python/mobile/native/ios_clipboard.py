"""Guard UIKit and WebKit's standard clipboard responder actions."""


def install(blocked):
    from ctypes import c_bool
    from rubicon.objc import ObjCInstance, SEL, objc_id, objc_method, send_super
    from toga_iOS.widgets import multilinetextinput, textinput, webview

    selectors = frozenset((b'cut:', b'copy:', b'paste:', b'pasteAndMatchStyle:'))

    def guarded_type(base):
        class LGClipboardResponder(base, auto_rename=True):
            @objc_method
            def canPerformAction_withSender_(self, action: SEL, sender: objc_id) -> c_bool:
                return (not (action.name in selectors and blocked())
                        and send_super(__class__, self, 'canPerformAction:withSender:', action, sender,
                                       restype=c_bool, argtypes=[SEL, objc_id]))

            @objc_method
            def targetForAction_withSender_(self, action: SEL, sender: objc_id) -> objc_id:
                if action.name in selectors and blocked():
                    # WKContentView consults its WKWebView for the action target.
                    # Keep dispatch here if a command was already offered.
                    return self
                result = send_super(__class__, self, 'targetForAction:withSender:', action, sender,
                                    restype=objc_id, argtypes=[SEL, objc_id])
                return ObjCInstance(result) if result else None

            @objc_method
            def cut_(self, sender: objc_id):
                if not blocked():
                    send_super(__class__, self, 'cut:', sender, argtypes=[objc_id])

            @objc_method
            def copy_(self, sender: objc_id):
                if not blocked():
                    send_super(__class__, self, 'copy:', sender, argtypes=[objc_id])

            @objc_method
            def paste_(self, sender: objc_id):
                if not blocked():
                    send_super(__class__, self, 'paste:', sender, argtypes=[objc_id])

            @objc_method
            def pasteAndMatchStyle_(self, sender: objc_id):
                if not blocked() and base.instancesRespondToSelector(SEL('pasteAndMatchStyle:')):
                    send_super(__class__, self, 'pasteAndMatchStyle:', sender, argtypes=[objc_id])

        return LGClipboardResponder

    textinput.TogaTextField = guarded_type(textinput.TogaTextField)
    multilinetextinput.TogaMultilineTextView = guarded_type(multilinetextinput.TogaMultilineTextView)
    webview.TogaWebView = guarded_type(webview.TogaWebView)


def copy_text(text):
    from rubicon.objc import ObjCClass
    ObjCClass('UIPasteboard').generalPasteboard.string = text
