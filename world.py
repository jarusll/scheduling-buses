from dataclasses import dataclass, field

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


def time_str(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    return f"{h:02d}:{m:02d}"


def time_parse(s: str) -> int:
    h, m = s.split(":")
    return int(h) * 3600 + int(m) * 60


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
class BusCosts:
    wait_time_s: int = 0


@dataclass
class Bus:
    bus_id: str
    operator: str
    route: str
    departure_time: int
    route_index: int = 0
    km_remaining: int = 0
    status: BusStatus = field(default_factory=NotStarted)
    costs: BusCosts = field(default_factory=BusCosts)


@dataclass
class Charge:
    stop: str
    bus_id: str
    charger_id: int


@dataclass
class Skip:
    stop: str
    bus_id: str


Action = Charge | Skip


@dataclass
class BusStop:
    name: str
    chargers: list[Charger] = field(default_factory=lambda: [Charger(0)])
    queue: list[Bus] = field(default_factory=list)


@dataclass
class World:
    routes: dict[str, list[str]]
    connections: dict[tuple[str, str], int]
    buses: dict[str, Bus] = field(default_factory=dict)
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

    def show(self):
        print(f"\n{'Bus ID':<20} {'Operator':<12} {'Route':<6} {'Departure':<8}")
        print("-" * 48)
        for bus in self.buses.values():
            print(f"{bus.bus_id:<20} {bus.operator:<12} {bus.route:<6} {time_str(bus.departure_time):<8}")
        print(f"\nRoutes: {list(self.routes.keys())}")
        print(f"Stops: {list(self.stops.keys())}")
        print(f"Connections: {len(self.connections) // 2} bidirectional")
        print(f"Range: {self.config.battery_range_km}km, Charge: {self.config.charge_time_s}s, Speed: {self.config.speed_kmph}km/h")


class WorldBuilder:
    def __init__(self):
        self.routes = {}
        self.connections = {}
        self.buses = {}
        self.stops = {}
        self.config = Config()

    def add_route(self, route_id: str, stops: list[str]):
        self.routes[route_id] = stops
        return self

    def add_connection(self, from_stop: str, to_stop: str, distance_km: int):
        self.connections[(from_stop, to_stop)] = distance_km
        self.connections[(to_stop, from_stop)] = distance_km
        return self

    def add_stop(self, name: str, chargers: int = 1):
        self.stops[name] = BusStop(name, [Charger(i) for i in range(chargers)])
        return self

    def load_csv(self, path: str):
        import csv
        with open(path) as f:
            for row in csv.DictReader(f):
                departure = time_parse(row["departure"])
                self.buses[row["busid"]] = Bus(
                    bus_id=row["busid"],
                    operator=row["operator"],
                    route=row["route"],
                    departure_time=departure,
                )
        return self

    def set_weights(self, **weights: float):
        self.config.weights.update(weights)
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
        for bus in self.buses.values():
            bus.km_remaining = self.config.battery_range_km
        return World(
            routes=self.routes,
            connections=self.connections,
            buses=self.buses,
            stops=self.stops,
            config=self.config,
        )
