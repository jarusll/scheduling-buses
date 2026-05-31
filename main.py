from dataclasses import dataclass, field


@dataclass
class Vacant:
    pass


@dataclass
class Occupied:
    bus_id: str
    available_at: int


ChargerState = Vacant | Occupied


@dataclass
class NotStarted:
    pass


@dataclass
class Waiting:
    at_stop: str


@dataclass
class Charging:
    at_stop: str
    charger_id: int


@dataclass
class Driving:
    from_stop: str
    to_stop: str
    remaining_km: int


@dataclass
class OutOfCharge:
    pass


@dataclass
class Finished:
    pass


BusStatus = NotStarted | Waiting | Charging | Driving | OutOfCharge | Finished


@dataclass
class Charger:
    id: int
    status: ChargerState = field(default_factory=Vacant)


@dataclass
class Bus:
    bus_id: str
    operator: str
    route: str
    departure_time: int
    status: BusStatus = field(default_factory=NotStarted)


@dataclass
class BusStop:
    name: str
    chargers: list[Charger] = field(default_factory=lambda: [Charger(0)])
    queue: list[Bus] = field(default_factory=list)


@dataclass
class Config:
    battery_range_km: int = 240
    charge_time_s: int = 1500
    speed_kmph: int = 60
    weights: dict[str, float] = field(default_factory=lambda: {
        "individual": 1.0,
        "operator": 1.0,
        "overall": 1.0,
    })


@dataclass
class World:
    routes: dict[str, list[str]]
    connections: dict[tuple[str, str], int]
    buses: list[Bus] = field(default_factory=list)
    stops: dict[str, BusStop] = field(default_factory=dict)
    config: Config = field(default_factory=Config)

    def get_stop(self, name: str) -> BusStop:
        return self.stops[name]

    def distance(self, from_stop: str, to_stop: str) -> int:
        return self.connections[(from_stop, to_stop)]

    def next_stop(self, route_id: str, current_index: int) -> str | None:
        stops = self.routes[route_id]
        if current_index + 1 < len(stops):
            return stops[current_index + 1]
        return None


class WorldBuilder:
    def __init__(self):
        self.routes = {}
        self.connections = {}

    def add_route(self, route_id: str, stops: list[str]):
        self.routes[route_id] = stops
        return self

    def add_connection(self, from_stop: str, to_stop: str, distance_km: int):
        self.connections[(from_stop, to_stop)] = distance_km
        return self

    def validate(self) -> list[str]:
        missing = []
        for route_id, stops in self.routes.items():
            for i in range(len(stops) - 1):
                pair = (stops[i], stops[i + 1])
                if pair not in self.connections:
                    missing.append(f"{route_id}: {pair[0]} \u2192 {pair[1]} missing")
        return missing

    def build(self) -> World:
        errors = self.validate()
        if errors:
            raise ValueError(
                "Missing connections:\n" + "\n".join(f"  {e}" for e in errors)
            )
        return World(routes=self.routes, connections=self.connections)
