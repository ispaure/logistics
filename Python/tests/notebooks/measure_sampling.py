"""Read-only, aggregate sampling audit for a completed calibration worksheet.

The manifest supplies task rectangles. Speed groups mean the left/right halves
of the requested slow-then-fast cell, not a measured clock or firmware rule.
No handwriting coordinates, stroke IDs or per-point records are emitted.
"""
import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
import math
from pathlib import Path
from statistics import median

from features.notebooks._vendor.rmscene import scene_stream as ss
from features.notebooks.notebook import Notebook


def quantile(values, fraction):
    if not values:
        return None
    values = sorted(values)
    position = (len(values) - 1) * fraction
    before = int(position)
    after = min(len(values) - 1, before + 1)
    return values[before] + (values[after] - values[before]) * (position - before)


def distribution(values):
    return dict(count=len(values), minimum=min(values) if values else None,
                median=median(values) if values else None, p90=quantile(values, .9),
                p99=quantile(values, .99), maximum=max(values) if values else None)


def correlation(pairs):
    if len(pairs) < 2:
        return None
    mx = sum(p[0] for p in pairs) / len(pairs)
    my = sum(p[1] for p in pairs) / len(pairs)
    numerator = sum((x - mx) * (y - my) for x, y in pairs)
    denominator = math.sqrt(sum((x - mx) ** 2 for x, _ in pairs)
                            * sum((y - my) ** 2 for _, y in pairs))
    return numerator / denominator if denominator else None


def summarize(lines):
    spacings, turns, speed_spacing, direction_error = [], [], [], []
    lengths, counts, speeds, widths, pressures = [], [], [], [], []
    identical_model = pressure_changes = width_changes = same_xy_dynamics = 0
    pressure_extrema = width_extrema = 0
    for line in lines:
        points = line.points
        counts.append(len(points))
        speeds.extend(p.speed for p in points)
        widths.extend(p.width / 4 for p in points)
        pressures.extend(p.pressure for p in points)
        length = 0
        for a, b in zip(points, points[1:]):
            distance = math.hypot(b.x - a.x, b.y - a.y)
            length += distance
            spacings.append(distance)
            speed_spacing.append((b.speed, distance))
            pressure_changes += a.pressure != b.pressure
            width_changes += a.width != b.width
            identical_model += (a.x, a.y, a.pressure, a.width) == (b.x, b.y, b.pressure, b.width)
            same_xy_dynamics += distance == 0 and (a.pressure != b.pressure or a.width != b.width)
            if distance:
                tangent = math.atan2(b.y - a.y, b.x - a.x)
                stored = b.direction * 2 * math.pi / 255
                direction_error.append(abs((stored - tangent + math.pi) % (2 * math.pi) - math.pi) * 180 / math.pi)
        lengths.append(length)
        for a, b, c in zip(points, points[1:], points[2:]):
            first, second = (b.x - a.x, b.y - a.y), (c.x - b.x, c.y - b.y)
            n1, n2 = math.hypot(*first), math.hypot(*second)
            if n1 and n2:
                dot = max(-1, min(1, (first[0] * second[0] + first[1] * second[1]) / (n1 * n2)))
                turns.append(math.acos(dot) * 180 / math.pi)
            pressure_extrema += (b.pressure - a.pressure) * (c.pressure - b.pressure) < 0
            width_extrema += (b.width - a.width) * (c.width - b.width) < 0
    length = sum(lengths)
    return dict(strokes=len(lines), points=sum(counts), path_length=length,
                points_per_100_units=100 * sum(counts) / length if length else None,
                points_per_stroke=distribution(counts), path_length_per_stroke=distribution(lengths),
                spacing=distribution(spacings), spacing_below=dict(
                    unit_0_1=sum(v < .1 for v in spacings), unit_0_25=sum(v < .25 for v in spacings),
                    unit_0_5=sum(v < .5 for v in spacings), unit_1=sum(v < 1 for v in spacings)),
                turning_degrees=distribution(turns), turns_above_30_degrees=sum(v > 30 for v in turns),
                native_speed=distribution(speeds), native_speed_nonzero=sum(v != 0 for v in speeds),
                native_speed_spacing_pearson=correlation(speed_spacing),
                encoded_direction_vs_xy_heading_error_degrees=distribution(direction_error),
                pressure_byte=distribution(pressures), width_scene_units=distribution(widths),
                adjacent_pressure_changes=pressure_changes, adjacent_width_changes=width_changes,
                strict_pressure_extrema=pressure_extrema, strict_width_extrema=width_extrema,
                identical_adjacent_model_points=identical_model,
                stationary_adjacent_pressure_or_width_changes=same_xy_dynamics)


