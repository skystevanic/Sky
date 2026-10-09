# Start here

This folder teaches Claude Code (or Codex) to research products for you. You send links to products you've seen brands advertising. For each one it checks six countries and tells you how saturated it is, then gives you a report (an interactive page you can click through, a PDF, or both) with a verdict per product: **Test now**, **Backlog** or **Avoid**.

## What it checks for every product

1. **Is the same object already in the shops?** It searches with the product's photo in Australia, the US, the UK, Canada, Germany and New Zealand. Red on the map means a big chain like Kmart or Walmart sells the same object. It then checks whether a shopper typing the product words into Amazon or Google would actually find each copy. Amber means a cheaper copy that shoppers will find or trust. Light green means copies exist, but they are hidden, have few reviews, sit on AliExpress, or cost about the same as the brand. Green means nobody else was found selling it.
2. **Who is advertising it on Facebook?** How many brands, how new they are, and whether one brand has kept its ads running for months (proof it works) or dozens have piled in this month (a swarm).
3. **Is demand rising?** Google searches over the last two years, plus how many units Amazon says were bought last month.
4. **What does a shopper see?** The real Google results page in each country, with every competitor clickable.

## What you need (about 10 minutes, once)

1. **Claude Code**, which is the Code tab in the Claude desktop app (paid Claude plan), or **Codex**.
2. **This folder**, unzipped anywhere you like, for example your Documents folder.
3. **Python 3.9 or newer** (Macs have it; Windows: python.org, tick "Add to PATH") and **Google Chrome**.
4. **A SerpApi account** (required). It runs the Google, Amazon and photo searches from each country. Free plan: 250 searches a month, no card. One product uses about 30.
5. **An Apify account** (required). It reads Facebook's public ad library for you, so nothing is ever read from your own computer. Pay-as-you-go: about US$0.30 to US$1.10 a product, with a small free monthly credit for new accounts.

You don't need to work out the setup yourself. The tool walks you through getting both codes, one step at a time.

## How to start

Open this folder in Claude Code (Code tab → choose folder) or Codex, then paste the message from `HANDOFF-PROMPT.md` as your first message. It will explain what it does, check your setup, help you save the two codes safely, build a sample report so you can see it works, then ask for your links.

**Never paste your SerpApi or Apify code into the chat.** The tool tells you where to save them instead.

## What to send it

- Links to brand product pages: the product you saw in an ad. That's the main input.
- Or a brand name, or a category such as "kitchen gadgets".
- Not AliExpress, Temu or Amazon links. Send the brand's own page.
- Tell it your home country.

It takes about 10 to 15 minutes a product. Say "stop" at any time.
