# Product Research skill — setup (15 minutes, once)

Short version: read `START-HERE.md`, then paste `HANDOFF-PROMPT.md` into Claude Code or Codex and let it guide you. This page is the detail if you want it.

## 1. What you need

- A paid Claude plan (Pro or Max) with **Claude Code** — it's the "Code" tab in the Claude desktop app, no terminal needed. **Codex** works too.
- This folder, `product-research`, unzipped anywhere (your Documents folder is fine). Open it in Claude Code or Codex and paste the message from `HANDOFF-PROMPT.md`. If you already keep skills in a project, you can instead copy it to `.claude/skills/` there and type `/product-research`.
- Python 3.9 or newer (Macs have it; Windows: install from python.org and tick "Add to PATH").
- **Google Chrome** installed (used only to save the report as a PDF).

## 2. Run the setup check

In Claude Code type `/product-research check my setup` (Codex: "run scripts/check_setup.py and explain it"). It says in plain words what works and what's missing.

## 3. SerpApi (required)

SerpApi runs Google, Google Shopping, Amazon and photo searches as if from each country, and hands back clean results. Google blocks robots, so this is the only reliable way to see what a shopper in another country sees.

1. Go to **serpapi.com**, click Register and sign up. The free plan gives 250 searches a month with no card. One product across six countries uses about 30.
2. Open **serpapi.com/manage-api-key** and press the copy button beside "Your Private API Key". This code is the password the tool uses to talk to SerpApi. **Never paste it into the chat.**
3. Save it:
   - **Mac:** in the Terminal panel run `security add-generic-password -U -a "$USER" -s serpapi-api-key -w` and paste the code at both prompts. Nothing shows while you paste. That's normal. If it fights you, copy the code and tell Claude "it's in my clipboard".
   - **Windows:** make a folder named `.product-research` in your home folder. Inside it make a file named `config.json` containing `{"serpapi_key": "PASTE-HERE", "apify_token": "PASTE-HERE"}`.
4. Run the setup check again. It should say "SerpApi works". If you go past 250 searches a month, the US$25 plan gives 1,000.

## 4. Apify (required)

Apify reads Facebook's public ad library for you: how many brands advertise the product, since when, and links to each brand's ads. Reading Facebook from your own computer with a robot breaks Facebook's rules and can get your connection blocked, so Apify's computers do it instead.

1. Go to **apify.com**, click "Get started free" and sign up.
2. In the Apify console open **Settings → API & Integrations** and copy your "Personal API token". Same rule: **never paste it into the chat.**
3. Save it:
   - **Mac:** `security add-generic-password -U -a "$USER" -s apify-api-token -w`, paste at both prompts.
   - **Windows:** put it in the `apify_token` line of the same `config.json`.
4. Run the setup check again. It should say "Apify works".

Cost: about half a US cent per ad read, so US$0.30 to US$1.10 a product. New accounts get a small free monthly credit. The tool stops every run itself and tells you what it cost.

## 5. Prove it works

`python3 scripts/build_report.py examples/sample-run/report.json` builds the sample PDF. Open it. If you see the map and the pictures, you're set.

## 6. Running it

```
/product-research
Home country: Australia
https://brand.com/products/thing-one
https://otherbrand.com/products/thing-two
```

It accepts brand product pages (the main input), a brand name, or a category plus country. Not AliExpress, Temu or Amazon links: those sites block robots, so send the brand's own page. It runs one product at a time (say "stop" to halt) and ends with `report.pdf`.

## 7. What it can and can't see

- Sees: where the SAME OBJECT is sold in each country (found by searching with the product's photo); who is advertising it on Facebook and since when (via Apify); any Shopify store's product feed (launch date, prices, catalogue growth); Google Shopping and plain Google from each country (sellers, chains, prices, the real page); Amazon's own search in each country (review counts, prices, units bought last month); product pictures for the visual check.
- Can't see without more tools: Temu and AliExpress listing pages, individual Amazon product pages (it reads Amazon's search results, not each listing), and the Meta Ad Library (the report gives you the link; paste the oldest "started running" date yourself). These stay marked as assumptions.

## 8. Editing the chain lists

`reference/chains.json` lists the big retailers per country. If a chain shows up in a report that isn't on the list, add it. That list decides red versus green.
