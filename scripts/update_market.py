#!/usr/bin/env python3
"""Refresh the HDB resale figures on mirta.me.

Pulls HDB resale transactions for every HDB town in the North, North-East and
East regions (URA planning regions) from data.gov.sg,
summarises the last 12 months against the 12 months before, saves the result
to data/market.json and rewrites the marked blocks in index.html and
property-updates.html. Standard library only, so GitHub Actions needs no installs.

Usage:
  python3 scripts/update_market.py              # fetch fresh data, then render
  python3 scripts/update_market.py --render-only  # re-render from data/market.json

Optional: set DATA_GOV_SG_API_KEY (a GitHub secret) for higher rate limits.
"""
import datetime as dt
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_FILE = os.path.join(ROOT, "data", "market.json")
DATASET = "d_8b84c4ee58e3cfc0ece0d773c8ca6abc"
API = "https://data.gov.sg/api/action/datastore_search"
REGIONS = {
    "North-East": ["PUNGGOL", "SENGKANG", "HOUGANG", "SERANGOON", "ANG MO KIO"],
    "North": ["WOODLANDS", "YISHUN", "SEMBAWANG"],
    "East": ["TAMPINES", "PASIR RIS", "BEDOK"],
}
TOWNS = [t for ts in REGIONS.values() for t in ts]
REGION_OF = {t: r for r, ts in REGIONS.items() for t in ts}
FLAT_TYPES = ["3 ROOM", "4 ROOM", "5 ROOM", "EXECUTIVE"]
UPGRADER_TYPES = ["4 ROOM", "5 ROOM", "EXECUTIVE"]
TYPE_LABEL = {"3 ROOM": "3-room", "4 ROOM": "4-room", "5 ROOM": "5-room", "EXECUTIVE": "Executive"}
TOWN_LABEL = {t: t.title() for t in TOWNS}


def slug(name):
    return name.lower().replace(" ", "-")


# ---------- dates ----------
def add_months(month, delta):
    y, m = (int(x) for x in month.split("-"))
    t = y * 12 + (m - 1) + delta
    return f"{t // 12}-{t % 12 + 1:02d}"


def month_label(month):
    y, m = (int(x) for x in month.split("-"))
    return dt.date(y, m, 1).strftime("%b %Y")


# ---------- fetch ----------
def fetch_town(town, oldest_month):
    """Newest-first rows for one town, back to oldest_month."""
    rows, offset, limit = [], 0, 5000
    headers = {"User-Agent": "mirta.me market updater"}
    if os.environ.get("DATA_GOV_SG_API_KEY"):
        headers["x-api-key"] = os.environ["DATA_GOV_SG_API_KEY"]
    while True:
        query = urllib.parse.urlencode({
            "resource_id": DATASET, "limit": limit, "offset": offset,
            "sort": "month desc", "filters": json.dumps({"town": town}),
        })
        for attempt in range(6):
            try:
                req = urllib.request.Request(f"{API}?{query}", headers=headers)
                with urllib.request.urlopen(req, timeout=60) as r:
                    payload = json.load(r)
                break
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < 5:
                    time.sleep(15 * (attempt + 1))
                    continue
                raise
        if not payload.get("success"):
            raise RuntimeError(f"data.gov.sg error for {town}: {payload}")
        recs = payload["result"]["records"]
        rows.extend(recs)
        if len(recs) < limit or recs[-1]["month"] < oldest_month:
            return rows
        offset += limit
        time.sleep(3)


