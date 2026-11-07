"""
A checklist and a second opinion for the weekly direction of the US 10-year Treasury yield.

What this file does, in plain words:
  1. It reads public data that download_data.py saved in the data/ folder (nothing is downloaded here).
  2. It uses available archived economic snapshots, dated by archive availability, using
     the St. Louis Fed's archive of original releases (ALFRED). Market histories remain current-vintage; this is not a fully point-in-time data set.
  3. Every Friday since 2001 it answers 13 simple yes/no questions (the "checklist").
  4. It tests 14 extra questions and keeps the best two, judging them only on the years before November 2016.
  5. It trains a simple model (logistic regression) on the same questions, using only the past each week.
  6. It takes a position only when the checklist and the model don't disagree (the "two-key" rule).
  7. It measures the results over every calendar week (weeks with no position count as zero).

Run:  python model.py      (it writes tables to results/ and pictures to charts/; about 15 minutes with the placebo tests)
"""
# Lets us write type hints like "list[str]" on older Python versions too.
from __future__ import annotations

# json writes our summary numbers to a text file that people and programs can both read.
import json
import os
# Path lets us build file paths that work on Windows, Mac and Linux alike.
from pathlib import Path

# numpy does fast math on whole columns of numbers at once.
import numpy as np
# pandas holds our data as tables with dates down the side, like a spreadsheet.
import pandas as pd
# statsmodels estimates HAC uncertainty, allowing dependence over the specified lags.
import statsmodels.api as sm
# LogisticRegression is the simple model that turns our answers into a probability that yields fall.
from sklearn.linear_model import LogisticRegression

# ---------------------------------------------------------------------------------------------------- settings
# ROOT is the folder this file lives in, so the code finds its data wherever you copy the folder.
ROOT = Path(__file__).resolve().parent
# DATA is where download_data.py saved the raw files.
DATA = Path(os.environ.get("TREASURY_DATA_DIR", ROOT / "data"))
# VINTAGES holds the original-release archives (one file per economic series).
VINTAGES = DATA / "vintages"
# OUT is where we save result tables.
OUT = ROOT / "results"
# Make the results folder if it isn't there yet (and don't complain if it is).
OUT.mkdir(exist_ok=True)
# CHARTS is where we save pictures.
CHARTS = ROOT / "charts"
# Make the charts folder if it isn't there yet.
CHARTS.mkdir(exist_ok=True)

# The first Friday of the study.
START = "2001-05-04"
# The last Friday of the study (the research sample is frozen here; weekly_signal.py handles new weeks).
END = "2026-10-30"
# The start of the later retrospective slice; mechanical feature selection scores earlier weeks.
HOLDOUT_START = "2016-11-04"
# The model makes its first forecast here, so it has almost five years of history to learn from.
CLF_START = "2006-01-06"
# How strongly we stop the model from over-reacting to noise (smaller = calmer).
CLF_C = 0.1
# Annual research reference. The explicitly selected live specification uses 13-week refits.
# Optional refit_weeks arguments reproduce that variant without rewriting earlier experiments.
CLF_REFIT = 52
# "Last month" means the last four Fridays.
FOUR_WEEKS = 4
# Number of lags for the Newey-West t-statistic (how many neighboring weeks may be related).
HAC_LAGS = 4
# How many times we reshuffle history in the placebo test that keeps the chosen questions fixed.
PLACEBO_DRAWS = 500
# How many times we reshuffle history in the placebo test that also repeats the whole feature search.
PLACEBO_FULL_DRAWS = 200
# Major currencies for our dollar index: (FRED code, True if quoted as dollars per foreign unit).
FX = [("DEXUSEU", True), ("DEXJPUS", False), ("DEXUSUK", True), ("DEXCAUS", False), ("DEXSZUS", False), ("DEXUSAL", True)]


# ------------------------------------------------------------------------------------------------ data helpers
def fred(series: str) -> pd.Series:
    """Read one series that download_data.py saved from FRED (the St. Louis Fed's free data site)."""
    # Read the saved file: the first column is the date, the second is the value.
    df = pd.read_csv(DATA / f"{series}.csv")
    # Give the two columns simple names so the rest of the code is easy to read.
    df.columns = ["date", series]
    # Turn the date text (like "2026-10-30") into real dates the computer can sort and compare.
    df["date"] = pd.to_datetime(df["date"])
    # Turn the values into numbers; FRED writes "." for missing days, which becomes "not a number" here.
    values = pd.to_numeric(df[series], errors="coerce")
    # Return the values with dates as the index, dropping the missing days.
    return pd.Series(values.values, index=df["date"], name=series).dropna()


def vintages(series: str) -> pd.DataFrame:
    """Read the archive of original releases for one series: each row says 'on vintage date V, the published
    value for period O was X'. Vintage dates record archive availability; exact source timestamps can differ."""
    # Read the archive file saved by download_data.py.
    v = pd.read_csv(VINTAGES / f"{series}.csv", parse_dates=["vintage", "obs"])
    # Keep it in date order so "latest" means latest.
    return v.sort_values(["vintage", "obs"])


def realtime(series: str, rule) -> pd.Series:
    """Turn an archive into one number per release date, computed only from what that release showed.
    `rule` takes one release (its periods and values) and returns the number we want from it."""
    # Reject malformed snapshots rather than mistaking old historical fragments for a current release.
    rows = []
    for date, g in valid_releases(series):
        rows.append((date, rule(g.set_index("obs")["value"])))
    out = pd.Series(dict(rows), dtype=float).sort_index()
    # Hand back a series dated by release date.
    return out.dropna()


def valid_releases(series: str):
    """Archive snapshots with finite values, consecutive months and a recent latest observation.
    The supplied German 2013-08-01 snapshot ends in 1969; it is rejected by these checks.
    Vintage dates are archive availability dates, not an intraday release-time guarantee.
    """
    previous_month = None
    for date, g in vintages(series).groupby("vintage", sort=True):
        g = g.sort_values("obs")
        obs = pd.DatetimeIndex(g["obs"])
        if (g.empty or not np.isfinite(g["value"]).all() or obs.has_duplicates
                or obs[-1] > date or (date - obs[-1]).days > 120
                or (len(obs) > 1 and not np.all(np.diff(obs.to_period("M").asi8) == 1))
                or (previous_month is not None and obs[-1] < previous_month)):
            continue
        previous_month = obs[-1]
        yield date, g


def unemployment_first_prints() -> pd.Series:
    """One first-observed value per distinct month; revision-only vintages are not extra reports."""
    seen, values = set(), {}
    for date, g in valid_releases("UNRATE"):
        latest = g.iloc[-1]
        if latest["obs"] not in seen:
            seen.add(latest["obs"])
            values[date] = float(latest["value"])
    return pd.Series(values, dtype=float).sort_index()


def asof(series: pd.Series, dates: pd.DatetimeIndex) -> pd.Series:
    """For each Friday, take the latest value that was already known on that day."""
    # Sort by date, add our Fridays to its dates, carry each value forward, then keep only the Fridays.
    return series.sort_index().reindex(series.index.union(dates)).ffill().reindex(dates)


def zscore(s: pd.Series) -> pd.Series:
    """How unusual is this week's number compared with everything before it? 0 = normal, +2 = very high.
    It uses only the past and the present, never the future."""
    # Subtract the average so far and divide by the typical spread so far (needs at least a year of history).
    return (s - s.expanding(52).mean()) / s.expanding(52).std()


