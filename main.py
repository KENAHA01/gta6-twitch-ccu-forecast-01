"""gta6-twitch-ccu-forecast-01 entry: fitted launch-day curve forecaster.

Model: for each forecast hour h = 2..24, the five quantiles of that hour's
Twitch viewers are hour 1's print p1 times exp() of a fitted log-ratio:

    q_tau(h) = p1 * exp(median_h + (q_tau_h - median_h) * WIDEN)

where (q05, q25, q50, q75, q95)_h are the empirical quantiles of
ln(viewers_h / viewers_1) over past big game launches' release days,
taken from the comparables shipped in the kit (SullyGnome hourly
category averages). Two fits are baked in:

  - BASE_Q: 27 launches whose hour-1 print was at least 20,000 viewers
    (a real launch hour, not a pre-unlock trickle).
  - BIG_Q: 20 launches whose hour-1 print was at least 50,000 viewers.

The BIG fit is used when p1 >= 50,000, else BASE. Big launches behave
differently: their hour-1 print is already near the day's early peak
(median ratio dips to ~0.53 around hours 10-11, then climbs to ~1.36
around hours 20-21 as the US audience unlocks and prime time arrives),
while smaller launches keep climbing longer. Launches with a tiny
hour-1 print (unlock still hours away at 00:00 UTC) were excluded:
their ratios explode 100x-2000x and would poison the quantiles.

WIDEN = 1.25 stretches every quantile away from its median. The
empirical quantiles come from only 20-27 launches, so their tails are
too narrow; leave-one-out backtesting over the 27 launches picked
1.2-1.4 as a flat optimum (loss 0.273 at 1.25 vs 0.277 unwidened),
so 1.25 sits mid-plateau rather than at a tuned peak.

Leave-one-out backtest (each launch held out, fit from the rest,
mean pinball loss on the log scale, same scorer as the contest):
model 0.273 vs house baseline 0.321 over the 27 launches with
hour-1 >= 20,000. The house baseline scores about 0.387 on the
four practice cases; the practice cases' true answers are not in
the kit, so no direct practice score is claimed here.

Python 3.13 standard library only, no network, deterministic:
same input bytes give the same output bytes. Reads every *.in in
MAKEFUN_INPUT_DIR (else /input) and writes <id>.out per case into
MAKEFUN_OUTPUT_DIR (else /output).
"""

import json
import math
import os
import sys
from pathlib import Path

# The grader's -P leaves /bot off sys.path: put it back first, so a
# module shipped beside this file would import. (No such module here.)
sys.path.insert(0, str(Path(__file__).resolve().parent))

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

# Quantile levels, in the order each output row lists them.
LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
# Hour-1 print at/above which the BIG fit is used.
BIG_THRESHOLD = 50000
# Tail widening factor around each hour's median log-ratio.
WIDEN = 1.25

# Empirical log-ratio quantiles (q05, q25, q50, q75, q95) per hour,
# fitted on 27 past launches with hour-1 print >= 20,000.
# Row i is forecast hour i + 2.
BASE_Q = [
    (-0.3448, -0.2036, -0.1200, 0.0079, 0.2585),  # hour 2
    (-0.7342, -0.3941, -0.3248, -0.0949, 0.1914),  # hour 3
    (-0.8571, -0.6436, -0.3044, -0.1648, 0.1644),  # hour 4
    (-0.9289, -0.4555, -0.2426, -0.0987, 0.1793),  # hour 5
    (-0.9582, -0.5413, -0.1789, 0.0310, 0.4741),  # hour 6
    (-0.9807, -0.6060, -0.2316, 0.0421, 0.6357),  # hour 7
    (-0.9077, -0.5970, -0.2812, -0.0345, 0.6245),  # hour 8
    (-0.9148, -0.7155, -0.3134, -0.0016, 0.6344),  # hour 9
    (-0.8665, -0.7291, -0.3617, 0.0141, 0.6405),  # hour 10
    (-0.8951, -0.7010, -0.2442, 0.0216, 0.6196),  # hour 11
    (-0.9277, -0.6590, -0.0890, 0.0513, 0.6520),  # hour 12
    (-0.6880, -0.5098, -0.0710, 0.1549, 0.7884),  # hour 13
    (-0.5654, -0.3909, 0.0375, 0.2990, 0.8985),  # hour 14
    (-0.5180, -0.2797, 0.1523, 0.4745, 0.9754),  # hour 15
    (-0.5266, -0.1874, 0.2012, 0.6108, 1.0010),  # hour 16
    (-0.4702, -0.0630, 0.2453, 0.6929, 0.9978),  # hour 17
    (-0.2042, 0.0199, 0.3211, 0.7758, 1.1873),  # hour 18
    (-0.1369, 0.0468, 0.4044, 0.9451, 1.5921),  # hour 19
    (-0.1607, 0.0898, 0.4284, 0.9260, 1.9813),  # hour 20
    (-0.1368, 0.1735, 0.4015, 0.8912, 2.0155),  # hour 21
    (-0.1566, 0.0941, 0.4758, 0.8646, 1.8116),  # hour 22
    (-0.2747, 0.0422, 0.5217, 0.8333, 1.7041),  # hour 23
    (-0.3419, -0.0244, 0.1726, 0.7755, 1.4671),  # hour 24
]

