"""Shared helpers for the product-research skill. Python 3.9+, standard library only."""
import glob
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".product-research")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
KEYCHAIN_SERVICE = "serpapi-api-key"

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)


def get_serpapi_key():
    """Return (key, source) or (None, reason). Never print the key."""
    if platform.system() == "Darwin":
        try:
            out = subprocess.run(["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
                                 capture_output=True, text=True, timeout=10)
            k = out.stdout.strip()
            if out.returncode == 0 and k:
                return k, "Mac Keychain"
        except Exception:
            pass
    k = os.environ.get("SERPAPI_KEY", "").strip()
    if k:
        return k, "environment setting SERPAPI_KEY"
    if os.path.exists(CONFIG_FILE):
        try:
            k = (json.load(open(CONFIG_FILE)).get("serpapi_key") or "").strip()
            if k:
                return k, CONFIG_FILE
        except Exception:
            pass
    return None, "no SerpApi code found (Keychain, SERPAPI_KEY, or ~/.product-research/config.json)"


def key_looks_valid(k):
    return bool(k) and bool(re.fullmatch(r"[0-9a-zA-Z]{64}", k))


def fetch(url, timeout=60, binary=False):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    return data if binary else data.decode("utf-8", "replace")


def fetch_json(url, timeout=60):
    return json.loads(fetch(url, timeout=timeout))


def chrome_path():
    cands = []
    sysname = platform.system()
    if sysname == "Darwin":
        cands += ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                  "/Applications/Chromium.app/Contents/MacOS/Chromium",
                  "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                  "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"]
    elif sysname == "Windows":
        for base in [os.environ.get("PROGRAMFILES", r"C:\Program Files"),
                     os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
                     os.environ.get("LOCALAPPDATA", "")]:
            if base:
                cands += [os.path.join(base, "Google", "Chrome", "Application", "chrome.exe"),
                          os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe")]
    for name in ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge"]:
        p = shutil.which(name)
        if p:
            cands.append(p)
    # Cloud sessions: the Chromium that Playwright ships with.
    pw = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers")
    cands += sorted(glob.glob(os.path.join(pw, "chromium-*", "*", "chrome")), reverse=True)
    for c in cands:
        if c and os.path.exists(c):
            return c
    return None


def price_to_number(p):
    """'$49.99' -> 49.99 ; '45,98 €' -> 45.98 ; '1.499,00 €' -> 1499.0 ; 'NZ$1,299.00' -> 1299.0"""
    if not p:
        return None
    m = re.search(r"\d[\d.,]*", str(p))
    if not m:
        return None
    s = m.group(0)
    if re.search(r",\d{2}$", s):          # decimal comma (European)
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def slugify(s):
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")
    return s[:40] or "product"


def eprint(*a):
    print(*a, file=sys.stderr)


def run_chrome(args, out_file, max_wait=90):
    """Chrome often fails to close itself after printing or taking a picture, which made every build sit for minutes.
    Start it, watch for the output file to appear and stop growing, then close Chrome ourselves."""
    import tempfile, time as _t
    cp = chrome_path()
    if not cp:
        return "Chrome not found"
    prof = tempfile.mkdtemp(prefix="pr-chrome-")
    if os.path.exists(out_file):
        os.remove(out_file)
    # Chrome refuses to start as the root user (as in cloud sessions) without --no-sandbox.
    root = ["--no-sandbox"] if hasattr(os, "geteuid") and os.geteuid() == 0 else []
    proc = subprocess.Popen([cp] + root + ["--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check", "--user-data-dir=" + prof] + args,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    t0, last, steady = _t.time(), -1, 0
    while _t.time() - t0 < max_wait:
        _t.sleep(0.7)
        if proc.poll() is not None:
            break
        size = os.path.getsize(out_file) if os.path.exists(out_file) else 0
        steady = steady + 1 if (size > 1000 and size == last) else 0
        last = size
        if steady >= 3:
            break
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
    shutil.rmtree(prof, ignore_errors=True)
    return "ok" if os.path.exists(out_file) and os.path.getsize(out_file) > 1000 else "Chrome did not produce the file"


def shop_listing_link(row):
    """Google Shopping results no longer carry the shop's own web address, only a Google page that re-opens the CATEGORY search.
    A search for the listing's exact title plus the seller's name lands on that listing (or the seller's page for it) far more
    often, so that is what the report links to. A real shop address, when there is one, always wins."""
    import urllib.parse as _u
    link = row.get("link") or ""
    if link and "google." not in link:
        return link
    title, seller = (row.get("title") or "").strip(), re.sub(r"\s+-\s+.*$", "", (row.get("source") or "")).strip()
    if not title:
        return row.get("product_link") or link or "#"
    return "https://www.google.com/search?q=" + _u.quote_plus('"%s" %s' % (title[:110], seller))
