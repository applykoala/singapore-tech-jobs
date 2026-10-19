"""Rebuild README.md and jobs.json from the public job boards in companies.json.

Only the companies' own public job-board APIs are read (Greenhouse, Lever, Ashby),
the same feeds their careers pages use. Standard library only, so the GitHub Action
needs no install step. Run: python3 update.py
"""
import concurrent.futures as cf
import datetime as dt
import json
import re
import urllib.request

UA = {"User-Agent": "singapore-tech-jobs (+https://github.com/shangxiang0907/singapore-tech-jobs)"}

# Software, AI and data roles. Checked against the title only.
TECH = re.compile(
    r"\b(engineer|engineering|developer|programmer|sre|devops|architect|scientist|"
    r"machine learning|ml|ai|llm|data|analytics|security|infrastructure|platform|"
    r"backend|back-end|frontend|front-end|full[- ]?stack|mobile|ios|android|qa|test|"
    r"quant(itative)? (developer|researcher)|researcher|technical program)\b",
    re.I,
)
NOT_TECH = re.compile(r"\b(sales engineer|account executive|recruit|legal|counsel|marketing|"
                      r"customer success|business development|accountant|finance manager)\b", re.I)
AI = re.compile(r"\b(ai|ml|machine learning|llm|genai|generative|deep learning|nlp|computer vision|applied scientist|research scientist)\b", re.I)


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return json.load(r)


def iso(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).date().isoformat() if s else ""


def greenhouse(slug):
    for j in get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs")["jobs"]:
        loc = (j.get("location") or {}).get("name", "")
        yield j["title"], loc, j["absolute_url"], iso(j.get("first_published") or j.get("updated_at"))


def lever(slug):
    for j in get(f"https://api.lever.co/v0/postings/{slug}?mode=json"):
        c = j.get("categories") or {}
        loc = " / ".join(c.get("allLocations") or [c.get("location", "")])
        yield j["text"], loc, j["hostedUrl"], dt.datetime.fromtimestamp(j["createdAt"] / 1000, dt.timezone.utc).date().isoformat()


def ashby(slug):
    for j in get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")["jobs"]:
        if j.get("isListed") is False:
            continue
        locs = [j.get("location") or ""] + [s.get("location", "") for s in j.get("secondaryLocations") or []]
        yield j["title"], " / ".join(l for l in locs if l), j["jobUrl"], iso(j.get("publishedAt"))


ATS = {"greenhouse": greenhouse, "lever": lever, "ashby": ashby}


def company_jobs(c):
    out = []
    try:
        for title, loc, url, posted in ATS[c["ats"]](c["slug"]):
            if "singapore" not in loc.lower() or not TECH.search(title) or NOT_TECH.search(title):
                continue
            out.append({"company": c["name"], "title": title.strip(), "location": loc, "url": url,
                        "posted": posted, "ai": bool(AI.search(title))})
        return c["name"], out, None
    except Exception as e:  # one broken board must not stop the rest
        return c["name"], [], str(e)


def cell(s):
    return s.replace("|", "\\|").replace("\n", " ")


def main():
    companies = json.load(open("companies.json"))
    jobs, errors = [], []
    with cf.ThreadPoolExecutor(12) as ex:
        for name, js, err in ex.map(company_jobs, companies):
            jobs += js
            if err:
                errors.append(f"{name}: {err}")
    jobs.sort(key=lambda j: (j["posted"], j["company"], j["title"]), reverse=True)
    json.dump(jobs, open("jobs.json", "w"), indent=1, ensure_ascii=False)

    today = dt.date.today()
    def age(p):
        if not p:
            return ""
        d = (today - dt.date.fromisoformat(p)).days
        return "today" if d <= 0 else f"{d}d"

    ai_jobs = [j for j in jobs if j["ai"]]
    rows = lambda js: "\n".join(
        f"| **{cell(j['company'])}** | {cell(j['title'])} | {cell(j['location'])} | [Apply]({j['url']}) | {age(j['posted'])} |" for j in js)
    head = "| Company | Role | Location | Link | Posted |\n|---|---|---|---|---|"
    n_co = len({j["company"] for j in jobs})
    readme = open("README.template.md").read()
    readme = (readme.replace("{{UPDATED}}", today.isoformat())
              .replace("{{COUNT}}", str(len(jobs))).replace("{{COMPANIES}}", str(n_co))
              .replace("{{AI_COUNT}}", str(len(ai_jobs)))
              .replace("{{AI_TABLE}}", head + "\n" + rows(ai_jobs) if ai_jobs else "_None today._")
              .replace("{{ALL_TABLE}}", head + "\n" + rows(jobs)))
    open("README.md", "w").write(readme)
    print(f"{len(jobs)} jobs at {n_co} companies ({len(ai_jobs)} AI/ML)")
    for e in errors:
        print("skipped", e)


if __name__ == "__main__":
    main()
