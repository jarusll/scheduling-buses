import streamlit as st
import pandas as pd
import glob
from dataclasses import dataclass, field

from src.world import WorldBuilder, time_str, Occupied, Vacant
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


def bus_timeline(bus):
    segs = []
    for i in range(len(bus.logs) - 1):
        t_start, st = bus.logs[i]
        t_end, _ = bus.logs[i + 1]
        segs.append({
            "Start": time_str(t_start),
            "End": time_str(t_end),
            "Duration (min)": (t_end - t_start) // 60,
            "Activity": type(st).__name__,
            "Detail": str(st),
        })
    return segs


def station_charges(stop):
    rows = []
    for charger in stop.chargers:
        charge_start = None
        for t, sts in charger.logs:
            match sts:
                case Occupied(bus_id=bid):
                    charge_start = t
                case Vacant():
                    if charge_start is not None:
                        rows.append({
                            "Bus": bid,
                            "Charger": charger.id,
                            "Start": time_str(charge_start),
                            "End": time_str(t),
                            "Duration (min)": (t - charge_start) // 60,
                        })
                        charge_start = None
    return rows


def build_and_run(csv_path, config):
    world = (
        WorldBuilder()
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
        .load_csv(csv_path)
        .set_config(config)
        .build()
    )
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
        [RangeConstraint()],
        ComposedActionCost([WaitTimeCost(), ChargingTooEarlyCost()]),
        StateCost,
        BusDispatchCost,
    )
    s.run()
    return world, s


st.set_page_config(layout="wide")
st.title("Bus Charging Scheduler")

with st.sidebar:
    st.header("Config")
    battery_range = st.number_input("Battery range (km)", value=240)
    charge_time = st.number_input("Charge time (s)", value=1500)
    speed = st.number_input("Speed (km/h)", value=60)
    wi = st.number_input("Individual weight", value=1.0)
    wo = st.number_input("Operator weight", value=1.0)
    ws = st.number_input("System weight", value=1.0)
config = Config(battery_range, charge_time, speed, {"individual": wi, "operator": wo, "overall": ws})

scenario_files = sorted(glob.glob("Scenarios/*.csv"))
scenario_names = [f.split("/")[-1].replace(".csv", "") for f in scenario_files]
selected_scenario = st.selectbox("Select scenario", scenario_names)

csv_path = f"Scenarios/{selected_scenario}.csv"
df = pd.read_csv(csv_path)

with st.spinner("Running scheduler..."):
    world, s = build_and_run(csv_path, config)

tab1, tab2, tab3 = st.tabs(["Input", "Bus Schedule", "Charger"])
with tab1:
    st.dataframe(df, use_container_width=True, height=600)
with tab2:
    buses_sorted = sorted(s.results().values(), key=lambda b: b.bus_id)
    bus_ids = [b.bus_id for b in buses_sorted]
    selected = st.selectbox("Select bus", bus_ids)
    bus = next(b for b in buses_sorted if b.bus_id == selected)

    segs = bus_timeline(bus)
    total = sum(s["Duration (min)"] for s in segs)
    charge = sum(s["Duration (min)"] for s in segs if s["Activity"] == "Charging")
    wait = sum(s["Duration (min)"] for s in segs if s["Activity"] == "Waiting")
    arrival = segs[-1]["End"] if segs else ""

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total trip", f"{total} min")
    c2.metric("Charging", f"{charge} min")
    c3.metric("Waiting", f"{wait} min")
    c4.metric("Departure", time_str(bus.departure_time))
    c5.metric("Arrival", arrival)

    st.dataframe(pd.DataFrame(segs), use_container_width=True, height=600)
with tab3:
    station = st.selectbox("Select station", ["A", "B", "C", "D"])
    stop = world.stops[station]
    charges = station_charges(stop)
    st.dataframe(pd.DataFrame(charges), use_container_width=True, height=600)
