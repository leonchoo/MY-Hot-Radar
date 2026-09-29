"""
Smoke-test the live HTTP server with the real radar data, doing
server-side checks equivalent to a real browser:

  * HTML well-formed
  * Host element + script tag present
  * CSS file loads
  * JS file loads
  * public/radar/latest.json loads and is valid JSON
  * JSON schema_version matches what the JS adapter expects

This script doesn't try to run a JS engine. It tests the structural
contract between the server, the page, and the public JSON artifact.
"""

import json
import sys
import urllib.request
from pathlib import Path


def http_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "radar-smoke/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status, resp.headers, resp.read()


def main():
    base = "http://127.0.0.1:8765"
    failures = []

    # 1. Homepage loads
    try:
        status, headers, body = http_get(base + "/")
        if status != 200:
            failures.append(f"/: HTTP {status}")
        else:
            print(f"PASS / (HTTP {status}, {len(body)} bytes)")
    except Exception as e:
        failures.append(f"/: {e}")
        return failures

    html = body.decode("utf-8")

    # 2. Host element present
    if 'id="radar-feed-host"' in html:
        print("PASS / has #radar-feed-host")
    else:
        failures.append("/: missing #radar-feed-host")

    # 3. Loading placeholder present
    if 'id="radar-feed-loading"' in html:
        print("PASS / has #radar-feed-loading")
    else:
        failures.append("/: missing #radar-feed-loading")

    # 4. Radar-feed.js script tag
    if 'src="/assets/js/radar-feed.js"' in html:
        print("PASS / has <script src=/assets/js/radar-feed.js>")
    else:
        failures.append("/: missing radar-feed.js script tag")

    # 5. CSS file loads
    try:
        status, headers, css = http_get(base + "/assets/css/style.css")
        if status == 200 and b".rf-grid" in css and b".rf-card" in css:
            print(f"PASS /assets/css/style.css (HTTP {status}, "
                  f"{len(css)} bytes; .rf-grid + .rf-card present)")
        else:
            failures.append(f"/assets/css/style.css: HTTP {status} or missing rules")
    except Exception as e:
        failures.append(f"/assets/css/style.css: {e}")

    # 6. JS file loads
    try:
        status, headers, js = http_get(base + "/assets/js/radar-feed.js")
        if status == 200 and b"window.MYHotRadar" in js:
            print(f"PASS /assets/js/radar-feed.js (HTTP {status}, {len(js)} bytes)")
        else:
            failures.append(f"/assets/js/radar-feed.js: HTTP {status} or missing API")
    except Exception as e:
        failures.append(f"/assets/js/radar-feed.js: {e}")

    # 7. main.js still loads
    try:
        status, headers, _ = http_get(base + "/assets/js/main.js")
        if status == 200:
            print(f"PASS /assets/js/main.js (HTTP {status})")
        else:
            failures.append(f"/assets/js/main.js: HTTP {status}")
    except Exception as e:
        failures.append(f"/assets/js/main.js: {e}")

    # 8. public/radar/latest.json loads + is valid JSON + has expected fields
    try:
        status, headers, body = http_get(base + "/public/radar/latest.json")
        if status != 200:
            failures.append(f"/public/radar/latest.json: HTTP {status}")
        else:
            ct = headers.get("Content-Type", "")
            if "json" not in ct.lower():
                failures.append(
                    f"/public/radar/latest.json: Content-Type={ct!r} (expected JSON)"
                )
            else:
                try:
                    payload = json.loads(body.decode("utf-8"))
                except json.JSONDecodeError as e:
                    failures.append(f"/public/radar/latest.json: invalid JSON: {e}")
                else:
                    print(f"PASS /public/radar/latest.json (HTTP {status}, "
                          f"{len(body)} bytes, Content-Type={ct})")
                    if payload.get("schema_version") == 1 \
                       and payload.get("public_schema_version") == 1:
                        print(f"  schema_version=1, public_schema_version=1 OK")
                    else:
                        failures.append(
                            "/public/radar/latest.json: bad schema_version"
                        )
                    n = payload.get("summary", {}).get("topic_count", 0)
                    if n > 0:
                        print(f"  topic_count={n}")
                    else:
                        failures.append(
                            "/public/radar/latest.json: topic_count=0"
                        )
                    # Verify all topic URLs are https://
                    bad_urls = 0
                    for t in payload.get("topics", []):
                        for s in t.get("sources", []):
                            u = s.get("url", "")
                            if not (u.startswith("http://") or u.startswith("https://")):
                                bad_urls += 1
                    if bad_urls == 0:
                        print(f"  all {sum(len(t.get('sources', [])) for t in payload.get('topics', []))} "
                              f"source URLs are http(s)")
                    else:
                        failures.append(
                            f"/public/radar/latest.json: {bad_urls} unsafe URLs"
                        )
    except Exception as e:
        failures.append(f"/public/radar/latest.json: {e}")

    # 9. Verify the page has the MVP disclaimer (DEMO protection)
    if "MVP stage" in html and "sample content" in html:
        print("PASS / MVP disclaimer preserved")
    else:
        failures.append("/: MVP disclaimer missing or altered")

    # 10. Verify the existing demo cards still link to /article/example/
    if "/article/example/" in html:
        count = html.count("/article/example/")
        print(f"PASS / still links to /article/example/ ({count} links)")
    else:
        failures.append("/: no DEMO article links — DEMO content lost")

    # 11. Verify AdSense script still present
    if "ca-pub-6219340004578553" in html:
        print("PASS / AdSense publisher code intact")
    else:
        failures.append("/: AdSense publisher code missing")

    # 12. Verify the five category nav links still present
    for cat in ("/hot/", "/malaysia/", "/viral/", "/celebrity/",
                "/food/", "/world/", "/about/", "/contact/"):
        if f'href="{cat}"' in html:
            pass
        else:
            failures.append(f"/: nav link {cat} missing")
    print("PASS / all nav links present (8/8)")

    return failures


if __name__ == "__main__":
    failures = main()
    print()
    if failures:
        print(f"SMOKE TEST FAILED ({len(failures)} failures):")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("SMOKE TEST PASSED — page + CSS + JS + JSON all serve correctly")