def went_up(s: pd.Series, weeks: int = FOUR_WEEKS) -> pd.Series:
    """+1 if the series is higher than `weeks` Fridays ago, -1 if lower, 0 if unchanged or unknown."""
    # Compare today with `weeks` Fridays ago and keep only the sign (missing stays missing, filled later as 0).
    return np.sign(s - s.shift(weeks))


def curve_change(d: pd.DataFrame) -> pd.Series:
    """Four-week 2s10s change in percentage points, removing subtraction round-off."""
    # Equal quoted spreads must give zero, not a vote from a 1e-16 arithmetic residual.
    spread = d["y10"] - d["y2"]
    return spread.diff(FOUR_WEEKS).round(10)


# ------------------------------------------------------------------------------------------------ load the data
def load(end: str = END) -> pd.DataFrame:
    """Build a Friday panel with declared lags and archived macro snapshots; market histories remain current-vintage."""
    # Every Friday from the start to the end of the sample.
    fridays = pd.date_range(START, end, freq="W-FRI")
    # Daily Treasury reference yield; historical availability limitations are disclosed in the paper.
    y10 = fred("DGS10")
    # The 2-year Treasury yield every day; we use it for the shape of the yield curve.
    y2 = fred("DGS2")
    # Start an empty table with one row per Friday.
    d = pd.DataFrame(index=fridays)

    # --- Market observations: current-vintage histories; timing assumptions are disclosed in the paper. ---
    # 10-year yield at Friday's close.
    d["y10"] = asof(y10, fridays)
    # 2-year yield at Friday's close.
    d["y2"] = asof(y2, fridays)
    # US stocks (the Nasdaq Composite) at Friday's close.
    d["us_eq"] = asof(fred("NASDAQCOM"), fridays)
    # Emerging market stocks at Friday's close.
    d["em_eq"] = asof(fred("NASDAQNQEM"), fridays)
    # WTI spot observations delayed seven days; this is not a same-Friday futures price.
    d["oil"] = asof(fred("DCOILWTICO").shift(7, freq="D"), fridays)
    # VIX: option-implied 30-day equity volatility; not a direct Treasury demand measure.
    d["vix"] = asof(fred("VIXCLS"), fridays)
    # Three-month option-implied equity volatility; this history starts in 2007.
    d["vix3m"] = asof(fred("VXVCLS"), fridays)
    # 10-year breakeven: inflation compensation, also affected by risk and liquidity premia.
    d["breakeven"] = asof(fred("T10YIE"), fridays)
    # Natural gas spot observations delayed seven days, matching the research assumption.
    d["natgas"] = asof(fred("DHHNGSP").shift(7, freq="D"), fridays)
    # Oil volatility index at Friday's close.
    d["ovx"] = asof(fred("OVXCLS"), fridays)

    # Dollar: an equal-weight index of six major exchange rates. Their observation histories may be corrected,
    # and the basket definition is fixed here (unlike the Fed's broad index, which was redesigned in 2019 and backfilled).
    logs = []
    # Each currency in turn.
    for code, usd_per_foreign in FX:
        # Read the exchange rate.
        r = fred(code)
        # Flip it if needed so that a higher number always means a stronger dollar.
        r = 1 / r if usd_per_foreign else r
        # Keep its logarithm as known each Friday, so each currency counts equally in the average.
        # H.10 reports the preceding week on Monday; a full week of delay avoids same-week use.
        logs.append(np.log(asof(r.shift(7, freq="D"), fridays)))
    # Average the six; a rise means the dollar got stronger.
    d["usd"] = pd.concat(logs, axis=1).mean(axis=1, skipna=False)

    # --- Economic statistics: rebuilt from available snapshots, dated by archive availability. ---
    # Unemployment rate: the latest month shown in each jobs report, dated by the day the report came out.
    first_print = unemployment_first_prints()
    # Store it as known each Friday.
    d["unrate"] = asof(first_print, fridays)
    # Its average over the previous 60 reports (five years), using only numbers as they were first published.
    d["unrate_5y"] = asof(first_print.shift(1).rolling(60).mean(), fridays)
    # Core PCE inflation over the past 12 months, computed inside each release from that release's own numbers.
    d["core_pce_yoy"] = asof(realtime("PCEPILFE", lambda s: (s.iloc[-1] / s.iloc[-13] - 1) * 100 if len(s) >= 13 else np.nan), fridays)
    # German, UK and Japanese 10-year yields (OECD monthly averages of market yields): the latest month's change.
    for col, code in [("de10", "IRLTLT01DEM156N"), ("uk10", "IRLTLT01GBM156N"), ("jp10", "IRLTLT01JPM156N")]:
        # Where valid archived snapshots exist, take the change between their two newest months.
        rt = realtime(code, lambda s: s.iloc[-1] - s.iloc[-2] if len(s) >= 2 else np.nan)
        # No revised-data fallback before the archive: the rule is unavailable and therefore neutral.
        d[col + "_chg"] = asof(rt, fridays)
    # Nominal yield less trailing core inflation: a backward-looking gap, not a TIPS yield or fair value.
    d["real_y10"] = d["y10"] - d["core_pce_yoy"]

    # --- Weekly releases with a small, fixed delay. ---
    # Retail gasoline price survey: the Monday survey is published that Monday; shift one day to be safe.
    d["gasoline"] = asof(fred("GASREGW").shift(1, freq="D"), fridays)
    # The Fed's balance sheet, published Thursday afternoon for the week ending Wednesday; shift one day.
    d["fed_bs"] = asof(fred("WALCL").shift(1, freq="D"), fridays)

    # --- Short-term bond-market measures built from the daily 10-year yield (price-based candidate measures). ---
    # Group the daily yields into weeks that end on Friday.
    week = y10.resample("W-FRI")
    # The highest and lowest daily yield of each week.
    hi, lo = week.max().reindex(fridays), week.min().reindex(fridays)
    # Where Friday's yield closed inside the week's range: 0 = at the week's low, 1 = at the week's high.
    d["week_close"] = (d["y10"] - lo) / (hi - lo).replace(0, np.nan)
    # The average size of a daily move over the last 25 days, our yardstick for "a big move".
    avg_move = y10.diff().abs().rolling(25).mean()
    # The lowest yield of the last 10 days.
    low10 = y10.rolling(10).min()
    # How many "average daily moves" the yield has run up above its 10-day low (a bond "washout" when large).
    d["washout"] = (d["y10"] - asof(low10, fridays)) / asof(avg_move, fridays)
    # +1 when the yield is below its 300-day average (bonds in an uptrend), -1 when above.
    d["regime"] = np.where(d["y10"] < asof(y10.rolling(300).mean(), fridays), 1.0, -1.0)

    # --- Calendar events in the coming week. ---
    # Every scheduled Fed decision date (from the Fed's own calendar pages; ships with the code).
    fomc = pd.to_datetime(pd.read_csv(DATA / "fomc_dates.csv")["decision_date"])
    # 1 if a Fed decision falls in the 7 days after this Friday, else 0.
    d["fomc_next"] = [float(((fomc > t) & (fomc <= t + pd.Timedelta(days=7))).any()) for t in fridays]
    # A deterministic calendar proxy, knowable in advance. Realized future release dates would leak.
    d["jobs_next"] = ((fridays + pd.Timedelta(days=7)).day <= 7).astype(float)
    # How much the VIX moved this week; a rise is our "anxiety tell".
    d["vix_1w"] = d["vix"].diff(1)

    # The thing we forecast: the change in the 10-year yield from this Friday to next Friday, in basis points.
    d["dy_next_bp"] = (d["y10"].shift(-1) - d["y10"]) * 100
    # Hand back the finished weekly table.
    return d


