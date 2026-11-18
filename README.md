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
anchors on hour 1's print `p1` and multiplies it by a fitted launch-day
curve:

```
q_tau(h) = p1 * exp(median_h + (q_tau_h - median_h) * 1.25)
```

`(q05, q25, q50, q75, q95)_h` are the empirical quantiles of
`ln(viewers_h / viewers_1)` over past big game launches' release days,
taken from the comparables shipped in the kit (SullyGnome hourly
Twitch category averages). Two fits are baked in as literal tables:

- **BASE_Q** - 27 launches with hour-1 print >= 20,000 viewers.
- **BIG_Q** - 20 launches with hour-1 print >= 50,000 viewers, used
  when `p1 >= 50,000`. Big launches behave differently: hour 1 is
  already near the early peak (median ratio dips to ~0.53 around
  hours 10-11, then climbs to ~1.36 around hours 20-21 as the US
  audience unlocks and prime time arrives).

Launches with a tiny hour-1 print were excluded: at 00:00 UTC their
unlock was still hours away, so their ratios explode 100x-2000x and
would poison the quantiles. The 1.25 tail widening corrects for the
small fit samples (20-27 launches); leave-one-out backtesting picked
1.2-1.4 as a flat optimum.

## Backtest

Leave-one-out over the 27 launches with hour-1 >= 20,000 (each launch
held out, fit from the rest, mean pinball loss on the log scale, the
contest's own scorer): **model 0.273 vs house baseline 0.321**.
The house baseline scores about 0.387 on the four practice cases;
their true answers are not in the kit, so no direct practice score
is claimed.

## Run

```sh
mkdir -p out
MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

Reads every `*.in` in the input directory and writes `<id>.out` per
case: `{"hours": [{"hour": 2, "q": [...]}, ...]}` with exactly 23 rows
(hours 2-24), each quantile finite, > 0, <= 1e9, non-decreasing,
rounded half-up to 2 decimals.

## License

MIT (see LICENSE).
