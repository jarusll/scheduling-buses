import heapq
from dataclasses import dataclass
from world import World, Action, Skip, Charge


@dataclass
class BusArrived:
    stop: str
    bus_id: str


@dataclass
class ChargerFreed:
    stop: str
    charger_id: int


@dataclass
class Event:
    time: int
    payload: BusArrived | ChargerFreed

    def __lt__(self, other):
        return self.time < other.time


class EventQueue:
    def __init__(self):
        self._heap: list[Event] = []

    def push(self, time: int, payload: BusArrived | ChargerFreed):
        heapq.heappush(self._heap, Event(time, payload))

    def pop(self) -> Event:
        return heapq.heappop(self._heap)

    def __bool__(self):
        return bool(self._heap)


class Constraint:
    def validate(self, world: World, action: Action) -> bool:
        return True


class RangeConstraint(Constraint):
    def validate(self, world: World, action: Action) -> bool:
        match action:
            case Skip(stop=s, bus_id=b):
                bus = world.buses[b]
                next_stop = world.next_stop(bus.route, bus.route_index)
                if next_stop is None:
                    return True
                return bus.km_remaining >= world.distance(s, next_stop)
            case _:
                return True


class Cost:
    def score(self, world: World, action: Action) -> float:
        return 0.0


class WaitTimeCost(Cost):
    def score(self, world: World, action: Action) -> float:
        match action:
            case Charge(bus_id=b):
                return world.config.charge_time_s
            case _:
                return 0.0
