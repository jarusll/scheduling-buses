import heapq
from dataclasses import dataclass, field
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
    costs: dict[str, dict[str, int]] = field(default_factory=dict)


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
    def calculate(self, world: World, action: Action) -> float:
        return 0.0


class WaitTimeCost(Cost):
    def calculate(self, world: World, action: Action) -> float:
        match action:
            case Charge():
                return world.config.charge_time_s
            case _:
                return 0.0


class Scheduler:
    def __init__(self, world: World, constraints: list[Constraint], costs: list[Cost]):
        self.state = SimState(world, EventQueue())
        for bid in world.buses:
            self.state.costs[bid] = {"wait": 0}
        self.constraints = constraints
        self.costs = costs
        self.seed()

    def seed(self):
        for bus in self.state.world.buses.values():
            first_stop = self.state.world.routes[bus.route][0]
            self.state.events.push(bus.departure_time, BusArrived(first_stop, bus.bus_id))

    def run(self):
        world = self.state.world
        config = world.config

        while self.state.events:
            event = self.state.events.pop()
            now = event.time

            match event.payload:
                case BusArrived(stop=sid, bus_id=bid):
                    bus = world.buses[bid]
                    stop = world.stops[sid]
                    i = bus.route_index

                    if not stop.chargers:
                        next_sid = world.next_stop(bus.route, i)
                        if next_sid is None:
                            bus.set_status(now, Finished())
                        else:
                            distance = world.distance(sid, next_sid)
                            travelDuration = int(distance / config.speed_kmph * 3600)
                            bus.set_status(now, Driving(from_stop=sid, to_stop=next_sid, remaining_km=distance))
                            bus.route_index = i + 1
                            bus.km_remaining -= distance
                            self.state.events.push(now + travelDuration, BusArrived(next_sid, bid))
                        continue

                    allCases: list[Action] = [Skip(sid, bid)]
                    vacantCharger = None
                    for charger in stop.chargers:
                        match charger.status:
                            case Vacant():
                                vacantCharger = charger
                                break
                    if vacantCharger:
                        allCases.append(Charge(sid, bid, vacantCharger.id))
                    else:
                        allCases.append(Waiting(at_stop=sid))

                    validCases = []
                    for case in allCases:
                        allConstraintsPassed = True
                        for constraint in self.constraints:
                            if not constraint.validate(world, case):
                                allConstraintsPassed = False
                                break
                        if allConstraintsPassed:
                            validCases.append(case)

                    best = validCases[0]
                    best_score = None
                    for case in validCases:
                        pass
                    match best:
                        case Skip():
                            next_sid = world.next_stop(bus.route, i)
                            distance = world.distance(sid, next_sid)
                            travelDuration = int(distance / config.speed_kmph * 3600)
                            bus.set_status(now, Driving(from_stop=sid, to_stop=next_sid, remaining_km=distance))
                            bus.route_index = i + 1
                            bus.km_remaining -= distance
                            self.state.events.push(now + travelDuration, BusArrived(next_sid, bid))
                        case Charge(stop=sid, bus_id=bid, charger_id=cid):
                            charger = stop.chargers[cid]
                            charger.set_status(now, Occupied(bid, now + config.charge_time_s))
                            bus.set_status(now, Charging(at_stop=sid, charger_id=cid))
                            bus.km_remaining = config.battery_range_km
                            self.state.events.push(now + config.charge_time_s, ChargerFreed(sid, cid))

                case ChargerFreed(stop=sid, charger_id=cid):
                    stop = world.stops[sid]
                    charger = stop.chargers[cid]
                    bid = charger.status.bus_id
                    bus = world.buses[bid]
                    next_sid = world.next_stop(bus.route, bus.route_index)
                    if next_sid is None:
                        bus.set_status(now, Finished())
                    else:
                        distance = world.distance(sid, next_sid)
                        travelDuration = int(distance / config.speed_kmph * 3600)
                        bus.set_status(now, Driving(from_stop=sid, to_stop=next_sid, remaining_km=distance))
                        bus.route_index += 1
                        bus.km_remaining -= distance
                        self.state.events.push(now + travelDuration, BusArrived(next_sid, bid))
                    charger.set_status(now, Vacant())
                    if stop.queue:
                        bus = stop.queue.pop(0)
                        bid = bus.bus_id
                        bus.set_status(now, Charging(at_stop=sid, charger_id=cid))
                        bus.km_remaining = config.battery_range_km
                        charger.set_status(now, Occupied(bid, now + config.charge_time_s))
                        self.state.events.push(now + config.charge_time_s, ChargerFreed(sid, cid))

    def results(self) -> dict[str, Bus]:
        return self.state.world.buses
