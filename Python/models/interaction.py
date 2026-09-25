from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class Interaction:
    name: str
    action: Callable | None
    args: Any = None