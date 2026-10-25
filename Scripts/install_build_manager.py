"""Explicitly install a reviewed external manager Git checkout in this interpreter."""
import argparse
from pathlib import Path
import subprocess
import sys
import tomllib


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('checkout', type=Path, nargs='?')
    parser.add_argument('--from-pin', type=Path, metavar='DESTINATION', help='Explicitly clone the pinned manager into a new setup location')
    args = parser.parse_args()
    if args.from_pin:
        import json
        pin = json.loads((Path(__file__).resolve().parents[1] / 'build-manager-dependency.json').read_text())
        if pin.get('schema') != 1 or pin.get('adapter_api') != 1:
            parser.error('Unsupported manager dependency schema.')
        destination = args.from_pin.expanduser().absolute()
        if destination.exists():
            parser.error('Choose a new manager setup destination; existing checkouts are never pulled or reset.')
        subprocess.run(['git', 'clone', '--no-checkout', pin['repository'], str(destination)], check=True)
        subprocess.run(['git', '-C', str(destination), 'checkout', '--detach', pin['revision']], check=True)
        subprocess.run(['git', '-C', str(destination), 'submodule', 'update', '--init', '--recursive'], check=True)
        args.checkout = destination
    if args.checkout is None:
        parser.error('Supply a reviewed manager checkout or --from-pin DESTINATION.')
    root = args.checkout.expanduser().absolute()
    config = root / 'pyproject.toml'
    if not config.is_file() or tomllib.loads(config.read_text()).get('project', {}).get('name') != 'build-deployment-manager':
        parser.error('Select a reviewed build-deployment-manager checkout.')
    subprocess.run([sys.executable, '-m', 'pip', 'install', '--no-deps', '-e', str(root)], check=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
