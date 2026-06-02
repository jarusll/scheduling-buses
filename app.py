from src.world import WorldBuilder, time_str
from src.scheduler import (
    ComposedDispatchCost,
    IndividualDispatchCost,
    OperatorDispatchCost,
    Scheduler,
    RangeConstraint,
    SystemDispatchCost,
    WaitTimeCost,
    ChargingTooEarlyCost,
    ComposedActionCost,
    ComposedCost,
    WeightedCost,
    IndividualCost,
    OperatorCost,
    SystemCost,
    WeightedDispatchCost,
)

world = (WorldBuilder()
    .add_route("BK", ["Bengaluru", "A", "B", "C", "D", "Kochi"])
    .add_route("KB", ["Kochi", "D", "C", "B", "A", "Bengaluru"])
    .add_connection("Bengaluru", "A", 100)
    .add_connection("A", "B", 120)
    .add_connection("B", "C", 100)
    .add_connection("C", "D", 120)
    .add_connection("D", "Kochi", 100)
    .add_stop("Bengaluru", 0)
    .add_stop("A", 1)
    .add_stop("B", 1)
    .add_stop("C", 1)
    .add_stop("D", 1)
    .add_stop("Kochi", 0)
    .load_csv("Scenarios/1.csv")
    .build()
)

w = world.config.weights
StateCost = ComposedCost([
    WeightedCost(
        w["individual"],
        IndividualCost(),
    ),
    WeightedCost(
        w["operator"],
        OperatorCost(),
    ),
    WeightedCost(
        w["overall"],
        SystemCost(),
    ),
])

BusDispatchCost = ComposedDispatchCost([
            WeightedDispatchCost(
                w["individual"],
                IndividualDispatchCost(),
            ),
            WeightedDispatchCost(
                w["operator"],
                OperatorDispatchCost(),
            ),
            WeightedDispatchCost(
                w["overall"],
                SystemDispatchCost(),
            ),
        ])

s = Scheduler(
    world,
    [RangeConstraint()],
    ComposedActionCost([WaitTimeCost(), ChargingTooEarlyCost()]),
    StateCost,
    BusDispatchCost
)
s.run()

for bus in sorted(s.results().values(), key=lambda b: b.bus_id):
    print(f"\n{bus.bus_id} ({bus.operator}, {bus.route})")
    for t, st in bus.logs:
        print(f"  {time_str(t)}  {type(st).__name__:<15} {st}")

print("\n\nCharger logs:")
for sid, stop in world.stops.items():
    for charger in stop.chargers:
        if charger.logs:
            print(f"\n  {sid} charger {charger.id}:")
            for t, st in charger.logs:
                print(f"    {time_str(t)}  {type(st).__name__:<15} {st}")