def monthly_known(series: pd.Series, lag_days: int) -> pd.Series:
    """Move a monthly number to a fixed number of days after its month ends (used only where no release archive exists)."""
    # Copy so we don't change the original.
    s = series.copy()
    # Jump each date to the end of its month, then add the delay.
    s.index = s.index + pd.offsets.MonthEnd(0) + pd.Timedelta(days=lag_days)
    # Hand back the re-dated series.
    return s


# ------------------------------------------------------------------------------------------ the 13 questions
# Each question: (short name, group, the exact rule in words).
QUESTIONS_13 = [
    ("us_eq", "Cross-asset moves", "Nasdaq Composite 4-week return > 0"),
    ("em_eq", "Cross-asset moves", "Nasdaq Emerging Markets 4-week return > 0"),
    ("oil", "Cross-asset moves", "WTI oil 4-week return > 0 (one-week-delayed observations)"),
    ("usd", "Cross-asset moves", "Six-currency dollar index 4-week change > 0"),
    ("vix", "Cross-asset moves", "VIX 4-week change > 0"),
    ("slack", "Macro state", "Unemployment earliest archived monthly value > mean of 60 earlier monthly values"),
    ("pce", "Macro state", "Core PCE inflation, 12-month (within vintage) < 2%"),
    ("real", "Rates-market state", "10-year yield minus core PCE inflation < 0"),
    ("curve", "Rates-market state", "2s10s spread 4-week change > 0"),
    ("de10", "Foreign bond markets", "German 10-year yield, latest monthly change (as published) > 0"),
    ("jp10", "Foreign bond markets", "Japanese 10-year yield, latest monthly change (as published) > 0"),
    ("uk10", "Foreign bond markets", "UK 10-year yield, latest monthly change (as published) > 0"),
    ("dec", "Calendar", "The signal date is in December"),
]


def answers_13(d: pd.DataFrame) -> pd.DataFrame:
    """Answer each of the 13 questions every Friday: +1 = buy Treasuries, -1 = sell, 0 = no view."""
    # Economic explanations below are hypotheses behind the fixed directions, not causal findings.
    # Start an empty table with one row per Friday.
    a = pd.DataFrame(index=d.index)
    # Hypothesis: stronger equities reflect easier conditions/growth and point to higher yields.
    a["us_eq"] = -went_up(d["us_eq"])
    # Apply the same continuation hypothesis to EM equities; no capital flow is observed here.
    a["em_eq"] = -went_up(d["em_eq"])
    # Baseline hypothesis: rising oil signals persistent inflation pressure; growth/supply shocks can differ.
    a["oil"] = -went_up(d["oil"])
    # Hypothesis: a stronger dollar tightens conditions and moderates inflation; a Fed repricing can reverse this sign.
    a["usd"] = went_up(d["usd"])
    # Hypothesis: rising equity volatility supports Treasury demand; inflation/liquidity shocks can break the link.
    a["vix"] = went_up(d["vix"])
    # Relative labor-market weakness may favor lower yields. The five-year mean is not a natural-rate estimate.
    a["slack"] = np.where(d["unrate"].isna() | d["unrate_5y"].isna(), 0, np.where(d["unrate"] > d["unrate_5y"], 1, -1))
    # Fixed core-PCE cutoff as policy backdrop. The formal Fed goal is headline PCE; this is not a release-surprise signal.
    a["pce"] = np.where(d["core_pce_yoy"].isna(), 0, np.where(d["core_pce_yoy"] < 2, 1, -1))
    # Retained gap rule: favor yields above trailing inflation. It does not establish bonds are cheap or expensive.
    a["real"] = np.where(d["real_y10"].isna(), 0, np.where(d["real_y10"] < 0, -1, 1))
    # Relative-yield/carry hypothesis. Steepening can occur with rising or falling yields; roll-down is not scored here.
    a["curve"] = np.sign(curve_change(d))
    # Continuation hypothesis for global rates; lagged monthly averages are not evidence of foreign Treasury flows.
    for c in ["de10", "jp10", "uk10"]:
        # The sign of the latest published monthly change (unchanged = no view).
        a[c] = -np.sign(d[c + "_chg"])
    # Seasonal sell hypothesis for December; the calendar alone does not measure liquidity or identify flow direction.
    a["dec"] = np.where(d.index.month == 12, -1, 0)
    # Fill any gaps with "no view" and store as whole numbers.
    return a.fillna(0).astype(int)


def features_13(d: pd.DataFrame) -> pd.DataFrame:
    """The same 13 questions as numbers (how much, not just which way), for the model to learn from."""
    # Change in a level over four weeks (used for yields and spreads).
    chg = lambda s: s - s.shift(FOUR_WEEKS)
    # Percent-style change over four weeks (used for prices).
    lchg = lambda s: np.log(s).diff(FOUR_WEEKS)
    # Start an empty table with one row per Friday.
    f = pd.DataFrame(index=d.index)
    # How much US stocks moved last month, compared with normal.
    f["us_eq"] = zscore(lchg(d["us_eq"]))
    # How much EM stocks moved last month, compared with normal.
    f["em_eq"] = zscore(lchg(d["em_eq"]))
    # How much oil moved last month, compared with normal.
    f["oil"] = zscore(lchg(d["oil"]))
    # How much the dollar moved last month (already a log index, so a plain change), compared with normal.
    f["usd"] = zscore(chg(d["usd"]))
    # How much the VIX moved last month, compared with normal.
    f["vix"] = zscore(chg(d["vix"]))
    # How far unemployment is above its five-year average, compared with normal.
    f["slack"] = zscore(d["unrate"] - d["unrate_5y"])
    # How far inflation is from 2%, compared with normal.
    f["pce"] = zscore(d["core_pce_yoy"] - 2)
    # Nominal yield less trailing inflation, compared with its past; retain the internal name for compatibility.
    f["real"] = zscore(d["real_y10"])
    # How much the curve steepened last month, compared with normal.
    f["curve"] = zscore(curve_change(d))
    # How big each foreign market's latest published monthly yield change was, compared with normal.
    for c in ["de10", "jp10", "uk10"]:
        # Store that country's change.
        f[c] = zscore(d[c + "_chg"])
    # 1 in December, 0 otherwise (a yes/no input is not standardized).
    f["dec"] = (d.index.month == 12).astype(float)
    # Cap extreme values at 4 so one crazy week can't dominate, and fill gaps with 0 (= normal).
    return f.clip(-4, 4).fillna(0)


