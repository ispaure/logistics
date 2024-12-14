import subprocess
import sys
import importlib as importlib
import platform


def install_python_package(package, version=None):

    if package in installed_packages:
        print('Package already installed: ' + package)
    else:
        if version is None:
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])
        else:
            subprocess.check_call([sys.executable, "-m", "pip", "install", str(package) + '==' + str(version)])


def install_yt_dlp():
    if 'yt-dlp' in installed_packages:
        print('Package yt-dlp already installed')
    else:
        subprocess.check_call([sys.executable, "-m", "pip", "install", '--force-reinstall', 'https://github.com/yt-dlp/yt-dlp/archive/master.tar.gz', '--user'])


# Get installed packages
reqs = subprocess.check_output([sys.executable, '-m', 'pip', 'freeze'])
installed_packages = [r.decode().split('==')[0] for r in reqs.split()]

# Install package (if missing)
if sys.platform == 'win32':
    install_python_package('pySide2')
else:
    if platform.processor() == 'arm':
        # Need this specific version as 6.7.0+ has incompatibility issues (some stuff changed)
        install_python_package('pyside6', version='6.6.1')
    else:
        install_python_package('pySide2')

install_python_package('py7zr')
install_python_package('pyzipper')
install_python_package('patool')
install_python_package('pyunpack')
install_python_package('phue')
install_python_package('youtube-dl')
install_python_package('piexif')
