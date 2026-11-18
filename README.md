# GTA VI Twitch CCU forecast

[![make.fun](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01)
[![rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/KENAHA01/gta6-twitch-ccu-forecast-01/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01)
[![reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/KENAHA01/gta6-twitch-ccu-forecast-01/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01)

Entry for the [make.fun bounty gta6-twitch-ccu-forecast-01](https://make.fun/bounty/gta6-twitch-ccu-forecast-01):
forecast how many people watch Grand Theft Auto VI live on Twitch in each
hour of its release day (2026-11-19 UTC), hours 2-24, as five quantiles
(5%, 25%, 50%, 75%, 95%) per hour, from hour 1's print alone.

## Model

`main.py` (Python 3.13, standard library only, no network, deterministic)
reads the case's own comparables at run time: past big game launches
with their hourly SullyGnome Twitch curves. It anchors on hour 1's
print `p1` and multiplies it by the shape of a launch day:

```
q_tau(h) = p1 * exp(median_h + (q_tau_h - median_h) * 1.25)
```

`(q05, q25, q50, q75, q95)_h` are quantiles of `ln(viewers_h / viewers_1)`
across the comparables, but not plain ones: each launch is weighted by
how close its hour-1 print is to the target's, in log space (Gaussian
kernel, sigma 1.0, weight floored at 0.05). A launch that opened at a
similar scale counts more than one that opened 10x smaller or bigger,
and the floor keeps the effective sample usable even if GTA VI opens
far above every comparable. Launches with an hour-1 print under 20,000
are left out: at 00:00 UTC their unlock was still hours away, so their
ratios explode 100x-2000x and would poison the quantiles.

Nothing is baked into the file: no fitted tables, no GTA VI numbers.
The same program on a different case forecasts that case from its own
comparables.

## Backtest

Leave-one-out over the 27 launches with hour-1 >= 20,000 (each launch
held out, fit from the rest, mean pinball loss on the log scale, the
contest's own scorer): **v2 0.2652 vs v1 unweighted 0.2730 vs house
baseline 0.3214**, winning 22 of 27 launches. The gain holds for
sigma 0.85 to 1.2, so it is not a knife-edge tuning. The house baseline
scores about 0.387 on the four practice cases; their true answers are
not in the kit, so no direct practice score is claimed.

## Run

```sh
mkdir -p out
MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

Reads every `*.in` in the input directory and writes `<id>.out` per
case: `{"hours": [{"hour": 2, "q": [...]}, ...]}` with exactly 23 rows
(hours 2-24), each quantile finite, > 0, <= 1e9, non-decreasing,
rounded half-up to 2 decimals. Four practice cases run in about
0.15 seconds, byte-identical on repeat runs.

## License

MIT (see LICENSE).
