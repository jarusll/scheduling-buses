import heapq
from dataclasses import dataclass, field
from world import World, Bus, BusAction, Skip, Wait, Charge, Vacant, Occupied, Charging, Driving, Waiting, Finished


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
    now: int = 0
    metrics: dict[str, dict[str, int]] = field(default_factory=dict)


class Constraint:
    def validate(self, world: World, action: BusAction) -> bool:
        return True


class RangeConstraint(Constraint):
    def validate(self, world: World, action: BusAction) -> bool:
        match action:
            case Skip(stop=s, bus_id=b):
                bus = world.buses[b]
                next_stop = world.next_stop(bus.route, bus.route_index)
                if next_stop is None:
                    return True
                return bus.km_remaining >= world.distance(s, next_stop)
            case _:
                return True


class StateCost:
    def calculate(self, state: SimState) -> float:
        raise NotImplementedError


class WeightedCost(StateCost):
    def __init__(self, weight: float, cost: StateCost):
        self.weight = weight
        self.cost = cost

    def calculate(self, state: SimState) -> float:
        return self.weight * self.cost.calculate(state)


class ComposedCost(StateCost):
    def __init__(self, costs: list[StateCost]):
        self.costs = costs

    def calculate(self, state: SimState) -> float:
        return sum(cost.calculate(state) for cost in self.costs)


class IndividualWaitCost(StateCost):
    def calculate(self, state: SimState) -> float:
        cost = 0.0
        for bus in state.world.buses.values():
            cost += state.metrics[bus.bus_id]["wait"]
        return cost / len(state.world.buses)


class OperatorWaitCost(StateCost):
    def calculate(self, state: SimState) -> float:
        operator_waits: dict[str, list[int]] = {}

        for bus in state.world.buses.values():
            operator_waits.setdefault(bus.operator, []).append(
                    state.metrics[bus.bus_id]["wait"]
                )

        total = 0.0
        for waits in operator_waits.values():
            total += sum(waits) / len(waits)

        return total / len(operator_waits)

class SystemWaitCost(StateCost):
    def calculate(self, state: SimState) -> float:
        total = 0.0

        for bus in state.world.buses.values():
            total += state.metrics[bus.bus_id]["wait"]

        return total


IndividualCost = IndividualWaitCost
OperatorCost = OperatorWaitCost
SystemCost = SystemWaitCost


class ActionCost:
    def calculate(self, state: SimState, action: BusAction) -> float:
        raise NotImplementedError


class WeightedActionCost(ActionCost):
    def __init__(self, weight: float, cost: ActionCost):
        self.weight = weight
        self.cost = cost

    def calculate(self, state: SimState, action: BusAction) -> float:
        return self.weight * self.cost.calculate(state, action)


class ComposedActionCost(ActionCost):
    def __init__(self, costs: list[ActionCost]):
        self.costs = costs

    def calculate(self, state: SimState, action: BusAction) -> float:
        return sum(cost.calculate(state, action) for cost in self.costs)


class WaitTimeCost(ActionCost):
    def calculate(self, state: SimState, action: BusAction) -> float:
        match action:
            case Wait(stop=stop_id, bus_id=_):
                stop = state.world.stops[stop_id]
                charge_time = state.world.config.charge_time_s

                free_times: list[int] = []
                for charger in stop.chargers:
                    match charger.status:
                        case Occupied(available_at=available_at):
                            free_times.append(available_at)
                        case _:
                            free_times.append(state.now)

                for _ in stop.queue:
                    next_free = min(free_times)
                    free_times[free_times.index(next_free)] = next_free + charge_time

                start_time = min(free_times)
                return max(0, start_time - state.now)

            case _:
                return 0.0


WaitActionCost = WaitTimeCost


class ChargingTooEarlyCost(ActionCost):
    def __init__(
        self,
        high_penalty: float = 5.0,
        medium_penalty: float = 3.0,
        low_penalty: float = 1.0,
        high_threshold: float = 0.75,
        medium_threshold: float = 0.50,
        low_threshold: float = 0.25,
    ):
        self.high_penalty = high_penalty
        self.medium_penalty = medium_penalty
        self.low_penalty = low_penalty
        self.high_threshold = high_threshold
        self.medium_threshold = medium_threshold
        self.low_threshold = low_threshold

    def calculate(self, state: SimState, action: BusAction) -> float:
        match action:
            case Charge(bus_id=bus_id):
                bus = state.world.buses[bus_id]
                max_range = state.world.config.battery_range_km
                if max_range <= 0:
                    return 0.0

                pct_remaining = bus.km_remaining / max_range

                if pct_remaining >= self.high_threshold:
                    return self.high_penalty
                if pct_remaining >= self.medium_threshold:
                    return self.medium_penalty
                if pct_remaining >= self.low_threshold:
                    return self.low_penalty
                return 0.0

            case _:
                return 0.0


class Scheduler:
    def __init__(self, world: World, constraints: list[Constraint], costs: list[StateCost]):
        self.state = SimState(world, EventQueue())
        for bid in world.buses:
            self.state.metrics[bid] = {"wait": 0}
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
            self.state.now = now

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

                    allCases: list[BusAction] = [Skip(sid, bid)]
                    vacantCharger = None
                    for charger in stop.chargers:
                        match charger.status:
                            case Vacant():
                                vacantCharger = charger
                                break
                    if vacantCharger and not stop.queue:
                        allCases.append(Charge(sid, bid, vacantCharger.id))
                    else:
                        allCases.append(Wait(sid, bid))

                    validCases = []
                    for case in allCases:
                        allConstraintsPassed = True
                        for constraint in self.constraints:
                            if not constraint.validate(world, case):
                                allConstraintsPassed = False
                                break
                        if allConstraintsPassed:
                            validCases.append(case)

                    best = None
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
                        case Wait(stop=sid, bus_id=bid):
                            bus.set_status(now, Waiting(at_stop=sid))
                            stop.queue.append(bus)
                        case _:
                            print(self.state)
                            raise Exception("No valid action for bus arrived event")

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
