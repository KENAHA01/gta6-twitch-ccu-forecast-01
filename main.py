"""Launch-day Twitch forecaster for GTA VI, rebuilt from the kit data.

Idea: do not bake in any fitted numbers. At run time, read the case's
own comparables (past big launches, hourly SullyGnome curves shipped in
the case file), pull each launch's 24 hourly viewer counts starting at
its release-day midnight, and work in log-ratios to its hour-1 print.

For a forecast hour h, the five quantiles are hour 1's print p1 times
exp() of the empirical quantiles of ln(viewers_h / viewers_1) across
comparable launches, widened a little around the median:

    q_tau(h) = p1 * exp(median_h + (q_tau_h - median_h) * WIDEN)

Two pools are used, because big launches behave differently from
smaller ones: their hour-1 print is already near the early peak, the
median ratio dips to about 0.53 around hours 10-11 and climbs back to
about 1.3 around hours 20-21 as the US audience unlocks. Launches
whose hour-1 print was under 20,000 are left out entirely: their
unlock was still hours away at 00:00 UTC, so their ratios explode
100x-2000x and would poison the quantiles. When p1 is at least
50,000, only launches with p1 at least 50,000 are used; otherwise
every launch with p1 at least 20,000 is used.

Leave-one-out backtest over the 27 launches with p1 >= 20,000 in the
kit (each launch held out, quantiles fit from the rest, same log-scale
pinball scorer as the contest): model 0.273 vs house baseline 0.321,
winning 22 of 27 launches. WIDEN = 1.25 sits in the middle of a flat
optimum (1.15 gives 0.274, 1.35 gives 0.273), so it is not a sharp
tuned peak. The house baseline scores about 0.387 on the four
practice cases; their true answers are not in the kit, so no direct
practice score is claimed here.

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
BIG_P1 = 50000
WIDEN = 1.25


def empirical_quantile(sorted_values, tau):
    """Linear-interpolation quantile of a sorted list."""
    if len(sorted_values) == 1:
        return sorted_values[0]
    pos = tau * (len(sorted_values) - 1)
    low = int(pos)
    high = min(low + 1, len(sorted_values) - 1)
    frac = pos - low
    return sorted_values[low] * (1.0 - frac) + sorted_values[high] * frac


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
    threshold = BIG_P1 if p1 >= BIG_P1 else MIN_P1
    chosen = [curve for curve in pool if curve[0] >= threshold]
    if len(chosen) < 5:
        chosen = pool
    if not chosen:
        # No comparable cleared MIN_P1 (a tiny hour-1 print, or a
        # sparse case): use every full curve we have, whatever its
        # hour-1 size, rather than falling back to a flat forecast.
        # Only when there is no full curve at all do we use the
        # house shape, a flat median with a widening spread.
        chosen = []
        for comparable in case.get("comparables", []):
            curve = day_curve(comparable)
            if curve is not None:
                chosen.append(curve)
        if not chosen:
            chosen = None
    hours = []
    for hour in range(2, 25):
        if chosen is None:
            spread = 0.15 * math.sqrt(hour - 1)
            quantiles = [
                p1 * math.exp(z * spread)
                for z in (-1.645, -0.674, 0.0, 0.674, 1.645)
            ]
        else:
            ratios = sorted(
                math.log(curve[hour - 1] / curve[0]) for curve in chosen
            )
            fitted = [empirical_quantile(ratios, tau) for tau in LEVELS]
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