# ---------- summarise ----------
def median(values):
    v = sorted(values)
    n = len(v)
    if not n:
        return None
    return v[(n - 1) // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2


def type_stats(cur, prev, ft, with_max=True):
    c = [r for r in cur if r["flat_type"] == ft]
    if not c:
        return None
    prices = [float(r["resale_price"]) for r in c]
    p = [float(r["resale_price"]) for r in prev if r["flat_type"] == ft]
    m, pm = median(prices), median(p)
    out = {
        "count": len(c),
        "median": m,
        "prev_median": pm,
        "change_pct": round((m / pm - 1) * 100, 1) if pm else None,
        "million_count": sum(1 for x in prices if x >= 1_000_000),
    }
    if with_max:
        top = max(c, key=lambda r: float(r["resale_price"]))
        out["max"] = {"price": float(top["resale_price"]), "block": top["block"], "street": top["street_name"],
                      "storey": top["storey_range"], "month": top["month"], "area_sqm": float(top["floor_area_sqm"])}
    return out


def summarise(rows_by_town):
    latest = max(r["month"] for rows in rows_by_town.values() for r in rows)
    start, prev_start, prev_end = add_months(latest, -11), add_months(latest, -23), add_months(latest, -12)
    out = {
        "source": f"HDB resale flat prices, data.gov.sg (dataset {DATASET})",
        "updated": dt.date.today().isoformat(),
        "latest_month": latest,
        "period": {"from": start, "to": latest},
        "prev_period": {"from": prev_start, "to": prev_end},
        "regions": {},
        "towns": {},
    }
    split = {}
    for town, rows in rows_by_town.items():
        cur = [r for r in rows if start <= r["month"] <= latest]
        prev = [r for r in rows if prev_start <= r["month"] <= prev_end]
        split[town] = (cur, prev)
        types = {ft: st for ft in FLAT_TYPES if (st := type_stats(cur, prev, ft))}
        recent = sorted((r for r in cur if r["flat_type"] in UPGRADER_TYPES),
                        key=lambda r: (r["month"], float(r["resale_price"])), reverse=True)[:5]
        out["towns"][town] = {
            "region": REGION_OF[town],
            "flat_types": types,
            "recent": [{"month": r["month"], "flat_type": r["flat_type"], "block": r["block"], "street": r["street_name"],
                        "storey": r["storey_range"], "area_sqm": float(r["floor_area_sqm"]),
                        "price": float(r["resale_price"])} for r in recent],
        }
    for region, towns in REGIONS.items():
        cur = [r for t in towns if t in split for r in split[t][0]]
        prev = [r for t in towns if t in split for r in split[t][1]]
        out["regions"][region] = {
            "towns": towns,
            "flat_types": {ft: st for ft in FLAT_TYPES if (st := type_stats(cur, prev, ft, with_max=False))},
        }
    return out


# ---------- render ----------
def money(x, exact=False):
    if x is None:
        return "–"
    return f"${x:,.0f}" if exact else f"${round(x / 1000) * 1000:,.0f}"


def change_text(pct):
    if pct is None:
        return "no comparison available"
    if abs(pct) < 0.5:
        return "about the same as the 12 months before"
    return f"{'up' if pct > 0 else 'down'} {abs(pct):.1f}% on the 12 months before"


ABBR = {"DR": "Drive", "AVE": "Avenue", "ST": "Street", "RD": "Road", "CTRL": "Central", "CRES": "Crescent",
        "PL": "Place", "NTH": "North", "STH": "South", "CL": "Close", "TER": "Terrace", "PK": "Park"}


def street(s):
    return " ".join(ABBR.get(w, w.title()) for w in s.split())


def esc(s):
    return html.escape(str(s))


def period_text(d):
    return f"{month_label(d['period']['from'])} to {month_label(d['period']['to'])}"


def summary_sentences(d):
    out = []
    for region, reg in d["regions"].items():
        parts = []
        for ft in ("4 ROOM", "5 ROOM"):
            st = reg["flat_types"].get(ft)
            if st:
                parts.append(f"{TYPE_LABEL[ft]} median {money(st['median'])} from {st['count']:,} sales "
                             f"({change_text(st['change_pct'])})")
        if parts:
            towns = ", ".join(TOWN_LABEL[t] for t in reg["towns"])
            out.append(f"{region} ({towns}), {period_text(d)}: " + "; ".join(parts) + ".")
    best = max(((t, s["max"]) for t, td in d["towns"].items() for s in td["flat_types"].values()),
               key=lambda x: x[1]["price"], default=None)
    if best:
        t, mx = best
        out.append(f"The highest HDB resale price in these towns over the period was {money(mx['price'], True)}, "
                   f"for Blk {mx['block']} {street(mx['street'])} in {TOWN_LABEL[t]} ({month_label(mx['month'])}).")
    return out


def town_sentence(d, town):
    td = d["towns"][town]["flat_types"]
    bits = [f"{TYPE_LABEL[ft]} {money(td[ft]['median'])} ({td[ft]['count']:,} sales)" for ft in ("4 ROOM", "5 ROOM") if ft in td]
    return f"Median HDB resale prices in {TOWN_LABEL[town]} from {period_text(d)}: " + ", ".join(bits) + "."


def pct_html(pct):
    if pct is None:
        return "–"
    cls = "up" if pct >= 0.5 else "down" if pct <= -0.5 else ""
    return f'<span class="{cls}">{pct:+.1f}%</span>'


def render_snapshot(d):
    """Short block for the homepage: medians by region."""
    cards = []
    for region, reg in d["regions"].items():
        ft = reg["flat_types"]
        cells = "".join(
            f'<div><dt>{TYPE_LABEL[t]} median</dt><dd>{money(ft[t]["median"])}</dd></div>'
            for t in ("4 ROOM", "5 ROOM") if t in ft)
        towns = ", ".join(TOWN_LABEL[t] for t in reg["towns"])
        cards.append(f'<div class="snap-town"><h3>{esc(region)}</h3><p class="snap-towns">{esc(towns)}</p><dl>{cells}</dl></div>')
    return (
        f'<p class="snap-period">HDB resale, {period_text(d)}. Updated {esc(d["updated"])}.</p>'
        f'<div class="snap-grid">{"".join(cards)}</div>'
    )


def render_updates(d):
    """Full market block for /property-updates."""
    parts = [f'<p class="lede">Every HDB resale registered in the North, North-East and East of Singapore from '
             f'{period_text(d)}, compared with the 12 months before. Updated automatically every week from HDB data on '
             f'data.gov.sg. Last updated {esc(d["updated"])}.</p>']
    parts.append('<ul class="key-facts">' + "".join(f"<li>{esc(x)}</li>" for x in summary_sentences(d)) + "</ul>")
    # jump links
    links = " ".join(f'<a href="#{slug(t)}">{TOWN_LABEL[t]}</a>' for t in TOWNS if t in d["towns"])
    parts.append(f'<nav class="town-nav" aria-label="Jump to a town">{links}</nav>')
    # overview table
    rows = []
    for region, reg in d["regions"].items():
        rows.append(f'<tr class="region-row"><th colspan="6" scope="colgroup">{esc(region)}</th></tr>')
        for t in reg["towns"]:
            td = d["towns"].get(t, {}).get("flat_types", {})
            c4, c5 = td.get("4 ROOM"), td.get("5 ROOM")
            rows.append(
                f'<tr><th scope="row"><a href="#{slug(t)}">{TOWN_LABEL[t]}</a></th>'
                f'<td>{money(c4["median"]) if c4 else "–"}</td><td>{pct_html(c4["change_pct"]) if c4 else "–"}</td>'
                f'<td>{money(c5["median"]) if c5 else "–"}</td><td>{pct_html(c5["change_pct"]) if c5 else "–"}</td>'
                f'<td>{sum(x["count"] for x in td.values()):,}</td></tr>')
    parts.append(f"""
<h2 class="market-h">Median prices by town</h2>
<div class="table-wrap"><table class="overview">
  <caption>4-room and 5-room median resale prices, {period_text(d)}, with change on the 12 months before</caption>
  <thead><tr><th scope="col">Town</th><th scope="col">4-room median</th><th scope="col">Change</th><th scope="col">5-room median</th><th scope="col">Change</th><th scope="col">All sales</th></tr></thead>
  <tbody>{''.join(rows)}</tbody>
</table></div>""")
    return "\n".join(parts)


def render_towns(d):
    """Town-by-town detail for /property-updates."""
    parts = ['<h2 class="market-h">Prices by town</h2>']
    for region, reg in d["regions"].items():
        parts.append(f'<h3 class="region-h" id="{slug(region)}">{esc(region)}</h3>')
        for town in reg["towns"]:
            t = d["towns"].get(town)
            if not t:
                continue
            trs = []
            for ft in FLAT_TYPES:
                s = t["flat_types"].get(ft)
                if not s:
                    continue
                mx = s["max"]
                trs.append(
                    f"<tr><th scope=\"row\">{TYPE_LABEL[ft]}</th><td>{s['count']:,}</td><td>{money(s['median'])}</td>"
                    f"<td>{pct_html(s['change_pct'])}</td><td>{money(mx['price'], True)}<small>Blk {esc(mx['block'])} {esc(street(mx['street']))}, "
                    f"{esc(mx['storey'].lower())}, {month_label(mx['month'])}</small></td></tr>")
            recent = "".join(
                f"<tr><td>{month_label(r['month'])}</td><td>{TYPE_LABEL[r['flat_type']]}</td>"
                f"<td>Blk {esc(r['block'])} {esc(street(r['street']))}</td><td>{esc(r['storey'].lower())}</td>"
                f"<td>{r['area_sqm']:.0f} sqm</td><td>{money(r['price'], True)}</td></tr>" for r in t["recent"])
            parts.append(f"""
<article class="town-block" id="{slug(town)}">
  <h4>{TOWN_LABEL[town]} HDB resale prices</h4>
  <p>{esc(town_sentence(d, town))}</p>
  <div class="table-wrap"><table>
    <thead><tr><th scope="col">Flat type</th><th scope="col">Sales</th><th scope="col">Median price</th><th scope="col">vs prior 12 months</th><th scope="col">Highest sale</th></tr></thead>
    <tbody>{''.join(trs)}</tbody>
  </table></div>
  <details class="recent-sales"><summary>Latest larger-flat sales in {TOWN_LABEL[town]}</summary>
  <div class="table-wrap"><table>
    <thead><tr><th scope="col">Month</th><th scope="col">Type</th><th scope="col">Block</th><th scope="col">Storey</th><th scope="col">Size</th><th scope="col">Price</th></tr></thead>
    <tbody>{recent}</tbody>
  </table></div></details>
</article>""")
    parts.append(
        f'<p class="fine" style="margin-top:32px">Source: Housing &amp; Development Board, resale flat prices based on registration date, via '
        f'<a href="https://data.gov.sg/datasets/{DATASET}/view" rel="noopener">data.gov.sg</a>. Regions follow URA planning regions. '
        f'Figures for {month_label(d["latest_month"])} are partial and fill in as HDB registers more sales. Medians are rounded to '
        f'the nearest $1,000. Past prices are not a valuation of your flat.</p>')
    return "\n".join(parts)


def render_dataset_ld(d):
    ld = {
        "@context": "https://schema.org",
        "@type": "Dataset",
        "name": f"HDB resale prices in North, North-East and East Singapore towns, {period_text(d)}",
        "description": " ".join(summary_sentences(d)),
        "url": "https://mirta.me/property-updates#market",
        "dateModified": d["updated"],
        "temporalCoverage": f"{d['period']['from']}/{d['period']['to']}",
        "spatialCoverage": [f"{TOWN_LABEL[t]}, Singapore" for t in TOWNS],
        "creator": {"@id": "https://mirta.me/#mirta"},
        "isBasedOn": f"https://data.gov.sg/datasets/{DATASET}/view",
        "license": "https://data.gov.sg/open-data-licence",
    }
    return '<script type="application/ld+json">' + json.dumps(ld, ensure_ascii=False) + "</script>"


def inject(path, name, content):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    pattern = re.compile(rf"(<!-- {name}:START -->)(.*?)(<!-- {name}:END -->)", re.S)
    if not pattern.search(text):
        raise RuntimeError(f"marker {name} missing in {path}")
    text = pattern.sub(lambda m: m.group(1) + "\n" + content + "\n" + m.group(3), text)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def update_sitemap(updated):
    path = os.path.join(ROOT, "sitemap.xml")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    text = re.sub(r"(<loc>https://mirta\.me/property-updates</loc>\s*<lastmod>)[^<]*(</lastmod>)",
                  rf"\g<1>{updated}\g<2>", text)
    text = re.sub(r"(<loc>https://mirta\.me/</loc>\s*<lastmod>)[^<]*(</lastmod>)", rf"\g<1>{updated}\g<2>", text)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def render_all(d):
    inject(os.path.join(ROOT, "index.html"), "MARKET-SNAPSHOT", render_snapshot(d))
    pu = os.path.join(ROOT, "property-updates.html")
    inject(pu, "MARKET", render_updates(d))
    inject(pu, "MARKET-TOWNS", render_towns(d))
    inject(pu, "MARKET-LD", render_dataset_ld(d))
    update_sitemap(d["updated"])


def main():
    if "--render-only" in sys.argv:
        with open(DATA_FILE, encoding="utf-8") as f:
            data = json.load(f)
    else:
        today = dt.date.today()
        oldest = add_months(f"{today.year}-{today.month:02d}", -26)
        rows = {}
        for town in TOWNS:
            rows[town] = fetch_town(town, oldest)
            time.sleep(3)
        data = summarise(rows)
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
    render_all(data)
    print("Rendered market data for", data["latest_month"], "updated", data["updated"])


if __name__ == "__main__":
    main()
