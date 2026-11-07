"""Calendar-only 30-year TIPS feature. No auction results enter this module.

Historical records are supplemented by the official announced-securities feed.
Only announcements strictly before the reference Friday are eligible. An event
must fall after that Friday and on or before the following Friday.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import model as M

ANNOUNCED_URL = 'https://www.treasurydirect.gov/TA_WS/securities/announced?format=json'
FIELDS = ('cusip', 'security_type', 'original_security_term', 'inflation_index_security',
          'announcemt_date', 'auction_date')


def validate_row(row):
    out = {k: str(row[k]) for k in FIELDS}
    if len(out['cusip']) != 9 or not out['original_security_term']:
        raise ValueError('Incomplete auction identity')
    for k in ('announcemt_date', 'auction_date'):
        value = pd.Timestamp(out[k])
        if pd.isna(value):
            raise ValueError('Missing auction date')
        out[k] = str(value.date())
    if out['announcemt_date'] > out['auction_date']:
        raise ValueError('Auction precedes its announcement')
    if out['security_type'] in ('Bond', 'Note') and out['inflation_index_security'] not in ('Yes', 'No'):
        raise ValueError('Unknown inflation protection')
    return out


def normalize_announced(raw):
    if not isinstance(raw, list) or not raw:
        raise ValueError('Empty or malformed announcement feed')
    rows = []
    for r in raw:
        # Bills sometimes have an empty protection flag; long bonds must state it.
        rows.append(validate_row(dict(zip(FIELDS, [r['cusip'], r['securityType'],
            r['originalSecurityTerm'], r['inflationProtected'], r['announcementDate'],
            r['competitiveAuctionCloseDate']]))))
    return rows


def merge_calendar(historical, announced):
    records = {}
    for r in historical + announced:
        row = validate_row(r)
        key = (row['cusip'], row['auction_date'])
        if key in records and records[key] != row:
            # A blank bill flag is equivalent to No; it cannot affect TIPS selection.
            prior = records[key].copy()
            current = row.copy()
            for item in (prior, current):
                if item['security_type'] == 'Bill':
                    item['inflation_index_security'] = 'No'
            if prior != current:
                raise ValueError('Conflicting auction calendar records: ' + str(key))
        records[key] = row
    return sorted(records.values(), key=lambda r: (r['auction_date'], r['cusip']))


def download_calendar(target, previous, fetch):
    """Archive a validated fresh calendar inside a new, not-yet-complete snapshot."""
    source = Path(previous) / 'auction_calendar.json'
    historical = (json.loads(source.read_text())['records'] if source.exists() else
                  json.loads((M.ROOT/'auction_study/auction_calendar_records.json').read_text()))
    announced = normalize_announced(json.loads(fetch(ANNOUNCED_URL)))
    now = datetime.now(timezone.utc)
    latest = max(r['announcemt_date'] for r in announced)
    if not 0 <= (now.date()-pd.Timestamp(latest).date()).days <= 7:
        raise ValueError('Announcement feed is stale or future dated')
    # A feed that starts after our stored history would leave an unknown calendar gap.
    if min(r['auction_date'] for r in announced) > max(r['auction_date'] for r in historical):
        raise ValueError('Announcement feed no longer overlaps stored history')
    value = {'fetched_at_utc':now.isoformat(), 'source':ANNOUNCED_URL,
             'latest_announcement':latest, 'records':merge_calendar(historical, announced)}
    (Path(target)/'auction_calendar.json').write_text(json.dumps(value, indent=2), encoding='utf-8')


def read_calendar(snapshot, reference=None):
    value = json.loads((Path(snapshot)/'auction_calendar.json').read_text())
    if reference is not None:
        age = (pd.Timestamp(reference)-pd.Timestamp(value['latest_announcement'])).days
        # A newer download is also usable for a dated illustration; the flag itself
        # always filters on each announcement's historical date.
        if age > 7:
            raise ValueError('Auction announcement calendar is stale')
    if not value['records']:
        raise ValueError('Auction calendar is empty')
    return value


def tips_flag(index, records):
    flag = pd.Series(0, index=index, name='tips_30', dtype=int)
    for raw in records:
        r = validate_row(raw)
        if not (r['original_security_term'].startswith('30-Year') and r['inflation_index_security']=='Yes'):
            continue
        ann, auction = pd.Timestamp(r['announcemt_date']), pd.Timestamp(r['auction_date'])
        flag.loc[(ann < index) & (index < auction) & (auction <= index+pd.Timedelta(days=7))] = 1
    return flag


def selected_inputs(d, records):
    flag = tips_flag(d.index, records)
    return M.answers_13(d).assign(tips_30=flag), M.features_13(d).assign(tips_30=flag)