# ------------------------------------------------------------------------------------ candidate questions
def candidates(d: pd.DataFrame) -> dict:
    """The 14 extra questions we tested. Each has a family (so we never add two that say the same thing),
    the rule in words, a yes/no answer, and a number version for the model.
    Answers start as "+1 = buy"; the feature hunt flips negative early-sample yield scores."""
    # 1 when a big event (a Fed decision or a jobs report) is due next week, else 0.
    event = ((d["fomc_next"] + d["jobs_next"]) > 0).astype(float)
    # 1 when option-implied equity volatility rose this week, else 0; this does not identify the shock.
    fear_up = (d["vix_1w"] > 0).astype(float)
    # How big this week's VIX move was compared with normal, capped at 4 (gaps become 0 = normal).
    fear_size = zscore(d["vix_1w"]).clip(-4, 4).fillna(0)
    # 1 when 30-day implied volatility exceeds three-month implied volatility; a relative volatility state.
    inverted = (d["vix"] > d["vix3m"]).astype(float).where(d["vix3m"].notna(), 0)
    # 1 when the washout exceeds 2.5 average daily moves, else 0.
    washed = pd.Series(np.where(d["washout"] > 2.5, 1.0, 0.0), index=d.index)
    # 1 when Friday closed in the top 30% of the week's yield range, else 0.
    top_close = pd.Series(np.where(d["week_close"] > 0.7, 1.0, 0.0), index=d.index)
    # Each entry: name -> (family, rule in words, yes/no answer, number version).
    return {
        "oil_yoy": ("Energy", "WTI oil 52-week return > 0", went_up(d["oil"], 52), zscore(np.log(d["oil"]).diff(52))),
        "gasoline": ("Energy", "Retail gasoline 4-week change > 0", went_up(d["gasoline"]), zscore(np.log(d["gasoline"]).diff(4))),
        "natgas": ("Energy", "Natural gas 4-week return > 0 (one-week-delayed observations)", went_up(d["natgas"]), zscore(np.log(d["natgas"]).diff(4))),
        "ovx": ("Energy", "Oil volatility (OVX) 4-week change > 0", went_up(d["ovx"]), zscore(d["ovx"].diff(4))),
        "breakeven": ("Inflation expectations", "10-year breakeven 4-week change > 0", went_up(d["breakeven"]), zscore(d["breakeven"].diff(4))),
        "fed_bs": ("Supply", "Fed balance sheet 4-week change > 0", went_up(d["fed_bs"]), zscore(np.log(d["fed_bs"]).diff(4))),
        "trend": ("Yield dynamics", "10-year yield below its 300-day average", d["regime"], d["regime"]),
        "washout": ("Yield dynamics", "10-year yield more than 2.5 average daily moves above its 10-day low", washed, zscore(d["washout"])),
        "week_close": ("Yield dynamics", "Friday's 10-year yield in the top 30% of the week's range", top_close, zscore(d["week_close"])),
        "fomc_next": ("Calendar events", "A scheduled Fed decision falls in the next 7 days", d["fomc_next"], d["fomc_next"]),
        "jobs_next": ("Calendar events", "Next Friday falls in the first seven days of a month (jobs calendar proxy)", d["jobs_next"], d["jobs_next"]),
        "fomc_anxiety": ("Calendar events", "A Fed decision falls in the next 7 days and the VIX rose this week", d["fomc_next"] * fear_up, d["fomc_next"] * fear_size),
        "event_anxiety": ("Calendar events", "A Fed decision or jobs calendar proxy falls next week and the VIX rose this week", event * fear_up, event * fear_size),
        "vix_inverted": ("Calendar events", "VIX above 3-month VIX", inverted, inverted),
    }


# ------------------------------------------------------------------------------------------ the classifier
def walk_forward(f: pd.DataFrame, dy: pd.Series, refit_weeks: int | None = None) -> tuple[pd.Series, pd.DataFrame]:
    """Each week, the probability that the 10-year yield falls next week. The annual reference is the default;
    pass refit_weeks=13 for the subsequently selected quarterly model. Each version
    only ever sees weeks whose result was already known: at Friday i, the result of the signal from Friday i-1 is known."""
    interval = CLF_REFIT if refit_weeks is None else refit_weeks
    if not isinstance(interval, int) or isinstance(interval, bool) or interval < 1:
        raise ValueError('Refit interval must be a positive integer')
    # The thing to learn: 1 if the yield fell the following week, 0 if it rose or stayed the same.
    y = (dy < 0).astype(int)
    # Empty column to fill with one probability per week.
    prob = pd.Series(np.nan, index=f.index)
    # A list to remember the model's weights at every refit, so we can show them.
    coefs = []
    # All the Fridays.
    idx = f.index
    # Position of the first Friday on which we make a forecast.
    first = idx.get_loc(idx[idx >= CLF_START][0])
    # Step through history one refit period at a time.
    for i in range(first, len(idx), interval):
        # Training weeks: every Friday before today (their results were all known by today's close).
        train = idx[:i]
        # Drop any weeks whose result is missing.
        train = train[dy.loc[train].notna()]
        # Fit the logistic regression on those past weeks only.
        model = LogisticRegression(C=CLF_C, max_iter=2000).fit(f.loc[train].values, y.loc[train].values)
        # The weeks this fitted model will forecast, until the next refit.
        test = idx[i: i + interval]
        # Store the forecast probability that yields fall, for each of those weeks.
        prob.loc[test] = model.predict_proba(f.loc[test].values)[:, 1]
        # Remember the weights the model learned this time.
        coefs.append({"refit": str(idx[i].date()), **dict(zip(f.columns, np.round(model.coef_[0], 3)))})
    # Hand back the probabilities and the weight history.
    return prob, pd.DataFrame(coefs)


def two_key(a: pd.DataFrame, f: pd.DataFrame, dy: pd.Series, refit_weeks: int | None = None) -> dict:
    """Run both keys and combine them: trade only when the checklist and the model don't point opposite ways."""
    # Key one: add up all the answers. Positive = buy, negative = sell, zero = no view.
    score = a.sum(axis=1).astype(float)
    # Key two: the model's probability that yields fall next week.
    prob, coefs = walk_forward(f, dy, refit_weeks=refit_weeks)
    # Turn the probability into a view: above 50% = buy (positive), below 50% = sell (negative).
    clf = (prob - 0.5).fillna(0)
    # Add the two views' directions; the sign of the total is our position (+1 buy, -1 sell, 0 if they cancel).
    # Note: when the checklist score is exactly zero, the model alone decides.
    position = np.sign(np.sign(score) + np.sign(clf))
    # Hand back everything so other parts of the code can report on each piece.
    return {"score": score, "prob": prob, "clf": clf, "two_key": position, "coefs": coefs}


# ------------------------------------------------------------------------------------------------ statistics
def hac_t(x: pd.Series, lags: int = HAC_LAGS) -> float:
    """t-statistic of the average of x, corrected for neighboring weeks being related (Newey-West)."""
    # Regress x on a constant; the constant is the average, and its t-statistic is what we want.
    m = sm.OLS(x.values.astype(float), np.ones(len(x))).fit(cov_type="HAC", cov_kwds={"maxlags": lags})
    # Hand back the t-statistic as a plain number.
    return float(m.tvalues[0])


def wilson(k: int, n: int) -> tuple[float, float]:
    """A 95% range for a hit rate of k wins out of n tries (assumes the tries are independent)."""
    # With no tries there is no range.
    if n == 0:
        # Say "unknown".
        return (np.nan, np.nan)
    # The observed share of wins.
    p = k / n
    # The 95% multiplier.
    z = 1.96
    # The center of the Wilson range.
    center = (p + z * z / (2 * n)) / (1 + z * z / n)
    # Its half-width.
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    # Hand back the low and high ends.
    return (round(center - half, 4), round(center + half, 4))


