A Simple Weekly Signal for the U.S. 10-Year Treasury Yield
Chirag Mirani | Working paper version 4 | November 7, 2026

Signal tool: https://chiragmirani.github.io/treasury-signal/
Preprint and downloads: https://chiragmirani.github.io/treasury-signal/paper/
Questions and comments: chiragmirani@gmail.com

PURPOSE
Form the macro view and intended duration exposure first. Use the weekly
checklist to review whether to add, wait or build the position gradually.
Positions are fixed +1 (add-duration direction), -1 (reduce) or 0 (no tactical
view). A neutral signal does not tell an investor to close a macro position.
The checklist score and regression probability do not mechanically size risk.

SELECTED MODEL
Version weekly-14-quarterly-tips-2026-11-07-v4 adds a 30-year TIPS auction flag
to thirteen baseline readings. An eligible auction is after the reference
Friday and no later than the next Friday; its announcement must be strictly
before the reference Friday. The vote is +1 for an event and zero otherwise.
The same 0/1 flag enters the regression. C=0.1, expanding history, refit every
13 weeks. This is NOT a 13-week rolling training window.

The quarterly refit and TIPS addition were selected AFTER reviewing the later
historical results. The early-only quarterly auction winner remains nominal
30-year +1 in the archived study; it was not retroactively changed to TIPS.
Selected later result: 52.9% of 342 active calls, +32.6 yield bp/year gross,
+27.2 after the illustrative charge, t=1.67 (four lags). Always-higher-yields
scores +31.4 gross. These are retrospective yield scores, not portfolio returns.

model.py retains annual thirteen-rule defaults to reproduce earlier searches.
auction_inputs.selected_inputs supplies the adopted fourteen-input model.
spec.json binds the five production source files by SHA-256. Do not edit them
without a separately reviewed and recorded version. Prior versions are archived.

SETUP AND DATA
Use Python 3.11 or newer. Tested on Python 3.14 on Windows.
  python -m pip install -r requirements.txt
  python -m unittest discover -s tests -v
  python -m unittest auction_study.test_timing -v
  python download_data.py

Data come from public FRED/ALFRED sources and official Treasury announcements.
The initial archive download may take several minutes. Later runs reuse stored
vintages. Complete snapshots are checksummed and immutable. Failed downloads do
not replace data/latest_snapshot.json. Current market histories may be revised.
Raw market and macro histories are excluded from this release. The research
manifest identifies exact archived inputs by hash; a fresh download may differ.
Government auction calendar extracts and Fed dates are included. The production
auction downloader merges the official announced-securities feed with stored
history and exports only calendar and identity fields, never auction results.

REFRESH AND PUBLISH
  python refresh_public.py --download

Run on any day. It refreshes data, settles existing outcomes, calculates a
separately labelled preview and builds public_site/treasury-signal. The browser
button checks the latest published JSON; it does not run a new model remotely.
Publish only this public_site subdirectory through your authenticated GitHub
connection. Do not publish raw snapshots, fitted-model caches or private files.
The local scheduled job needs the computer and Codex app running and connected.

New issued forecasts are permitted Friday after 18:00 New York through Saturday,
starting with the November 13, 2026 reference. They require a snapshot completed
within 36 hours, valid source hashes, fresh market and archive observations and
an up-to-date auction calendar. Missing inputs withhold a new issue, including
on holidays. Withheld is position=null, not a valid zero-position forecast.

A Monday run can read the existing weekly forecast and update its record. It
does not backdate an issue or turn Friday-to-Friday results into Monday-to-Monday
results. Keep any new horizon as a separately specified and tested model.

Issued records in results/issued are exclusive-create. Coefficients are cached
under the model version and refit anchor. Outcomes in results/observed_outcomes
are recorded once separately. Public histories whitelist fields; private paths
and source observations are excluded. Preserve these local folders between runs.

REPRODUCTION
  python reproduce.py --data PATH_TO_ARCHIVED_DATA
  python reproduce.py --latest

The second command recalculates from a new snapshot and may not match the paper.
Reproduction runs the annual reference, original feature search, placebo checks,
input substitutions, both larger searches, the 2026 watchlist, economic-logic
checks, refit comparison, both auction rounds and the final selected summary.
It never overwrites spec.json. The research endpoint is October 30, 2026.
To verify the selected model against the saved quarterly auction trial:
  python selected_model_results.py
To update the dated paper illustration after a complete download:
  python paper_signal_preview.py
To rebuild the paper and page from saved outputs:
  python build_paper.py
  node make_pdf.js
  python build_public_page.py
The PDF renderer requires Playwright and Chromium. PAPER_CHROMIUM and
PAPER_PYTHON can select installed executables. Body text uses double leading.

RESULTS AND INTERPRETATION
results/selected_summary.json and selected_weekly.csv are the adopted model.
results/summary.json and two_key_weekly.csv retain the annual reference.
auction_study/quarterly contains all eight quarterly auction variants; the
parent auction_study folder is the annual experiment. Neither selection file
is rewritten to pretend the adopted variant won the early-only search.
improvement_study contains the refit comparison and all 3,870 broader trials.
watchlist_2027 contains the 54 retrospective direction trials, separate from
production. economic_review contains interpretation checks, not causal claims.

Scores equal minus the position times the weekly DGS10 yield change in basis
points. All calendar weeks enter t-statistics; inactive weeks score zero.
Hit rates use active weeks and count an unchanged yield as a non-win. Wilson
intervals assume independent weeks and do not adjust for selection. Costs are
an illustrative 0.25 yield bp per position-unit change including entry and exit.
No bond return, carry, financing or executable entry price is modelled.
The annual placebo fractions do not cover the later refit or auction choices.
