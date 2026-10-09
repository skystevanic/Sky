#!/usr/bin/env python3
"""Check my setup — says in plain words what works and what's missing. Never prints the SerpApi code."""
import json
import sys
import urllib.parse

from common import get_serpapi_key, key_looks_valid, fetch_json, chrome_path

ok = True
lines = []

v = sys.version_info
if v < (3, 9):
    ok = False
    lines.append("✗ Python is too old (need 3.9 or newer). Install from python.org and try again.")
else:
    lines.append("✓ Python %d.%d works." % (v.major, v.minor))

key, src = get_serpapi_key()
mode = "no-extras"
if not key:
    ok = False
    lines.append("✗ SerpApi: not connected. It is required: it runs the Google, Amazon and photo searches from each country. "
                 "Sign up free at serpapi.com, copy the code from serpapi.com/manage-api-key, and save it (README-for-members.md, step 3).")
elif not key_looks_valid(key):
    lines.append("✗ SerpApi code found in %s but it doesn't look right (should be 64 letters and digits, nothing else). "
                 "Copy it again with the copy button and re-save it." % src)
else:
    try:
        d = fetch_json("https://serpapi.com/account.json?api_key=" + urllib.parse.quote(key), timeout=30)
        left = d.get("total_searches_left")
        lines.append("✓ SerpApi works (%s, %s, %s searches left this month). Country checks will run. FULL mode."
                     % (src, d.get("plan_name", "plan?"), left))
        mode = "full"
        if isinstance(left, int) and left < 12:
            lines.append("• Only %d searches left. One product across six countries needs 6. Consider upgrading or fewer countries." % left)
    except Exception as e:
        lines.append("✗ SerpApi code found in %s but SerpApi rejected it (%s). Re-copy it from serpapi.com/manage-api-key and re-save."
                     % (src, str(e)[:80]))

try:
    from meta_ads_apify import get_token as _apify_token, call as _apify_call, API as _APIFY
    tk, tsrc = _apify_token()
    if tk:
        me = _apify_call("GET", _APIFY + "/users/me", tk)
        if me.get("error"):
            lines.append("✗ Apify code found in %s but Apify rejected it. Re-copy it from console.apify.com (Settings → API & Integrations)." % tsrc)
        else:
            lines.append("✓ Apify works (%s). Reading Facebook's ad library costs about half a US cent per ad, and every run stops itself." % tsrc)
    else:
        ok = False
        lines.append("✗ Apify: not connected. It is required: it reads Facebook's public ad library so we never touch Facebook from your computer. Sign up at apify.com, copy the Personal API token from Settings → API & Integrations, and save it (README-for-members.md, step 4).")
except Exception:
    pass

cp = chrome_path()
if cp:
    lines.append("✓ Chrome found — reports will be saved as PDF.")
else:
    lines.append("• Chrome not found — reports will be saved as a web page (HTML). Open it and use Print → Save as PDF. "
                 "Installing Google Chrome fixes this.")

try:
    import PIL  # noqa
    lines.append("✓ Pillow found — side-by-side pictures will be built as one image.")
except Exception:
    lines.append("• Pillow (a picture helper) not found — side-by-side pictures will be shown as two images. Optional.")

print("\n".join(lines))
print("\nREADY: both services work." if ok else "\nNOT READY: fix the lines marked ✗ above, then run this check again.")
sys.exit(0 if ok else 1)
