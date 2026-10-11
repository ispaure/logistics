"""Read AppKit menus in native Cocoa regressions; never open or trigger them."""
import ctypes


class CocoaMenus:
    def __init__(self):
        self.objc = ctypes.CDLL('/usr/lib/libobjc.A.dylib')
        self.objc.sel_registerName.argtypes = [ctypes.c_char_p]
        self.objc.sel_registerName.restype = ctypes.c_void_p
        self.objc.objc_getClass.argtypes = [ctypes.c_char_p]
        self.objc.objc_getClass.restype = ctypes.c_void_p
        address = ctypes.cast(self.objc.objc_msgSend, ctypes.c_void_p).value
        self.pointer = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)(address)
        self.integer = ctypes.CFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p)(address)
        self.item = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long)(address)
        self.string = ctypes.CFUNCTYPE(ctypes.c_char_p, ctypes.c_void_p, ctypes.c_void_p)(address)
        self.activate = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_bool)(address)
        self.app = self.send(self.objc.objc_getClass(b'NSApplication'), 'sharedApplication')

    def selector(self, name):
        return self.objc.sel_registerName(name.encode())

    def send(self, obj, name):
        return self.pointer(obj, self.selector(name))

    def foreground(self):
        """Activate only the temporary regression app before inspecting its bar."""
        self.activate(self.app, self.selector('activateIgnoringOtherApps:'), True)

    def contents(self):
        menu = self.send(self.app, 'mainMenu')
        result = {}
        for index in range(self.integer(menu, self.selector('numberOfItems'))):
            entry = self.item(menu, self.selector('itemAtIndex:'), index)
            title = self.string(self.send(entry, 'title'), self.selector('UTF8String')).decode()
            submenu = self.send(entry, 'submenu')
            result[title] = [self.string(self.send(self.item(submenu, self.selector('itemAtIndex:'), child),
                'title'), self.selector('UTF8String')).decode()
                for child in range(self.integer(submenu, self.selector('numberOfItems')))]
        return result
