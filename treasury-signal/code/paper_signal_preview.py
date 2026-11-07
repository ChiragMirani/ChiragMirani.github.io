"""Dated paper preview; never issues a live forecast or changes study results.

Run after download_data.py. The requested Friday must pass the production data
checks. If it does not, report unavailable and separately date the most recent
complete Friday illustration. A preview is calculated now, never backdated.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
import numpy as np
import pandas as pd
import model as M
import production_signal as P
import auction_inputs as A


def preview(now=None):
    now = now or datetime.now(timezone.utc)
    spec = json.loads(P.SPEC_PATH.read_text())
    P.validate_spec(spec)
    snapshot = P.use_snapshot(now)
    requested = P.expected_friday(now)
    manifest = json.loads((snapshot/'manifest.json').read_text())
    out = {'kind':'paper_research_preview', 'checked_at_utc':now.isoformat(),
           'checked_at_new_york':now.astimezone(P.NY).isoformat(),
           'requested_reference_friday':str(requested.date()),
           'live_start':spec['live_start'], 'model_version':spec['version'],
           'status':'unavailable', 'position':None,
           'requested_data_error':None, 'latest_complete_research_reading':None,
           'live_record_created':False,
           'snapshot_completed_at_utc':manifest['completed_at_utc'],
           'snapshot_manifest_sha256':P.digest(snapshot/'manifest.json'),
           'snapshot_id':snapshot.name,
           'spec_sha256':P.digest(P.SPEC_PATH),
           'qualification':'Calculated at the stated check time, not an issued live forecast. Any earlier reference date is a historical illustration, not a current instruction.'}
    # Reconstruct each candidate only through its own reference Friday.
    for offset in range(4):
        t = requested-pd.Timedelta(weeks=offset)
        d = M.load(end=str(t.date()))
        try:
            provenance=P.check_inputs(t,d)
        except ValueError as exc:
            if offset==0:out['requested_data_error']=str(exc)
            continue
        calendar=A.read_calendar(snapshot,t)
        a,f=A.selected_inputs(d,calendar['records'])
        model=M.two_key(a.astype(float),f,d.dy_next_bp,refit_weeks=spec['clf_refit_weeks'])
        score=int(a.loc[t].sum())
        probability=float(model['prob'].loc[t])
        position=int(np.sign(np.sign(score)+np.sign(probability-0.5)))
        reading={'reference_friday':str(t.date()),
                 'target_end':str((t+pd.Timedelta(days=7)).date()),
                 'checklist_score':score, 'prob_yield_down_uncalibrated':probability,
                 'position':position,
                 'view':{1:'Favors adding duration',-1:'Favors reducing duration',0:'No tactical view'}[position],
                 'votes_add':int((a.loc[t]>0).sum()), 'votes_reduce':int((a.loc[t]<0).sum()),
                 'votes_neutral':int((a.loc[t]==0).sum()),
                 'answers':a.loc[t].to_dict(),
                 'freshness_checked':True,
                 'input_dates':{k:{field:value for field,value in v.items() if field!='value'}
                                for k,v in provenance.items()}}
        out['latest_complete_research_reading']=reading
        if offset==0:
            out['status']='research_preview_only'
            out['position']=position
        break
    P.write_json(M.OUT/'paper_signal_preview.json',out)
    print(json.dumps(out,indent=2))
    return out


if __name__=='__main__':
    preview()
