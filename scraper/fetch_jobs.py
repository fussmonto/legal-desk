#!/usr/bin/env python3
"""Legal Desk: collect legal jobs in Kolkata from several sources into docs/jobs.json.

Sources (each is optional; the script skips any whose key is not set):
  - Adzuna       ADZUNA_APP_ID, ADZUNA_APP_KEY      (required in practice)
  - Jooble       JOOBLE_API_KEY
  - JSearch      JSEARCH_API_KEY  (OpenWeb Ninja; covers Google Jobs, LinkedIn, Naukri-type listings)

No personal data is used or published; matching uses only the keyword list in config.json.
"""
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
CONFIG = json.loads((Path(__file__).parent / "config.json").read_text(encoding="utf-8"))
OUT = ROOT / "docs" / "jobs.json"
UA = {"User-Agent": "legal-desk/1.0 (personal job digest)"}
NOW = datetime.now(timezone.utc)


def clean(text):
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", text).strip()


def make_id(title, company, location):
    raw = f"{title}|{company}|{location}".lower()
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


def parse_date(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def get(url, **kw):
    for attempt in range(3):
        try:
            r = requests.get(url, headers=UA, timeout=30, **kw)
            if r.status_code == 429:
                time.sleep(5 * (attempt + 1))
                continue
            r.raise_for_status()
            return r
        except Exception as e:
            print(f"  ! GET failed ({e.__class__.__name__}): {url[:80]}", file=sys.stderr)
            time.sleep(2)
    return None


def from_adzuna():
    app_id, app_key = os.getenv("ADZUNA_APP_ID"), os.getenv("ADZUNA_APP_KEY")
    if not (app_id and app_key):
        print("Adzuna: keys not set, skipped")
        return []
    jobs = []
    for q in CONFIG["queries"]:
        for page in (1, 2):
            r = get(
                f"https://api.adzuna.com/v1/api/jobs/in/search/{page}",
                params={
                    "app_id": app_id, "app_key": app_key, "results_per_page": 50,
                    "what": q, "where": CONFIG["city_label"], "distance": 40,
                    "max_days_old": CONFIG["max_age_days"], "sort_by": "date",
                    "content-type": "application/json",
                },
            )
            if not r:
                break
            results = r.json().get("results", [])
            for j in results:
                sal = ""
                if j.get("salary_min") and j.get("salary_max"):
                    sal = f"₹{int(j['salary_min']):,} – ₹{int(j['salary_max']):,} / yr"
                jobs.append({
                    "title": clean(j.get("title")),
                    "company": clean((j.get("company") or {}).get("display_name")),
                    "location": clean((j.get("location") or {}).get("display_name")),
                    "url": j.get("redirect_url"),
                    "posted": j.get("created"),
                    "salary": sal,
                    "desc": clean(j.get("description"))[:600],
                    "source": "Adzuna",
                })
            if len(results) < 50:
                break
        time.sleep(0.5)
    print(f"Adzuna: {len(jobs)} raw")
    return jobs


def from_jooble():
    key = os.getenv("JOOBLE_API_KEY")
    if not key:
        print("Jooble: key not set, skipped")
        return []
    jobs = []
    for q in CONFIG["queries"][:12]:
        try:
            r = requests.post(
                f"https://jooble.org/api/{key}",
                json={"keywords": q, "location": CONFIG["city_label"], "page": 1},
                headers=UA, timeout=30,
            )
            r.raise_for_status()
        except Exception as e:
            print(f"  ! Jooble failed ({e.__class__.__name__})", file=sys.stderr)
            continue
        for j in r.json().get("jobs", []):
            jobs.append({
                "title": clean(j.get("title")),
                "company": clean(j.get("company")),
                "location": clean(j.get("location")),
                "url": j.get("link"),
                "posted": j.get("updated"),
                "salary": clean(j.get("salary")),
                "desc": clean(j.get("snippet"))[:600],
                "source": "Jooble",
            })
        time.sleep(0.5)
    print(f"Jooble: {len(jobs)} raw")
    return jobs


def from_jsearch():
    key = os.getenv("JSEARCH_API_KEY")
    if not key:
        print("JSearch: key not set, skipped")
        return []
    jobs = []
    for q in CONFIG["queries"][:10]:
        r = get(
            "https://api.openwebninja.com/jsearch/search",
            params={"query": f"{q} in {CONFIG['city_label']}, India", "page": 1, "num_pages": 2,
                    "date_posted": "month", "country": "in"},
            headers={**UA, "x-api-key": key},
        )
        if not r:
            continue
        for j in (r.json().get("data") or []):
            loc = ", ".join(x for x in [j.get("job_city"), j.get("job_state")] if x)
            sal = ""
            if j.get("job_min_salary") and j.get("job_max_salary"):
                sal = f"{int(j['job_min_salary']):,} – {int(j['job_max_salary']):,} {j.get('job_salary_currency') or ''}".strip()
            jobs.append({
                "title": clean(j.get("job_title")),
                "company": clean(j.get("employer_name")),
                "location": loc,
                "url": j.get("job_apply_link"),
                "posted": j.get("job_posted_at_datetime_utc"),
                "salary": sal,
                "desc": clean(j.get("job_description"))[:600],
                "source": f"JSearch / {j.get('job_publisher') or 'web'}",
            })
        time.sleep(0.5)
    print(f"JSearch: {len(jobs)} raw")
    return jobs


def in_kolkata(job):
    blob = f"{job['location']} {job['title']}".lower()
    return any(t in blob for t in CONFIG["location_terms"])


def is_legal(job):
    blob = f"{job['title']} {job['desc']}".lower()
    title = job["title"].lower()
    if not any(w in blob for w in CONFIG["must_have_any"]):
        return False
    if any(w in f"{title} " for w in CONFIG["exclude_title_words"]):
        return False
    return True


def category(job):
    blob = f"{job['title']} {job['company']} {job['desc']}".lower()
    best, best_n = "Other legal", 0
    for name, words in CONFIG["categories"].items():
        n = sum(1 for w in words if w in blob)
        if n > best_n:
            best, best_n = name, n
    return best


def match_score(job):
    blob = f"{job['title']} {job['desc']}".lower()
    kws = CONFIG["skill_keywords"]
    hits = [k for k in kws if k in blob]
    # 6 distinct hits already counts as a very strong match
    score = min(100, round(len(hits) / 6 * 100))
    return score, hits[:8]


def main():
    raw = from_adzuna() + from_jooble() + from_jsearch()
    old = {}
    if OUT.exists():
        try:
            old = {j["id"]: j for j in json.loads(OUT.read_text(encoding="utf-8")).get("jobs", [])}
        except Exception:
            old = {}

    cutoff = NOW - timedelta(days=CONFIG["max_age_days"])
    fresh = {}
    for j in raw:
        if not (j["title"] and j["url"]):
            continue
        if not in_kolkata(j) or not is_legal(j):
            continue
        posted = parse_date(j["posted"])
        if posted and posted < cutoff:
            continue
        jid = make_id(j["title"], j["company"], j["location"])
        score, hits = match_score(j)
        rec = {
            "id": jid, "title": j["title"], "company": j["company"] or "Not disclosed",
            "location": j["location"] or CONFIG["city_label"], "url": j["url"],
            "source": j["source"], "salary": j["salary"],
            "posted": posted.isoformat() if posted else None,
            "category": category(j), "match": score, "matched_skills": hits,
            "desc": j["desc"],
        }
        # keep the first listing seen for a job; remember other sources
        if jid in fresh:
            fresh[jid].setdefault("also_on", [])
            if j["source"] not in fresh[jid]["also_on"] and j["source"] != fresh[jid]["source"]:
                fresh[jid]["also_on"].append(j["source"])
        else:
            fresh[jid] = rec

    today = NOW.date().isoformat()
    merged = {}
    for jid, rec in fresh.items():
        prev = old.get(jid, {})
        rec["first_seen"] = prev.get("first_seen", today)
        rec["last_seen"] = today
        merged[jid] = rec

    # keep jobs not seen today for a few days, then drop them (dead-listing cleanup)
    drop_before = (NOW - timedelta(days=CONFIG["drop_after_unseen_days"])).date().isoformat()
    for jid, prev in old.items():
        if jid not in merged and prev.get("last_seen", "0000") >= drop_before:
            merged[jid] = prev

    jobs = sorted(merged.values(), key=lambda x: (x.get("first_seen", ""), x["match"]), reverse=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps({"updated": NOW.isoformat(), "count": len(jobs), "jobs": jobs}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print(f"Wrote {len(jobs)} jobs ({len(fresh)} seen today)")
    if not raw:
        print("WARNING: no source returned data. Check the secrets.", file=sys.stderr)


if __name__ == "__main__":
    main()
