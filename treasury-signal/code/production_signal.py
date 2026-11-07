"""Versioned Friday research signal; complete snapshots, fixed refit schedule, immutable records.
Run weekly_signal.py after Friday 18:00 New York time and before Sunday. No network publication occurs.
"""
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
import model as M
import auction_inputs as A

NY = ZoneInfo('America/New_York')
# Selected after the November 2026 historical comparison; never described as an untouched test choice.
APPROVED_REFIT_WEEKS = 13
SPEC_PATH = M.ROOT / 'spec.json'
RECORDS, MODELS, OUTCOMES = [M.OUT / p for p in ['issued', 'fitted_models', 'observed_outcomes']]
LATEST = M.OUT / 'latest.json'
MARKET = {'y10': ('DGS10', 0), 'y2': ('DGS2', 0), 'us_eq': ('NASDAQCOM', 0),
          'em_eq': ('NASDAQNQEM', 0), 'oil': ('DCOILWTICO', 7), 'vix': ('VIXCLS', 0)}
MACRO = {'unrate': ('UNRATE', 40), 'core_pce_yoy': ('PCEPILFE', 70),
         'de10_chg': ('IRLTLT01DEM156N', 75), 'jp10_chg': ('IRLTLT01JPM156N', 75),
         'uk10_chg': ('IRLTLT01GBM156N', 75)}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value, exclusive=False):
    """Records use exclusive creation; the public view is replaced atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(M.nan_to_none(value), indent=2, allow_nan=False)
    if exclusive:
        with path.open('x', encoding='utf-8') as out:
            out.write(text)
    else:
        temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
        temp.write_text(text, encoding='utf-8')
        os.replace(temp, path)


def expected_friday(now):
    date = pd.Timestamp(now.astimezone(NY).date())
    return date - pd.Timedelta(days=(date.dayofweek - 4) % 7)


def validate_spec(spec):
    expected_sources = {'model.py', 'download_data.py', 'weekly_signal.py', 'production_signal.py', 'auction_inputs.py'}
    if set(spec['source_sha256']) != expected_sources:
        raise ValueError('The approved specification must bind all five source files')
    if spec['added'] != [{'key':'tips_30', 'sign':1}] or spec['questions_13'] != [q[0] for q in M.QUESTIONS_13]:
        raise ValueError('Rule list differs from the approved specification')
    expected = {'clf_c': M.CLF_C, 'clf_refit_weeks': APPROVED_REFIT_WEEKS, 'clf_start': M.CLF_START, 'start': M.START}
    if any(spec[k] != v for k, v in expected.items()):
        raise ValueError('Signal settings differ from the approved specification')
    for name, sha in spec['source_sha256'].items():
        if digest(M.ROOT / name) != sha:
            raise ValueError('Source changed since specification freeze: ' + name)


def use_snapshot(now):
    pointer = json.loads((M.ROOT / 'data/latest_snapshot.json').read_text())
    root = (M.ROOT / 'data' / pointer['snapshot']).resolve()
    if not root.is_relative_to((M.ROOT / 'data/snapshots').resolve()):
        raise ValueError('Snapshot path is outside the snapshot directory')
    manifest = json.loads((root / 'manifest.json').read_text())
    fetched = datetime.fromisoformat(manifest['completed_at_utc'])
    if fetched > now or (now - fetched).total_seconds() > 36 * 3600:
        raise ValueError('A complete snapshot from the last 36 hours is required')
    for rel, sha in manifest['sha256'].items():
        path = (root / rel).resolve()
        if not path.is_relative_to(root) or digest(path) != sha:
            raise ValueError('Snapshot checksum failed: ' + rel)
    required = {v[0] + '.csv' for v in MARKET.values()} | {code + '.csv' for code, _ in M.FX}
    required |= {'vintages/' + code + '.csv' for code, _ in MACRO.values()}
    required.add('fomc_dates.csv')
    required.add('auction_calendar.json')
    if not required <= set(manifest['sha256']):
        raise ValueError('Snapshot is missing required inputs')
    M.DATA, M.VINTAGES = root, root / 'vintages'
    return root


def check_inputs(t, d):
    errors, provenance = [], {}
    series = dict(MARKET)
    series.update({code: (code, 7) for code, _ in M.FX})
    for name, (code, lag) in series.items():
        s = M.fred(code)
        cutoff = t - pd.Timedelta(days=lag)
        s = s[s.index <= cutoff]
        # Conservative holiday policy: withhold if the expected Friday observation is absent.
        if s.empty or s.index[-1] != cutoff or not np.isfinite(s.iloc[-1]):
            errors.append(name + ' is missing or stale')
        else:
            provenance[name] = {'observation': str(s.index[-1].date()), 'delay_days': lag, 'value': float(s.iloc[-1])}
    for name, (code, max_age) in MACRO.items():
        groups = [(date, g) for date, g in M.valid_releases(code) if date <= t]
        if name == 'unrate':
            # A revision-only vintage cannot make the first-observed unemployment value fresh.
            first_dates = M.unemployment_first_prints().index
            groups = [(date, g) for date, g in groups if date in first_dates]
        if not groups or (t - groups[-1][0]).days > max_age:
            errors.append(name + ' has no fresh valid archive snapshot')
        else:
            date, g = groups[-1]
            provenance[name] = {'vintage': str(date.date()), 'last_observation': str(g.obs.iloc[-1].date())}
    required = list(MARKET) + ['usd', 'unrate', 'unrate_5y', 'core_pce_yoy', 'real_y10', 'de10_chg', 'jp10_chg', 'uk10_chg']
    for name in required:
        if not np.isfinite(d.loc[t, name]):
            errors.append(name + ' has no usable value')
    if any(d.loc[t, name] <= 0 for name in ['oil', 'us_eq', 'em_eq']):
        errors.append('A logarithmic input is not positive')
    if errors:
        raise ValueError('; '.join(errors))
    return provenance


def fitted_model(f, dy, t, spec, snapshot):
    """Fit on the specification's anchor dates and persist exact coefficients between refits."""
    first = f.index.get_loc(f.index[f.index >= spec['clf_start']][0])
    current = f.index.get_loc(t)
    anchor = first + ((current - first) // spec['clf_refit_weeks']) * spec['clf_refit_weeks']
    refit = f.index[anchor]
    path = MODELS / (spec['version'] + '_' + str(refit.date()) + '.json')
    if path.exists():
        artifact = json.loads(path.read_text())
    else:
        train = f.index[:anchor]
        train = train[dy.loc[train].notna()]
        fit = M.LogisticRegression(C=spec['clf_c'], max_iter=2000).fit(f.loc[train].values, (dy.loc[train] < 0).astype(int))
        artifact = {'refit': str(refit.date()), 'columns': list(f.columns), 'coef': fit.coef_[0].tolist(),
                    'intercept': float(fit.intercept_[0]), 'snapshot': str(snapshot), 'spec_sha256': digest(SPEC_PATH)}
        try:
            write_json(path, artifact, exclusive=True)
        except FileExistsError:
            artifact = json.loads(path.read_text())
    if artifact['columns'] != list(f.columns) or artifact['spec_sha256'] != digest(SPEC_PATH):
        raise ValueError('Cached classifier does not match the frozen specification')
    logit = artifact['intercept'] + np.dot(f.loc[t].values, artifact['coef'])
    return float(1 / (1 + np.exp(-np.clip(logit, -700, 700)))), artifact


def live_history(t, snapshot=None):
    """First observed outcomes are stored once, separately from forecasts."""
    rows = []
    y = M.fred('DGS10') if snapshot is not None else None
    for path in sorted(RECORDS.glob('*.json')):
        r = json.loads(path.read_text())
        end = pd.Timestamp(r['forecast_end'])
        outpath = OUTCOMES / path.name
        if not outpath.exists() and y is not None and end <= t:
            available = y[y.index <= end]
            if not available.empty and available.index[-1] == end:
                outcome = {'signal_date': r['signal_date'], 'end_date': str(end.date()),
                           'end_yield': float(available.iloc[-1]), 'snapshot': str(snapshot),
                           'score_bp': round(-r['position'] * (float(available.iloc[-1]) - r['y10']) * 100, 1)}
                try:
                    write_json(outpath, outcome, exclusive=True)
                except FileExistsError:
                    pass
        outcome = json.loads(outpath.read_text()) if outpath.exists() else {}
        rows.append({'signal_date': r['signal_date'], 'issued_at_utc': r['issued_at_utc'],
                     'position': r['position'], 'score_bp': outcome.get('score_bp')})
    return rows


def main(now=None):
    now = now or datetime.now(timezone.utc)
    t = expected_friday(now)
    path = RECORDS / (str(t.date()) + '.json')
    snapshot = None
    try:
        spec = json.loads(SPEC_PATH.read_text())
        validate_spec(spec)
        local = now.astimezone(NY)
        if t < pd.Timestamp(spec['live_start']):
            raise ValueError('Prospective publication has not started')
        if path.exists():
            record = json.loads(path.read_text())
        else:
            if local.weekday() not in (4, 5) or (local.weekday() == 4 and local.hour < 18):
                raise ValueError('Issue after Friday 18:00 New York time and before Sunday; never backdate')
            snapshot = use_snapshot(now)
            d = M.load(end=str(t.date()))
            provenance = check_inputs(t, d)
            calendar = A.read_calendar(snapshot, t)
            a, f = A.selected_inputs(d, calendar['records'])
            provenance['tips_30'] = {'source':calendar['source'], 'fetched_at_utc':calendar['fetched_at_utc'],
                                    'latest_announcement':calendar['latest_announcement']}
            prob, artifact = fitted_model(f, d.dy_next_bp, t, spec, snapshot)
            score = int(a.loc[t].sum())
            position = int(np.sign(np.sign(score) + np.sign(prob - 0.5)))
            record = {'status': 'issued', 'signal_date': str(t.date()), 'forecast_end': str((t + pd.Timedelta(days=7)).date()),
                      'issued_at_utc': now.isoformat(), 'model': spec['version'], 'spec_sha256': digest(SPEC_PATH),
                      'snapshot': str(snapshot), 'snapshot_manifest': digest(snapshot / 'manifest.json'),
                      'y10': float(d.loc[t, 'y10']), 'checklist_score': score, 'prob_yield_down_uncalibrated': prob,
                      'position': position, 'view': {1: 'Lower yields expected', -1: 'Higher yields expected', 0: 'No position: model views do not support a direction'}[position],
                      'answers': a.loc[t].to_dict(), 'features': f.loc[t].to_dict(),
                      'input_provenance': provenance, 'classifier': artifact}
            try:
                write_json(path, record, exclusive=True)
            except FileExistsError:
                record = json.loads(path.read_text())
        page = {k: record[k] for k in ['status', 'signal_date', 'forecast_end', 'issued_at_utc', 'model', 'y10',
                                      'checklist_score', 'prob_yield_down_uncalibrated', 'position', 'view', 'answers']}
    except Exception as exc:
        page = {'status': 'withheld', 'signal_date': str(t.date()), 'issued_at_utc': now.isoformat(),
                'position': None, 'prob_yield_down_uncalibrated': None, 'view': 'Signal unavailable', 'reason': str(exc)}
    try:
        # Reading an already-issued signal must still settle newly available outcomes.
        if snapshot is None:
            try:
                snapshot = use_snapshot(now)
            except Exception:
                pass
        page['live_record'] = live_history(t, snapshot)
    except Exception as exc:
        page['live_record'] = None
        page['live_record_error'] = str(exc)
    page['measurement'] = 'Signed DGS10 yield change; not an executable investment return. Probability is uncalibrated.'
    write_json(LATEST, page)
    print(json.dumps({k: page[k] for k in ['status', 'signal_date', 'view']}, indent=2))
    return page


if __name__ == '__main__':
    main()