# Empirical log-ratio quantiles (q05, q25, q50, q75, q95) per hour,
# fitted on 20 past launches with hour-1 print >= 50,000.
# Row i is forecast hour i + 2.
BIG_Q = [
    (-0.2172, -0.1523, -0.0910, 0.0301, 0.2842),  # hour 2
    (-0.5584, -0.3711, -0.2267, -0.0830, 0.1648),  # hour 3
    (-0.7935, -0.5947, -0.3208, -0.1668, 0.0096),  # hour 4
    (-0.7744, -0.4737, -0.3173, -0.1695, 0.0791),  # hour 5
    (-0.7830, -0.5898, -0.3050, 0.0087, 0.2697),  # hour 6
    (-1.0492, -0.6774, -0.3865, -0.0048, 0.2648),  # hour 7
    (-0.9793, -0.6158, -0.4144, -0.0494, 0.2567),  # hour 8
    (-0.9500, -0.7306, -0.4749, -0.0669, 0.2083),  # hour 9
    (-0.8772, -0.7580, -0.6076, -0.0595, 0.1780),  # hour 10
    (-0.9327, -0.7115, -0.6271, -0.0544, 0.2743),  # hour 11
    (-0.8925, -0.6795, -0.5392, -0.0199, 0.4140),  # hour 12
    (-0.6792, -0.5334, -0.3478, 0.0749, 0.5108),  # hour 13
    (-0.5567, -0.4159, -0.1363, 0.1927, 0.6626),  # hour 14
    (-0.4658, -0.2863, 0.0189, 0.3160, 0.8149),  # hour 15
    (-0.3824, -0.2033, 0.0884, 0.3759, 0.8242),  # hour 16
    (-0.2945, -0.0911, 0.2133, 0.4922, 0.9303),  # hour 17
    (-0.2209, -0.0317, 0.2494, 0.5029, 0.9243),  # hour 18
    (-0.1783, -0.0177, 0.2706, 0.6134, 0.9572),  # hour 19
    (-0.1905, -0.0225, 0.2980, 0.7312, 0.9726),  # hour 20
    (-0.1639, 0.0214, 0.3096, 0.8076, 0.9106),  # hour 21
    (-0.1708, -0.0783, 0.2189, 0.7700, 0.8885),  # hour 22
    (-0.2871, -0.0119, 0.1370, 0.6775, 0.8692),  # hour 23
    (-0.3617, -0.1356, 0.1536, 0.5142, 0.8226),  # hour 24
]


def round2(x: float) -> float | int:
    """x rounded to 2 decimals, half up, as JavaScript's Math.round(x * 100) / 100 rounds it.

    A whole number comes back as an int, so json.dumps writes 1240 where JavaScript writes 1240 (not 1240.0).
    """
    scaled = x * 100
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    value = whole / 100
    return int(value) if value.is_integer() else value


def hour_quantiles(p1: float, h: int) -> list[float | int]:
    """The five quantiles of hour h: p1 times exp() of the widened log-ratio quantiles."""
    table = BIG_Q if p1 >= BIG_THRESHOLD else BASE_Q
    row = table[h - 2]
    median = row[2]
    out: list[float | int] = []
    prev = 0.0
    for q in row:
        widened = median + (q - median) * WIDEN
        value = p1 * math.exp(widened)
        if value < 1.0:
            value = 1.0
        elif value > 1e9:
            value = 1e9
        rounded = round2(value)
        if rounded < prev:
            rounded = prev
        out.append(rounded)
        prev = float(rounded)
    return out


def hour1_print(case: dict) -> float:
    """Hour 1's print, floored at 1; falls back to the last history point, then 1."""
    first = next((k for k in case.get("known", []) if k.get("hour") == 1), None)
    if first is not None:
        try:
            return max(1.0, float(first["viewers"]))
        except (TypeError, ValueError, KeyError):
            pass
    history = case.get("history") or []
    if history:
        try:
            return max(1.0, float(history[-1]["viewers"]))
        except (TypeError, ValueError, KeyError):
            pass
    return 1.0


def forecast_case(case: dict, name: str) -> dict:
    # Always emit exactly hours 2..24 from the fitted tables, whatever
    # the case's forecast list holds: a missing or malformed row must
    # never turn the whole run into an invalid case.
    p1 = hour1_print(case)
    return {"hours": [{"hour": h, "q": hour_quantiles(p1, h)} for h in range(2, 25)]}


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # Every case file, in name order, so two runs write the same bytes.
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        forecast = forecast_case(case, path.name)
        (OUTPUT_DIR / f"{path.stem}.out").write_text(json.dumps(forecast, separators=(",", ":")) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
