#!/usr/bin/env python3
"""Turn report.json (shape: examples/report.example.json) into a SIMPLE report.html + report.pdf.

Layout (kept deliberately plain):
  page 1  — every product in one strip: verdict, score, six coloured country dots, one line
  per product — verdict + score, a world map with the target countries coloured red / amber / green,
                one line per colour, the two pictures side by side with a one-line verdict,
                three "why" lines, biggest risk, fastest test. That's it.
  --detail  adds the old detail pages (scorecard, gates, seller grid, ledger, seller appendix) at the end.

Usage: python3 build_report.py <run>/report.json [--no-pdf] [--detail]
- Images referenced in the JSON (brand_image / match_image; paths relative to the JSON's folder) are embedded.
- PDF is printed with Chrome (headless). No Chrome → the HTML is written and you're told to Print → Save as PDF.
- Look before you show it: `pdftoppm -png -r 55 report.pdf page` (Poppler) or `sips -s format png report.pdf --out page1.png` (Mac, page 1).
"""
import base64
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date

from common import chrome_path, run_chrome, shop_listing_link, SKILL_DIR

RED, AMBER, GREEN, GREY = "#d32f2f", "#f0a500", "#2e8b3d", "#c9c9c9"
LIGHT = "#8bc34a"      # light green: copies exist, but only weak ones
STATUS = {"blocked": ("Red", RED), "crowded": ("Amber", AMBER), "weak": ("Light green", LIGHT), "open": ("Green", GREEN), "error": ("No data", "#777")}
VERDICT_COLOR = {"Test now": GREEN, "Backlog": AMBER, "Avoid": RED}
MAP_CC = {"uk": "gb"}  # the map tags Britain as gb
COUNTRY_NAMES = {"au": "Australia", "us": "United States", "uk": "United Kingdom", "ca": "Canada", "de": "Germany", "nz": "New Zealand"}

CSS = """
@page { size: A4; margin: 12mm 13mm; }
* { box-sizing: border-box; }
body { font: 10.5pt/1.35 -apple-system, "Helvetica Neue", Helvetica, Arial, sans-serif; color: #1a1a1a; margin: 0; background: #fff; }
h1 { font-size: 26pt; margin: 0 0 2pt; letter-spacing: -0.02em; }
h2 { font-size: 19pt; margin: 0; letter-spacing: -0.01em; }
h3 { font-size: 10pt; margin: 10pt 0 4pt; text-transform: uppercase; letter-spacing: 0.08em; color: #666; }
p { margin: 0 0 5pt; }
.muted { color: #666; } .small { font-size: 9pt; }
.page { page-break-after: always; } .page:last-child { page-break-after: auto; }
.btn { display: inline-block; background: #1877f2; color: #fff !important; text-decoration: none; font-weight: 700; font-size: 10.5pt; padding: 5pt 12pt; border-radius: 6px; }
.pill { display: inline-block; padding: 2px 10px; border-radius: 12px; color: #fff; font-weight: 700; font-size: 10pt; white-space: nowrap; }
.score { font-size: 28pt; font-weight: 700; line-height: 1; }
.hdr { display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #1a1a1a; padding-bottom: 6pt; margin-bottom: 8pt; }
.dots span { display: inline-block; width: 26px; height: 18px; border-radius: 4px; color: #fff; font-size: 8pt; font-weight: 700; text-align: center; line-height: 18px; margin-right: 3px; }
table.strip { width: 100%; border-collapse: collapse; margin: 6pt 0 10pt; }
table.strip td { padding: 7pt 6pt; border-bottom: 1px solid #e3e3e3; vertical-align: middle; }
table.strip th { text-align: left; font-size: 9pt; color: #666; padding: 4pt 6pt; border-bottom: 2px solid #1a1a1a; }
.tight { zoom: 0.92; } .tighter { zoom: 0.85; }
.mapRow { display: flex; gap: 10pt; align-items: center; margin: 4pt 0 3pt; } .mapCol { flex: 0 0 27%; } .ctyCol { flex: 1; }
table.cty { width: 100%; border-collapse: collapse; } table.cty th { font-size: 7.2pt; text-transform: uppercase; letter-spacing: 0.05em; color: #777; text-align: left; font-weight: 600; padding: 0 4pt 2pt 0; border-bottom: 1px solid #ccc; } table.cty th.right { text-align: right; }
table.cty td { padding: 1.6pt 4pt 1.6pt 0; border-bottom: 1px solid #e6e6e6; vertical-align: top; font-size: 8.8pt; line-height: 1.18; }
.chip { display: inline-block; min-width: 46pt; text-align: center; color: #fff; font-weight: 700; font-size: 8pt; padding: 1.5pt 5pt; border-radius: 3px; white-space: nowrap; }
.map { width: 100%; margin: 0; }
.map svg { width: 100%; height: auto; max-height: 40mm; display: block; }
.legend { display: flex; gap: 10pt; margin: 4pt 0 8pt; }
.legend > div { flex: 1; border-top: 4px solid #ccc; padding-top: 3pt; font-size: 7.8pt; line-height: 1.2; }
.legend b { display: block; font-size: 10pt; margin-bottom: 2pt; }
.sbs { display: flex; gap: 10pt; page-break-inside: avoid; margin-top: 4pt; }
.sbs > div { flex: 1; text-align: center; }
.sbs img { max-width: 100%; max-height: 21mm; object-fit: contain; border: 1px solid #e3e3e3; border-radius: 4px; }
.sbs .cap { font-size: 9pt; color: #444; margin-top: 2pt; }
.why { display: flex; gap: 10pt; page-break-inside: avoid; }
.why > div { flex: 1; font-size: 9.6pt; } .why h3 { margin-top: 6pt; }
ul { margin: 0 0 4pt 14pt; padding: 0; } li { margin: 0 0 2pt; }
.assume { border-left: 4px solid #f0a500; background: #fff7e6; padding: 6pt 9pt; margin: 8pt 0; font-size: 9.5pt; }
.key { font-size: 9pt; color: #555; }
table.grid { width: 100%; border-collapse: collapse; font-size: 9pt; }
table.grid th, table.grid td { text-align: left; padding: 3pt 5pt; border-bottom: 1px solid #e3e3e3; vertical-align: top; }
table.grid th { background: #f4f4f4; font-size: 9pt; }
.right { text-align: right; }
.asis { display: flex; gap: 10pt; }
.asis .shot { flex: 0 0 52%; }
.asis .shot img { width: 100%; max-height: 236mm; object-fit: cover; object-position: top; border: 1px solid #ddd; border-radius: 4px; }
.asis .side { flex: 1; font-size: 9.5pt; }
.asis ol { margin: 0 0 6pt 14pt; padding: 0; } .asis li { margin: 0 0 5pt; }
.kind { display: inline-block; font-size: 8pt; font-weight: 700; padding: 0 5px; border-radius: 3px; background: #eee; color: #333; margin-left: 3px; }
.kind.chain { background: #d32f2f; color: #fff; } .kind.market { background: #f0a500; color: #fff; }
.amz { font-size: 9pt; margin: 2pt 0 6pt; } .amz b { font-weight: 700; }
.amzdots span { display: inline-block; padding: 0 6px; height: 16px; border-radius: 4px; color: #fff; font-size: 8pt; font-weight: 700; line-height: 16px; margin-right: 3px; }
.amzbox { border: 1px solid #ddd; border-radius: 4px; padding: 5pt 7pt; margin: 0 0 6pt; }
.amzbox ol { margin: 3pt 0 0 14pt; } .amzbox li { margin: 0 0 3pt; }
table.ads { width: 100%; border-collapse: collapse; font-size: 9.5pt; margin: 4pt 0 8pt; }
table.ads th { text-align: left; font-size: 8.5pt; color: #666; border-bottom: 2px solid #1a1a1a; padding: 3pt 5pt; }
table.ads a { color: #0b57d0; text-decoration: none; } table.ads td { padding: 4pt 5pt; border-bottom: 1px solid #e3e3e3; vertical-align: top; }
.hero { border: 2px solid #1a1a1a; border-radius: 8px; padding: 10pt 12pt; margin: 8pt 0 10pt; display: flex; gap: 12pt; align-items: center; }
.hero img { width: 26mm; height: 26mm; object-fit: cover; border-radius: 6px; border: 1px solid #ddd; }
.hero .k { font-size: 9pt; text-transform: uppercase; letter-spacing: 0.08em; color: #666; }
.hero .n { font-size: 20pt; font-weight: 700; letter-spacing: -0.01em; margin: 1pt 0 3pt; }
.how { display: flex; gap: 8pt; margin: 6pt 0 10pt; } .how > div { flex: 1; font-size: 8.8pt; line-height: 1.3; border-top: 3px solid #1a1a1a; padding-top: 4pt; }
.how b { display: block; font-size: 9.5pt; }
table.lead { width: 100%; border-collapse: collapse; } table.lead th { text-align: left; font-size: 8.5pt; color: #666; border-bottom: 2px solid #1a1a1a; padding: 3pt 4pt; }
table.lead td { padding: 3pt 4pt; border-bottom: 1px solid #e3e3e3; vertical-align: middle; font-size: 8.8pt; line-height: 1.25; }
table.lead img { width: 11mm; height: 11mm; object-fit: cover; border-radius: 4px; border: 1px solid #ddd; display: block; }
.sig { display: inline-block; width: 15px; height: 15px; border-radius: 50%; vertical-align: middle; }
.tiles { display: flex; gap: 6pt; margin: 4pt 0 6pt; } .tile { flex: 1; border-radius: 6px; padding: 4pt 7pt; color: #fff; min-height: 19mm; }
.tile .t { font-size: 8pt; text-transform: uppercase; letter-spacing: 0.07em; opacity: 0.9; } .tile .v { font-size: 12.5pt; font-weight: 700; line-height: 1.15; margin: 1pt 0 2pt; }
.tile .d { font-size: 8pt; line-height: 1.25; } .tile svg { display: block; margin-top: 2pt; }
.divider { padding-top: 90mm; text-align: center; }
.gr { display: inline-block; font-size: 8.5pt; font-weight: 700; padding: 0 6px; border-radius: 3px; color: #fff; }
"""


