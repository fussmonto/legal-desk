# Legal Desk · Kolkata

A zero-cost daily job finder for legal roles in Kolkata. GitHub Actions fetches jobs every day at 12:00 PM IST, saves them to `docs/jobs.json`, and GitHub Pages shows them as a webpage. No email.

Targets: bank / NBFC legal, real estate developer in-house legal, law firms & consultancies, and corporate legal / compliance, at Executive to Senior Executive level.

## Setup (about 10 minutes)

1. **Create the repo** `legal-desk` under your GitHub account (public, empty). Upload all files from this folder, keeping the folder structure (including the hidden `.github` folder).
2. **Add secrets**: Settings → Secrets and variables → Actions → New repository secret.
   | Secret | Needed? | Where to get it |
   |---|---|---|
   | `ADZUNA_APP_ID` | Yes | Same as site-desk |
   | `ADZUNA_APP_KEY` | Yes | Same as site-desk |
   | `JOOBLE_API_KEY` | Optional | jooble.org/api/about (free) |
   | `JSEARCH_API_KEY` | Optional | OpenWeb Ninja JSearch (adds Google Jobs / LinkedIn / Naukri-type listings) |
3. **Turn on the page**: Settings → Pages → Source: *Deploy from a branch* → Branch `main`, folder `/docs` → Save.
4. **First run**: Actions tab → *Update legal jobs* → *Run workflow*. After about a minute the site is live at `https://<your-username>.github.io/legal-desk/`.

## Tuning

Edit `scraper/config.json`:
- `queries`: search phrases sent to each source
- `exclude_title_words`: titles to skip (intern, fresher, head, partner…)
- `skill_keywords`: drive the match % shown on each card
- `max_age_days`: how old a posting can be

Privacy: the CV is not stored in the repo. Only generic skill keywords are used, so no phone, address or date of birth is published.
