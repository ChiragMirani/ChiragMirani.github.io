"""Fill recent missing FRED observations from the same series' original publisher.

Treasury par constant-maturity yields and the Cboe cash VIX CLOSE are used;
futures, ETFs and intraday quotes are not substitutes. Existing nonmissing
observations are never changed. Raw responses and retrieval times stay with
the immutable snapshot so a Friday reference is never mistaken for issue time.
"""
import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd

TREASURY = ('https://home.treasury.gov/resource-center/data-chart-center/interest-rates/'
            'daily-treasury-rates.csv/{year}/all?_format=csv&field_tdr_date_value={year}'
            '&page=&type=daily_treasury_yield_curve')
CBOE = 'https://cdn-api.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv'


def parse(raw, date_column, value_column):
    frame = pd.read_csv(io.BytesIO(raw))
    dates = pd.to_datetime(frame[date_column], format='%m/%d/%Y', errors='raise')
    values = pd.to_numeric(frame[value_column], errors='raise')
    if dates.duplicated().any() or dates.isna().any():
        raise ValueError('Duplicate or invalid publisher dates')
    result = pd.Series(values.to_numpy(), index=dates).dropna().sort_index()
    if result.empty or not np.isfinite(result).all() or (result <= 0).any():
        raise ValueError('Invalid publisher observations')
    return result


def checked_extension(fred, direct, cutoff):
    """Return additions only after FRED's last valid date, with recent overlap proof."""
    cutoff = pd.Timestamp(cutoff)
    if fred.index.duplicated().any() or direct.index.duplicated().any():
        raise ValueError('Duplicate observations')
    known = fred.dropna().sort_index()
    if known.empty or (cutoff - known.index[-1]).days > 7:
        raise ValueError('FRED history too stale for a recent-observation fallback')
    overlap = pd.concat([known.rename('fred'), direct.rename('direct')], axis=1).dropna()
    overlap = overlap.loc[overlap.index <= cutoff].sort_index().tail(20)
    if len(overlap) != 20 or (cutoff - overlap.index[-1]).days > 7:
        raise ValueError('Need 20 recent overlapping observations')
    if not np.allclose(overlap.fred, overlap.direct, rtol=0, atol=1e-8):
        raise ValueError('Publisher observations conflict with recent FRED history')
    additions = direct.loc[(direct.index > known.index[-1]) & (direct.index <= cutoff)]
    if cutoff not in additions.index:
        raise ValueError('Publisher does not yet have the required Friday observation')
    return additions, {'observations':len(overlap), 'first':str(overlap.index[0].date()),
                       'last':str(overlap.index[-1].date()), 'max_absolute_difference':float(abs(overlap.fred-overlap.direct).max())}


def supplement_snapshot(target, fetch, now=None):
    """Called before snapshot commit. Failure leaves the previous snapshot pointer intact."""
    now = now or datetime.now(timezone.utc)
    day = pd.Timestamp(now.astimezone(ZoneInfo('America/New_York')).date())
    cutoff = day - pd.Timedelta(days=(day.dayofweek-4) % 7)
    target = Path(target)
    records, cache = [], {}

    def download(url, filename):
        if url not in cache:
            raw = fetch(url)
            retrieved = datetime.now(timezone.utc).isoformat()
            path = target/'publisher_raw'/filename
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            cache[url] = (raw, {'url':url, 'retrieved_at_utc':retrieved,
                               'raw_sha256':hashlib.sha256(raw).hexdigest()})
        return cache[url]

    for code, field in [('DGS10','10 Yr'), ('DGS2','2 Yr'), ('VIXCLS','CLOSE')]:
        path = target/(code+'.csv')
        frame = pd.read_csv(path, index_col=0, parse_dates=True)
        fred = pd.to_numeric(frame.iloc[:,0], errors='coerce')
        if cutoff in fred.index and pd.notna(fred.loc[cutoff]):
            continue
        sources = []
        if code == 'VIXCLS':
            raw, source = download(CBOE, 'cboe_vix.csv')
            direct = parse(raw, 'DATE', field); sources.append(source)
        else:
            raw, source = download(TREASURY.format(year=cutoff.year), 'treasury_'+str(cutoff.year)+'.csv')
            direct = parse(raw, 'Date', field); sources.append(source)
            if len(direct.loc[direct.index <= cutoff].index.intersection(fred.dropna().index)) < 20:
                raw, source = download(TREASURY.format(year=cutoff.year-1), 'treasury_'+str(cutoff.year-1)+'.csv')
                direct = pd.concat([parse(raw, 'Date', field), direct]).sort_index(); sources.append(source)
        additions, overlap = checked_extension(fred, direct, cutoff)
        # Retain the exact downloaded FRED file as well as its supplemented series.
        (target/'publisher_raw'/('fred_'+code+'.csv')).write_bytes(path.read_bytes())
        combined = fred.copy()
        for date, value in additions.items():
            combined.loc[date] = value
            records.append({'series':code, 'observation_date':str(date.date()), 'value':float(value),
                            'publisher_field':field, 'sources':sources, 'overlap_check':overlap})
        combined.sort_index().to_frame(frame.columns[0]).to_csv(path, index_label=frame.index.name)
    report = {'reference_friday':str(cutoff.date()), 'additions':records,
              'policy':'Missing recent observations only; no changes to existing FRED values. Actual retrieval times recorded.'}
    (target/'market_source_provenance.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report
