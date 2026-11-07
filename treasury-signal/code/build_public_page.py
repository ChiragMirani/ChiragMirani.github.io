"""Build crawlable static pages and public-only signal data for GitHub Pages.

No credentials, source observations, local paths or private research files are
exported. Issued forecasts and calculated research previews stay distinct.
"""
import csv
from datetime import datetime, timezone
from html import escape as esc
import io
import json
from pathlib import Path
import re
import shutil
import model as M
import production_signal as P

ROOT=Path(__file__).resolve().parent
SITE=ROOT/'public_site'/'treasury-signal'
BASE='https://chiragmirani.github.io/treasury-signal/'
LABELS={
 'us_eq':('U.S. equities','Four-week equity move; rising prices vote to reduce duration.'),
 'em_eq':('Emerging-market equities','Four-week equity move; rising prices vote to reduce duration.'),
 'oil':('Oil','Delayed four-week WTI move; rising prices vote to reduce duration.'),
 'usd':('U.S. dollar','Delayed six-currency basket; a rise votes to add duration.'),
 'vix':('Equity volatility','Four-week VIX change; a rise votes to add duration.'),
 'slack':('Labour market','Unemployment above its preceding five-year average votes to add duration.'),
 'pce':('Core inflation','Core PCE inflation below 2% votes to add; otherwise reduce.'),
 'real':('Yield minus trailing inflation','A nonnegative nominal yield minus trailing core PCE gap votes to add.'),
 'curve':('2s10s yield curve','Four-week steepening votes to add; flattening votes to reduce.'),
 'de10':('German yields','A rise in the latest published monthly change votes to reduce.'),
 'jp10':('Japanese yields','A rise in the latest published monthly change votes to reduce.'),
 'uk10':('U.K. yields','A rise in the latest published monthly change votes to reduce.'),
 'dec':('December seasonality','One reduce-duration vote during December; otherwise neutral.'),
 'tips_30':('30-year TIPS auction','One add-duration vote for an eligible announced auction in the next seven days.')}

def state_text(key,vote):
    if key=='dec':return 'December' if vote else 'Outside December'
    if key=='tips_30':return 'Eligible auction next week' if vote else 'No eligible auction next week'
    if vote==0:return 'Unchanged / neutral'
    if key=='slack':return 'Above preceding five-year average' if vote==1 else 'At or below preceding five-year average'
    if key=='pce':return 'Below 2%' if vote==1 else 'At or above 2%'
    if key=='real':return 'Yield at or above trailing inflation' if vote==1 else 'Yield below trailing inflation'
    if key=='curve':return 'Steepened over four weeks' if vote==1 else 'Flattened over four weeks'
    rising=vote==(-1 if key in ('us_eq','em_eq','oil','de10','jp10','uk10') else 1)
    return ('Rose' if rising else 'Fell')+(' in latest published monthly change' if key in ('de10','jp10','uk10') else ' over four weeks')


def write_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(M.nan_to_none(value),indent=2,allow_nan=False),encoding='utf-8')


def history(now):
    rows=[]
    for file in sorted(P.RECORDS.glob('*.json')):
        r=json.loads(file.read_text()); outcome_path=P.OUTCOMES/file.name
        o=json.loads(outcome_path.read_text()) if outcome_path.exists() else {}
        # Explicit whitelist: private snapshots and fitted artifacts are never copied.
        rows.append({k:r.get(k) for k in ['signal_date','forecast_end','issued_at_utc','model','position','view','checklist_score',
                    'prob_yield_down_uncalibrated','answers']} | {'score_bp':o.get('score_bp'),'outcome_status':'completed' if o else 'pending'})
    completed=[r for r in rows if r['score_bp'] is not None]
    active=[r for r in completed if r['position']!=0]
    stats={'issued':len(rows),'completed':len(completed),'active_completed':len(active),
           'hit_rate':sum(r['score_bp']>0 for r in active)/len(active) if active else None,
           'total_gross_yield_score_bp':round(sum(r['score_bp'] for r in completed),1) if completed else None,
           'measurement':'Signed DGS10 yield change, before costs; not an investment return.'}
    return rows,stats