def evaluate(signal: pd.Series, dy: pd.Series) -> dict:
    """How a signal did. Signal > 0 = buy Treasuries, so we gain when yields fall. Units: basis points (bp) of yield.
    Every eligible calendar week counts; weeks with no position count as zero."""
    # Our position each week: +1, -1 or 0.
    pos = np.sign(signal)
    # Eligible weeks: we know what happened next.
    ok = dy.notna()
    # Signed yield-change score each week: if we bought (+1) and yields fell (a negative change), it's positive.
    pnl = (-pos * dy)[ok].fillna(0)
    # Weeks where we actually had a position.
    active = (pos[ok] != 0)
    # Wins among active weeks (an unchanged yield counts as not a win).
    wins = int((pnl[active] > 0).sum())
    # Number of active weeks.
    n = int(active.sum())
    # Collect the numbers we report.
    return {
        # Eligible calendar weeks in the period.
        "calendar_weeks": int(ok.sum()),
        # Weeks with a position.
        "active_weeks": n,
        # Share of weeks with a position.
        "share_active": round(n / max(int(ok.sum()), 1), 3),
        # Share of active weeks with a positive signed yield-change score.
        "hit_ratio": round(wins / n, 4) if n else np.nan,
        # A 95% range for that hit ratio (treating weeks as independent, so read it as a rough guide).
        "hit_ratio_95": wilson(wins, n),
        # Average score in a week with a position (descriptive).
        "avg_bp_active_week": round(float(pnl[active].mean()), 3) if n else np.nan,
        # Average score per calendar week, times 52.
        "bp_per_year": round(float(pnl.mean() * 52), 1),
        # How sure we can be that the calendar-week average isn't just luck (Newey-West, 4 lags).
        "t_stat": round(hac_t(pnl), 2) if n else np.nan,
        # The same with 8 lags, as a check.
        "t_stat_8_lags": round(hac_t(pnl, 8), 2) if n else np.nan,
        # Bumpiness of the weekly scores, scaled to a year.
        "vol_bp_per_year": round(float(pnl.std() * np.sqrt(52)), 1),
        # Reward per unit of bumpiness over calendar weeks (a Sharpe-like ratio).
        "sharpe_like": round(float(pnl.mean() / pnl.std() * np.sqrt(52)), 2) if pnl.std() > 0 else np.nan,
    }


def weekly_score(signal: pd.Series, dy: pd.Series) -> pd.Series:
    """The signed yield-change score for every week (zero when flat), used for running totals and comparisons."""
    # Position times the negative of next week's yield change; missing outcomes stay missing.
    return (-np.sign(signal) * dy).where(dy.notna())


def periods(d: pd.DataFrame) -> dict:
    """True/false masks for the time periods we report."""
    # True from the test period's first Friday onward.
    hold = d.index >= HOLDOUT_START
    # True once the model starts forecasting.
    live = d.index >= CLF_START
    # The Fridays whose outcome is known.
    known = d.index[d["dy_next_bp"].notna()]
    # Design period (2006 to Oct 2016), test period, everything before Nov 2016, and the last 52 signal weeks.
    return {"design": live & ~hold, "test": hold, "before": ~hold, "last_year": d.index.isin(known[-52:])}


# ------------------------------------------------------------------------------------------ the feature hunt
def pack(e1: dict, e2: dict) -> dict:
    """Squeeze two result sets (before and after November 2016) into one table row."""
    # The before and after hit ratio, score per year and t-statistic.
    return {"in_sample_hit": e1["hit_ratio"], "in_sample_bp_yr": e1["bp_per_year"], "in_sample_t": e1["t_stat"],
            "out_sample_hit": e2["hit_ratio"], "out_sample_bp_yr": e2["bp_per_year"], "out_sample_t": e2["t_stat"]}


def extend(a13: pd.DataFrame, f13: pd.DataFrame, oriented: dict, keys: list) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The 13 questions plus the chosen extra ones, as answers (for the checklist) and numbers (for the model)."""
    # Copy so we don't change the originals.
    A, F = a13.copy().astype(float), f13.copy()
    # Add each chosen candidate.
    for k in keys:
        # Its yes/no answer goes into the checklist.
        A[k] = oriented[k][2]
        # Its number version goes into the model.
        F[k] = oriented[k][3]
    # Hand back both tables.
    return A, F


def orient(cands: dict, dy: pd.Series, before: np.ndarray) -> dict:
    """Set each candidate's direction from 2001 to Oct 2016 only: flip a negative early yield score."""
    # The candidates with their chosen direction.
    oriented = {}
    # Each candidate in turn.
    for key, (family, rule, ans, feat) in cands.items():
        # Fill gaps with "no view".
        ans = ans.fillna(0)
        # How it did before November 2016 with "+1 = buy".
        e = evaluate(ans, dy.where(before))
        # Keep the direction with a nonnegative early signed yield-change score.
        sign = 1 if e["bp_per_year"] >= 0 else -1
        # Store it with its direction (and its number version capped and gap-filled).
        oriented[key] = (family, rule, sign * ans, sign * feat.clip(-4, 4).fillna(0), sign)
    # Hand back the oriented candidates.
    return oriented


def select(a13, f13, oriented, dy, design, record=None) -> list:
    """Forward selection: add the candidate that most improves the two-key t-statistic in 2006 to Oct 2016,
    one family at most, twice. Nothing after October 2016 is used to choose."""
    # Start with nothing added.
    chosen = []
    # We add exactly two questions, one at a time.
    for step in (1, 2):
        # Families already used, so we don't add a second question that says the same thing.
        used = {oriented[k][0] for k in chosen}
        # Score for every candidate we could add at this step.
        trial = {}
        # Try each candidate that isn't already in and isn't from a family we already have.
        for key, (family, rule, ans, feat, sign) in oriented.items():
            # Skip ones already chosen or from a family we already used.
            if key in chosen or family in used:
                # Move on to the next candidate.
                continue
            # Build the checklist and model inputs with this candidate added.
            A, F = extend(a13, f13, oriented, chosen + [key])
            # Run the two-key rule.
            # Only design forecasts are needed to rank a candidate; later fits cannot affect them.
            cutoff = dy.index[np.asarray(design)][-1]
            tk = two_key(A.loc[:cutoff], F.loc[:cutoff], dy.loc[:cutoff])["two_key"]
            # Measure it in the design period only.
            design_dy = dy.loc[tk.index].where(np.asarray(design)[:len(tk)])
            e = evaluate(tk, design_dy)
            # The design-period t-statistic is this candidate's score.
            trial[key] = hac_t(weekly_score(tk, design_dy).dropna())
            # If asked, keep a row for the step table.
            if record is not None:
                # Save the row.
                record.append({"step": step, "added": key, "family": family, "design_hit": e["hit_ratio"], "design_t": e["t_stat"]})
        # Keep the candidate with the highest design-period t-statistic.
        chosen.append(max(trial, key=trial.get))
    # Hand back the two chosen names.
    return chosen


def nan_to_none(x):
    """Replace "not a number" with null so the summary is valid JSON for browsers."""
    # Dictionaries: clean each value.
    if isinstance(x, dict):
        # Rebuild the dictionary with cleaned values.
        return {k: nan_to_none(v) for k, v in x.items()}
    # Lists and tuples: clean each item.
    if isinstance(x, (list, tuple)):
        # Rebuild as a list.
        return [nan_to_none(v) for v in x]
    # A plain number that is "not a number" becomes null.
    if isinstance(x, (float, np.floating)) and not np.isfinite(x):
        # Null in JSON.
        return None
    # Anything else stays as it is.
    return x


_PLACEBO_CONTEXT = None


def _placebo_init(context):
    global _PLACEBO_CONTEXT
    _PLACEBO_CONTEXT = context
    # Small fits are faster and reproducible without nested BLAS thread pools.
    from threadpoolctl import threadpool_limits
    threadpool_limits(1)


def _placebo_one(task):
    kind, shift = task
    d, a, f, dy, masks, cands = _PLACEBO_CONTEXT
    idx = dy.dropna().index
    shifted = pd.Series(np.roll(dy.loc[idx].values, shift), index=idx).reindex(d.index)
    if kind == "search":
        oriented = orient(cands, shifted, masks["before"])
        chosen = select(a, f, oriented, shifted, masks["design"])
        a, f = extend(a, f, oriented, chosen)
    pos = two_key(a, f, shifted)["two_key"]
    return hac_t(weekly_score(pos, shifted.where(masks["test"])).dropna())


