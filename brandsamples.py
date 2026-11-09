#!/usr/bin/env python3
"""brandsamples: find realistic brand-impersonation test data in AlienVault OTX.

Search OTX pulses for a brand, pull the domain, hostname and URL indicators from the
matching pulses, and keep the hosts that look like the brand without being the brand.
Each kept row says why it was kept, so a detector's test set can be balanced by kind.

Standard library only. The API key is read from OTX_API_KEY.
"""
import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://otx.alienvault.com/api/v1"
HOST_TYPES = {"domain", "hostname", "URL", "URI"}

# Characters an impersonator swaps in for the ones a reader expects.
HOMOGLYPHS = str.maketrans({"0": "o", "1": "l", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s"})
SEQUENCES = (("rn", "m"), ("vv", "w"), ("cl", "d"))

# Order matters: the first kind that matches is the row's kind.
KINDS = ("label", "affix", "embedded", "lookalike")


# ---------- classification (pure, tested) ----------

def host_of(indicator):
    s = indicator if "://" in indicator else "http://" + indicator
    try:
        return (urllib.parse.urlsplit(s).hostname or "").lower().strip(".")
    except ValueError:
        return ""


def is_own(host, own_domains):
    return any(host == d or host.endswith("." + d) for d in own_domains)


def normalize(label):
    s = label.lower().translate(HOMOGLYPHS)
    for seq, repl in SEQUENCES:
        s = s.replace(seq, repl)
    return s


def osa_distance(a, b, limit=2):
    """Optimal string alignment distance, stopping early once it exceeds `limit`."""
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    prev2, prev = None, list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        cur = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                cur[j] = min(cur[j], prev2[j - 2] + 1)
        if min(cur) > limit:
            return limit + 1
        prev2, prev = prev, cur
    return prev[-1]


def classify(host, brand, own_domains=()):
    """Return the kind of impersonation `host` shows for `brand`, or None.

    label      the brand is a whole DNS label: brand.example.net
    affix      the brand is joined to other words in a label: brand-login, secure-brand
    embedded   the brand sits inside a longer label: mybrandhelp
    lookalike  a label is one edit from the brand after homoglyph folding: brannd, br4nd
    """
    brand = brand.lower()
    if not host or is_own(host, own_domains):
        return None
    labels = host.split(".")
    if brand in labels:
        return "label"
    for lab in labels:
        if brand in lab.split("-") and "-" in lab:
            return "affix"
    for lab in labels:
        if brand in lab:
            return "embedded"
    if len(brand) >= 5:
        for lab in labels:
            folded = normalize(lab)
            if folded == brand or osa_distance(folded, brand, limit=1) <= 1:
                return "lookalike"
            if any(osa_distance(part, brand, limit=1) <= 1 for part in folded.split("-") if part):
                return "lookalike"
    return None


def defang(url):
    return url.replace("http", "hxxp", 1).replace(".", "[.]")


# ---------- OTX access ----------

def fetch_json(url, key, timeout=60, retries=2):
    req = urllib.request.Request(url, headers={"X-OTX-API-KEY": key, "User-Agent": "otx-brand-samples"})
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code in (429, 502, 503, 504) and attempt < retries:
                time.sleep(5 * (attempt + 1))
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            if attempt < retries:
                time.sleep(3)
                continue
            raise


def search_pulses(brand, key, max_pulses, fetch=fetch_json):
    """Pulses whose name, description or tags mention the brand, most recently modified first."""
    pulses, page = [], 1
    while len(pulses) < max_pulses:
        q = urllib.parse.urlencode({"q": brand, "limit": 50, "page": page, "sort": "-modified"})
        data = fetch(f"{API}/search/pulses?{q}", key)
        results = data.get("results", [])
        if not results:
            break
        for p in results:
            pulses.append({"id": p["id"], "name": p.get("name", ""), "modified": p.get("modified", "")})
        if not data.get("next"):
            break
        page += 1
    return pulses[:max_pulses]


def pulse_indicators(pulse_id, key, since="", max_pages=20, fetch=fetch_json):
    rows, page = [], 1
    while page <= max_pages:
        q = urllib.parse.urlencode({"limit": 500, "page": page})
        data = fetch(f"{API}/pulses/{pulse_id}/indicators?{q}", key)
        for r in data.get("results", []):
            if r.get("type") in HOST_TYPES and r.get("created", "") >= since:
                rows.append({"indicator": r["indicator"], "created": r.get("created", "")})
        if not data.get("next"):
            break
        page += 1
    return rows


# ---------- run ----------

def collect(brand, own_domains, key, max_pulses=20, since="", fetch=fetch_json):
    seen, out = set(), []
    for p in search_pulses(brand, key, max_pulses, fetch=fetch):
        for ind in pulse_indicators(p["id"], key, since=since, fetch=fetch):
            host = host_of(ind["indicator"])
            if host in seen:
                continue
            kind = classify(host, brand, own_domains)
            if kind is None:
                continue
            seen.add(host)
            url = ind["indicator"] if "://" in ind["indicator"] else "http://" + ind["indicator"]
            out.append({"host": host, "url": url, "kind": kind, "pulse_id": p["id"],
                        "pulse_name": p["name"], "first_seen": ind["created"]})
    out.sort(key=lambda r: (KINDS.index(r["kind"]), r["host"]))
    return out


def write_csv(rows, fh, live=False):
    w = csv.DictWriter(fh, fieldnames=["host", "url", "kind", "pulse_id", "pulse_name", "first_seen"])
    w.writeheader()
    for r in rows:
        w.writerow({**r, "url": r["url"] if live else defang(r["url"]),
                    "host": r["host"] if live else r["host"].replace(".", "[.]")})


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--brand", required=True, help="brand token as it appears in hostnames, e.g. examplebank")
    ap.add_argument("--own", default="", help="comma-separated domains the brand really owns (excluded)")
    ap.add_argument("--pulses", type=int, default=20, help="most pulses to read (default 20)")
    ap.add_argument("--since", default="", help="only indicators created on or after this ISO date")
    ap.add_argument("--out", default="-", help="CSV path, or - for stdout")
    ap.add_argument("--live", action="store_true", help="write real URLs instead of defanged ones")
    a = ap.parse_args(argv)

    key = os.environ.get("OTX_API_KEY", "")
    if not key:
        sys.exit("set OTX_API_KEY (free at otx.alienvault.com, under your account settings)")
    own = [d.strip().lower() for d in a.own.split(",") if d.strip()]
    rows = collect(a.brand, own, key, max_pulses=a.pulses, since=a.since)

    fh = sys.stdout if a.out == "-" else open(a.out, "w", newline="")
    try:
        write_csv(rows, fh, live=a.live)
    finally:
        if fh is not sys.stdout:
            fh.close()
    counts = {k: sum(r["kind"] == k for r in rows) for k in KINDS}
    print(f"{len(rows)} hosts: " + ", ".join(f"{k} {n}" for k, n in counts.items()), file=sys.stderr)


if __name__ == "__main__":
    main()
