"""Reconcile the adopted 14-rule model to the disclosed quarterly auction trial."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import model as M
import auction_inputs as A
from auction_study.analyze import extended_metrics, paired


def main():
    d=M.load()
    a,f=A.selected_inputs(d,json.loads((M.ROOT/'auction_study/auction_calendar_records.json').read_text()))
    tk=M.two_key(a,f,d.dy_next_bp,refit_weeks=13)
    pos=tk['two_key']; dy=d.dy_next_bp
    saved=pd.read_csv(M.ROOT/'auction_study/quarterly/all_weekly_positions.csv',index_col=0,parse_dates=True)
    mask=(d.index>=M.CLF_START)&dy.notna()
    np.testing.assert_array_equal(pos[mask],saved.loc[mask,'tips_30_+1'])
    later=(d.index>=M.HOLDOUT_START)&dy.notna()
    early=(d.index>=M.CLF_START)&(d.index+pd.Timedelta(days=7)<pd.Timestamp(M.HOLDOUT_START))&dy.notna()
    study=json.loads((M.ROOT/'auction_study/quarterly/summary.json').read_text())
    periods={'early':early,'later':later,'last_52':d.index.isin(d.index[later][-52:]),'2026':later&(d.index.year==2026)}
    out={'version':json.loads((M.ROOT/'spec.json').read_text())['version'],
         'selection':'Quarterly refit and 30-year TIPS +1 vote selected after inspecting later outcomes on 2026-11-07.',
         'measurement':'Signed weekly yield change in basis points, not a portfolio return.',
         'periods':{},'brier_later':float(((tk['prob'][later]-(dy[later]<0))**2).mean()),
         'quarterly_13_reference':study['baseline']}
    for name,m in periods.items():
        stats=extended_metrics(pos[m],dy[m]); original=study['combined']['tips_30']['1'][name]
        for key in ('gross_bp_year','net_bp_year','gross_t','hit_rate','active_weeks'):
            assert np.isclose(stats[key],original[key]),(name,key)
        out['periods'][name]={**stats,'first_signal':str(d.index[m][0].date()),'last_signal':str(d.index[m][-1].date()),
            'last_outcome':str((d.index[m][-1]+pd.Timedelta(days=7)).date()),
            'paired_quarterly_13':paired(pos[m],saved.loc[m,'baseline'],dy[m]),
            'paired_always_reduce':paired(pos[m],pd.Series(-1.,index=d.index)[m],dy[m])}
    weekly=pd.DataFrame({'position':pos,'dy_next_bp':dy,'score_bp':-pos*dy,'prob_yield_down_uncalibrated':tk['prob'],
                         'checklist_score':a.sum(axis=1)},index=d.index).loc[mask]
    weekly.to_csv(M.OUT/'selected_weekly.csv',index_label='signal_date')
    yearly=[]
    for year,g in weekly.loc[weekly.index>=M.HOLDOUT_START].groupby(lambda t:t.year):
        yearly.append({'year':year,'weeks':len(g),'active':int(g.position.ne(0).sum()),'score_bp':round(g.score_bp.sum(),1)})
    out['by_year']=yearly
    quarters=[]
    for q,g in weekly.tail(52).groupby(lambda t:str(t.to_period('Q'))):
        quarters.append({'quarter':q,'weeks':len(g),'active':int(g.position.ne(0).sum()),'score_bp':round(g.score_bp.sum(),1),
                         'yield_change_bp':round(g.dy_next_bp.sum(),1)})
    out['last_52_by_quarter']=quarters
    (M.OUT/'selected_summary.json').write_text(json.dumps(M.nan_to_none(out),indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps(out['periods']['later'],indent=2))


if __name__=='__main__':main()
