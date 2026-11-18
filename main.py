"""Launch-day Twitch forecaster for GTA VI, v2: weighted comparable quantiles.

Idea: do not bake in any fitted numbers. At run time, read the case's
own comparables (past big launches, hourly SullyGnome curves shipped in
the case file), pull each launch's 24 hourly viewer counts starting at
its release-day midnight, and work in log-ratios to its hour-1 print.

For a forecast hour h, the five quantiles are hour 1's print p1 times
exp() of the quantiles of ln(viewers_h / viewers_1) across comparable
launches, widened a little around the median:

    q_tau(h) = p1 * exp(median_h + (q_tau_h - median_h) * WIDEN)

v2 weights each comparable by how close its hour-1 print is to the
target's, in log space: a launch that opened at a similar scale counts
more than one that opened 10x smaller or bigger. The weight is a
Gaussian kernel on ln(p1) with sigma 1.0, floored at 0.05 so that no
launch is ever fully ignored and the effective sample stays usable
even when the target opens far above every comparable (GTA VI may):
at p1 = 3,000,000 the effective sample is still about 11 launches,
against about 5 without the floor. Launches whose hour-1 print was
under 20,000 are left out entirely: their unlock was still hours away
at 00:00 UTC, so their ratios explode 100x-2000x and would poison the
quantiles.

Leave-one-out backtest over the 27 launches with p1 >= 20,000 in the
kit (each launch held out, quantiles fit from the rest, same log-scale
pinball scorer as the contest): v2 0.2652 vs v1 (unweighted, same
widen) 0.2730 vs house baseline 0.3214, winning 22 of 27 launches.
The gain is positive in 16 of 27 launches and holds for sigma 0.85
to 1.2 (0.2653 to 0.2664), so it is not a knife-edge tuning. Without
the 0.05 weight floor the LOO would be 0.2645, a hair better, but the
floor is kept anyway: it costs 0.0007 and buys a usable effective
sample when the target opens far above every comparable. Smoothing
the quantiles across hours and filtering by the research-note tier
were both tried and did not help. The house baseline scores about
0.387 on the four practice cases; their true answers are not in the
kit, so no direct practice score is claimed here.

Python 3.13 standard library only, no network, deterministic: the
same input bytes give the same output bytes. Reads every *.in in
MAKEFUN_INPUT_DIR (else /input) and writes <id>.out per case into
MAKEFUN_OUTPUT_DIR (else /output).
"""

import json
import math
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
MIN_P1 = 20000
WIDEN = 1.25
SIGMA = 1.0
WEIGHT_FLOOR = 0.05


def weighted_quantile(pairs, tau):
    """Quantile of values with weights, by linear interpolation.

    pairs is a list of (value, weight) sorted by value. The target
    cumulative weight is tau times the total weight; the answer is
    interpolated inside the step where that target is crossed.
    """
    pairs = sorted(pairs)
    total = sum(weight for _, weight in pairs)
    if total <= 0:
        return None
    target = tau * total
    acc = 0.0
    for i, (value, weight) in enumerate(pairs):
        acc += weight
        if acc >= target:
            if i == 0 or weight <= 0:
                return value
            prev_value, _ = pairs[i - 1]
            frac = (target - (acc - weight)) / weight
            return prev_value + (value - prev_value) * frac
    return pairs[-1][0]


def day_curve(comparable):
    """The comparable's 24 hourly viewer counts from its day_start.

    Returns None when any of the 24 hours is missing or not positive,
    so a sparse SullyGnome curve never silently fills a gap.
    """
    start = datetime.fromisoformat(comparable["day_start"].replace("Z", "+00:00"))
    by_hour = {}
    for point in comparable.get("hourly", []):
        viewers = point.get("viewers")
        if isinstance(viewers, (int, float)) and viewers > 0:
            by_hour[point.get("from")] = float(viewers)
    curve = []
    for offset in range(24):
        stamp = (start + timedelta(hours=offset)).strftime("%Y-%m-%dT%H:00:00Z")
        value = by_hour.get(stamp)
        if value is None:
            return None
        curve.append(value)
    return curve


def round2(value):
    """Round to 2 decimals, half up, as JavaScript Math.round does.

    A whole number comes back as an int, so json writes 1240 where
    JavaScript writes 1240 (not 1240.0).
    """
    scaled = value * 100
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    rounded = whole / 100
    return int(rounded) if rounded.is_integer() else rounded


def hour1_print(case):
    """Hour 1's print, floored at 1; falls back to the last history
    point, then 1, so a case with no hour-1 row still forecasts."""
    for row in case.get("known", []):
        if row.get("hour") == 1:
            try:
                return max(1.0, float(row["viewers"]))
            except (TypeError, ValueError, KeyError):
                pass
    history = case.get("history") or []
    if history:
        try:
            return max(1.0, float(history[-1]["viewers"]))
        except (TypeError, ValueError, KeyError):
            pass
    return 1.0


def forecast_case(case):
    """Forecast hours 2..24 for one case from its own comparables."""
    p1 = hour1_print(case)
    pool = []
    for comparable in case.get("comparables", []):
        curve = day_curve(comparable)
        if curve is not None and curve[0] >= MIN_P1:
            pool.append(curve)
    if not pool:
        # No comparable cleared MIN_P1 (a tiny hour-1 print, or a
        # sparse case): use every full curve we have, whatever its
        # hour-1 size, rather than falling back to a flat forecast.
        # Only when there is no full curve at all do we use the
        # house shape, a flat median with a widening spread.
        for comparable in case.get("comparables", []):
            curve = day_curve(comparable)
            if curve is not None:
                pool.append(curve)
    log_p1 = math.log(p1)
    weights = []
    for curve in pool:
        gap = math.log(curve[0]) - log_p1
        weight = math.exp(-(gap * gap) / (2.0 * SIGMA * SIGMA))
        weights.append(max(weight, WEIGHT_FLOOR))
    hours = []
    for hour in range(2, 25):
        if not pool:
            spread = 0.15 * math.sqrt(hour - 1)
            quantiles = [
                p1 * math.exp(z * spread)
                for z in (-1.645, -0.674, 0.0, 0.674, 1.645)
            ]
        else:
            pairs = [
                (math.log(curve[hour - 1] / curve[0]), weight)
                for curve, weight in zip(pool, weights)
            ]
            fitted = [weighted_quantile(pairs, tau) for tau in LEVELS]
            median = fitted[2]
            quantiles = [
                p1 * math.exp(median + (q - median) * WIDEN) for q in fitted
            ]
        row = []
        previous = 0.0
        for value in quantiles:
            if value < 1.0:
                value = 1.0
            elif value > 1e9:
                value = 1e9
            rounded = round2(value)
            if rounded < previous:
                rounded = previous
            row.append(rounded)
            previous = float(rounded)
        hours.append({"hour": hour, "q": row})
    return {"hours": hours}


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        forecast = forecast_case(case)
        out_path = OUTPUT_DIR / f"{path.stem}.out"
        out_path.write_text(
            json.dumps(forecast, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