def esc(s):
    return html.escape("" if s is None else str(s))


def pill(text, color):
    return '<span class="pill" style="background:%s%s">%s</span>' % (color, "", esc(text))


MONEY_SIGN = {"au": "A$", "us": "US$", "uk": "£", "ca": "C$", "de": "€", "nz": "NZ$"}


def price_to_number_safe(txt):
    m = re.search(r"\d[\d.,]*", str(txt or ""))
    if not m:
        return 9e9
    t = m.group(0)
    t = t.replace(".", "").replace(",", ".") if re.search(r",\d{2}$", t) else t.replace(",", "")
    try:
        return float(t)
    except ValueError:
        return 9e9


def ladder_text(r):
    """'Brand about A$88 · cheapest copy A$18 · typical copy A$25' for one country, or '' when no copy has a price."""
    pr = r.get("prices") or {}
    if not pr.get("cheapest_copy"):
        return ""
    sign = MONEY_SIGN.get(r.get("cc"), "")
    def m(v):
        return "%s%s" % (sign, "{:,.0f}".format(v))
    bits = []
    if pr.get("brand"):
        bits.append("Brand about %s" % m(pr["brand"]))
    bits.append("cheapest copy %s" % m(pr["cheapest_copy"]))
    if pr.get("typical_copy") and pr.get("priced_copies", 0) >= 3 and pr["typical_copy"] != pr["cheapest_copy"]:
        bits.append("typical copy %s" % m(pr["typical_copy"]))
    return " · ".join(bits)


def ladder_short(r):
    """'A$88 vs A$18' : the brand's price here against the cheapest copy."""
    pr = r.get("prices") or {}
    if not pr.get("cheapest_copy"):
        return ""
    sign = MONEY_SIGN.get(r.get("cc"), "")
    return ("%s%s vs %s%s" % (sign, "{:,.0f}".format(pr["brand"]), sign, "{:,.0f}".format(pr["cheapest_copy"]))) if pr.get("brand") else ("copy %s%s" % (sign, "{:,.0f}".format(pr["cheapest_copy"])))