def placebo_statistics(d, a, f, dy, masks, real_position, search_position):
    """Circular shifts; all comparisons use full precision. Neither null recreates human design choices."""
    from concurrent.futures import ProcessPoolExecutor
    rng = np.random.default_rng(7)
    n = len(dy.dropna())
    tasks = [("conditional", int(k)) for k in rng.integers(52, n - 52, PLACEBO_DRAWS)]
    tasks += [("search", int(k)) for k in rng.integers(52, n - 52, PLACEBO_FULL_DRAWS)]
    context = (d, a.astype(float), f, dy, masks, candidates(d))
    values = []
    with ProcessPoolExecutor(max_workers=4, initializer=_placebo_init, initargs=(context,)) as pool:
        for i, value in enumerate(pool.map(_placebo_one, tasks, chunksize=1), 1):
            values.append(value)
            if i % 25 == 0:
                print(f"Placebo draws completed: {i}/{len(tasks)}", flush=True)
    pl = np.asarray(values[:PLACEBO_DRAWS])
    ps = np.asarray(values[PLACEBO_DRAWS:])
    def summarize(draws, pos):
        observed = hac_t(weekly_score(pos, dy.where(masks["test"])).dropna())
        count = int((draws >= observed).sum())
        return {"draws": len(draws), "real_t": round(observed, 4), "at_or_above": count,
                "p_value": round((count + 1) / (len(draws) + 1), 4),
                "t_95th_percentile": round(float(np.percentile(draws, 95)), 2)}
    pd.DataFrame({"conditional_t": pd.Series(pl), "full_procedure_t": pd.Series(ps)}).to_csv(OUT / "placebo.csv", index=False)
    return {"conditional": summarize(pl, real_position), "search_procedure_15q": summarize(ps, search_position)}


