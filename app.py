import streamlit as st
import pandas as pd
import tempfile
import os

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


def build_and_run(csv_path):
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

uploaded = st.file_uploader("Choose a CSV scenario file", type="csv")
if uploaded is None:
    st.info("Upload a CSV file to run the scheduler.")
    st.stop()

df = pd.read_csv(uploaded)

with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
    f.write(uploaded.getbuffer())
    csv_path = f.name

with st.spinner("Running scheduler..."):
    world, s = build_and_run(csv_path)
os.unlink(csv_path)

bus_rows = []
for bus in sorted(s.results().values(), key=lambda b: b.bus_id):
    for t, sts in bus.logs:
        bus_rows.append({
            "Bus": bus.bus_id,
            "Operator": bus.operator,
            "Route": bus.route,
            "Time": time_str(t),
            "Event": type(sts).__name__,
            "Detail": str(sts),
        })
df_bus = pd.DataFrame(bus_rows)

charger_rows = []
for sid in ["A", "B", "C", "D"]:
    stop = world.stops[sid]
    for charger in stop.chargers:
        for t, sts in charger.logs:
            charger_rows.append({
                "Station": sid,
                "Charger": charger.id,
                "Time": time_str(t),
                "Event": type(sts).__name__,
                "Detail": str(sts),
            })
df_charger = pd.DataFrame(charger_rows)

tab1, tab2, tab3 = st.tabs(["Input", "Bus Schedule", "Charger"])
with tab1:
    st.dataframe(df, use_container_width=True, height=600)
with tab2:
    st.dataframe(df_bus, use_container_width=True, height=600)
with tab3:
    st.dataframe(df_charger, use_container_width=True, height=600)
