## Framework used
None. I am using Constraints and Cost optimization to find a reasonable schedule. I react to the events in order and get valid paths from there, and then Lookahead at N events and pick the one with minimum of current action cost + future cost.

## Data Structure
Time is remaining seconds since midnight 00:00 just in case if minute wasn't granular enough.

SimState = {
    WorldState = {
        Routes,
        Connections,
        Buses,
        Stops
    }
    EventQueue = MinHeap(BusEvents | ChargerEvents)
}

Routes are deterministic so its a List[Stops]
Connections = Map[Tuple(Stop, Stop)] = Distance

SimState contains the whole state and can be forked off easily.

## Future changes anticipated

All costs are composable so it can be easily reduced into 1.
Stations can have multiple chargers.

## How to change weights?
```py
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
```

## How you'd add a new rule?

Cost calculation for bus - ActionCost#calculate(self, state: SimState, action: BusAction) -> float
Cost calculation for current world state = StateCost#calculate(self, state: SimState) -> float
Cost calculation at Chargers = DispatchCost#calculate(self, state: SimState, bus: Bus) -> float

```py
w = world.config.weights
StateCost = ComposedCost([
    WeightedCost(w["individual"], IndividualCost()),
    WeightedCost(w["operator"], OperatorCost()),
    WeightedCost(w["overall"], SystemCost()),
])
BusDispatchCost = ComposedDispatchCost([
    WeightedDispatchCost(w["individual"], IndividualDispatchCost()),
    WeightedDispatchCost(w["operator"], OperatorDispatchCost()),
    WeightedDispatchCost(w["overall"], SystemDispatchCost()),
])
s = Scheduler(
    world,
    [RangeConstraint()], # constraints
    ComposedActionCost([WaitTimeCost(), ChargingTooEarlyCost()]), # ActionCost for buses
    StateCost,
    BusDispatchCost, # Charger priority cost
)
```

## Assumptions
Keep the world general enough to be easy for future changes.