def build(now=None):
    now=now or datetime.now(timezone.utc)
    SITE.mkdir(parents=True,exist_ok=True);(SITE/'paper').mkdir(exist_ok=True);(SITE/'data').mkdir(exist_ok=True)
    meta=json.loads((M.OUT/'publication_metadata.json').read_text())
    summary=json.loads((M.OUT/'selected_summary.json').read_text());s=summary['periods']['later']
    preview=json.loads((M.OUT/'paper_signal_preview.json').read_text())
    rows,stats=history(now)
    refresh_error_path=M.OUT/'refresh_error.json'
    refresh_error=json.loads(refresh_error_path.read_text()) if refresh_error_path.exists() else None
    refresh_failed=bool(refresh_error and refresh_error['checked_at_utc']>preview['checked_at_utc'])
    reading=preview['latest_complete_research_reading']
    kind='historical_preview';issue=None
    if rows and (reading is None or rows[-1]['signal_date']>=reading['reference_friday']):
        r=rows[-1];answers=r['answers'];issue=r['issued_at_utc'];kind='issued_forecast'
        reading={'reference_friday':r['signal_date'],'target_end':r['forecast_end'],'checklist_score':r['checklist_score'],
                 'prob_yield_down_uncalibrated':r['prob_yield_down_uncalibrated'],'position':r['position'],
                 'answers':answers,'votes_add':sum(v>0 for v in answers.values()),'votes_reduce':sum(v<0 for v in answers.values()),
                 'votes_neutral':sum(v==0 for v in answers.values()),'view':{1:'Favors adding duration',-1:'Favors reducing duration',0:'No tactical view'}[r['position']]}
    expired=reading is not None and now.astimezone(P.NY).date()>datetime.fromisoformat(reading['target_end']).date()
    latest={'schema_version':1,'page_updated_at_utc':now.isoformat(),'checked_at_utc':preview['checked_at_utc'],
            'kind':kind,'issued_at_utc':issue,'reference_period_ended':expired,
            'model':json.loads(P.SPEC_PATH.read_text())['version'],'reading':reading,
            'requested_reference_friday':preview['requested_reference_friday'],
            'refresh_note':refresh_error['error'] if refresh_failed else preview.get('requested_data_error'),
            'last_refresh_attempt_at_utc':refresh_error['checked_at_utc'] if refresh_failed else preview['checked_at_utc'],
            'interpretation':'An older reference period is a dated illustration, not a current forecast.' if kind=='historical_preview' or expired else 'Published weekly signal; assess against your macro view and risk budget.',
            'forecast_horizon':'Friday to Friday; visiting on another day does not change the horizon.',
            'prospective':stats,'links':{'tool':BASE,'paper':BASE+'paper/','history':BASE+'data/weekly-history.csv'}}
    write_json(SITE/'data/latest.json',latest);write_json(SITE/'data/history.json',rows);write_json(SITE/'data/historical-summary.json',summary)
    with (SITE/'data/weekly-history.csv').open('w',newline='',encoding='utf-8') as file:
        fields=['signal_date','forecast_end','issued_at_utc','model','position','checklist_score','prob_yield_down_uncalibrated','outcome_status','score_bp']
        writer=csv.DictWriter(file,fields,extrasaction='ignore');writer.writeheader();writer.writerows(rows)
    shutil.copy2(M.OUT/'selected_weekly.csv',SITE/'data/historical-weekly.csv')
    historical_label='Historical reconstruction · reference period ended' if expired else 'Calculated research preview'
    status=('Issued forecast · reference period ended' if expired else 'Issued weekly forecast') if kind=='issued_forecast' else historical_label
    r=reading or {};view=r.get('view','Awaiting a complete reading')
    date=r.get('reference_friday','—');end=r.get('target_end','—');score=r.get('checklist_score')
    probability=r.get('prob_yield_down_uncalibrated')
    action={1:'A bullish macro view has weekly support. Review the planned addition or the next staged entry.',
            -1:'The weekly reading leans against a bullish duration view. Examine the opposing inputs before adding.',
             0:'For a bullish macro view, this reading adds no tactical confirmation. Keep the macro plan and review the disagreement.'}.get(r.get('position'),'The last complete reading will appear here when the required inputs pass their checks.')
    votes=''.join(f'<tr><th scope="row">{esc(LABELS[k][0])}</th><td>{state_text(k,v)}</td><td><span class="vote v{v}">{ {1:"Add",-1:"Reduce",0:"Neutral"}[int(v)]}</span></td><td>{esc(LABELS[k][1])}</td></tr>' for k,v in r.get('answers',{}).items())
    checked=datetime.fromisoformat(preview['checked_at_utc']).astimezone(P.NY).strftime('%b %d, %Y at %I:%M %p %Z')
    if kind=='issued_forecast': checked=datetime.fromisoformat(issue).astimezone(P.NY).strftime('%b %d, %Y at %I:%M %p %Z')
    issue_label='Issued' if kind=='issued_forecast' else 'Calculated'
    live_total='—' if stats['total_gross_yield_score_bp'] is None else f"{stats['total_gross_yield_score_bp']:+.1f}"
    live_hit='—' if stats['hit_rate'] is None else f"{stats['hit_rate']:.1%}"
    balance=f'{r.get("votes_add",0)} add / {r.get("votes_reduce",0)} reduce / {r.get("votes_neutral",0)} neutral'
    headline='US 10-Year Treasury Signal & Duration Checklist | Chirag Mirani'
    description='A weekly US 10-year Treasury yield signal for reviewing duration timing after forming a macro view. See the dated checklist, model results, practical example, preprint and code.'
    faq=[('What does the Treasury signal help me decide?','It is an additional timing check after you form a macro view: review whether to add duration now, wait, or build the planned position gradually.'),
         ('Is the position scaled by the score?','No. The model outputs +1, 0 or -1. The score shows the balance of votes; the regression probability is uncalibrated. Portfolio size comes from your risk budget and implementation plan.'),
         ('Can I use the page on Monday or another day?','Yes. You can check the latest published data on any day. The tested signal remains Friday to Friday; a Monday visit does not create a Monday-to-Monday forecast.'),
         ('How are results measured?','The score is minus the position times the next weekly change in the 10-year Treasury yield, in basis points. Flat weeks score zero. It is a yield-direction measure, not a bond or ETF return.'),
         ('Were these historical results selected after seeing the data?','Yes. Quarterly refits and the 30-year TIPS auction addition were selected after reviewing the later results. The preprint reports the full searches and benchmarks. Prospective forecasts are recorded separately.'),
         ('What happens when data are late?','The page keeps the last complete reading and its original reference dates. It does not turn missing data into a neutral vote or backdate a new forecast. A new issue needs complete fresh inputs in the issue window.'),
         ('Where are the paper and reproducible code?','The preprint page links the PDF, readable paper, full code package and historical result tables. The weekly tracker supplies JSON and CSV downloads.')]
    faqs=''.join(f'<details><summary>{esc(q)}</summary><p>{esc(a)}</p></details>' for q,a in faq)
    ld={'@context':'https://schema.org','@graph':[
        {'@type':'WebApplication','name':'Weekly Treasury Duration Checklist','url':BASE,'applicationCategory':'FinanceApplication','operatingSystem':'Any browser','description':description,'creator':{'@type':'Person','name':'Chirag Mirani','url':'https://chiragmirani.github.io/'}},
        {'@type':'Dataset','name':'Weekly Treasury Signal: Prospective Forecasts and Outcomes','url':BASE+'#record','description':'Actual issue times and subsequent signed yield-change scores; historical simulations are separate.','creator':{'@type':'Person','name':'Chirag Mirani'},'distribution':{'@type':'DataDownload','contentUrl':BASE+'data/weekly-history.csv','encodingFormat':'text/csv'}},
        {'@type':'FAQPage','mainEntity':[{'@type':'Question','name':q,'acceptedAnswer':{'@type':'Answer','text':a}} for q,a in faq]}]}
    history_table=(''.join(f'<tr><td>{r["signal_date"]}</td><td>{r["position"]:+d}</td><td>{r["outcome_status"]}</td><td>{r["score_bp"]:+.1f}</td></tr>' if r['score_bp'] is not None else f'<tr><td>{r["signal_date"]}</td><td>{r["position"]:+d}</td><td>Pending</td><td>—</td></tr>' for r in rows[-16:])
                   or '<tr><td colspan="4">The prospective record starts with eligible signals from November 13, 2026. The first issued forecast will appear here.</td></tr>')
    score_text=f'{score:+d}' if score is not None else '—';prob_text=f'{probability:.1%}' if probability is not None else '—'
    html=f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{headline}</title><meta name="description" content="{description}"><link rel="canonical" href="{BASE}">
