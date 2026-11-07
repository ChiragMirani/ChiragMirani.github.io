# A Simple Weekly Signal for the U.S. 10-Year Treasury Yield

By Chirag Mirani. Working paper, version 4, November 7, 2026.

[Weekly signal tool](https://chiragmirani.github.io/treasury-signal/) · [Preprint and PDF](https://chiragmirani.github.io/treasury-signal/paper/) · [Code and result tables](https://chiragmirani.github.io/treasury-signal/paper/treasury-signal-code.zip)

A macro view tells a bond investor why to add or reduce duration. It still leaves a timing decision. I present a simple weekly signal for the U.S. 10-year Treasury yield to help review that decision. Fourteen market, economic and calendar readings form an equal-vote checklist. A logistic regression, refitted every 13 weeks, provides a second view; the combined signal takes a direction when the two do not conflict. Across November 2016-October 2026, the selected model gets 52.9% of 342 active calls right and scores +32.6 yield basis points per year, or +27.2 after an illustrative charge. The refit frequency and 30-year TIPS auction addition were chosen after reviewing the historical results; the paper reports the searches and benchmarks alongside the selected model. A practical example shows how an investor with a bullish macro view can use the readings to add duration, wait or build gradually. The public tool supplies the dated checklist and an accumulating record of weekly outcomes. Scores measure yield direction, not portfolio returns; allocation size remains a portfolio decision.

## Data

[Latest reading](data/latest.json), [prospective weekly record](data/weekly-history.csv), [historical results](data/historical-weekly.csv). Historical simulations and actual issued forecasts are separate. Reference and calculation dates accompany each reading.

Questions: chiragmirani@gmail.com.
