"""Collect successful programmatic Qt simulator evidence from the proof container."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess

CASES = ['existing_file_browser_independent_tabs', 'existing_code_editor_highlighting_save',
         'existing_markdown_reader', 'native_rclone_import_list_download_probe']

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('simulator')
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    container = Path(subprocess.check_output(['xcrun', 'simctl', 'get_app_container', args.simulator,
        'io.github.ispaure.logisticsqtproof', 'data'], text=True).strip())
    root = container / 'Library/Application Support/Logistics Qt Proof/proof'
    report = json.loads((root / 'evidence.json').read_text())
    if report.get('platform') != 'ios' or report.get('passed') != CASES or report.get('error') or report.get('root') != str(root):
        raise ValueError('No current complete iOS proof result in this container')
    args.destination.mkdir(parents=True, exist_ok=False)
    report['root'] = '<private proof container>'
    report['column_navigation'] = False
    report['verification'] = 'Programmatic real Qt widgets and compiled rclone bridge; not physical touch/provider verification'
    (args.destination / 'evidence.json').write_text(json.dumps(report, indent=2) + '\n')
    for name in ('files', 'editor', 'reader', 'rclone'):
        shutil.copy2(root / f'{name}.png', args.destination / f'{name}.png')
    subprocess.run(['xcrun', 'simctl', 'io', args.simulator, 'screenshot',
                    str(args.destination / 'native-screen.png')], check=True)
