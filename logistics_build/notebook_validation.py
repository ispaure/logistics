"""Shared native notebook selection for the manager's desktop guest adapters."""
from contextlib import contextmanager
import json
from pathlib import Path
import platform
import shutil
import sys
import tarfile
import zipfile

from Python.tests.notebooks.notebook_platform_probe import CORE_PROBES, PROBES


def arguments(parser, *, windows=False):
    parser.add_argument('--notebook-profile', choices=('core', 'full'), default='core')
    parser.add_argument('--notebook-probe', action='append', choices=tuple(PROBES))
    parser.add_argument('--notebook-rendering', choices=('native', 'software', 'chromium-software',
                                                       *(('warp',) if windows else ()), 'all'))
    parser.add_argument('--notebook-go', help='Go compiler path inside the selected guest')
    parser.add_argument('--notebook-latency-mode', choices=('enforce', 'diagnostic'), default='enforce')


def command(args, python, output, *, windows=False):
    profile = getattr(args, 'notebook_profile', 'core')
    probes = getattr(args, 'notebook_probe', None)
    selected = probes or (CORE_PROBES if profile == 'core' else tuple(PROBES))
    argv = [python, '-m', 'logistics_build.notebook_validation', '--output', str(output),
            '--profile', profile, '--latency-mode', getattr(args, 'notebook_latency_mode', 'enforce')]
    rendering = getattr(args, 'notebook_rendering', None)
    if rendering:
        argv += ['--rendering', rendering]
    for probe in probes or ():
        argv += ['--probe', probe]
    if getattr(args, 'notebook_go', None):
        argv += ['--go', args.notebook_go]
    graphics = (4 if windows else 3) if rendering == 'all' else 1
    timeout = sum(PROBES[name][1] * (graphics if PROBES[name][2] else 1) for name in selected) + 30
    return tuple(argv), timeout


@contextmanager
def guest_go():
    """Keep a verified portable compiler inside the existing leased cache policy."""
    from logistics_build.build_retention import compiler_cache, scratch
    from commonUtils.runtime.streams.downloads import DownloadSpec, provision
    system = {'Linux': 'linux', 'Windows': 'windows'}[platform.system()]
    arch = {'aarch64': 'arm64', 'ARM64': 'arm64', 'AMD64': 'amd64', 'x86_64': 'amd64'}[platform.machine()]
    # Official go.dev release archive digests; no system-wide installation.
    hashes = {('linux', 'arm64'): '3f4227ce7b206a513e794f1393adb473a07b46e94d18bd15d1c684bbb7319797',
              ('linux', 'amd64'): 'ccfe7ae822d2c2f41f4fe7c956199967a4dac22d0ee0d2b2bfdb440aab3b20c5',
              ('windows', 'arm64'): '6831fd8c31091243d5695c8fa3a721c9f4ae2bb36482763e77e57ee01b76489f',
              ('windows', 'amd64'): '7ecd2d7260e82c59bcbd7f1077a07cee2dea607295b858df67195a1e4e09629b'}
    digest = hashes[system, arch]
    name = 'go1.26.10.' + system + '-' + arch
    suffix = '.zip' if system == 'windows' else '.tar.gz'
    with compiler_cache('notebook-go') as cache:
        destination = cache / name
        receipt = destination / '.verified-archive.json'
        go = destination / 'bin' / ('go.exe' if system == 'windows' else 'go')
        if not receipt.is_file() or json.loads(receipt.read_text()) != {'sha256': digest} or not go.is_file():
            if destination.exists():
                raise ValueError('Portable Go cache is incomplete; preserve it for inspection.')
            with scratch() as work:
                archive = provision(DownloadSpec('Notebook Go', '1.26.10', 'https://go.dev/dl/' + name + suffix,
                                                 digest, digest), work / ('go' + suffix))
                if system == 'windows':
                    with zipfile.ZipFile(archive) as bundle:
                        bundle.extractall(work / 'unpacked')
                else:
                    with tarfile.open(archive) as bundle:
                        bundle.extractall(work / 'unpacked', filter='data')
                shutil.move(str(work / 'unpacked/go'), destination)
                receipt.write_text(json.dumps({'sha256': digest}))
        yield go


def main():
    from Python.tests.notebooks.notebook_platform_probe import main as run
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--profile', choices=('core', 'full'), default='core')
    parser.add_argument('--probe', action='append', choices=tuple(PROBES))
    parser.add_argument('--rendering')
    parser.add_argument('--latency-mode', choices=('enforce', 'diagnostic'), default='enforce')
    parser.add_argument('--go', type=Path)
    args = parser.parse_args()
    def execute(go):
        return run(args.output, args.rendering, args.probe, profile=args.profile, go=go,
                   latency_mode=args.latency_mode)
    selected = args.probe or (CORE_PROBES if args.profile == 'core' else PROBES)
    if 'independent-codec' in selected and not args.go and not shutil.which('go'):
        with guest_go() as go:
            return execute(go)
    return execute(args.go)


if __name__ == '__main__':
    sys.exit(main())
