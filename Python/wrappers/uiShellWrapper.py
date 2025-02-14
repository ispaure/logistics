import sys
import ctypes
import commonUtils.wrappers.cmdShellWrapper as cmdShellWrapper
from commonUtils.osUtils import *
from commonUtils.debugUtils import *


def empty_fn():
    pass


def show_dialog_box(title, message, execute_fn=empty_fn):
    """
    Displays dialog box
    :param title: Dialog box title
    :type title: str
    :param message: Message to be shown in dialog box
    :type message: str
    :param execute_fn: (Optional) Function to execute if user presses "OK" button
    :type execute_fn: function
    """
    print('Showing dialog box.')

    class MbConstants:
        MB_OKCANCEL = 1
        IDCANCEL = 2
        IDOK = 1

    # Prevent escape sequences
    message = message.replace('\\n', '\n').replace('\\t', '\t')

    # Show Dialog Window (Windows) and return user input
    def show_dialog_box_win32(message, title):
        return ctypes.windll.user32.MessageBoxW(0, message, title, MbConstants.MB_OKCANCEL)

    # Show Dialog Window (MacOS) and return user input
    def show_dialog_box_macos(message, title):
        command_str = "osascript -e 'Tell application \"System Events\" to display dialog \"{message}\" with title \"{title}\"'".format(message=message, title=title)
        return_val = cmdShellWrapper.exec_cmd(command_str)
        return return_val

    # Since Blender API doesn't have proper message box that waits on user, we have to get a bit creative.

    match get_os():
        case OS.WIN:  # Solution which only works on Windows
            rc = show_dialog_box_win32(message, title)
            if rc == MbConstants.IDOK:
                execute_fn()
                return True
            elif rc == MbConstants.IDCANCEL:
                return False
        case OS.MAC:
            message = message.replace('"', '')
            message = message.replace("'", '')
            if 'OK' in show_dialog_box_macos(message, title)[0]:
                execute_fn()
                return True
            else:
                return False
        case _:
            log(Severity.CRITICAL, 'uiShellWrapper', 'Platform unsupported!')
            return