# ---------------------------------------------------------------------------------------------------- main
def main() -> None:
    """Run everything and save the results."""
    # Build the weekly table of everything we know each Friday.
    d = load()
    # The thing we forecast: next week's change in the 10-year yield.
    dy = d["dy_next_bp"]
    # The time periods we report.
    P = periods(d)
    # The 13 main answers and their number versions.
    a13, f13 = answers_13(d), features_13(d)
    # The candidate questions, with directions set from pre-2016 data.
    oriented = orient(candidates(d), dy, P["before"])
    # The summary we will save at the end.
    res = {"sample": {"first_week": str(d.index[0].date()), "last_signal_week": str(d.index[dy.notna()][-1].date()),
                      "last_outcome_week_ends": str((d.index[dy.notna()][-1] + pd.Timedelta(days=7)).date())}}

    # Table: every question on its own, before and after November 2016.
    rows = []
    # The 13 main questions.
    for key, group, rule in QUESTIONS_13:
        # Results before and after.
        rows.append({"key": key, "group": group, "question": rule, "status": "main 13",
                     **pack(evaluate(a13[key], dy.where(P["before"])), evaluate(a13[key], dy.where(P["test"])))})
    # The 14 candidates.
    for key, (family, rule, ans, feat, sign) in oriented.items():
        # Note when the early data flipped the direction.
        label = rule + ("  [yes = sell]" if sign < 0 else "  [yes = buy]")
        # Results before and after, using the chosen direction.
        rows.append({"key": key, "group": family, "question": label, "status": "candidate",
                     **pack(evaluate(ans, dy.where(P["before"])), evaluate(ans, dy.where(P["test"])))})
    # Save the table.
    hunt = pd.DataFrame(rows)
    # Write it out.
    hunt.to_csv(OUT / "feature_hunt.csv", index=False)

    # Forward selection, judged on 2006 to Oct 2016 only.
    steps = []
    # Pick the two.
    chosen = select(a13, f13, oriented, dy, P["design"], steps)
    # Save the step-by-step table.
    pd.DataFrame(steps).to_csv(OUT / "selection_steps.csv", index=False)
    # Record which two were added and in which direction.
    res["added_questions"] = [{"key": k, "family": oriented[k][0], "rule": oriented[k][1],
                               "direction": "yes = buy" if oriented[k][4] > 0 else "yes = sell"} for k in chosen]

    # The final 15-question model: the 13 plus the two the hunt picked.
    a15, f15 = extend(a13, f13, oriented, chosen)
    # Run the two-key rule with 15 questions (reported as a cautionary result: the search did not hold up).
    m15 = two_key(a15, f15, dy)
    # Run it with the main 13 questions: this is the MAIN model of the paper.
    m13 = two_key(a13.astype(float), f13, dy)
    # Short names for the main model and its inputs (the 15-question version is reported only as a cautionary result).
    mM, aM, fM = m13, a13.astype(float), f13
    # Save the main thirteen-question model's weight history.
    mM["coefs"].to_csv(OUT / "classifier_coefficients.csv", index=False)

    # Report each piece in each period, for both versions.
    for tag, m in [("", mM), ("15", m15)]:
        # Checklist alone, model alone, and the two together.
        for name, sig in [("checklist", m["score"]), ("classifier", m["clf"]), ("two_key", m["two_key"])]:
            # Each period we care about.
            for per in ["design", "test", "last_year"]:
                # Save the result; only that period's outcomes count.
                res[f"{name}{tag}_{per}"] = evaluate(sig, dy.where(P[per]))
    # The main checklist over all of 2001 to Oct 2016.
    res["checklist_before_nov_2016"] = evaluate(mM["score"], dy.where(P["before"]))

    # Paired comparison in the test period: is two-key better than the model alone, week by week?
    diff = (weekly_score(mM["two_key"], dy) - weekly_score(mM["clf"], dy))[P["test"]].dropna()
    # Save the average difference per year and its t-statistic.
    res["paired_two_key_minus_classifier_test"] = {"bp_per_year": round(float(diff.mean() * 52), 1), "t_stat": round(hac_t(diff), 2)}
    # Same comparison against the checklist alone.
    diff2 = (weekly_score(mM["two_key"], dy) - weekly_score(mM["score"], dy))[P["test"]].dropna()
    # Save it.
    res["paired_two_key_minus_checklist_test"] = {"bp_per_year": round(float(diff2.mean() * 52), 1), "t_stat": round(hac_t(diff2), 2)}
    for label, first, second in [
        ("paired_15_minus_13_test", m15["two_key"], m13["two_key"]),
        ("paired_two_key_minus_short_test", mM["two_key"], pd.Series(-1.0, index=d.index))]:
        difference = (weekly_score(first, dy) - weekly_score(second, dy))[P["test"]].dropna()
        res[label] = {"bp_per_year": round(float(difference.mean() * 52), 1), "t_stat": round(hac_t(difference), 2)}

    # Robustness checks on the test period (each changes one thing).
    # Strict agreement: both keys must have a view and agree.
    strict = np.sign(mM["score"]).where(np.sign(mM["score"]) == np.sign(mM["clf"]), 0)
    # Save it.
    res["robust_strict_agreement_test"] = evaluate(strict, dy.where(P["test"]))
    # Re-learning more often changes a global setting, so declare it.
    global CLF_REFIT
    # Try each refit length.
    for rf in [26, 13]:
        # Remember the normal setting and switch.
        keep, CLF_REFIT = CLF_REFIT, rf
        # Rerun the main thirteen-question two-key rule.
        alt = two_key(aM, fM, dy)["two_key"]
        # Put the normal setting back.
        CLF_REFIT = keep
        # Save the result.
        res[f"robust_refit_{rf}w_test"] = evaluate(alt, dy.where(P["test"]))
    # Market prices one week late (as if we only saw last Friday's prices): a harsh timing check.
    d_late = d.copy()
    # Shift every market-price column by one week.
    for col in ["y10", "y2", "us_eq", "em_eq", "oil", "vix", "vix3m", "usd", "breakeven", "natgas", "ovx", "gasoline", "fed_bs"]:
        # One week older.
        d_late[col] = d[col].shift(1)
    d_late["real_y10"] = d_late["y10"] - d_late["core_pce_yoy"]
    # Rebuild all predictors from the late data; dy retains the original target timing.
    a_late, f_late = answers_13(d_late).astype(float), features_13(d_late)
    # Save the result.
    res["robust_market_prices_one_week_late_test"] = evaluate(two_key(a_late, f_late, dy)["two_key"], dy.where(P["test"]))
    # Benchmarks.
    res["benchmark_always_buy_test"] = evaluate(pd.Series(1.0, index=d.index), dy.where(P["test"]))
    # Always sell.
    res["benchmark_always_sell_test"] = evaluate(pd.Series(-1.0, index=d.index), dy.where(P["test"]))
    # Bet that last week's move repeats.
    res["benchmark_last_week_test"] = evaluate(-np.sign(d["y10"].diff()).fillna(0), dy.where(P["test"]))

    # Turnover in the test period: count position changes (buy to sell counts as 2), including entering and leaving.
    tk = mM["two_key"][P["test"] & dy.notna()]
    # Add a flat position before the first week and after the last, so boundary trades count too.
    path = pd.concat([pd.Series([0.0]), tk.reset_index(drop=True), pd.Series([0.0])])
    # Position units traded per year.
    turns = float(path.diff().abs().fillna(0).sum()) / (len(tk) / 52)
    # Save it with an illustrative cost of 0.25bp of yield per unit.
    res["two_key_turnover_test"] = {"units_traded_per_year": round(turns, 1), "illustrative_cost_bp_per_unit": 0.25,
                                    "bp_per_year_after_illustrative_cost": round(float(weekly_score(tk, dy.loc[tk.index]).mean() * 52) - 0.25 * turns, 1)}

    # The last 52 signal weeks in detail.
    last = d.index[P["last_year"]]
    # Collect the facts about the year.
    ly = {
        # First and last signal week, and the Friday the last outcome ends.
        "first_signal_week": str(last[0].date()), "last_signal_week": str(last[-1].date()),
        "last_outcome_ends": str((last[-1] + pd.Timedelta(days=7)).date()),
        # 10-year yield on the first signal Friday and on the final Friday.
        "y10_start": float(d["y10"].loc[last[0]]), "y10_end": round(float(d["y10"].loc[last[-1]] + dy.loc[last[-1]] / 100), 2),
        # Typical weekly move this year, and over the whole history.
        "avg_abs_move_bp": round(float(dy.loc[last].abs().mean()), 1), "avg_abs_move_bp_all": round(float(dy.abs().mean()), 1),
        # Real yield at the start and end of the year.
        "real_y10_start": round(float(d["real_y10"].loc[last[0]]), 2), "real_y10_end": round(float(d["real_y10"].loc[last[-1]]), 2),
        # Share of weeks the yield sat above its 300-day average (bonds in a downtrend).
        "share_above_300d": round(float((d["regime"].loc[last] < 0).mean()), 3),
        # Weeks with no position.
        "flat_weeks": int((mM["two_key"][last] == 0).sum()),
    }
    # Score from each question on its own over the year (what each would have earned alone).
    ly["by_question_bp"] = {k: round(float((-aM[k].loc[last] * dy[last]).sum()), 1) for k in aM.columns}
    # Leave-one-out: how much the two-key total over the year changes when each question is removed (refit included).
    loo = {}
    # Each question in turn.
    for k in aM.columns:
        # Drop it from both the checklist and the model.
        tk_k = two_key(aM.drop(columns=k), fM.drop(columns=k), dy)["two_key"]
        # Year total without it, minus the year total with everything.
        loo[k] = round(float(weekly_score(tk_k, dy)[last].sum() - weekly_score(mM["two_key"], dy)[last].sum()), 1)
    # Save it (positive = the year would have been better without this question).
    ly["leave_one_out_change_bp"] = loo
    # The last six months.
    last26 = last[-26:]
    # The two-key rule over the last six months.
    ly["two_key_last_26w"] = {"active_weeks": int((mM["two_key"][last26] != 0).sum()),
                              "total_bp": round(float(weekly_score(mM["two_key"], dy)[last26].sum()), 1)}
    # The model alone over the last six months.
    ly["classifier_last_26w_bp"] = round(float(weekly_score(mM["clf"], dy)[last26].sum()), 1)
    # Save the year's facts.
    res["last_12_months"] = ly
    # Quarter-by-quarter table for the year (quarters assigned by signal date).
    q = pd.DataFrame({"yield_change_bp": dy[last], "checklist": weekly_score(mM["score"], dy)[last],
                      "classifier": weekly_score(mM["clf"], dy)[last], "two_key": weekly_score(mM["two_key"], dy)[last],
                      "two_key_active_weeks": (mM["two_key"][last] != 0).astype(int)})
    # Add up each quarter and save.
    q.groupby(q.index.to_period("Q")).sum().round(1).to_csv(OUT / "last_year_by_quarter.csv")

    res["placebo"] = placebo_statistics(d, aM, fM, dy, P, mM["two_key"], m15["two_key"])

    # Weekly record from the first forecast onward.
    live = (d.index >= CLF_START) & dy.notna()
    # One row per week with every piece of the model and its score.
    tw = pd.DataFrame({"score": mM["score"], "prob_yield_down": mM["prob"].round(4), "two_key_position": mM["two_key"],
                       "y10": d["y10"], "dy_next_bp": dy,
                       "checklist_bp": weekly_score(mM["score"], dy), "classifier_bp": weekly_score(mM["clf"], dy),
                       "two_key_bp": weekly_score(mM["two_key"], dy), "two_key15_bp": weekly_score(m15["two_key"], dy)})[live]
    # Save it.
    tw.to_csv(OUT / "two_key_weekly.csv")
    # Yearly totals, with 2016 split at the start of the test period.
    period_label = np.where(tw.index < HOLDOUT_START, tw.index.year.astype(str), tw.index.year.astype(str))
    # Label the two parts of 2016 separately.
    period_label = np.where((tw.index.year == 2016) & (tw.index >= HOLDOUT_START), "2016 (Nov-Dec, test)", period_label)
    # The early part of 2016.
    period_label = np.where((tw.index.year == 2016) & (tw.index < HOLDOUT_START), "2016 (Jan-Oct, design)", period_label)
    # Add up each year (or part-year) and save.
    tw.assign(period=period_label).groupby("period", sort=False)[["checklist_bp", "classifier_bp", "two_key_bp", "two_key15_bp"]].sum().round(1).to_csv(OUT / "two_key_by_year.csv")
    # Every question's answer each week.
    aM[live].to_csv(OUT / "answers.csv")

    # Running total of the two-key score in the test period.
    cum = tw.loc[tw.index >= HOLDOUT_START, "two_key_bp"].cumsum()
    # The worst fall from a high point (the maximum drawdown).
    res["two_key_max_drawdown_test_bp"] = round(float((cum - cum.cummax().clip(lower=0)).min()), 1)

    # Average next-week yield change for each checklist score range.
    full = pd.DataFrame({"score": mM["score"], "dy": dy}).dropna()
    # Ranges and labels.
    bins, labels = [-13.5, -6.5, -3.5, -0.5, 0.5, 3.5, 6.5, 13.5], ["-13 to -7", "-6 to -4", "-3 to -1", "0", "+1 to +3", "+4 to +6", "+7 to +13"]
    # Average yield change and number of weeks in each range.
    buckets = full.groupby(pd.cut(full["score"], bins=bins, labels=labels), observed=False)["dy"].agg(["count", "mean"]).round(2)
    # Save it.
    buckets.to_csv(OUT / "buckets.csv")

    # Save the frozen specification that signal.py will use every week.
    spec = {"frozen_on": "2026-11-07", "questions_13": [q[0] for q in QUESTIONS_13],
            "added": [],
            "clf_c": CLF_C, "clf_refit_weeks": CLF_REFIT, "clf_start": CLF_START, "start": START}
    # Research runs never rewrite the approved production specification.
    (OUT / "proposed_spec.json").write_text(json.dumps(spec, indent=1))

    # This Friday's reading.
    res["latest"] = {"date": str(d.index[-1].date()), "score": int(mM["score"].iloc[-1]),
                     "prob_yield_down": round(float(mM["prob"].iloc[-1]), 3), "two_key_position": int(mM["two_key"].iloc[-1]),
                     "answers": {k: int(v) for k, v in aM.iloc[-1].items()}}
    # Save the whole summary as valid JSON (no "not a number" values).
    (OUT / "summary.json").write_text(json.dumps(nan_to_none(res), indent=1, allow_nan=False))
    # Draw the charts.
    charts(tw, hunt, buckets)
    # Print the headline numbers.
    for k in ["added_questions", "two_key_design", "two_key_test", "two_key_last_year", "two_key15_design", "two_key15_test", "placebo"]:
        # One line per headline.
        print(k, res[k])


