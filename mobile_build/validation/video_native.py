"""Compile native video adapters against pinned upstream SDK interfaces.

This is a syntax/API check, not device playback acceptance. Downloads and compiler
outputs live only inside the build manager's disposable scratch lease.
"""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
from urllib.request import urlopen
from zipfile import ZipFile

from logistics_build.build_retention import scratch
from mobile_build.build_support.video_build import VLC_REVISION

ROOT = Path(__file__).resolve().parents[2]


def download(url, destination):
    with urlopen(url, timeout=60) as source, destination.open('wb') as output:
        shutil.copyfileobj(source, output)


def android(workspace):
    config = ROOT / 'mobile_build/.tools/android-sdk.json'
    values = json.loads(config.read_text()) if config.exists() else {}
    sdk = Path(os.environ.get('ANDROID_HOME') or values.get('ANDROID_HOME', ''))
    platforms = sorted(sdk.glob('platforms/android-*/android.jar'))
    if not platforms:
        raise RuntimeError('An existing Android SDK platform is required.')
    aar = workspace / 'libvlc.aar'
    download('https://repo.maven.apache.org/maven2/org/videolan/android/libvlc-all/3.7.5/libvlc-all-3.7.5.aar', aar)
    with ZipFile(aar) as archive:
        (workspace / 'classes.jar').write_bytes(archive.read('classes.jar'))
    source = ROOT / 'Python/features/video/mobile/android/io/github/ispaure/logistics/video/VideoPlayer.java'
    extra = [ROOT / 'Python/mobile/android/io/github/ispaure/logistics/audio/AudioOutputs.java',
             ROOT / 'Python/features/books/mobile/android/io/github/ispaure/logistics/books/SpeechMediaService.java']
    subprocess.run(['javac', '-cp', str(platforms[-1]) + os.pathsep + str(workspace / 'classes.jar'),
                    '-d', str(workspace / 'compiled'), str(source), *map(str, extra)], check=True)


def ios(workspace):
    archive = workspace / 'vlckit.tar.gz'
    download(f'https://api.github.com/repos/videolan/vlckit/tarball/{VLC_REVISION}', archive)
    includes = workspace / 'include/VLCKit'
    includes.mkdir(parents=True)
    with tarfile.open(archive) as tar:
        for member in tar.getmembers():
            if member.isfile() and '/Headers/' in member.name and member.name.endswith('.h'):
                file = tar.extractfile(member)
                if file is not None:
                    (includes / Path(member.name).name).write_bytes(file.read())
    sdk = subprocess.check_output(['xcrun', '--sdk', 'iphonesimulator', '--show-sdk-path'], text=True).strip()
    source = ROOT / 'Python/features/video/mobile/ios/VideoPlayer.m'
    subprocess.run(['xcrun', 'clang', '-fsyntax-only', '-fobjc-arc', '-fmodules',
        '-fmodules-cache-path=' + str(workspace / 'modules'),
        '-target', 'arm64-apple-ios15.0-simulator', '-isysroot', sdk,
        '-I', str(includes.parent), str(source)], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('platform', choices=('android', 'ios'))
    args = parser.parse_args()
    with scratch() as workspace:
        (android if args.platform == 'android' else ios)(workspace)
    owner = ROOT / 'Python/features/video/mobile'
    source = (owner / 'ios/VideoPlayer.m' if args.platform == 'ios'
              else owner / 'android/io/github/ispaure/logistics/video/VideoPlayer.java')
    report = ROOT / f'test-results/media/{args.platform}-api-compile.json'
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(dict(status='passed', scope='native SDK API compile only',
        platform=args.platform, checked_at=datetime.now(timezone.utc).isoformat(),
        source_sha256=sha256(source.read_bytes()).hexdigest(),
        sdk=VLC_REVISION if args.platform == 'ios' else 'libvlc-all:3.7.5', scratch_removed=True), indent=2) + '\n')
    print(args.platform + ' video adapter API compile passed; scratch removed.')


if __name__ == '__main__':
    main()
