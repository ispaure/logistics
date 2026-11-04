"""Compare portable Java Ballpoint math with Python; no Android/device build."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess

from logistics_build.build_retention import scratch
from features.notebooks.brushes import BRUSHES, stroke_points


def main(output):
    java = shutil.which('java')
    javac = shutil.which('javac')
    if not java or not javac:
        raise RuntimeError('Java/Javac is required for the optional portable parity check.')
    source = Path(__file__).resolve().parents[2] / 'features/notebooks/mobile/android/io/github/ispaure/logistics/notebooks/BooxBallpoint.java'
    brush = BRUSHES[15]
    with scratch() as root:
        helper = root / 'com/onyx/android/sdk/pen/TouchHelper.java'
        helper.parent.mkdir(parents=True)
        helper.write_text('package com.onyx.android.sdk.pen; public class TouchHelper { public void setStrokeWidth(float width) {} }')
        target = root / 'io/github/ispaure/logistics/notebooks'
        target.mkdir(parents=True)
        shutil.copyfile(source, target / source.name)
        runner = target / 'Parity.java'
        runner.write_text('package io.github.ispaure.logistics.notebooks; public class Parity { public static void main(String[] args) {'
            + 'for(float base: new float[]{' + ','.join(str(w)+'f' for w in brush['widths']) + '})'
            + 'for(int p=0;p<256;p++)System.out.println(BooxBallpoint.width(p/255f,base,'
            + str(brush['pressure'])+'f,'+str(brush['exponent'])+'f));}}')
        subprocess.run([javac, '-d', str(root), str(helper), str(target/source.name), str(runner)], check=True, capture_output=True, timeout=30)
        result = subprocess.run([java, '-cp', str(root), 'io.github.ispaure.logistics.notebooks.Parity'],
                                check=True, text=True, capture_output=True, timeout=30)
        observed = [float(value) for value in result.stdout.splitlines()]
        expected = [stroke_points([[20, 30, p / 255]], 15, width)[0][3]
                    for width in (1, 2, 3) for p in range(256)]
        assert observed == expected, [(i, a, b) for i, (a, b) in enumerate(zip(observed, expected)) if a != b][:10]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(dict(success=True, checks=len(expected),
        source_sha256=sha256(source.read_bytes()).hexdigest(),
        scope='Portable Java math only; TouchHelper stub, no native pen/device acceptance'), indent=2))
    print('768 Java/Python Ballpoint widths match exactly.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    main(parser.parse_args().output)
