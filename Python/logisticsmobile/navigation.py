"""Platform-independent destination state; native widgets are presentation only."""
from dataclasses import dataclass, field

DESTINATIONS = ('home', 'files', 'documents', 'settings')


@dataclass
class NavigationState:
    destination: str = 'home'
    routes: dict = field(default_factory=lambda: {key: [] for key in DESTINATIONS})

    def select(self, destination):
        if destination not in DESTINATIONS:
            raise ValueError('Unknown mobile destination.')
        self.destination = destination

    def push(self, route):
        if not isinstance(route, str) or not route or len(route) > 200:
            raise ValueError('Invalid navigation route.')
        self.routes[self.destination].append(route)

    def back(self):
        routes = self.routes[self.destination]
        return routes.pop() if routes else None
