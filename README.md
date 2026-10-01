# Price Gap

Local web app for Souren Das, Bengaluru. It takes a product name, asks SerpApi's official Google Shopping API for Indian offers, and shows the cheapest in-stock price.

Built for the [SerpApi India Hackathon 2026](https://serpapi.github.io/serpapi-india-hackathon-2026/). Solo entry. Deadline on the official rules page: **10 October 2026, 23:59 IST**.

Public repo: https://github.com/Sourendas/price-gap. No API key is stored in the repo.

## What it does

One live lookup calls:

`GET https://serpapi.com/search.json`

with `engine=google_shopping`, `gl=in`, `hl=en`, `google_domain=google.co.in`, and `location` defaulting to `Bengaluru, Karnataka, India`.

From `shopping_results` it keeps the lowest **in-stock, new, INR** price per retailer. Out-of-stock, unpriced, non-INR, and refurbished/used listings are shown separately and do not win. A cheaper refurbished offer wins only if you tick “Include refurbished and used”.

The rupee gap is the difference between the cheapest in-stock retailer and the next one. Google returns about one page of offers (around 40). That is the comparison set, not every shop in India.

Each new successful search uses one credit. SerpApi does not bill cached, failed, or errored searches. This app does not set `no_cache`, so an identical repeat within the cache window is free. Do not upgrade the plan.

## Run it

Python 3.9+ from the standard library. No pip install, no paid plan, no card.

```bash
cd price-gap
python3 app.py
```

Open http://127.0.0.1:8765

Without `SERPAPI_KEY`, the page is in **sample data** mode. The banner says the prices are invented. Try `Sony WH-1000XM5`. Flipkart should win; Imagine is cheaper but out of stock, and Cashify is cheaper but refurbished.

```bash
python3 -m unittest tests.test_compare -v
```

## Use a free key (only step that needs you)

1. Create a free account: https://serpapi.com/users/sign_up?plan=free (GitHub or Google). The free plan is $0 and 250 searches per month. SerpApi's own posts say no credit card is required, and the free signup page only offers GitHub or Google.
2. Copy the private API key from the SerpApi dashboard. Do not paste it into chat, git, or this README.
3. Put the key in a local `.env` file (already gitignored) as `SERPAPI_KEY=...`, or export it. Then:

```bash
python3 app.py
```

The app loads `.env` from this folder. A variable already set in the environment wins. Restart after changing the key. The pill should say “Live key detected”. Leave “Sample data only” unticked for a real search. Tick it when you want the screen without spending a credit.

## Suggested track

**Commerce & Market Intelligence.** The official track text is: turn product, price, and merchant results into a tool for shoppers.

## Not submitted

The public repo is https://github.com/Sourendas/price-gap. Still undone: a public demo video under 3 minutes, GitHub sign-in on the hackathon dashboard, and pressing Submit project before 10 Oct 2026, 23:59 IST. A draft does not enter.

Dashboard: https://serpapi.github.io/serpapi-india-hackathon-2026/submit.html

Sign in with GitHub (`signin.html`, GitHub OAuth), then **New submission**.

Required before “Submit project” counts:

1. Lead name, email, mobile (10–15 digits), occupation (`student` or `working_professional`), years of experience (0 if none).
2. Project name: Price Gap.
3. Track: Commerce & Market Intelligence.
4. Public GitHub URL shaped exactly `https://github.com/owner/project` (two path parts, https).
5. Demo video under 3 minutes, https link (unlisted YouTube, shareable Drive, or similar) that opens in a private window with no access request. Show the app running locally.
6. Description and how it uses SerpApi. Paste from below if you want.
7. How you heard about it (required). BangPypers is the Bengaluru partner community; pick it only if that is actually how you heard.
8. Confirm the incognito-link checkbox, accept the Rules, accept the Terms.
9. Press **Submit project**, not only Save as draft.

Optional: AI tools field (do not leave this blank), up to four teammates (none for solo), “existed before the hackathon” (leave unchecked; this project is new), marketing opt-in.

Rules: https://serpapi.github.io/serpapi-india-hackathon-2026/rules.html

### Description you can paste

Price Gap helps a shopper in India see which retailer currently has the lowest in-stock price. You type a product name and a city (Bengaluru by default). The app reads Google Shopping offers for India and puts the cheapest new, in-stock rupee price on top, with the gap to the next retailer. Out-of-stock and refurbished listings stay visible but do not win unless you include used items.

### SerpApi usage you can paste

The live comparison is a call to SerpApi's Google Shopping API (`engine=google_shopping` on `https://serpapi.com/search.json`), scoped with `gl=in`, `hl=en`, `google_domain=google.co.in`, and a city location. `shopping_results` supplies retailer (`source`), price (`extracted_price` / `price`), stock wording, and `second_hand_condition`. Without that response the app cannot rank live Indian offers. Sample mode runs only when `SERPAPI_KEY` is unset, and the UI labels those prices as fake.

### AI tools you can paste

Grok (xAI), in Cursor, wrote this app, its tests, and this README. I reviewed the result before submitting.

## Files

- `app.py` — local server, SerpApi client, price comparison
- `static/` — the page
- `tests/test_compare.py` — winner rules and sample mode
- `.env.example` — placeholder only
