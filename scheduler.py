import heapq
from dataclasses import dataclass
from world import World, Bus, Action, Skip, Charge, Vacant, Occupied, Charging, Driving, Waiting, Finished


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


@dataclass
class SimState:
    world: World
    events: EventQueue


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
            case Charge():
                return world.config.charge_time_s
            case _:
                return 0.0


class Scheduler:
    def __init__(self, world: World):
        self.state = SimState(world, EventQueue())
        self.seed()

    def seed(self):
        for bus in self.state.world.buses.values():
            first_stop = self.state.world.routes[bus.route][0]
            self.state.events.push(bus.departure_time, BusArrived(first_stop, bus.bus_id))
        for sid, stop in self.state.world.stops.items():
            for cid in range(len(stop.chargers)):
                self.state.events.push(0, ChargerFreed(sid, cid))

    def run(self):
        world = self.state.world
        config = world.config

        while self.state.events:
            event = self.state.events.pop()
            now = event.time

            match event.payload:
                case BusArrived(stop=sid, bus_id=bid):
                    pass

                case ChargerFreed(stop=sid, charger_id=cid):
                    stop = world.stops[sid]
                    charger = stop.chargers[cid]
                    match charger.status:
                        case Occupied(bus_id=bid):
                            bus = world.buses[bid]
                            next_sid = world.next_stop(bus.route, bus.route_index)
                            if next_sid is None:
                                bus.status = Finished()
                            else:
                                dist = world.distance(sid, next_sid)
                                travel = int(dist / config.speed_kmph * 3600)
                                bus.status = Driving(from_stop=sid, to_stop=next_sid, remaining_km=dist)
                                bus.route_index += 1
                                bus.km_remaining -= dist
                                self.state.events.push(now + travel, BusArrived(next_sid, bid))
                    charger.status = Vacant()
                    if stop.queue:
                        bus = stop.queue.pop(0)
                        bus.status = Charging(at_stop=sid, charger_id=cid)
                        bus.km_remaining = config.battery_range_km
                        charger.status = Occupied(bus.bus_id, now + config.charge_time_s)
                        self.state.events.push(now + config.charge_time_s, ChargerFreed(sid, cid))

    def results(self) -> dict[str, Bus]:
        return self.state.world.buses
