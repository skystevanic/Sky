# judgement.json — the one file you write by hand

Everything measured (shops, Amazon, advertisers, demand, photos, screenshots) is copied into the report for you by `scripts/assemble_report.py`. You only write your judgement. A full worked example is in `examples/sample-run/judgement.json`.

## Top of the file

| Field | What to put |
|---|---|
| `run.title` | "Product Research" |
| `run.date` | today, like 2026-09-21 |
| `run.prepared_for` | the member's name |
| `run.countries` | the countries you searched, like ["au","us","uk"] |
| `run.assumptions` | 2 to 4 short plain lines the member should keep in mind (costs are estimates, and so on). Never tools, costs of the run, or how the report was made |
| `headline` | the one sentence a beginner reads first, about the top product |

## For each product (`products` is a list)

| Field | Required | What to put |
|---|---|---|
| `slug` | yes | the same nickname you used in every script |
| `name` | yes | a plain name a shopper would recognise, brand in brackets if useful |
| `brand`, `url`, `category`, `price` | yes | price WITH its currency, like "US$70" |
| `one_liner` | yes | one or two plain sentences: the verdict in words |
| `verdict` | yes | exactly "Test now", "Backlog" or "Avoid" |
| `overall` | yes | 0 to 100, from `reference/scoring.md` |
| `confidence` | yes | "High", "Medium" or "Low" |
| `scores` | yes | `saturated`, `margin`, `viral`, `pain`, `differentiation`, each 1 to 10 |
| `why` | yes | exactly 3 short reasons |
| `risk` | yes | one sentence |
| `next` | yes | 1 or 2 things to do next |
| `best_region` | yes | one sentence, or "None." |
| `gates` | yes | a list of `{name, result, why}`. Names: "Chain gate", "Copies gate", "Swarm gate", "Bulk gate", "Regulated gate". Result: "pass", "flag" or "fail" |
| `snapshot` | yes | `icp` (who buys it), `job`, `cogs` (landed cost, say "estimate"), `margin`, `claims`, `demoable` |
| `angles` | yes | 5 selling angles the brand is not using. Mark any a competitor already runs as "TAKEN: ..." |
| `compare` | yes | `brand_photo` (file name in `<run>/<slug>/`, like "img_2.jpg"), `match_number` (the number on the photo sheet of the closest same object), `match_name` ("Kmart Australia, A$63"), `verdict` ("identical", "functional" or "different"), `confidence`, `note` (one plain sentence) |
| `advertiser_takeaway` | yes | two or three plain sentences on what the advertiser numbers mean for this member |
| `ad_days`, `store_platform`, `store_launched`, `store_products` | optional | from the store read and the advertiser table |
| `country_takeaways` | optional | `{"au": "one sentence", ...}` for the "what a shopper sees" pages. Left out, a plain sentence is written for you |
| `category_notes` | optional | `{"au": "one sentence"}` to correct a misleading line in the category table (for example when the 'chain' match was a different product) |
| `tile_notes` | optional, use rarely | overrides one of the four tiles when the raw number would mislead. Keys: "Demand", "Same", "Amazon", "Advertisers". Each takes `head`, `detail` and `colour` ("green", "light green", "amber" or "red"). The colour must match the measured result: only set it if you can say why the measured one is wrong |

## Rules

- Write for the member. No tool names, no run costs, no "we checked", no notes about mistakes fixed along the way.
- Every number you quote must come from a script's output. If you don't have it, say "not checked".
- The verdict must agree with the map and the tiles. If demand is rising but the verdict is Avoid, say why in `one_liner`.


## Keep it short enough to fit one page

Each product gets ONE verdict page. The builder shrinks the page a little when you write a lot, but past a point it spills onto a second page. Aim for:

- `one_liner`: two sentences, under 250 characters. Do not start it with the verdict word ("Avoid."): the page already shows the verdict.
- `why`: exactly 3 bullets, each under 140 characters.
- `risk`: one sentence, under 150 characters.
- `next`: 1 or 2 bullets, each under 140 characters.
- `best_region`: one or two sentences.
- `name`: under 45 characters. "Heated Head and Eye Massager", not the store's full product title.


## The "Cost to buy" box

You do not write this. It comes from `supplier_check.py` (supplier listings found by the picture search, plus any price the member read for you). If a price was recorded, the report shows the supplier price, the margin at the brand's price and what is left per sale. If not, it shows how many supplier listings were found and tells the member to open one. Use the numbers in your `why` and `risk` lines when they matter ("AliExpress has it at about US$35, so only half the brand's price is left for ads").
