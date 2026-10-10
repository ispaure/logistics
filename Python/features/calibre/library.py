"""Calibre library model and public launch/export operations."""

from pathlib import Path
from subprocess import TimeoutExpired

from commonUtils.filesystem.directories import Directory
from commonUtils.runtime.diagnostics import Severity, log
from .export import build_export_plan, execute_export_plan
from .launching import launch_library

__author__ = 'Marc-André Voyer'
__copyright__ = 'Copyright (C) 2020-2026, Marc-André Voyer'
__license__ = 'MIT License'
__maintainer__ = 'Marc-André Voyer'
__email__ = 'marcandre.voyer@gmail.com'
__status__ = 'Production'


class CalibreLibrary(Directory):
    def __init__(self, path: Path):
        super().__init__(path)

    def open_in_calibre(self) -> bool:
        try:
            launch_library(self.path)
        except (OSError, TimeoutExpired) as error:
            log(Severity.ERROR, 'Open Calibre', str(error), popup=True)
            return False
        return True

    def echo_book_formats(self, destination: Path, extensions):
        """Mirror selected formats into a dedicated export directory."""
        plan = build_export_plan(self.path, destination, extensions)
        for warning in plan.warnings:
            log(Severity.WARNING, 'Calibre Book Format Echo', warning)
        result = execute_export_plan(plan)
        log(Severity.INFO, 'Calibre Book Format Echo',
            f'Copied {result.copied} new | Updated {result.updated} changed | Deleted {result.deleted} obsolete')
        return result