# ------------------------------------------------------------------------------------------------- charts
def charts(tw: pd.DataFrame, hunt: pd.DataFrame, buckets: pd.DataFrame) -> None:
    """Draw the pictures used in the paper."""
    # Use a drawing engine that writes files without needing a screen.
    import matplotlib
    # Pick the file-only engine.
    matplotlib.use("Agg")
    # The plotting tools.
    import matplotlib.pyplot as plt

    # Picture 1: running total of the weekly score for each piece of the model.
    fig, ax = plt.subplots(figsize=(8, 4.2), dpi=150)
    # One line per piece, each with its own color.
    for col, label, color in [("checklist_bp", "Checklist (13 questions)", "#8a8f99"), ("classifier_bp", "Classifier", "#4c78a8"),
                              ("two_key15_bp", "Two-key, 15 questions (search result)", "#e0a458"), ("two_key_bp", "Two-key, 13 questions (main)", "#d1495b")]:
        # Add up the weekly scores over time and draw the line.
        ax.plot(tw.index, tw[col].fillna(0).cumsum(), label=label, color=color, lw=1.5)
    # A dashed line where the test period starts.
    ax.axvline(pd.Timestamp(HOLDOUT_START), color="black", ls="--", lw=0.8)
    # Label that line.
    ax.text(pd.Timestamp(HOLDOUT_START), ax.get_ylim()[1] * 0.92, "  later evaluation", fontsize=8)
    # Label the side.
    ax.set_ylabel("Cumulative signed yield change (bp)")
    # A light grid.
    ax.grid(alpha=0.25)
    # A legend without a box.
    ax.legend(frameon=False, fontsize=8)
    # Remove the top and right borders for a cleaner look.
    [ax.spines[s].set_visible(False) for s in ["top", "right"]]
    # Fit everything inside the picture and save it.
    fig.tight_layout(); fig.savefig(CHARTS / "cumulative.png"); plt.close(fig)

    # Picture 2: two-key score in each calendar year, with 2016 split at the start of the test period.
    by = pd.read_csv(OUT / "two_key_by_year.csv", index_col=0)["two_key_bp"]
    # A wide, short picture.
    fig, ax = plt.subplots(figsize=(8, 3.4), dpi=150)
    # Short labels for the bars.
    labels = [str(i).replace(" (Jan-Oct, design)", "a").replace(" (Nov-Dec, test)", "b") for i in by.index]
    # Grey for design years, blue/red for test years by sign.
    colors = ["#b5b9c2" if (lab < "2016b") else ("#d1495b" if v < 0 else "#4c78a8") for lab, v in zip(labels, by.values)]
    # Draw the bars.
    ax.bar(range(len(by)), by.values, color=colors)
    # Put the year labels under the bars.
    ax.set_xticks(range(len(by))); ax.set_xticklabels(labels, rotation=90, fontsize=7)
    # Label the side.
    ax.set_ylabel("bp per year")
    # A light grid on the side axis.
    ax.grid(axis="y", alpha=0.25)
    # Remove the top and right borders.
    [ax.spines[s].set_visible(False) for s in ["top", "right"]]
    # Save it.
    fig.tight_layout(); fig.savefig(CHARTS / "two_key_by_year.png"); plt.close(fig)

    # Picture 3: every question on its own, before and after November 2016.
    fig, ax = plt.subplots(figsize=(8, 7.6), dpi=150)
    # Positions for the bars, top to bottom.
    ypos = np.arange(len(hunt))[::-1]
    # Grey bars: before November 2016.
    ax.barh(ypos + 0.2, hunt["in_sample_t"], height=0.4, color="#8a8f99", label="2001 to Oct 2016")
    # Blue bars: after.
    ax.barh(ypos - 0.2, hunt["out_sample_t"], height=0.4, color="#4c78a8", label="Nov 2016 to Oct 2026")
    # Where each question's label goes.
    ax.set_yticks(ypos)
    # Write each rule next to its bars, shortened if too long.
    ax.set_yticklabels([q if len(q) < 70 else q[:67] + "..." for q in hunt["question"]], fontsize=6)
    # A line at zero.
    ax.axvline(0, color="black", lw=0.6)
    # Dotted lines at -2 and +2.
    [ax.axvline(x, color="black", ls=":", lw=0.6) for x in (-2, 2)]
    # Label the bottom.
    ax.set_xlabel("t-statistic of the calendar-week score (Newey-West)")
    # The legend.
    ax.legend(frameon=False, fontsize=8, loc="upper right")
    # Remove the top and right borders.
    [ax.spines[s].set_visible(False) for s in ["top", "right"]]
    # Save it.
    fig.tight_layout(); fig.savefig(CHARTS / "feature_hunt.png"); plt.close(fig)

    # Picture 4: average next-week yield change for each checklist score range.
    fig, ax = plt.subplots(figsize=(6, 3), dpi=150)
    # One bar per range.
    ax.bar(buckets.index.astype(str), buckets["mean"], color="#4c78a8")
    # A line at zero.
    ax.axhline(0, color="black", lw=0.6)
    # Label the bottom.
    ax.set_xlabel("Checklist score (13 questions)")
    # Label the side.
    ax.set_ylabel("Next-week change in 10y yield (bp)")
    # Remove the top and right borders.
    [ax.spines[s].set_visible(False) for s in ["top", "right"]]
    # Save it.
    fig.tight_layout(); fig.savefig(CHARTS / "buckets.png"); plt.close(fig)


# Run main() only when this file is run directly (not when another file imports it).
if __name__ == "__main__":
    # Do everything.
    main()
