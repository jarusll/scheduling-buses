# How to run

```bash
streamlit run app.py
```

# How to change weights(or other values)
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