<meta property="og:type" content="website"><meta property="og:title" content="{headline}"><meta property="og:description" content="{description}"><meta property="og:url" content="{BASE}">
<meta name="twitter:card" content="summary"><meta name="robots" content="index,follow,max-snippet:-1"><meta name="author" content="Chirag Mirani">
<link rel="stylesheet" href="style.css"><link rel="alternate" type="application/json" href="data/latest.json" title="Latest Treasury signal data">
<script type="application/ld+json">{json.dumps(ld)}</script></head><body>
<header><a class="brand" href="https://chiragmirani.github.io/">CHIRAG MIRANI <span>Research</span></a><nav aria-label="Main"><a href="#checklist">Checklist</a><a href="#how">How to use it</a><a href="#record">Results</a><a href="paper/">Paper &amp; code ↗</a></nav></header>
<main><section class="intro"><p class="eyebrow">U.S. 10-YEAR TREASURY · WEEKLY DURATION TOOL</p><h1>A weekly check before<br>you change duration.</h1><p class="lead">Form your macro view. Then use the checklist to review the timing: <strong>add, wait or build gradually.</strong></p></section>
<section class="signal" aria-labelledby="signal-title"><div class="signal-top"><span class="eyebrow">LATEST COMPLETE READING</span><span class="status">{status}</span></div>
<div class="signal-body"><div><p class="dates">Reference: <time datetime="{date}">{date}</time> → <time datetime="{end}">{end}</time></p><h2 id="signal-title">{esc(view)}</h2><p class="interpretation">{esc(action)}</p><p class="timestamp">{issue_label} {checked}. {'This preview was not issued on its reference date.' if kind=='historical_preview' else ''}</p></div>
<div class="readings"><div><span>Checklist score</span><strong>{score_text}</strong><small>{balance}</small></div><div><span>Regression: lower yields</span><strong>{prob_text}</strong><small>Model probability · uncalibrated</small></div></div></div>
<div class="signal-bottom"><p>{'This reference period has ended. Keep the dates in view when using the illustration.' if expired else 'Compare the weekly evidence with your existing macro position and risk budget.'}</p><button id="refresh" type="button">Check latest published data ↻</button><span id="refresh-status" role="status"></span></div></section>
<section class="section" id="checklist"><div class="section-heading"><div><p class="eyebrow">THE BALANCE OF EVIDENCE</p><h2>What is behind the reading?</h2></div><p>Fourteen equal votes, plus a regression using the same inputs. Opposing model views produce no tactical signal.</p></div>
<div class="table-wrap"><table><thead><tr><th>Reading</th><th>Observed state</th><th>Duration vote</th><th>Rule in plain English</th></tr></thead><tbody>{votes}</tbody></table></div>
<p class="note">These are directional hypotheses. Yield minus trailing inflation is a historical gap, not a measure of fair value. The auction input uses announcements available before the reference Friday. <a href="paper/#rules">Full definitions in the paper</a>.</p></section>
<section class="section" id="how"><p class="eyebrow">MACRO VIEW FIRST, TIMING SECOND</p><h2>Bullish on bonds. How much to add now?</h2><p class="section-intro">Suppose your portfolio has 6 years of duration and your macro view supports a target of 7. Set the target and risk budget first; use the weekly evidence to review the entry.</p>
<div class="steps"><article><span class="step-number">01 / WAIT</span><h3>The reading leans against you.</h3><p>Hold at 6 years while you examine the opposing inputs. A weekly disagreement can change the entry without overturning the macro thesis.</p></article><article><span class="step-number">02 / ADD</span><h3>The evidence supports your view.</h3><p>Consider moving toward the planned 7-year target if the portfolio conditions still fit. The checklist does not set the amount.</p></article><article><span class="step-number">03 / BUILD</span><h3>You prefer to stage the position.</h3><p>With the same supportive signal, add 0.25 years to reach 6.25, then reassess before the next step.</p></article></div><p class="note">Illustrative decisions, not a tested allocation rule. The model itself uses fixed +1, 0 or -1 positions.</p></section>
<section class="section results" id="results"><p class="eyebrow">HISTORICAL RESEARCH · NOV 2016–OCT 2026</p><h2>The results, with the comparison in view.</h2><div class="stats"><div><strong>{s['hit_rate']:.1%}</strong><span>Hit rate · {s['active_weeks']} active weeks</span></div><div><strong>{s['gross_bp_year']:+.1f}</strong><span>Yield bp per year · before charge</span></div><div><strong>{s['net_bp_year']:+.1f}</strong><span>After illustrative charge · bp/year</span></div></div>
<p>Quarterly refits and the 30-year TIPS addition were selected after inspecting the later history. The same period's always-higher-yields benchmark scores +31.4 bp/year before the charge. The selected model's four-lag t-statistic is {s['gross_t']:.2f}; these are descriptive results after selection.</p><p class="note">Scores are signed changes in the 10-year yield, not investment returns. The charge is 0.25 yield bp per position unit changed, including entry and exit. <a href="data/historical-weekly.csv">Every historical week (CSV)</a> · <a href="data/historical-summary.json">Full statistics (JSON)</a></p></section>
<section class="section" id="record"><div class="section-heading"><div><p class="eyebrow">PROSPECTIVE WEEKLY RECORD</p><h2>Track each call as it happens.</h2></div><p>{stats['issued']} forecasts issued · {stats['completed']} outcomes recorded</p></div><p>Issued forecasts keep their actual timestamps. Outcomes are appended when available; historical reconstructions are kept out of this record.</p>
<div class="stats"><div><strong>{live_total}</strong><span>Cumulative gross yield score · bp</span></div><div><strong>{live_hit}</strong><span>Hit rate · completed active calls</span></div><div><strong>{stats['active_completed']}</strong><span>Completed active calls</span></div></div>
<div class="table-wrap"><table><thead><tr><th>Reference Friday</th><th>Position</th><th>Outcome</th><th>Yield score, bp</th></tr></thead><tbody>{history_table}</tbody></table></div><p class="note">+1 favors adding duration; -1 favors reducing; 0 is no tactical view. Unavailable weeks are not zero-score forecasts. <a href="data/weekly-history.csv">Weekly record (CSV)</a> · <a href="data/history.json">JSON</a> · <a href="data/latest.json">Latest reading (JSON)</a></p></section>
<section class="section"><p class="eyebrow">QUICK ANSWERS</p><h2>Using the Treasury checklist</h2><div class="faq">{faqs}</div></section>
<aside class="paper-call"><div><p class="eyebrow">OPEN WORKING PAPER</p><h2>Read it. Check it. Reproduce it.</h2><p>{esc(meta['title'])}<br>Chirag Mirani · November 7, 2026 · Version 4</p></div><a class="button" href="paper/">Read the preprint &amp; get the code ↗</a></aside>
<details class="operations"><summary>Data refresh details</summary><p>Last model check: {checked}. Requested reference Friday: {preview['requested_reference_friday']}.</p><p>{esc(latest['refresh_note'] or 'The requested inputs passed the checks.')}</p><p>The button checks the most recently published data. It does not run a new model in your browser. The scheduled local refresh downloads inputs, validates them and publishes eligible weekly forecasts.</p></details></main>
<footer><p>Research by <a href="https://chiragmirani.github.io/">Chirag Mirani</a> · <a href="mailto:chiragmirani@gmail.com">Questions or comments?</a></p><p><a href="paper/">Preprint</a> · <a href="https://github.com/ChiragMirani/ChiragMirani.github.io/tree/main/treasury-signal">GitHub</a> · <a href="data/latest.json">Machine-readable data</a></p></footer>
<script src="tool.js" defer></script></body></html>'''
    (SITE/'index.html').write_text(html,encoding='utf-8')
    # The paper landing page exposes the complete author-written text and a direct PDF link.
    paper=(ROOT/'paper.html').read_text(encoding='utf-8');body=paper.split('<body>',1)[1].rsplit('</body>',1)[0]
    body=body.replace('<h2 class="appendix">Appendix A.','<h2 class="appendix" id="rules">Appendix A.')
    article={'@context':'https://schema.org','@type':'ScholarlyArticle','headline':meta['title'],'author':{'@type':'Person','name':meta['author'],'url':'https://chiragmirani.github.io/'},'datePublished':meta['date'],'version':'4','description':meta['abstract'],'url':BASE+'paper/','encoding':{'@type':'MediaObject','contentUrl':BASE+'paper/treasury-signal-preprint.pdf','encodingFormat':'application/pdf'},'keywords':meta['keywords']}
    ph=f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(meta['title'])} | Chirag Mirani</title><meta name="description" content="{esc(description)}"><meta name="author" content="Chirag Mirani"><link rel="canonical" href="{BASE}paper/"><meta name="citation_title" content="{esc(meta['title'])}"><meta name="citation_author" content="Mirani, Chirag"><meta name="citation_publication_date" content="2026/11/07"><meta name="citation_pdf_url" content="{BASE}paper/treasury-signal-preprint.pdf"><meta name="citation_abstract_html_url" content="{BASE}paper/"><meta name="keywords" content="{esc('; '.join(meta['keywords']))}"><meta property="og:type" content="article"><meta property="og:title" content="{esc(meta['title'])}"><meta property="og:url" content="{BASE}paper/"><meta property="og:description" content="{esc(description)}"><link rel="stylesheet" href="../style.css"><script type="application/ld+json">{json.dumps(article)}</script></head><body class="paper-page"><header><a class="brand" href="../">CHIRAG MIRANI <span>Treasury signal</span></a><nav><a href="treasury-signal-preprint.pdf">PDF</a><a href="treasury-signal-code.zip">Code &amp; results</a><a href="../">Signal tool ↗</a></nav></header><main class="paper-content"><p class="paper-downloads"><a href="treasury-signal-preprint.pdf">Download PDF</a> · <a href="treasury-signal-code.zip">Download reproducible code and results</a> · <a href="citation.bib">BibTeX citation</a></p>{body}</main><footer>Questions: <a href="mailto:chiragmirani@gmail.com">chiragmirani@gmail.com</a> · <a href="../">Weekly Treasury signal tool</a></footer></body></html>'''
    (SITE/'paper/index.html').write_text(ph,encoding='utf-8')
    shutil.copy2(ROOT/'A_Simple_Weekly_Signal_US_10Y_Treasury_Yield.pdf',SITE/'paper/treasury-signal-preprint.pdf')
    (SITE/'paper/citation.bib').write_text('@techreport{mirani2026treasurysignal,\n  author = {Mirani, Chirag},\n  title = {A Simple Weekly Signal for the U.S. 10-Year Treasury Yield},\n  year = {2026},\n  month = {November},\n  type = {Working paper, version 4},\n  url = {https://chiragmirani.github.io/treasury-signal/paper/}\n}\n',encoding='utf-8')
    (SITE/'sitemap.xml').write_text('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+''.join(f'<url><loc>{BASE}{path}</loc><lastmod>{now.date()}</lastmod></url>' for path in ('','paper/'))+'</urlset>',encoding='utf-8')
    (SITE/'README.md').write_text(f'# {meta["title"]}\n\nBy Chirag Mirani. Working paper, version 4, November 7, 2026.\n\n[Weekly signal tool]({BASE}) · [Preprint and PDF]({BASE}paper/) · [Code and result tables]({BASE}paper/treasury-signal-code.zip)\n\n{meta["abstract"]}\n\n## Data\n\n[Latest reading](data/latest.json), [prospective weekly record](data/weekly-history.csv), [historical results](data/historical-weekly.csv). Historical simulations and actual issued forecasts are separate. Reference and calculation dates accompany each reading.\n\nQuestions: chiragmirani@gmail.com.\n',encoding='utf-8')
    print(json.dumps({'site':str(SITE),'reading':date,'view':view,'kind':kind,'issued':stats['issued']}))


if __name__=='__main__':build()
