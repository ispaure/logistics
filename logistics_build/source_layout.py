"""Resolve build commands against the selected source, including historical layout.

Current checkouts have one tooling owner. Historical snapshots retain the code
that belonged to their revision; no obsolete scripts are copied into new source.
"""
from dataclasses import replace
from pathlib import Path
import re


def adapt_plan(plan):
    phases = []
    for phase in plan.phases:
        root = Path(phase.cwd)
        legacy = (root / 'Scripts/build_project.py').is_file() and not (root / 'logistics_build/build_project.py').is_file()
        if not legacy:
            phases.append(phase)
            continue
        def adapted(command):
            result = []
            for index, argument in enumerate(command):
                if index and command[index - 1] == '-m' and re.fullmatch(r'logistics_build\.\w+', argument):
                    name = argument.partition('.')[2]
                    if not (root / 'Scripts' / (name + '.py')).is_file():
                        raise ValueError('Selected source predates the required build adapter: ' + name)
                    argument = 'Scripts.' + name
                result.append(argument)
            return tuple(result)
        phases.append(replace(phase, argv=adapted(phase.argv), reuse_probe=adapted(phase.reuse_probe)))
    return replace(plan, phases=tuple(phases))
