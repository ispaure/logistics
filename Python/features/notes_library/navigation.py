"""Pure path and history projection after a published library mutation."""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class PathChange:
    source: str | None = None
    destination: str | None = None
    deleted: str | None = None

    def removes(self, path):
        return bool(path is not None and self.deleted is not None and
                    (path == self.deleted or path.startswith(self.deleted + '/')))

    def remap(self, path):
        if path is not None and self.source is not None and self.destination is not None and (
                path == self.source or path.startswith(self.source + '/')):
            return self.destination + path[len(self.source):]
        return path

    def history(self, paths, index):
        """Preserve visit occurrences and the cursor, even for repeated paths."""
        retained = sum(not self.removes(path) for path in paths[:index + 1]) - 1
        return [self.remap(path) for path in paths if not self.removes(path)], retained

    def positions(self, positions):
        return {self.remap(path): value for path, value in positions.items()
                if not self.removes(path)}


@dataclass
class MutationResult:
    """A committed filesystem result survives refresh/reference failures."""
    destination: str
    folders: list = field(default_factory=list)
    refresh_errors: list = field(default_factory=list)
    reference_errors: list = field(default_factory=list)
