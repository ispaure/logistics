
import sys


def install_homebrew():
    """
    Installs Homebrew on the system
    """
    if sys.platform == 'win32':
        pass
    else:
        homebrew_install_cmd = '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'


def install_lunar():
    """
    Installs Lunar in homebrew. Only works on 32-bit macOS
    """
    if sys.platform == 'win32':
        pass
    else:
        lunar_install_cmd = 'brew install --cask lunar'