def candidate_audit(groups):
    """Exercise the new-stroke reducer on copies; never propose editing imports."""
    from features.notebooks import sampling
    source = Path(sampling.__file__).read_bytes()
    rows = {}
    for tool, lines in sorted(groups.items()):
        before = after = changed = 0
        maximum = dict(xy=0., raw_pressure=0., byte_pressure=0., width=0., projected_xy=0.,
                       projected_raw_pressure=0., projected_byte_pressure=0., projected_width=0.)
        for line in lines:
            points = [[p.x + 702, p.y, p.pressure / 255, p.width / 4] for p in line.points]
            unchanged = [point[:] for point in points]
            kept = sampling.retained_indices(points, tool)
            if points and (not kept or kept[0] != 0 or kept[-1] != len(points) - 1):
                raise AssertionError('Candidate lost an original endpoint.')
            if points != unchanged:
                raise AssertionError('Candidate mutated its audit input.')
            if tool == 21 and kept != list(range(len(points))):
                raise AssertionError('Calligraphy must bypass sample reduction.')
            before += len(points)
            after += len(kept)
            changed += len(kept) != len(points)
            distance = [0.]
            for a, b in zip(points, points[1:]):
                distance.append(distance[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
            for start, end in zip(kept, kept[1:]):
                a, b = points[start], points[end]
                dx, dy, span = b[0] - a[0], b[1] - a[1], distance[end] - distance[start]
                chord2 = dx * dx + dy * dy
                # Retained rows are exact. Evaluate only omitted rows, so a
                # stationary retained pressure transition is not assigned the
                # ambiguous nearest position of its other retained endpoint.
                for index in range(start + 1, end):
                    point = points[index]
                    if not span:
                        if point[2:] != a[2:] or point[2:] != b[2:]:
                            raise AssertionError('Candidate discarded stationary dynamics.')
                        continue
                    fraction = (distance[index] - distance[start]) / span
                    x, y = a[0] + fraction * dx, a[1] + fraction * dy
                    projection = max(0, min(1, ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / chord2)) if chord2 else 0.
                    errors = dict(xy=math.hypot(point[0] - x, point[1] - y),
                        raw_pressure=abs(point[2] - (a[2] + fraction * (b[2] - a[2]))),
                        byte_pressure=abs(round(point[2] * 255) / 255 - (
                            round(a[2] * 255) / 255 + fraction * (round(b[2] * 255) - round(a[2] * 255)) / 255)),
                        width=abs(point[3] - (a[3] + fraction * (b[3] - a[3]))),
                        projected_xy=math.hypot(point[0] - a[0] - projection * dx, point[1] - a[1] - projection * dy),
                        projected_raw_pressure=abs(point[2] - (a[2] + projection * (b[2] - a[2]))),
                        projected_byte_pressure=abs(round(point[2] * 255) / 255 - (
                            round(a[2] * 255) / 255 + projection * (round(b[2] * 255) - round(a[2] * 255)) / 255)),
                        projected_width=abs(point[3] - (a[3] + projection * (b[3] - a[3]))))
                    for key, value in errors.items():
                        maximum[key] = max(maximum[key], value)
        bounds = dict(xy=sampling.POSITION_TOLERANCE, projected_xy=sampling.POSITION_TOLERANCE,
                      raw_pressure=sampling.PRESSURE_TOLERANCE, byte_pressure=sampling.PRESSURE_TOLERANCE,
                      width=sampling.WIDTH_TOLERANCE, projected_raw_pressure=sampling.PRESSURE_TOLERANCE,
                      projected_byte_pressure=sampling.PRESSURE_TOLERANCE, projected_width=sampling.WIDTH_TOLERANCE)
        within = all(maximum[key] <= bound + 1e-10 for key, bound in bounds.items())
        rows[str(tool)] = dict(original_points=before, retained_points=after, reduced_strokes=changed,
            removed_fraction=1 - after / before if before else 0,
            nominal_uncompressed_point_bytes_saved=14 * (before - after),
            maximum_errors=maximum, within_candidate_bounds=within, calligraphy_bypass=tool == 21)
        if not within:
            raise AssertionError(f'Candidate exceeded independent bounds for tool {tool}: {maximum}')
    if Path(sampling.__file__).read_bytes() != source:
        raise ValueError('Candidate source changed during the audit; rerun against one version.')
    return dict(candidate_sha256=sha256(source).hexdigest(), tools=rows,
                position_tolerance=sampling.POSITION_TOLERANCE,
                pressure_tolerance=sampling.PRESSURE_TOLERANCE,
                width_tolerance=sampling.WIDTH_TOLERANCE,
                scope='Hypothetical application to copies of native points only; no archive/native scenes are rewritten and speed/direction are not inferred.')


def measure(archive, manifest, *, audit_candidate=False):
    data = archive.read_bytes()
    layout_data = manifest.read_bytes()
    layout = json.loads(layout_data)
    book = Notebook.read(data)
    if len(book.pages) != 12 or len(layout['pages']) != 12:
        raise ValueError('Use the complete twelve-page version-2 worksheet and manifest.')
    tasks, speed_groups, tools = defaultdict(list), defaultdict(list), defaultdict(list)
    unmatched, ambiguous_speed = Counter(), Counter()
    original_scenes = []
    for index, entry in enumerate(layout['pages']):
        ink = book.page(index)
        if ink.warning:
            raise ValueError(f'Page {index + 1} has unsupported ink: {ink.warning}')
        original_scenes.append(ink.to_bytes())
        native = {f'{b.item.item_id.part1}:{b.item.item_id.part2}': b.item.value
                  for b in ink._blocks if isinstance(b, ss.SceneLineItemBlock) and b.item.value is not None}
        for stroke in ink.strokes:
            line = native[stroke.id]
            if len(line.points) != len(stroke.points) or int(line.tool) != stroke.tool:
                raise AssertionError('Native/model identity mapping differs.')
            tools[int(line.tool)].append(line)
            if entry.get('kind') != 'brush' or int(line.tool) != entry['tool_id_hint'] or not line.points:
                continue
            cx = median(p.x + 702 for p in line.points)
            cy = median(p.y for p in line.points)
            found = False
            for band in entry['bands']:
                for cell in band['cells']:
                    left, top, right, bottom = cell['bounds']
                    if not left <= cx <= right or not top <= cy <= bottom:
                        continue
                    key = (index + 1, entry['title'], int(line.tool), band['width'], cell['task'])
                    tasks[key].append(line)
                    if cell['task'] == 'Speed':
                        middle = (left + right) / 2
                        before = sum(p.x + 702 < middle for p in line.points)
                        if .2 < before / len(line.points) < .8:
                            ambiguous_speed[int(line.tool)] += 1
                        else:
                            group = 'slow_left' if cx < middle else 'fast_right'
                            speed_groups[(index + 1, entry['title'], int(line.tool), band['width'], group)].append(line)
                    found = True
                    break
                if found:
                    break
            if not found:
                unmatched[int(line.tool)] += 1
    reopened = Notebook.read(book.to_bytes())
    if any(reopened.page(i).to_bytes() != scene for i, scene in enumerate(original_scenes)):
        raise AssertionError('Read-only audit changed an original native scene.')
    def records(groups, field):
        return [dict(page=key[0], brush=key[1], tool=key[2], requested_width_band=key[3],
                     **{field: key[4]}, measurements=summarize(lines)) for key, lines in sorted(groups.items())]
    report = dict(schema=1, archive_sha256=sha256(data).hexdigest(), manifest_sha256=sha256(layout_data).hexdigest(),
                pages=len(book.pages), all_tools={str(tool): summarize(lines) for tool, lines in sorted(tools.items())},
                tasks=records(tasks, 'task'), speed_groups=records(speed_groups, 'spatial_speed_label'),
                unmatched_brush_strokes=dict(unmatched), speed_midline_ambiguous_strokes=dict(ambiguous_speed),
                unchanged_original_scene_roundtrip=True,
                units='Native page coordinates; pressure byte 0..255; width in scene units; speed/direction native encoded fields.',
                limitations=[
                    'Task assignment uses median stroke location within guide cells, not handwritten text recognition.',
                    'slow_left/fast_right are spatial labels following the worksheet instruction and visual review, not clock measurements.',
                    'Point records contain no timestamps; native speed units and sampling cadence are not established by this audit.',
                    'Encoded direction is compared numerically with XY heading; correlation does not establish its physical meaning or justify synthesizing it.',
                    'A single tablet/firmware and unconstrained handwriting cannot establish the firmware point-selection algorithm.',
                    'Imported native samples are never candidates for automatic rewriting; measurements guide new-stroke-only decisions.'
                ])
    if audit_candidate:
        report['candidate_on_copies'] = candidate_audit(tools)
    if archive.read_bytes() != data:
        raise ValueError('Original archive changed during the read-only audit.')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--candidate-audit', action='store_true', help='Measure current new-stroke reducer on copies only')
    args = parser.parse_args()
    report = measure(args.archive, args.manifest, audit_candidate=args.candidate_audit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2))
    print(f'Measured {sum(row["points"] for row in report["all_tools"].values())} saved points; original scenes preserved.')