def proof_line(p):
    """When the brand has kept ads running for 3+ months at a price far above the copies, say so: shoppers are paying the gap."""
    mt, lens = p.get("meta") or {}, p.get("lens") or []
    host = re.sub(r"^www\.", "", (re.findall(r"https?://([^/]+)", p.get("url") or "") or [""])[0].lower())
    mine = [t for t in (mt.get("top_advertisers") or []) if host and (t.get("shop") or "").lower().endswith(host)]
    if not mine or not mine[0].get("oldest_live_ad"):
        return ""
    try:
        y, mo, d = [int(x) for x in mine[0]["oldest_live_ad"].split("-")]
        days = (date.today() - date(y, mo, d)).days
    except Exception:
        return ""
    gaps = [r for r in lens if (r.get("prices") or {}).get("brand") and (r["prices"].get("cheapest_copy") or 9e9) < 0.5 * r["prices"]["brand"]]
    if days < 90 or not gaps:
        return ""
    return ("%s has kept ads running for %d months at %s while copies sell for less than half that in %d of %d countries. "
            "Shoppers are paying the gap, so a cheaper copy existing has not stopped this product selling." % (
                p.get("brand") or "The brand", days // 30, (p.get("price") or "its price").split(" (")[0], len(gaps), len(lens)))


def status_color(s):
    return STATUS.get((s or "").lower(), ("?", "#777"))[1]


HAS_SUPPLY = False    # set when any product carries supplier data: the front page then shows a fifth dot
IMG_CAP = None        # the web version uses smaller pictures so the page opens fast
WEB_DIR = None        # set by --web: the folder that holds index.html and img/


def img_data(path, base, max_w=1000):
    if not path:
        return None
    if IMG_CAP:
        max_w = min(max_w, IMG_CAP)
    if WEB_DIR:                            # the web version keeps pictures as separate small files, so the page itself stays light
        p0 = path if os.path.isabs(path) else os.path.join(base, path)
        if not os.path.exists(p0):
            return None
        import hashlib
        name = hashlib.md5((p0 + str(max_w)).encode()).hexdigest()[:14] + ".jpg"
        dest = os.path.join(WEB_DIR, "img", name)
        if not os.path.exists(dest):
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            try:
                from PIL import Image
                im = Image.open(p0)
                im.seek(0)
                im = im.convert("RGB")
                if im.width > max_w:
                    im = im.resize((max_w, int(im.height * max_w / im.width)))
                im.save(dest, "JPEG", quality=62, optimize=True)
            except Exception:
                shutil.copyfile(p0, dest)
        return "img/" + name
    p = path if os.path.isabs(path) else os.path.join(base, path)
    if not os.path.exists(p):
        return None
    ext = os.path.splitext(p)[1].lower().lstrip(".") or "jpeg"
    mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp", "gif": "gif"}.get(ext, "jpeg")
    try:                                   # shrink big pictures so the PDF stays small enough to email
        from PIL import Image
        import io
        if os.path.getsize(p) > 150000:
            im = Image.open(p).convert("RGB")
            if im.width > max_w:
                im = im.resize((max_w, int(im.height * max_w / im.width)))
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=(58 if IMG_CAP else 72), optimize=True)
            return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        pass
    return "data:image/%s;base64,%s" % (mime, base64.b64encode(open(p, "rb").read()).decode())


_MAP_CACHE = {}


def world_map(regions):
    """Inline SVG world map with each target country coloured by status. Non-target land is light grey."""
    path = os.path.join(SKILL_DIR, "reference", "world-map.svg")
    if not os.path.exists(path):
        return '<p class="muted small">(world map file missing: reference/world-map.svg)</p>'
    if "svg" not in _MAP_CACHE:
        s = open(path, encoding="utf-8").read()
        s = s[s.index("<svg"):]
        # drop the file's own stylesheet so ours wins, keep everything else
        s = re.sub(r"<style[^>]*>.*?</style>", "", s, count=1, flags=re.S)
        s = re.sub(r"<svg[^>]*>", '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 110 2754 1000" preserveAspectRatio="xMidYMid meet">', s, count=1)
        _MAP_CACHE["svg"] = s
    rules = [".landxx{fill:#e2e2e2;stroke:#ffffff;stroke-width:0.6}", ".oceanxx{fill:#ffffff;stroke:none}",
             ".limitxx,.noxx,.unxx,.antxx{fill:#e2e2e2;stroke:#ffffff;stroke-width:0.6}", "circle{display:none}"]
    _MAP_CACHE["n"] = _MAP_CACHE.get("n", 0) + 1
    mid = "map%d" % _MAP_CACHE["n"]          # styles inside an SVG apply to the WHOLE page, so every map needs its own id
    for r in regions:
        cc = MAP_CC.get((r.get("cc") or "").lower(), (r.get("cc") or "").lower())
        rules.append("#%s .%s,#%s .%s *{fill:%s !important}" % (mid, cc, mid, cc, status_color(r.get("status"))))
    style = "<style>%s</style>" % "".join(rules)
    return '<div class="map" id="%s">' % mid + _MAP_CACHE["svg"].replace(">", ">" + style, 1) + "</div>"


AMZ = {"high": ("High", RED), "medium": ("Medium", AMBER), "low": ("Low", GREEN), "error": ("No data", "#777")}


def amazon_line(p):
    """One line under the map: Amazon pressure per country."""
    am = p.get("amazon") or []
    if not am:
        return ""
    cells = "".join('<span style="background:%s">%s %s</span>' % (AMZ.get(a.get("pressure"), ("?", "#777"))[1], esc((a.get("cc") or "").upper()),
                                                                   esc(AMZ.get(a.get("pressure"), ("?", ""))[0])) for a in am)
    return '<p class="amz"><b>On Amazon:</b> <span class="amzdots">%s</span> %s</p>' % (cells, esc(p.get("amazon_one_liner") or ""))


def amazon_box(p, cc):
    """Amazon block for one country's 'what a shopper sees' page."""
    a = next((x for x in (p.get("amazon") or []) if x.get("cc") == cc), None)
    if not a or a.get("pressure") == "error":
        return ""
    lab, col = AMZ.get(a.get("pressure"), ("?", "#777"))
    out = ['<h3>On Amazon (%s) &nbsp;%s</h3><div class="amzbox">' % (esc(a.get("amazon_site")), pill(lab + " pressure", col))]
    out.append("<div>%s%s</div>" % (esc((a.get("why") or "").capitalize()), " The brand itself sells here." if a.get("brand_present") else ""))
    if a.get("cheapest"):
        out.append("<div class='muted'>From %s, typical %s.</div>" % (esc(money_cc(cc, a.get("cheapest"))), esc(money_cc(cc, a.get("typical")))))
    out.append("<ol>")
    for t in (a.get("top3") or [])[:3]:
        bits = [esc(t.get("price_text") or ""), ("{:,} reviews".format(t["reviews"]) if t.get("reviews") else ""), esc(t.get("bought_text") or "")]
        out.append("<li>%s<br><span class='muted'>%s</span></li>" % (esc((t.get("title") or "")[:62]), " · ".join(b for b in bits if b)))
    out.append("</ol>")
    if a.get("note"):
        out.append("<div class='muted'>%s</div>" % esc(a["note"]))
    out.append("</div>")
    return "".join(out)


GREYC = "#8a8a8a"


def signals(p):
    """Four plain traffic lights. Returns [(title, headline, detail, colour, sparkline or None)]."""
    out = []
    tr = p.get("trends") or []
    usable = [t for t in tr if t.get("direction") in ("rising", "steady", "falling")]
    w = next((t for t in usable if t.get("place") == "world"), usable[0] if usable else (tr[0] if tr else None))
    if w:
        d = w.get("direction")
        col = {"rising": GREEN, "steady": AMBER, "falling": RED, "tiny": RED}.get(d, GREYC)
        head = {"rising": "Rising", "steady": "Steady", "falling": "Falling", "tiny": "Very small", "thin": "Too small for Google to measure"}.get(d, "No data")
        g = w.get("growth_pct")
        det = ("%s searches vs last year" % ("more than 4x the" if g > 300 else "%s%s%%" % ("+" if g >= 0 else "", g))) if g is not None else ""
        if w.get("spike"):
            det += " (includes a one-off spike)"
        if w.get("place") != "world" and d != "thin":
            det = "%s: %s" % (w.get("label"), det)
        det = det.replace("searches vs last year", "Google searches vs the year before")
        bought = max([(a.get("bought_last_month_min") or 0) for a in (p.get("amazon") or [])] or [0])
        if bought:
            det = (det + ". " if det else "") + "Amazon: {:,}+ bought last month".format(bought)
        elif w.get("seasonal"):
            det += ". Peaks %s" % ", ".join(w.get("peak_months") or [])
        out.append(("Demand (2 years)", head, det, col, w.get("line")))
    else:
        out.append(("Demand", "Not checked", "", GREYC, None))
    regs = map_regions(p)
    nb = sum(1 for r in regs if r.get("status") == "blocked")
    na = sum(1 for r in regs if r.get("status") == "crowded")
    ng = sum(1 for r in regs if r.get("status") == "open")
    nw = sum(1 for r in regs if r.get("status") == "weak")
    col = RED if nb >= 2 else (AMBER if (nb or na) else (LIGHT if nw else GREEN))
    if p.get("lens"):
        if nb >= 2 or (nb and nb >= na and nb >= nw + ng):
            head = "In a big chain in %d of %d" % (nb, len(regs))
        elif na and na >= nw + ng:
            head = "Real copies in %d of %d" % (na, len(regs))
        elif nw:
            head, col = "Copies hidden in %d of %d" % (nw, len(regs)), (AMBER if (nb + na) >= 2 else LIGHT)
        elif na or nb:
            head = "Real copies in %d of %d" % (na + nb, len(regs))
        else:
            head = "Nobody else sells it"
        det = "Found by picture: the same object. %d red, %d amber, %d light green, %d green." % (nb, na, nw, ng)
    else:
        head = "%d of %d countries" % (nb, len(regs)) if regs else "Not checked"
        det = ("A big chain already sells it there." if nb else "No big chain sells it yet.") + (" %d open." % ng if ng else "")
    out.append(("Same product in shops" if p.get("lens") else "Big shops", head, det, col if regs else GREYC, None))
    am = [a for a in (p.get("amazon") or []) if a.get("pressure") in ("high", "medium", "low")]
    if am:
        nh = sum(1 for a in am if a["pressure"] == "high")
        nl = sum(1 for a in am if a["pressure"] == "low")
        col = RED if nh >= 4 else (AMBER if nh >= 1 or nl < len(am) else GREEN)
        top = max((a.get("top_reviews") or 0) for a in am)
        out.append(("Amazon", "Crowded in %d of %d" % (nh, len(am)) if nh else "Quiet", "Biggest listing: {:,} reviews.".format(top), col, None))
    else:
        out.append(("Amazon", "Not checked", "", GREYC, None))
    ad = p.get("ads") or {}
    mt = p.get("meta") or {}
    if mt:
        pat = mt.get("pattern") or ""
        col = {"a swarm, right now": RED, "crowded": RED, "a handful": AMBER, "one brand owns it": AMBER, "hardly anyone": GREEN, "nobody": GREEN}.get(pat, GREYC)
        out.append(("Advertisers", "%d brands" % (mt.get("n_advertisers") or 0), (pat[:1].upper() + pat[1:] + ". " if pat else "") + ((mt.get("plain") or "").split(". ")[0].rstrip(".") + "."), col, None))
    elif ad:
        n = sum(1 for c in (ad.get("competitors") or []) if c.get("grade") in ("established", "proven"))
        col = {"high": RED, "medium": AMBER, "low": GREEN}.get(ad.get("pressure"), GREYC)
        vel = ad.get("velocity") or []
        vtxt = ""
        if vel:
            vtxt = " New advertisers per half-year: %s (%s)." % (" → ".join("%d%s" % (v["new_advertisers"], "+" if v.get("capped") else "") for v in vel), ad.get("velocity_direction") or "")
        out.append(("Advertisers", "%d brands, 60+ days" % n if n else "None found", ("Paying for Facebook ads for 2+ months." if n else "Nobody has kept an ad running 2 months.") + vtxt, col, None))
    else:
        out.append(("Advertisers", "Not checked", "", GREYC, None))
    sup = (p.get("supplier") or {}).get("summary")
    if sup:                                   # the supply side: can you buy it, and what is left after you pay for it
        if sup.get("status") == "priced" and sup.get("margin_pct") is not None:
            m = sup["margin_pct"]
            out.append(("Cost to buy", "About US$%.0f on %s" % (sup["cost_usd"], sup.get("cost_site") or "AliExpress"),
                        "Leaves about US$%.0f a sale (%d%%) for ads, fees and profit%s." % (sup["room_per_sale_usd"], m, "" if sup.get("cost_includes_shipping") else ", before shipping"),
                        GREEN if m >= 70 else (AMBER if m >= 50 else RED), None))
        elif sup.get("status") == "priced":
            out.append(("Cost to buy", "About US$%.0f" % sup["cost_usd"], "On %s." % (sup.get("cost_site") or "a supplier site"), GREYC, None))
        elif sup.get("status") == "found, price not read":
            out.append(("Cost to buy", "%d supplier listing%s" % (sup["found"], "" if sup["found"] == 1 else "s"), "Suppliers list it. Open a listing to read today's price.", GREYC, None))
        else:
            out.append(("Cost to buy", "Not found yet", "The photo search found no supplier listing. Search AliExpress for it before you decide.", GREYC, None))
    return out


def spark(line, w=120, h=22):
    if not line or max(line) == 0:
        return ""
    m = max(line)
    pts = " ".join("%.1f,%.1f" % (i * w / (len(line) - 1), h - 2 - (v / m) * (h - 4)) for i, v in enumerate(line))
    return '<svg width="%d" height="%d" viewBox="0 0 %d %d"><polyline points="%s" fill="none" stroke="#fff" stroke-width="1.6"/></svg>' % (w, h, w, h, pts)


def tiles(p):
    notes = p.get("tile_notes") or {}
    sig = []
    for t, v, d, c, ln in signals(p):
        key = t.split(" ")[0]
        o = notes.get(key) or {}
        sig.append((t, o.get("head", v), o.get("detail", d), {"green": GREEN, "light green": LIGHT, "amber": AMBER, "red": RED}.get(o.get("colour"), c), ln))
    return '<div class="tiles">%s</div>' % "".join(
        '<div class="tile" style="background:%s"><div class="t">%s</div><div class="v">%s</div><div class="d">%s</div>%s</div>' % (c, esc(t), esc(v), esc(d), spark(ln) if ln else "")
        for t, v, d, c, ln in sig)


def _tiles_old(p):
    return '<div class="tiles">%s</div>' % "".join(
        '<div class="tile" style="background:%s"><div class="t">%s</div><div class="v">%s</div><div class="d">%s</div>%s</div>' % (c, esc(t), esc(v), esc(d), spark(ln) if ln else "")
        for t, v, d, c, ln in signals(p))


def sigdots(p):
    notes = p.get("tile_notes") or {}
    cols = [{"green": GREEN, "light green": LIGHT, "amber": AMBER, "red": RED}.get((notes.get(t.split(" ")[0]) or {}).get("colour"), c) for t, _, _, c, _ in signals(p)]
    cells = ['<td style="text-align:center"><span class="sig" style="background:%s"></span></td>' % c for c in cols]
    while HAS_SUPPLY and len(cells) < 5:
        cells.append('<td style="text-align:center"></td>')
    return "".join(cells)


GRADE = {"established": RED, "proven": AMBER, "testing": "#888"}


def ads_line(p):
    ad = p.get("ads") or {}
    if not ad:
        return ""
    lab, col = AMZ.get(ad.get("pressure"), ("?", "#777"))
    return '<p class="amz"><b>In the ad library:</b> <span class="amzdots"><span style="background:%s">%s</span></span> %s</p>' % (col, esc(lab), esc(ad.get("one_liner") or ad.get("why") or ""))


def first_thought(text):
    """The first sentence, or the first two when the first is only a word or two ('Avoid. People clearly want this, but ...')."""
    parts = re.split(r"(?<=[.!?])\s", (text or "").strip())
    if len(parts) > 1 and len(parts[0]) < 25:
        return parts[1] if parts[0].rstrip(".!").lower() in ("avoid", "backlog", "test now") else parts[0] + " " + parts[1]
    return parts[0] if parts else ""


def clip(text, n):
    """Shorten at a word, never mid-word."""
    text = " ".join((text or "").split())
    if len(text) <= n:
        return text
    return text[:n].rsplit(" ", 1)[0].rstrip(",.;:") + "…"


def money_cc(cc, v):
    cur = {"au": "A$", "us": "US$", "uk": "£", "ca": "C$", "de": "€", "nz": "A$"}.get(cc, "")
    if isinstance(v, (int, float)):
        return "%s%.0f" % (cur, v)
    return v


def nice_date(d):
    """'2026-09-16' -> '16 Sep 2026' (and it never wraps mid-date)."""
    try:
        from datetime import datetime as _dt
        return _dt.strptime(d, "%Y-%m-%d").strftime("%-d %b %Y")
    except Exception:
        return d or ""


def meta_page(p):
    """Who is advertising it, from Facebook's own ad library (read through Apify)."""
    mt = p.get("meta") or {}
    if not mt:
        return ""
    pat = mt.get("pattern") or ""
    col = {"a swarm, right now": RED, "crowded": RED, "a handful": AMBER, "one brand owns it": AMBER, "hardly anyone": GREEN, "nobody": GREEN}.get(pat, GREYC)
    out = ['<div class="page" id="%s-ads"><div class="hdr"><div><h2>%s</h2><div class="small muted">Who is advertising it on Facebook and Instagram right now? Live ads using the words “%s”, from Facebook\'s own ad library, %s.</div></div><div>%s</div></div>' % (
        esc(p.get("slug")), esc(p.get("name")), esc(mt.get("phrase")), esc(mt.get("checked")), pill(pat[:1].upper() + pat[1:], col))]
    if mt.get("takeaway") or mt.get("plain"):
        out.append('<p style="font-size:12.5pt;line-height:1.3"><b>%s</b></p>' % esc(mt.get("takeaway") or mt.get("plain")))
    out.append('<div class="tiles">%s</div>' % "".join('<div class="tile" style="background:#1a1a1a;min-height:14mm"><div class="t">%s</div><div class="v">%s</div></div>' % (esc(a), esc(b)) for a, b in [
        ("Live ads", "%s%s" % (mt.get("ads_loaded"), "+" if mt.get("capped") else "")), ("Different brands", "%s%s" % (mt.get("n_advertisers"), "+" if mt.get("capped") else "")),
        ("Biggest brand's share", "%d%%" % round(100 * (mt.get("biggest_advertiser_share") or 0))),
        (("Big shops over a year old", "%s of %s" % (mt.get("shops_over_a_year_old"), mt.get("shops_checked"))) if (mt.get("shops_checked") or 0) >= 3 else ("Brands new in last 2 months", mt.get("brands_new_in_last_2_months"))),
        ("Brands with an ad running 3+ months", mt.get("brands_advertising_3_plus_months"))]))
    if re.match(r"https?://", mt.get("library_url") or ""):
        out.append('<p style="margin:5pt 0 6pt"><a class="btn" href="%s">See every one of these ads live on Facebook &rarr;</a> <span class="small muted" style="margin-left:6pt">Facebook\'s own ad library, this exact search. Free, no login.</span></p>' % esc(mt["library_url"]))
    months = mt.get("brand_months") or {}
    by_brand = bool(months)
    if not months:
        months = mt.get("months") or {}
    if months:
        keys = sorted(months)
        if len(keys) > 12:                      # everything older than the last 11 months goes into one "earlier" bar
            early = sum(months[k] for k in keys[:-11])
            keys = keys[-11:]
            months = dict(months, earlier=early)
            keys = ["earlier"] + keys
        m = max([months[k] for k in keys] + [1])
        bars = "".join('<div style="flex:1;text-align:center"><div style="height:15mm;position:relative"><div style="position:absolute;bottom:0;left:15%%;width:70%%;height:%.1fmm;background:%s;border-radius:3px 3px 0 0"></div></div><div style="font-weight:700;font-size:9.5pt">%s</div><div class="small muted">%s</div></div>' % (
            max(0.5, 15.0 * months[k] / m), col if (i >= len(keys) - 2 and k != "earlier") else "#1a1a1a", months[k], esc("earlier" if k == "earlier" else k[5:] + "/" + k[2:4])) for i, k in enumerate(keys))
        sample = ("<p class='small' style='margin:0 0 3pt'><b>A sample, not the whole market:</b> the first %s live ads. Facebook has more, so every number here is a minimum.</p>" % esc(mt.get("ads_loaded"))) if mt.get("capped") else ""
        if by_brand:
            out.append('<h3>Oldest ad still running, brand by brand (month/year)</h3>%s<div style="display:flex;gap:4pt;margin:2pt 0 4pt">%s</div>'
                       '<p class="small">Each brand is counted once, in the month its oldest still-running ad began. Facebook only shows ads that are still running and brands replace them often, so a brand can be far older than its bar. The shop ages in the table below are the better guide to who is new.</p>' % (sample, bars))
        else:
            out.append('<h3>When today\'s live ads started (month/year)</h3>%s<div style="display:flex;gap:4pt;margin:2pt 0 4pt">%s</div>'
                       '<p class="small">How to read it: an ad still running from many months ago is an ad that pays. Brands replace their ads often, so most live ads are always recent: a tall last bar is normal and does not by itself mean a rush.</p>' % (sample, bars))
    tops = mt.get("top_advertisers") or []
    if tops:
        out.append("<h3>The brands advertising it, biggest first</h3><table class='ads'><tr><th style='width:15%'>Brand</th><th style='width:11%'>Their Facebook ads</th><th class='right' style='width:5%'>Live ads</th><th style='width:10%'>Oldest live ad</th><th style='width:10%'>Shop open since (at least)</th><th class='right' style='width:6%'>Page likes</th><th style='width:17%'>The page their ad opens</th><th>What the ad says</th></tr>")
        for t in (tops if FULL else tops[:5]):
            ads_link = ('<a href="%s">See their ads &rarr;</a>' % esc(t["their_ads"])) if t.get("their_ads") else ""
            pp = t.get("product_page") if re.match(r"https?://[^\s/]+\.[^\s/]+", t.get("product_page") or "") else None
            shop = ('<a href="%s">%s</a>' % (esc(pp or "https://" + t["shop"]), esc(t["shop"]))) if t.get("shop") else ""
            likes = "{:,}".format(t["page_likes"]) if isinstance(t.get("page_likes"), int) else ""
            pg = ""
            if (t.get("pages") or 0) > 1:
                pg = ("<br><span class='small muted'>%d Facebook pages: %s</span>" % (t["pages"], esc(", ".join(t.get("page_names") or [])[:70]))) if FULL else ("<br><span class='small muted'>%d Facebook pages</span>" % t["pages"])
            out.append(("<tr><td><b>%s</b>" + pg.replace("%", "%%") + "</td><td class='small' style='white-space:nowrap'>%s</td><td class='right'>%s</td><td style='white-space:nowrap'>%s</td><td style='white-space:nowrap'>%s</td><td class='right'>%s</td><td class='small'>%s</td><td class='small'>%s</td></tr>") % (
                esc(t.get("name")), ads_link, esc(t.get("ads")), esc(nice_date(t.get("oldest_live_ad"))), esc((t.get("shop_open_since") or "")[:4] and nice_date(t["shop_open_since"])[-8:]), likes, shop, esc("" if "{{" in (t.get("headline") or "") else clip(t.get("headline"), 70 if FULL else 45))))
        out.append("</table>")
        if not FULL and len(tops) > 5:
            out.append('<p class="small muted">Showing the 5 biggest. %d more are listed in the full report.</p>' % (len(tops) - 5))
    out.append('<p class="small muted">Source: Facebook Ad Library, %s. <a href="%s">Open this search on Facebook</a>. It counts ads that use these exact words, so a brand that describes the product differently will not appear.</p></div>' % (esc(mt.get("checked") or ""), esc(mt.get("library_url") or "#")))
    return "\n".join(out)


def ads_page(p):
    return ""          # retired: advertiser numbers come from meta_page


FULL = False      # set by --full: nothing capped, every table and screenshot in one file


def map_regions(p):
    """The colour a country gets on the map.
       With the photo search: RED = the same object is in a big chain there, AMBER = real copies (Temu, a local shop,
       or much cheaper on Amazon), LIGHT GREEN = only weak copies (AliExpress, or Amazon at about the brand's price), GREEN = nobody else found. Without it, falls back to the category check, with a crowded Amazon turning green amber."""
    if p.get("lens"):
        return [dict(r) for r in p["lens"]]
    am = {a.get("cc"): a.get("pressure") for a in (p.get("amazon") or [])}
    out = []
    for r in p.get("regions") or []:
        r = dict(r)
        if r.get("status") == "open" and am.get(r.get("cc")) == "high":
            r["status"] = "crowded"
            r["why"] = (r.get("why") or "") + " Amazon there is crowded."
        out.append(r)
    return out


def dots(regions):
    return '<span class="dots">%s</span>' % "".join(
        '<span style="background:%s" title="%s">%s</span>' % (status_color(r.get("status")), esc(r.get("why")), esc((r.get("cc") or "").upper()))
        for r in regions)


def product_page(p, base):
    fin = p.get("final") or {}
    verdict = fin.get("verdict", "?")
    regs = map_regions(p)
    cmp_ = p.get("compare") or {}
    fin0 = p.get("final") or {}
    load = (len(p.get("name") or "") + len(p.get("one_liner") or "") + sum(len(x) for x in (fin0.get("why") or [])) + len(fin0.get("risk") or "")
            + sum(len(x) for x in (fin0.get("next") or [])) + len(p.get("best_region") or "") + sum(len(r.get("why") or "") for r in (p.get("lens") or p.get("regions") or []))
            + len((p.get("compare") or {}).get("note") or ""))
    if p.get("supplier"):
        load += 250                         # five boxes across the top are taller than four
    squeeze = "" if load < 1500 else (" tight" if load < 1750 else " tighter")     # long write-ups still fit on one page
    out = ['<div class="page%s" id="%s">' % (squeeze, esc(p.get("slug")))]
    out.append('<div class="hdr"><div><h2>%s</h2><div class="small muted">%s · %s</div></div>'
               '<div style="text-align:right">%s<br><span class="score">%s</span><span class="small muted">/100 · %s confidence</span></div></div>'
               % (esc(p.get("name")), esc(p.get("brand")), esc(p.get("price")), pill(verdict, VERDICT_COLOR.get(verdict, "#555")),
                  esc(p.get("overall", "—")), esc(p.get("confidence", "?"))))
    if p.get("one_liner"):
        out.append("<p><b>%s</b></p>" % esc(p["one_liner"]))
    out.append(tiles(p))
    if regs:
        # A small map for the glance, and a table beside it, because the UK, Germany and New Zealand are too small to read on a map.
        order = {"open": 0, "weak": 1, "crowded": 2, "blocked": 3}
        rows = []
        for r in sorted(regs, key=lambda r: order.get((r.get("status") or "").lower(), 9)):
            lab, colr = STATUS.get((r.get("status") or "error").lower(), ("No data", "#777"))
            rows.append("<tr><td style='width:16%%'><b>%s</b></td><td style='width:14%%'><span class='chip' style='background:%s'>%s</span></td><td class='small'>%s</td><td class='small right' style='width:15%%;white-space:nowrap'>%s</td></tr>" % (
                esc(COUNTRY_NAMES.get(r.get("cc"), (r.get("cc") or "").upper())), colr, esc(lab), esc((r.get("why") or "").replace("*", "")), esc(ladder_short(r))))
        key = ("Red = in a big chain. Amber = a cheaper copy that shoppers will find or trust. Light green = copies exist but are hidden, weak or about the same price. Green = nobody else found."
               if p.get("lens") else "Red = a big chain sells it. Amber = cheap sellers or a crowded Amazon. Green = no chain, no cheap sellers, quiet Amazon.")
        out.append('<div class="mapRow"><div class="mapCol">%s</div><div class="ctyCol"><table class="cty"><tr><th>Country</th><th></th><th>What we found</th><th class="right">Brand vs cheapest copy</th></tr>%s</table></div></div>' % (world_map(regs), "".join(rows)))
        out.append("<p class='small muted' style='margin:0 0 3pt'>%s Grey = not checked.</p>" % key)
        if p.get("best_region"):
            out.append("<p><b>Best region:</b> %s</p>" % esc(p["best_region"]))
        if proof_line(p):
            out.append("<p><b>Proof the price gap is survivable:</b> %s</p>" % esc(proof_line(p)))
    bi, mi = img_data(cmp_.get("brand_image"), base), img_data(cmp_.get("match_image"), base)
    if cmp_ and (bi or mi):
        vc = {"identical": RED, "cosmetic": RED, "functional": AMBER, "different": GREEN}.get((cmp_.get("verdict") or "").lower(), "#777")
        out.append('<h3>Picture check &nbsp; %s <span class="muted" style="text-transform:none;letter-spacing:0">%s</span></h3>' % (
            pill((cmp_.get("verdict") or "?").title(), vc), esc(cmp_.get("note") or "")))
        out.append('<div class="sbs"><div>%s<div class="cap">%s</div></div><div>%s<div class="cap">%s</div></div></div>' % (
            '<img src="%s">' % bi if bi else "", esc(p.get("name")), '<img src="%s">' % mi if mi else "", esc(cmp_.get("match_name"))))
    out.append('<div class="why"><div><h3>Why %s</h3><ul>%s</ul></div><div><h3>Biggest risk</h3><p>%s</p><h3>What to do next</h3><ul>%s</ul></div></div>' % (
        esc(verdict.lower()), "".join("<li>%s</li>" % esc(w) for w in (fin.get("why") or [])), esc(fin.get("risk") or "—"),
        "".join("<li>%s</li>" % esc(w) for w in (fin.get("fastest_test") or []))))
    out.append("</div>")
    return "\n".join(out)


def asis_pages(p, base):
    out = []
    for a in (p.get("asis") or []):
        img = img_data(a.get("image"), base)
        out.append('<div class="page"><div class="hdr"><div><h2>%s — what a shopper in %s sees</h2><div class="small muted">Google search for “%s”, as seen from %s</div></div></div>' % (
            esc(p.get("name")), esc(a.get("label")), esc(a.get("query")), esc(a.get("label"))))
        out.append('<div class="asis"><div class="shot">%s</div><div class="side">' % ('<img src="%s">' % img if img else '<p class="muted">(page picture not available)</p>'))
        out.append("<h3 style='margin-top:0'>Top 5 results</h3><ol>")
        for t in (a.get("top5") or [])[:5]:
            k = t.get("kind") or ""
            cls = "chain" if "chain" in k else ("market" if "marketplace" in k else "")
            out.append('<li><b><a href="%s" style="color:#0b57d0;text-decoration:none">%s</a></b> <span class="kind %s">%s</span><br><span class="muted">%s</span></li>' % (esc(t.get("link") or "#"), esc(t.get("domain")), cls, esc(k), esc((t.get("title") or "")[:70])))
        out.append("</ol>")
        if len(a.get("top5") or []) < 3:
            out.append("<p class='muted'>Under the product strip Google showed mostly videos and unrelated pages for this keyword here. Read the picture and the Amazon box instead.</p>")
        if a.get("popular_products"):
            srcs = sorted({x.get("source") for x in a["popular_products"] if x.get("source")})
            out.append("<h3>In the “popular products” strip</h3><p>%s</p>" % esc(", ".join(srcs)))
        out.append(amazon_box(p, a.get("cc")))
        if a.get("paa"):
            out.append("<h3>People also ask</h3><ul>%s</ul>" % "".join("<li>%s</li>" % esc(q) for q in a["paa"][:4]))
        if a.get("takeaway"):
            out.append("<h3>What this tells us</h3><p><b>%s</b></p>" % esc(a["takeaway"]))
        out.append("</div></div></div>")
        if FULL:
            out.append(sellers_page(p, a.get("cc"), base))
    return "\n".join(out)


def _load(path):
    try:
        return json.load(open(path))
    except Exception:
        return None


def evidence_page(p, base):
    """FULL mode: everything else we hold on the product — every rival we compared, the picture-search hits, demand by place."""
    out = ['<div class="page"><div class="hdr"><h2>%s — the evidence</h2></div>' % esc(p.get("name"))]
    tr = p.get("trends") or []
    if tr:
        out.append("<h3>Demand by place (Google searches, last 2 years)</h3><table class='grid'><tr><th>Place</th><th>Direction</th><th>What it says</th><th>Line</th></tr>")
        for t in tr:
            ln = t.get("line") or []
            sp = spark(ln, 160, 24).replace('stroke="#fff"', 'stroke="#1a1a1a"') if ln else ""
            out.append("<tr><td>%s</td><td><b>%s</b></td><td>%s</td><td>%s</td></tr>" % (esc(t.get("label")), esc(t.get("direction")), esc(t.get("why")), sp))
        out.append("</table>")
    same = []
    for r in (p.get("lens") or []):
        for h in (r.get("same_object_listings") or []):
            if h.get("thumb_file") and h["thumb_file"] not in [x["thumb_file"] for x in same]:
                same.append(h)
    if same:
        out.append("<h3>The same object, as other shops show it</h3><div class='sbs' style='flex-wrap:wrap'>")
        bi = img_data((p.get("compare") or {}).get("brand_image"), base)
        out.append("<div style='flex:0 0 23%%'>%s<div class='cap'><b>The brand's product</b><br>%s</div></div>" % ('<img src="%s">' % bi if bi else "", esc(p.get("price"))))
        for h in same[:7]:
            im = img_data(h.get("thumb_file"), base)
            out.append("<div style='flex:0 0 23%%'>%s<div class='cap'><a href='%s'>%s</a><br>%s</div></div>" % ('<img src="%s">' % im if im else "", esc(h.get("link") or "#"), esc(h.get("source")), esc(h.get("price_text") or "")))
        out.append("</div>")
    out.append("</div>")
    return "\n".join(out)


def supplier_page(p, base):
    """The supply side: which supplier sites list the same object, what it costs, and what is left per sale."""
    sup = p.get("supplier") or {}
    sm = sup.get("summary") or {}
    if not sup:
        return ""
    out = ['<div class="page" id="%s-supply"><div class="hdr"><div><h2>%s</h2><div class="small muted">What it costs to buy. The shops map shows who you would compete with; this page shows whether you can get the product, and what is left after you pay for it.</div></div></div>' % (esc(p.get("slug")), esc(p.get("name")))]
    out.append('<p style="font-size:12.5pt;line-height:1.3"><b>%s</b></p>' % esc(sm.get("plain") or ""))
    if sm.get("status") == "priced" and sm.get("margin_pct") is not None:
        out.append('<div class="tiles">%s</div>' % "".join('<div class="tile" style="background:#1a1a1a;min-height:14mm"><div class="t">%s</div><div class="v">%s</div></div>' % (esc(a), esc(b)) for a, b in [
            ("Supplier price", "about US$%.0f" % sm["cost_usd"]), ("The brand sells it for", "about US$%.0f" % sm["brand_price_usd"]),
            ("Left per sale", "about US$%.0f" % sm["room_per_sale_usd"]), ("Margin", "%d%%" % sm["margin_pct"])]))
        out.append("<p class='small'>How to read it: <b>left per sale</b> is the most you could spend on ads to win one sale before you lose money. Payment fees, returns%s and your profit all have to come out of it too, so a healthy test needs ads to cost well under that.</p>" % ("" if sm.get("cost_includes_shipping") else ", shipping"))
    rows = sup.get("listings") or []
    if rows:
        out.append("<h3>Supplier listings for the same object</h3><table class='grid' style='font-size:8.8pt'><tr><th style='width:9%'></th><th style='width:15%'>Supplier</th><th style='width:14%'>Sells in</th><th style='width:15%'>Price</th><th>Listing</th></tr>")
        for l in rows:
            im = img_data(l.get("thumb_file"), base, 200)
            price = ""
            if l.get("price") is not None:
                price = "%s %.2f%s" % ((l.get("currency") or "usd").upper(), l["price"], (" + %.2f shipping" % l["shipping"]) if l.get("shipping") else "")
            elif l.get("price_seen_in_search"):
                price = "%s (seen in search)" % l["price_seen_in_search"].replace("*", "")
            else:
                price = "<span class='muted'>open to see</span>"
            out.append("<tr><td>%s</td><td><b>%s</b></td><td class='small'>%s</td><td>%s%s</td><td><a href='%s'>%s</a></td></tr>" % (
                ('<img src="%s" style="max-width:100%%;max-height:16mm">' % im) if im else "", esc(l.get("site")), esc(l.get("order_type")), price if "<span" in price else esc(price),
                ("<br><span class='small muted'>%s</span>" % esc(l["note"])) if l.get("note") else "", esc(l.get("link") or "#"), esc(clip(l.get("title") or l.get("site") or "open listing", 90))))
        out.append("</table>")
        out.append("<p class='small muted'>Supplier prices change daily and are often sale prices. AliExpress and CJ Dropshipping sell one at a time, which is what a dropshipper needs. Alibaba and Made-in-China quote prices for bulk orders.</p>")
    else:
        out.append("<p>No supplier listing turned up for this exact object in the photo search. Most products sold this way do have one, so look before you decide: search AliExpress by name, or use its search-by-picture with the brand's photo. If you truly cannot find it, it may be custom-made, and a sourcing agent is the next step.</p>")
    if sup.get("aliexpress_search"):
        out.append('<p><a class="btn" href="%s">Search AliExpress for it &rarr;</a></p>' % esc(sup["aliexpress_search"]))
    out.append("<h3>Before you order, ask the supplier</h3><ul><li>What is the total cost delivered to my customer's country, per unit?</li><li>How many days from order to the customer's door?</li><li>Can you send one sample first, and do you have the safety paperwork this product needs?</li></ul></div>")
    return "\n".join(out)


def lens_page(p, base):
    """Where the SAME OBJECT is sold, country by country, found by searching with the product's photo."""
    ln = p.get("lens") or []
    if not ln:
        return ""
    out = ['<div class="page" id="%s-lens"><div class="hdr"><div><h2>%s</h2><div class="small muted">Where the same object is already for sale. We searched with the product\'s photo in each country, then checked whether a shopper typing the product words would find each copy. Click any listing to open it.</div></div></div>' % (esc(p.get("slug")), esc(p.get("name")))]
    for r in ln:
        hits = r.get("same_object_listings") or []
        lab, colr = STATUS.get(r.get("status"), ("?", "#777"))
        out.append("<div class='keep'><h3 style='margin-top:9pt'>%s &nbsp;%s &nbsp;<span style='text-transform:none;letter-spacing:0;color:#333;font-size:10.5pt'>%s</span></h3>" % (
            esc(COUNTRY_NAMES.get(r.get("cc"), r.get("cc"))), pill(lab, colr), esc(r.get("why"))))
        if hits:
            def verdict_cell(h):
                if h.get("kind") == "big chain" and h.get("price_text"):
                    return "<b style='color:%s'>Big chain</b>" % RED
                if not h.get("strength"):
                    return ""
                return "<b style='color:%s'>%s</b><br><span class='muted'>%s</span>" % (
                    "#b26a00" if h["strength"] == "strong" else "#4f7f1f", "Real copy" if h["strength"] == "strong" else "Weak or hidden", esc(h.get("strength_why") or ""))
            ordered = sorted(hits, key=lambda h: (h.get("strength") != "strong", not h.get("found_by_words"), price_to_number_safe(h.get("price_text"))))
            out.append("<table class='grid' style='font-size:8.5pt'><tr><th style='width:19%%'>Shop</th><th style='width:10%%'>Price</th><th style='width:27%%'>Can a shopper find it?</th><th>Listing</th></tr>%s</table>" % "".join(
                "<tr><td>%s%s</td><td>%s</td><td>%s</td><td><a href='%s'>%s</a>%s</td></tr>" % (
                    esc(h.get("source")), " <span class='kind chain'>big chain</span>" if h.get("kind") == "big chain" else "", esc((h.get("price_text") or "").replace("*", "")), verdict_cell(h),
                    esc(h.get("link") or "#"), esc((h.get("title") or "")[:80]),
                    (" <span class='muted'>(%s reviews%s)</span>" % (esc(h.get("reviews")), (", " + esc(h["bought"])) if h.get("bought") else "")) if h.get("reviews") else "") for h in (ordered if FULL else ordered[:6])))
            if ladder_text(r):
                out.append("<p class='small muted' style='margin:2pt 0 0'>%s</p>" % esc(ladder_text(r)))
        out.append("</div>")
    out.append("</div>")
    if FULL and p.get("lens_sheet"):
        first = p["lens_sheet"]
        more = []
        for i in range(2, 9):                      # big searches are split over several sheets: _sheet_2.jpg, _sheet_3.jpg ...
            cand = first.replace("_sheet.jpg", "_sheet_%d.jpg" % i)
            if cand != first and os.path.exists(cand if os.path.isabs(cand) else os.path.join(base, cand)):
                more.append(cand)
        for k, sh in enumerate([first] + more):
            pic = img_data(sh, base, 1500)
            if pic:
                out.append("<div class='page'><div class='hdr'><div><h2>%s</h2><div class='small muted'>Everything the photo search returned%s. The listings that are the same object are the ones in the country tables.</div></div></div><img src='%s' style='width:100%%'></div>" % (
                    esc(p.get("name")), (" (sheet %d of %d)" % (k + 1, len(more) + 1)) if more else "", pic))
    return "\n".join(out)


def sellers_page(p, cc, base):
    """FULL mode: the complete Google Shopping seller list and Amazon's first page for one country, all clickable."""
    slug = p.get("slug")
    g = _load(os.path.join(base, "grid", "%s_%s.json" % (slug, cc)))
    a = _load(os.path.join(base, "amazon", "%s_%s_amazon.json" % (slug, cc)))
    out = ['<div class="page"><div class="hdr"><h2>%s — every seller in %s</h2></div>' % (esc(p.get("name")), esc(COUNTRY_NAMES.get(cc, cc.upper())))]
    rows = (g or {}).get("shopping_results") or []
    if rows:
        out.append("<h3>Google Shopping: all %d listings (searched: “%s”)</h3><table class='grid' style='font-size:7.6pt'><tr><th>Seller</th><th>Listing</th><th class='right'>Price</th><th class='right'>Rating</th><th class='right'>Reviews</th></tr>" % (len(rows), esc(((g or {}).get("search_parameters") or {}).get("q", ""))))
        for r in rows:
            out.append("<tr><td>%s</td><td><a href='%s'>%s</a></td><td class='right'>%s</td><td class='right'>%s</td><td class='right'>%s</td></tr>" % (
                esc(r.get("source")), esc(shop_listing_link(r)), esc((r.get("title") or "")[:88]), esc(r.get("price") or ""), esc(r.get("rating") or ""), esc(r.get("reviews") or "")))
        out.append("</table>")
    arows = ((a or {}).get("organic_results") or [])[:20]
    if arows:
        out.append("<h3>Amazon (%s): first %d listings</h3><table class='grid' style='font-size:7.6pt'><tr><th>Listing</th><th class='right'>Price</th><th class='right'>Rating</th><th class='right'>Reviews</th><th>Bought last month</th></tr>" % (esc(((a or {}).get("search_parameters") or {}).get("amazon_domain", "")), len(arows)))
        for r in arows:
            out.append("<tr><td><a href='%s'>%s</a></td><td class='right'>%s</td><td class='right'>%s</td><td class='right'>%s</td><td>%s</td></tr>" % (
                esc(r.get("link_clean") or r.get("link") or "#"), esc((r.get("title") or "")[:95]), esc(r.get("price") or ""), esc(r.get("rating") or ""), esc(r.get("reviews") or ""), esc(r.get("bought_last_month") or "")))
        out.append("</table>")
    out.append("</div>")
    return "\n".join(out)


def detail_pages(p, base):
    sc, regs, cmp_ = p.get("scores") or {}, p.get("regions") or [], p.get("compare") or {}
    snap = p.get("snapshot") or {}
    out = ['<div class="page" id="%s-detail" style="font-size:9.3pt"><div class="hdr"><h2>%s — the scorecard</h2></div>' % (esc(p.get("slug")), esc(p.get("name")))]
    out.append("<h3>Snapshot</h3><table class='grid'>")
    for k, lab in [("ad_days", "Ads"), ("store_platform", "Store"), ("store_launched", "Store launched"), ("store_products", "Catalogue")]:
        if p.get(k):
            out.append("<tr><td style='width:30%%'>%s</td><td>%s</td></tr>" % (lab, esc(p[k])))
    for k, lab in [("icp", "Who buys it"), ("job", "Job to be done"), ("cogs", "Landed cost"), ("margin", "Gross margin"), ("claims", "Claims"), ("demoable", "Demo-able?")]:
        if snap.get(k):
            out.append("<tr><td>%s</td><td>%s</td></tr>" % (lab, esc(snap[k])))
    out.append("</table><h3>Scorecard (1–10)</h3><table class='grid'>")
    for k, lab in [("saturated", "Saturated (10 = bad)"), ("margin", "Gross margin"), ("viral", "Viral + visual"), ("pain", "Pain / need"), ("differentiation", "Differentiation")]:
        out.append("<tr><td style='width:60%%'>%s</td><td class='right'><b>%s</b></td></tr>" % (lab, esc(sc.get(k, "—"))))
    out.append("</table>")
    if p.get("gates"):
        out.append("<h3>Gates</h3><table class='grid'>%s</table>" % "".join(
            "<tr><td style='width:30%%'>%s</td><td style='width:12%%'>%s</td><td>%s</td></tr>" % (esc(g.get("name")), esc((g.get("result") or "").title()), esc(g.get("why"))) for g in p["gates"]))
    if regs:
        out.append("<h3>How crowded the CATEGORY is, by country (a word search for the type of product, not this exact object)</h3><table class='grid'><tr><th>Country</th><th>Category</th><th>Why</th><th class='right'>Sellers</th><th class='right'>Cheapest</th><th class='right'>Typical</th><th>Most reviewed</th></tr>%s</table>" % "".join(
            "<tr><td><b>%s</b></td><td>%s</td><td>%s</td><td class='right'>%s</td><td class='right'>%s</td><td class='right'>%s</td><td>%s</td></tr>" % (
                esc((r.get("cc") or "").upper()), pill({"blocked": "A chain sells this type", "crowded": "Crowded", "open": "Quiet"}.get((r.get("status") or "").lower(), "?"), status_color(r.get("status"))), esc(r.get("why")),
                esc(r.get("sellers", "")), esc(r.get("cheapest", "")), esc(r.get("typical", "")), esc(r.get("top", ""))) for r in regs))
    if cmp_.get("ledger"):
        out.append("<h3>Difference ledger</h3><table class='grid'><tr><th>Feature</th><th>Brand</th><th>Chain match</th><th>In the ads?</th></tr>%s</table>" % "".join(
            "<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (esc(l.get("feature")), esc(l.get("brand")), esc(l.get("match")), esc(l.get("in_ads"))) for l in cmp_["ledger"]))
    if p.get("angles"):
        out.append("<h3>Five angles</h3><ul>%s</ul>" % "".join("<li>%s</li>" % esc(a) for a in p["angles"]))
    out.append("</div>")
    return "\n".join(out)


def build_html(rep, base, detail=False, part="main"):
    run = rep.get("run") or {}
    prods = rep.get("products") or []
    by_slug = {p.get("slug"): p for p in prods}
    order = rep.get("ranking") or [p.get("slug") for p in prods]
    global HAS_SUPPLY
    HAS_SUPPLY = any(p.get("supplier") for p in prods)
    out = ["<!doctype html><html><head><meta charset='utf-8'><title>%s</title><style>%s</style></head><body>" % (esc(run.get("title", "Product Research")), CSS)]
    front_zoom = "" if len(order) <= 8 else (' style="zoom:%.2f"' % max(0.62, 1.0 - 0.036 * (len(order) - 7)))     # many products: shrink the front page so the whole ranking stays on one page
    out.append('<div class="page"%s><h1>%s</h1><p class="muted small">%s · %s · checked in %s.</p>' % (
        front_zoom, esc(run.get("title", "Product Research")), esc(run.get("date") or date.today().isoformat()), esc(run.get("prepared_for", "")),
        esc(", ".join(COUNTRY_NAMES.get(c, c.upper()) for c in run.get("countries", [])))))
    best = by_slug.get(order[0]) if order else None
    if best:
        bv = (best.get("final") or {}).get("verdict", "?")
        bimg = img_data((best.get("compare") or {}).get("brand_image") or best.get("image"), base)
        label = "The verdict" if len(order) == 1 else "Your best bet" if bv == "Test now" else ("Closest to a win (none is a clear yes)" if bv == "Backlog" else "None of these is a win. The least bad:")
        out.append('<div class="hero">%s<div><div class="k">%s</div><div class="n">%s &nbsp;%s</div><div>%s</div></div></div>' % (
            '<img src="%s">' % bimg if bimg else "", esc(label), esc(best.get("name")), pill(bv, VERDICT_COLOR.get(bv, "#555")),
            esc(rep.get("headline") or best.get("one_liner") or "")))
    out.append('<h3>How to read this</h3><div class="how">'
               '<div><b>Demand</b>Are more people searching for it than a year ago (last 2 years only), and is Amazon selling units? Green = rising.</div>'
               '<div><b>Same product in shops</b>A PHOTO search in each country, then a check of what a shopper finds by typing the product words. Red = in a big chain. Amber = a cheaper copy shoppers will find or trust. Light green = copies exist but are hidden or about the same price. Green = nobody else.</div>'
               '<div><b>Amazon</b>Are there listings with thousands of reviews? Green = not yet.</div>'
               '<div><b>Advertisers</b>How many brands run Facebook ads for it today, and when did they start? One brand for months = proof. Dozens in the last few weeks = a swarm.</div>' + ("<div><b>Cost to buy</b>What a supplier such as AliExpress charges for it, and what that leaves you per sale. Green = 70% or more left.</div>" if HAS_SUPPLY else "") + '</div>')
    out.append("<table class='lead'><tr><th>#</th><th></th><th style='width:46%%'>Product</th><th>Verdict</th><th class='right'>Score</th><th style='text-align:center'>Demand</th><th style='text-align:center'>In shops</th><th style='text-align:center'>Amazon</th><th style='text-align:center'>Ads</th>%s</tr>" % ("<th style='text-align:center'>Cost to buy</th>" if HAS_SUPPLY else ""))
    for i, sl in enumerate(order, 1):
        p = by_slug.get(sl)
        if not p:
            continue
        v = (p.get("final") or {}).get("verdict", "?")
        im = img_data((p.get("compare") or {}).get("brand_image") or p.get("image"), base)
        out.append("<tr><td rowspan='2' style='border-bottom:1px solid #ccc'>%d</td><td rowspan='2' style='border-bottom:1px solid #ccc'>%s</td><td style='border-bottom:none;padding-bottom:0'><b>%s</b> <span class='small muted'>%s · %s</span></td><td style='border-bottom:none;padding-bottom:0'>%s</td><td class='right' style='border-bottom:none;padding-bottom:0'><b>%s</b></td>%s</tr>"
                   "<tr><td colspan='8' class='small' style='padding-top:1pt;border-bottom:1px solid #ccc;color:#333'>%s</td></tr>" % (
            i, '<img src="%s">' % im if im else "", esc(p.get("name")), esc(p.get("brand")), esc(p.get("price")), pill(v, VERDICT_COLOR.get(v, "#555")),
            esc(p.get("overall", "—")), sigdots(p).replace("<td style=\"", "<td style=\"border-bottom:none;padding-bottom:0;"), esc(clip(first_thought(p.get("one_liner")), 400 if len(order) <= 8 else 95))))
    out.append("</table>")
    out.append("<p class='key'>Verdicts: %s worth a small paid test now &nbsp; %s interesting, but only with a twist &nbsp; %s don't. Scores are out of 100.</p>" % (
        pill("Test now", GREEN), pill("Backlog", AMBER), pill("Avoid", RED)))
    mode = run.get("mode", "full")
    out.append('<div class="assume"><b>Checked on %s.</b> Markets move fast, so check again before you spend money. ' % esc(run.get("date") or ""))
    if run.get("assumptions"):
        out.append("Keep in mind: %s." % esc("; ".join(run["assumptions"])))
    out.append("</div>")
    out.append("</div>")
    if part == "web":
        def sec(title, hint, body, open_=False):
            return ('<details class="sec"%s><summary>%s<span class="hint">%s</span></summary>%s</details>' % (" open" if open_ else "", esc(title), esc(hint), body)) if (body or "").strip() else ""
        nav = "".join('<option value="%s">%d. %s (%s)</option>' % (esc(sl), i, esc(clip(by_slug[sl].get("name"), 44)), esc((by_slug[sl].get("final") or {}).get("verdict", "?"))) for i, sl in enumerate(order, 1) if sl in by_slug)
        bar = ('<div class="topbar"><a href="#top">%s</a><select onchange="if(this.value){location.hash=\'p-\'+this.value;openFor(\'p-\'+this.value)}"><option value="">Jump to a product…</option>%s</select>'
               '<button onclick="allDetails(true)">Open everything</button><button onclick="allDetails(false)">Close everything</button></div>' % (esc(run.get("title", "Product Research")), nav))
        out[0] = out[0].replace("</style>", WEB_CSS + "</style><script>" + WEB_JS + "</script>").replace("<body>", "<body><a id='top'></a>" + bar)
        front = "\n".join(out)
        for sl in order:
            front = front.replace("href='#%s'" % sl, "href='#p-%s'" % sl).replace('href="#%s"' % sl, 'href="#p-%s"' % sl)
        body = [front]
        for i, sl in enumerate(order, 1):
            pr = by_slug.get(sl)
            if not pr:
                continue
            v = (pr.get("final") or {}).get("verdict", "?")
            mt = pr.get("meta") or {}
            n_real = sum(1 for r in (pr.get("lens") or []) if r.get("status") in ("crowded", "blocked"))
            inner = [product_page(pr, base).replace('id="%s"' % esc(sl), 'id="%s-verdict"' % esc(sl), 1),
                     sec("Who is advertising it", "%s brands · %s" % (mt.get("n_advertisers", "?"), mt.get("pattern") or "not checked"), meta_page(pr) or ads_page(pr)),
                     sec("Where the same object is sold", "a real copy or a big chain in %d of %d countries · every listing clickable" % (n_real, len(pr.get("lens") or [])), lens_page(pr, base)),
                     sec("What it costs to buy", ((pr.get("supplier") or {}).get("summary") or {}).get("status", "") and ("supplier listings: %s · %s" % (((pr.get("supplier") or {}).get("summary") or {}).get("found", 0), ((pr.get("supplier") or {}).get("summary") or {}).get("status", ""))), supplier_page(pr, base)),
                     sec("The evidence", "demand, and the matching pictures", evidence_page(pr, base).replace('<div class="page">', '<div class="page" id="%s-evidence">' % esc(sl), 1)),
                     sec("What a shopper sees, country by country", "the real Google page, top results and every seller", asis_pages(pr, base).replace('<div class="page">', '<div class="page" id="%s-countries">' % esc(sl), 1)),
                     sec("The scorecard", "scores, gates and selling angles", detail_pages(pr, base))]
            body.append('<details class="prod" id="p-%s"%s><summary><span class="rank">%d</span><span class="grow">%s</span>%s<span class="sc">%s</span></summary>%s</details>' % (
                esc(sl), " open" if i == 1 else "", i, esc(pr.get("name")), pill(v, VERDICT_COLOR.get(v, "#555")), esc(pr.get("overall", "")), "\n".join(x for x in inner if x)))
        body.append("</body></html>")
        return "\n".join(body)
    if part == "full":
        toc = ['<div class="page"><h2>Contents</h2><p class="muted">Click any line to jump there. Each product has the same sections.</p><table class="grid">']
        for i, s in enumerate(order, 1):
            pr = by_slug.get(s)
            if not pr:
                continue
            v = (pr.get("final") or {}).get("verdict", "?")
            toc.append("<tr><td style='width:5%%'>%d</td><td><a href='#%s'><b>%s</b></a> %s</td><td class='small'><a href='#%s'>verdict</a> · <a href='#%s-detail'>scorecard</a> · <a href='#%s-ads'>who advertises it</a> · <a href='#%s-lens'>where the same object is sold</a>%s · <a href='#%s-evidence'>evidence</a> · <a href='#%s-countries'>country pages</a></td></tr>" % (
                i, esc(s), esc(pr.get("name")), pill(v, VERDICT_COLOR.get(v, "#555")), esc(s), esc(s), esc(s), esc(s), (" · <a href='#%s-supply'>what it costs to buy</a>" % esc(s)) if pr.get("supplier") else "", esc(s), esc(s)))
        toc.append("</table></div>")
        out.append("".join(toc))
        for s in order:
            pr = by_slug.get(s)
            if not pr:
                continue
            out.append(product_page(pr, base))
            out.append(detail_pages(pr, base))
            out.append(meta_page(pr) or ads_page(pr))
            out.append(lens_page(pr, base))
            out.append(supplier_page(pr, base))
            out.append(evidence_page(pr, base).replace('<div class="page">', '<div class="page" id="%s-evidence">' % esc(s), 1))
            out.append(asis_pages(pr, base).replace('<div class="page">', '<div class="page" id="%s-countries">' % esc(s), 1))
        out.append("</body></html>")
        return "\n".join(out)
    for s in order:
        if by_slug.get(s):
            out.append(product_page(by_slug[s], base))
            out.append(meta_page(by_slug[s]) or ads_page(by_slug[s]))
    if part == "main":
        pass
    elif any((by_slug.get(s) or {}).get("asis") for s in order):
        out = out[:1]
        out.append('<div class="page divider"><h1>Appendix</h1><p class="muted">What a shopper actually sees on Google and Amazon, country by country.<br>Skim these. The answers are on the pages before this one.</p></div>')
        for s in order:
            if by_slug.get(s):
                out.append(asis_pages(by_slug[s], base))
    if detail and part == "main":
        for s in order:
            if by_slug.get(s):
                out.append(detail_pages(by_slug[s], base))
    out.append("</body></html>")
    return "\n".join(out)


WEB_CSS = """
html { scroll-behavior: smooth; } body { background: #f3f3f1; margin: 0; }
.page { width: auto !important; height: auto !important; min-height: 0 !important; max-width: 1000px; margin: 0 auto; padding: 14px 20px 18px; box-shadow: none; page-break-after: auto; background: #fff; }
.tight, .tighter { zoom: 1 !important; }
.topbar { position: sticky; top: 0; z-index: 9; background: #1a1a1a; color: #fff; padding: 7px 14px; display: flex; gap: 10px; align-items: center; font-size: 13px; flex-wrap: wrap; }
.topbar a { color: #fff; text-decoration: none; font-weight: 700; } .topbar select { font-size: 13px; padding: 3px 6px; max-width: 340px; }
.topbar button { font-size: 12px; padding: 3px 9px; border-radius: 5px; border: 1px solid #777; background: #333; color: #fff; cursor: pointer; }
details.prod { max-width: 1040px; margin: 12px auto; background: #fff; border: 1px solid #d9d9d6; border-radius: 10px; overflow: hidden; }
details.prod > summary { list-style: none; cursor: pointer; padding: 12px 18px; display: flex; gap: 12px; align-items: center; font-size: 17px; font-weight: 700; }
details.prod > summary::-webkit-details-marker, details.sec > summary::-webkit-details-marker { display: none; }
details.prod > summary .rank { color: #888; font-weight: 600; min-width: 22px; } details.prod > summary .grow { flex: 1; } details.prod > summary .sc { font-size: 20px; }
details.prod > summary:after, details.sec > summary:after { content: "+"; font-weight: 700; color: #888; font-size: 20px; margin-left: 8px; }
details[open].prod > summary:after, details[open].sec > summary:after { content: "\\2212"; }
details.prod[open] > summary { border-bottom: 1px solid #e4e4e0; background: #fafaf8; }
details.sec { margin: 0 14px 10px; border: 1px solid #e2e2de; border-radius: 8px; background: #fff; }
details.sec > summary { list-style: none; cursor: pointer; padding: 9px 14px; font-weight: 700; font-size: 14px; display: flex; justify-content: space-between; align-items: center; }
details.sec > summary span.hint { font-weight: 400; color: #777; font-size: 12.5px; margin-left: 10px; flex: 1; }
details.sec[open] > summary { border-bottom: 1px solid #ecece8; }
.asis .shot img { max-height: none !important; } img { max-width: 100%; }
@media (max-width: 760px) { .tiles, .mapRow, .how, .sbs { flex-wrap: wrap; } .mapCol { flex: 0 0 100% !important; } }
"""
WEB_JS = """
function openFor(id){ var el=document.getElementById(id); while(el){ if(el.tagName==='DETAILS') el.open=true; el=el.parentElement; } var t=document.getElementById(id); if(t) t.scrollIntoView(); }
window.addEventListener('hashchange', function(){ openFor(location.hash.slice(1)); });
window.addEventListener('DOMContentLoaded', function(){ if(location.hash) openFor(location.hash.slice(1));
  document.querySelectorAll('a[href^="#"]').forEach(function(a){ a.addEventListener('click', function(){ openFor(a.getAttribute('href').slice(1)); }); }); });
function allDetails(open){ document.querySelectorAll('details').forEach(function(d){ d.open=open; }); }
"""

def check_links(html):
    """Every link in the report must lead somewhere. Jump links need a matching page marker; web links need a real address.
    Returns a list of problems (empty = all good)."""
    ids = set(re.findall(r"""\bid=["']([^"']+)["']""", html))
    problems = []
    for h in re.findall(r"""href=["']([^"']*)["']""", html):
        if h.startswith("#"):
            if h[1:] not in ids:
                problems.append("jump link with no target: " + h)
        elif not re.match(r"https?://[^\s/]+\.[^\s/]+", h):
            problems.append("web link that is not a real address: " + (h or "(empty)"))
    targets = set(h[1:] for h in re.findall(r"""href=["\'](#[^"\']*)["\']""", html))
    all_ids = re.findall(r"""\bid=["\']([^"\']+)["\']""", html)
    for i in sorted(targets):
        if all_ids.count(i) > 1:
            problems.append("two pages share the marker: " + i)
    return sorted(set(problems))


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    jpath = os.path.abspath(sys.argv[1])
    base = os.path.dirname(jpath)
    rep = json.load(open(jpath))
    global FULL, IMG_CAP, WEB_DIR
    if "--web" in sys.argv:
        FULL, IMG_CAP = True, 760
        if "--no-pdf" not in sys.argv:
            sys.argv.append("--no-pdf")
        if "--web-folder" in sys.argv:          # lighter: pictures as separate files in report-web/ (serve_report.py can serve it)
            IMG_CAP, WEB_DIR = 900, os.path.join(base, "report-web")
            os.makedirs(WEB_DIR, exist_ok=True)
            jobs = [("report-web/index", "web")]
        else:                                   # one file the member can open or send to someone
            jobs = [("report-web", "web")]
    elif "--full" in sys.argv:
        FULL = True
        jobs = [("report-full", "full")]
    else:
        jobs = [("report", "main")]
        if any(p.get("asis") for p in rep.get("products") or []):
            jobs.append(("report-appendix", "appendix"))
    for stem, part in jobs:
        _build_one(rep, base, stem, part)


def _build_one(rep, base, stem, part):
    html_out = os.path.join(base, stem + ".html")
    page_html = build_html(rep, base, detail="--detail" in sys.argv, part=part)
    # a listing that came back with no web address is shown as plain text, never as a link that goes nowhere
    page_html = re.sub(r"""<a href=["']#["'][^>]*>(.*?)</a>""", r"\1", page_html, flags=re.S)
    open(html_out, "w", encoding="utf-8").write(page_html)
    print("wrote:", html_out)
    bad = check_links(page_html)
    n_links = len(re.findall(r"href=", page_html))
    if bad:
        print("LINK CHECK FAILED: %d of %d links are broken. Fix these before showing the report:" % (len(bad), n_links))
        for b in bad[:40]:
            print("   -", b)
    else:
        print("link check: all %d links lead somewhere" % n_links)
    if "--no-pdf" in sys.argv:
        return
    pdf_out = os.path.join(base, stem + ".pdf")
    if not chrome_path():
        print("Chrome not found — open %s and use Print → Save as PDF." % html_out)
        return
    print("saving the PDF (about 20 seconds for a big report)...")
    sys.stdout.flush()
    res = run_chrome(["--no-pdf-header-footer", "--print-to-pdf=" + pdf_out, "file://" + html_out], pdf_out, max_wait=150)
    if res == "ok":
        print("wrote:", pdf_out)
    else:
        print("PDF failed (%s) — open %s and use Print → Save as PDF." % (res, html_out))

if __name__ == "__main__":
    main()
