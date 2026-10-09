---
name: product-research
description: Tell a member whether a product they saw advertised is worth testing, using real data instead of guesses. From brand (D2C) product links it checks six countries (Australia, US, UK, Canada, Germany, New Zealand): whether the SAME object is already in a big chain or easy to find cheaper (searched by the product's photo, then by what a shopper finds typing the product words into Amazon and Google), who is advertising it on Facebook and how established they are, whether demand is rising, and what a supplier such as AliExpress charges for it. Delivers a verdict per product (Test now, Backlog or Avoid) with a red/amber/light green/green country map, as an interactive page, a PDF, or both. Walks beginners through setup. Use when a member says "/product-research", "score this product", "is this a winner", "research these links", pastes product links, or asks how to set this up.
---

# Product Research — run book (v2, 2026-09-21)

Home: `.claude/skills/product-research/`. Scripts in `scripts/`, chain lists in `reference/chains.json`, scoring in `reference/scoring.md`, beginner setup in `START-HERE.md` and `README-for-members.md`, a finished sample in `examples/sample-run/`.

**Who you're talking to:** a founder who may have never used Claude Code or Codex before. Plain English. One step at a time. Every technical word translated in the same sentence ("your SerpApi code — the password the tool uses to talk to SerpApi"). Never ask them to paste that code into the chat. Lead with the answer.

## Part A — the first message of every first session (beginner mode)

Trigger this when: the setup check fails, they say "how do I start", they paste the handoff prompt, or they seem unsure. Go ONE step at a time. Confirm each step worked before the next. Never dump the whole list.

**Step 1. Open with this, in your own plain words, before running anything:**
- *What it does:* "You send me links to products you've seen brands advertising. For each one I check six countries and tell you how saturated it is: is the same object already in a big shop or on Amazon, how many brands are advertising it on Facebook and whether they're piling in, and whether demand is rising. You get a PDF with a verdict per product (Test now / Backlog / Avoid) and a red, amber and green world map."
- *What it needs:* "Two outside services do the looking-up, and you need an account with both. Setting them up takes about ten minutes, once."
  1. **SerpApi** runs Google, Google Shopping, Amazon and photo searches as if from each country. Free plan: 250 searches a month, no card. One product uses about 30.
  2. **Apify** reads Facebook's public ad library for us. We never read Facebook from your own computer: that breaks Facebook's rules and could get your connection blocked. It is pay-as-you-go, about US$0.30 to US$1.10 a product, and new accounts get a small free monthly credit.
- *What else:* Python 3.9+ and Google Chrome on their computer (Chrome is only used to save the PDF). The setup check also mentions Pillow, a picture helper: if it's missing, run `python3 -m pip install pillow`, because the numbered photo sheet in step 7 needs it.
- Then say: "I'll check what you already have." and go to step 2.

**Step 2. Run the setup check** — `python3 scripts/check_setup.py` from the skill folder. Read each line back in plain words. If Python is missing: python.org, and on Windows tick "Add to PATH". Stop until they say it's installed.

**Step 3. SerpApi code** (skip if the check says it works):
1. They go to **serpapi.com**, click Register, and sign up themselves (free plan, no card).
2. They open **serpapi.com/manage-api-key** and press the copy button beside "Your Private API Key". Explain: this code is the password the tool uses to talk to SerpApi. **They must never paste it into this chat.**
3. Save it. Mac: give them exactly `security add-generic-password -U -a "$USER" -s serpapi-api-key -w` to run in the Terminal panel; paste at both prompts; nothing shows while pasting, that's normal. If that fails twice, use the clipboard route: they copy the code, say "it's in my clipboard", and you run `v="$(pbpaste | tr -d '[:space:]')"; security add-generic-password -U -a "$USER" -s serpapi-api-key -w "$v"` so you never see it. Windows: create the file `config.json` inside a folder named `.product-research` in their home folder, containing `{"serpapi_key": "PASTE-HERE", "apify_token": "PASTE-HERE"}`; give the exact clicks (Notepad → Save as → All files).
4. Re-run the check. Don't move on until it says "SerpApi works".

**Step 4. Apify code** (skip if the check says it works):
1. They go to **apify.com**, click "Get started free", and sign up themselves.
2. In the Apify console they open **Settings → API & Integrations** and copy the "Personal API token". Same rule: never into the chat.
3. Save it. Mac: `security add-generic-password -U -a "$USER" -s apify-api-token -w` (or the clipboard route with `-s apify-api-token`). Windows: the `apify_token` line in the same `config.json`.
4. Re-run the check. Don't move on until it says "Apify works". Reassure them on cost: the tool stops every run itself, and prints what each run cost.

**Step 5. Show them what they'll get.** Open `examples/sample-run/report-full.pdf`, which is a finished report for one product. To prove their computer can build one, run `python3 scripts/build_report.py examples/sample-run/report.json --full` from the skill folder (about 20 seconds). If they see the sample with its map and photos, everything works. Say so.

**Step 6. Ask for their product links and their home country.** Then Part B. Tell them roughly how long it takes: about 10 to 15 minutes a product, and they can say "stop" between products.

Both services are REQUIRED. If a member refuses one, explain what they lose (no SerpApi = no report at all; no Apify = no advertiser page, which is the saturation check) and let them decide; never invent the missing numbers.

On **Codex** instead of Claude Code: the folder's `AGENTS.md` points here; the steps are identical.

## Part B — one run

**Before you start.** Work from the skill folder: the folder that holds this file. It is either `.claude/skills/product-research` inside a project, or the unzipped `product-research` folder the member opened directly (the simple way, and just as good). Keep each run in a real folder: `<project>/product-research-runs/2026-09-21/`, or `runs/2026-09-21/` inside this folder when the member opened it directly. In the commands below `<run>` means the full path to that folder. Never use a temp folder: it gets wiped and the searches are paid for twice.

**Words used below.**
- **slug** = a short nickname you invent for each product, lowercase with no spaces, such as `pilates-board`. Every script uses it to name its files. Keep it the same for every step of that product.
- **the product words** = 2 to 4 plain words a shopper would type, NOT the brand's name for it. The brand says "Pilates Reformer Set"; shoppers say "pilates board". To choose them: read the store's title and description, look at what the Amazon listings in step 5 call it, and tell the member which words you picked and why. If a search comes back empty or off-topic, the words are wrong: try simpler ones. Long phrases return nothing.
- **the ad words** = the same idea for the advertiser step, which matches the EXACT phrase. Use the two or three words ads for this kind of product would actually say. If unsure, run the advertiser step first with `--cap 30` under a different slug (`--slug <slug>-try`) to see whether the phrase finds the right kind of ad, then run it properly under the real slug. If the brand invented its own product name ("anti-smoke gun"), that name only finds the brand itself: use the plain words other sellers use. If a phrase is very broad ("head massager" also finds horse massagers), say so in your takeaway: the count then describes the phrase, not the product.

**Tell the member the cost and time first:** "This will use about 30 searches and about 60 cents, and take roughly 12 minutes a product."

1. **Take the input.** Members send links to brand product pages. Also accepted: a brand name or store address (read its feed, pick the best seller, confirm with them), or a category plus country. If someone pastes an AliExpress, Temu or Amazon link, ask for the brand's own page or the product's plain name instead. Confirm the countries (default all six: `au,us,uk,ca,de,nz`) and their home market. Use the SAME `--countries` list in every step.
2. **Check the setup** — `python3 scripts/check_setup.py`. It must end with "READY". If not, go back to Part A.
3. **Read the store** — (If the member sent a store's home page, run this once on the home page to list its products, pick the one the home page is built around, tell the member which one and why, then run it again on that product's own link.) `python3 scripts/store_fetch.py <product link> --out <run>/<slug>`. Gives the title, price and its currency, launch date, catalogue size, and saves up to 6 photos as `<run>/<slug>/img_1.jpg` and so on. LOOK at the photos and note which one shows the product alone on a plain background: you need it in step 7. If every photo is a lifestyle shot with people or text, pick the one where the product is largest.
4. **Demand** — `python3 scripts/trends_check.py --slug <slug> --keyword "<the product words>" --out <run>/trends` (1 search, worldwide, last 2 years). Says rising, steady, falling, or too thin to measure. Single countries are usually too thin, so worldwide is the default.
5. **Category and Amazon** — run both, one after the other:
   `python3 scripts/shopping_grid.py --slug <slug> --query "<the product words>" --countries <list> --brand-price <number> --out <run>/grid`
   `python3 scripts/amazon_check.py --slug <slug> --query "<the product words>" --brand "<brand name>" --countries <list> --out <run>/amazon`
   `--brand-price` is the store's price as a plain number in the store's own currency. It is only a rough guide for the category table, so don't convert it. These two show how crowded the CATEGORY is and what Amazon's top listings sell ("bought in past month" is real demand proof). They do not colour the map.
6. **Who is advertising it** — `python3 scripts/meta_ads_apify.py --slug <slug> --phrase "<the ad words>" --cap 250 --out <run>/meta`. It reads Facebook's public ad library through Apify, stops itself at the cap, and prints the cost. It counts BRANDS by their shop, so several Facebook pages selling for one shop count once. It names the pattern: **one brand owns it** (proof without a crowd: the best pattern), **hardly anyone**, **a handful**, **crowded**, or **a swarm, right now** (10+ brands, 70% of them new in two months). If it says "stopped at N ads (there are more)", every number is a minimum: say "at least".
   Then LOOK at the top five advertisers: open what they sell from the shop column and the ad line. Drop your assumptions if they sell something different from the member's product, and say so in your takeaway.
   NEVER read Facebook's ad library from the member's own browser or computer with automation. It breaks Facebook's rules and risks a block on their connection.
7. **Where is the SAME OBJECT sold? (this colours the map)** — two steps, because you must LOOK:
   `python3 scripts/lens_check.py collect --slug <slug> --image-url "<web address of the cleanest product photo>" --brand-domain <brand's web address> --countries <list> --out <run>/lens`
   The photo's web address is in `<run>/<slug>/store.json` under `saved_images` → `src`. This builds numbered contact sheets: `<run>/lens/<slug>_sheet.jpg`, plus `_sheet_2.jpg`, `_sheet_3.jpg` when there are many listings. LOOK AT EVERY SHEET. Listings marked "no price" count just as much as priced ones: Walmart.com and Amazon.com often show no price in a picture search, and skipping them once turned a country green when the identical product was on sale there. If a picture is too small to be sure, open that listing's own file, `<slug>_thumb_NN.jpg`. Each listing's own picture is `<slug>_thumb_NN.jpg` (two digits) for the picture search and `<slug>_vis_thumb_NNN.jpg` (three digits) for the shopper sheets. "Same object" means the same design a shopper could not tell apart: an older model of the same gadget, a different colour or a gold trim all count as the same; a product that does the same job in a clearly different shape does not (say so in your category notes). Open it with your image viewer beside the brand's photo and decide which numbers are the same object: same shape and mechanism. Colour, logo and packaging do not make it different. Ignore articles, forums and anything that isn't for sale.
   `python3 scripts/lens_check.py decide --slug <slug> --same 0,3,4 --countries <list> --brand-price <number> --brand-currency <usd|aud|cad|gbp|eur|nzd> --out <run>/lens`
   Always give the brand's price and its currency (step 3 printed both). Without them the script can't tell a weak copy from a real one, and every Amazon or eBay copy counts as amber.
   Result per country: **red** = the same object is in a big chain there, with a price. **Amber** = real copies: on Temu or Shein, in a local shop, or on Amazon or eBay clearly cheaper than the brand (under 70% of its price). **Light green** = only weak copies: on a far-away marketplace like AliExpress (slow delivery), or on Amazon or eBay at about the brand's price. **Green** = nobody but the brand was found. Only countries you searched get a colour. **Never trust a green or light green without checking it.** When `decide` prints "CHECK BEFORE YOU TRUST THIS", open every listing number it names at full size. If any is the same object, add its number to `--same` and run `decide` again. Green should be rare: most products that are advertised hard are already on Amazon. If the sheet is mostly junk, the photo was a poor one: go back to step 3, pick a cleaner photo and run collect again with a new slug.
   **Then check whether a shopper can FIND those copies (costs nothing extra to collect):**
   `python3 scripts/visibility_check.py collect --slug <slug> --run <run> --countries <list>`
   This builds sheets of the top 12 results a shopper gets when they type the product words into Amazon and Google Shopping in each country (from the searches step 5 already paid for): `<run>/visible/<slug>_vis_sheet.jpg`, `_2`, `_3`. LOOK at every sheet beside the brand's photo and note the numbers that are the same object.
   `python3 scripts/visibility_check.py decide --slug <slug> --run <run> --same 3,17` (use `--same ""` if none match)
   It then looks up the top hidden Amazon copy in each country for its real price, reviews and sales badge (1 search a country, 6 at most), and re-colours the map. After this the colours mean: **amber** = a cheaper copy that shoppers will find (top 12 for the product words) or trust (100+ reviews or a "bought in past month" badge), or one on Temu or Shein. **Light green** = copies exist but are hidden (found only by photo, few reviews), far away, or about the brand's price. This step is what stops every advertised product coming out amber. It must run AFTER `lens_check.py decide`; it re-runs that colouring for you.
   One caution: the picture search cannot tell a chain from a seller on that chain's marketplace ("The Warehouse" and "The Warehouse - Marketplace" look the same to it). If a red rests on one chain listing, check the category table from step 5: if the same item appears there as "<chain> - Marketplace" or "<chain> - <seller>", say in your notes that the red may be a marketplace seller.
   **Then the supply side: what does it cost to buy? (costs nothing)**
   `python3 scripts/supplier_check.py list --slug <slug> --run <run> --brand-price <number> --brand-currency <usd|aud|cad|gbp|eur|nzd> --words "<the product words>"`
   This lists the supplier listings (AliExpress, Alibaba, DHgate and the like) that the picture search found for the SAME object, and prints a ready-made AliExpress search link. Supplier sites are where the member would BUY the product, so they no longer count as competing copies on the map. They do not show prices to search engines and they block automatic readers, so **do not try to read them with a browser tool** (it throws permission pop-ups at the member and breaks). Instead give the member the one or two AliExpress links and ask: "Open this, pick the same version, and tell me the price and the shipping to your country." Record what they say:
   `python3 scripts/supplier_check.py price --slug <slug> --run <run> --n 1 --price 8.40 --currency usd --shipping 3.10`
   If the list is empty, ask the member to use the AliExpress search link, find the same object by its picture, and paste the listing's address and price; record it with `supplier_check.py add ...` (see the top of the script). If they would rather skip this, carry on: the report then says "open a listing to read today's price". The report turns the price into the two numbers a beginner needs: the margin at the brand's price, and how much is left per sale to pay for ads.
8. **What a shopper sees** — `python3 scripts/google_asis.py --slug <slug> --query "<the product words>" --countries <list> --out <run>/asis`. About 20 seconds a country. Saves a picture of the real Google results page plus the top results, the product strip and the questions people ask. English product words can return off-topic pages in Germany, or medical articles for body-part words: if a country's page is off-topic, say so in a category note and rely on the product strip.
9. **Score and decide** using `reference/scoring.md`. The picture check verdict comes from step 7: **identical** (you found the same object), **functional** (closest match lacks a real feature), or **different**. Every product gets scores and a verdict, including ones that fail a gate.
10. **Write your judgement, then assemble** — write ONE file, `<run>/judgement.json`, holding only your own calls: verdict, scores, the one-line summary, why, risk, next step, gates, angles, the picture verdict and your advertiser takeaway. `reference/report-fields.md` explains every field and `examples/sample-run/judgement.json` is a worked example. Then:
    `python3 scripts/assemble_report.py <run>` copies everything else from the script files into `<run>/report.json` and tells you if a part is missing.
    `python3 scripts/build_report.py <run>/report.json --full` makes `report-full.pdf` (about 20 seconds). Run it again without `--full` for the short version, `report.pdf`.
    **Ask the member how they want it: "Do you want an interactive page you can click through here, a PDF to keep or share, or both?"** If they don't mind, make both.
    - **Interactive page:** `python3 scripts/build_report.py <run>/report.json --web` makes `report-web.html`. It is one page: the ranking at the top, then one fold-out section per product, with fold-outs inside for who advertises it, where the same object is sold, the evidence, what a shopper sees in each country, and the scorecard. Every competitor is clickable. If your app can show a file beside the chat (the Claude desktop app's side panel does), show `report-web.html` there. Otherwise open it in the member's browser.
    - **PDF:** the `--full` command above, plus the short version. Best for keeping, printing or sending to someone.
11. **Look before the member does.** The build prints a link check. It must say "all N links lead somewhere". If it says LINK CHECK FAILED, fix every line it lists and build again before anyone sees the report. If `pdftoppm` exists, `pdftoppm -png -r 50 -f 1 -l 4 <run>/report-full.pdf <run>/check` and view the pictures. If it doesn't (most computers), open `<run>/report-full.html` and read it through, then ask the member to skim the PDF with you. Check: the verdict matches the map and the tiles, no page contradicts another, nothing reads like a note to yourself. Then open the PDF for them.
12. **Rank** best to worst and name your top pick in one sentence. "None of these" is a valid and often honest answer.

Run steps 5 to 8 one product at a time, and run anything over a minute in the background so "stop" lands straight away.

## Hard rules

- Never ask for, print, or store the SerpApi or Apify code in chat. If one is missing → Part A.
- THE REPORT IS FOR THE MEMBER. No notes about how it was made: never mention SerpApi, Apify, searches used, costs, 'we marked', 'checked by eye', or mistakes fixed along the way. Put those in the chat, not the PDF.
- In the advertiser table the brand name is plain text; the link to their Facebook ads sits in its own column labelled "See their ads".
- Don't hallucinate. Unknown → **Assumption**, and keep going. Ad longevity: put the Meta Ad Library link in the report and ask the member to paste the oldest "started running" date.
- Jobs over a minute run one product at a time, in the background. "Stop" means stop.
- Keep each run in a real folder inside the member's project (for example `product-research-runs/2026-09-20/`), never in a temp folder. Temp folders get wiped and the searches are paid for twice.
- `reference/chains.json` decides red vs green. A seller that looks like a big retailer but isn't listed: flag it by eye and add it.
- Third-party sellers on a chain's marketplace ("Walmart - Seller", "The Warehouse - Marketplace") are NOT the chain. The script handles this; don't override it.
- Small markets (NZ) are thin on Google Shopping. Say "less reliable", don't pretend.
- The picture check is the one check no spy tool does. Don't skip it because the words matched.

## What the map colours mean

The map comes from the PICTURE search (step 7), so it is about this exact object, not the category:
- **Red** — the same object is sold by a big chain in that country.
- **Amber** — a REAL copy: clearly cheaper than the brand (under 70% of its price, or no price showing) AND either easy to find (top 12 when a shopper types the product words into Amazon or Google Shopping there), trusted (an Amazon listing with 100+ reviews or a 100+ "bought in past month" badge), or on Temu or Shein.
- **Light green** — copies exist, but none a shopper is likely to find or trust: found only by photo, few reviews, a far-away marketplace like AliExpress, or about the brand's price. A light green country is a fair place to test. The report prints a price ladder per country (brand, cheapest copy, typical copy): use it to judge margin and to set a price. When the brand itself has kept ads running 3+ months far above the copies' price, the report says so: that is proof shoppers pay the gap.
- **Green** — the picture search found nobody but the brand selling it there. Say "none found", not "none exists".
- The category and Amazon checks (step 5) still run. They feed the Amazon tile, the seller tables and the scorecard, not the map.
- Advertisers are worldwide (step 6); Facebook's library can't be split reliably by country for ordinary ads.

## Status rules (used by `shopping_grid.py`)

- **blocked (red)** — a big chain sells a listing at or under the brand's price. Amazon alone doesn't count.
- **crowded (amber)** — no chain, but 20+ sellers, or the cheapest is under a third of the typical price, or only marketplaces carry it.
- **open (green)** — none of the above. Rare. Say why.

## Cost

Two services, both required: **SerpApi** (free plan is enough to start) and **Apify** (pay-as-you-go, cents per product).

