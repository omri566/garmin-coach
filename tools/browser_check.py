"""Headless-browser smoke test: load the dashboard and capture console errors.

Loads the running app, exercises the tabs + run selector, and prints every
console error / page exception so UI regressions are caught without a human.

Usage: .venv/bin/python tools/browser_check.py [url]
"""
from __future__ import annotations

import sys
import time

from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8050"


def main() -> int:
    errors: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.on("console", lambda m: errors.append(f"[console.{m.type}] {m.text}")
                if m.type in ("error", "warning") else None)
        page.on("pageerror", lambda e: errors.append(f"[pageerror] {e}"))

        def scrape_overlay():
            # Dash debug error overlay (red "Errors" box) — capture its messages.
            for sel in (".dash-error-card__message", ".dash-fe-error__title",
                        ".dash-error-card__content"):
                for el in page.locator(sel).all():
                    try:
                        txt = el.inner_text(timeout=500).strip()
                        if txt:
                            errors.append(f"[debug-overlay] {txt}")
                    except Exception:
                        pass

        page.goto(URL, wait_until="networkidle")
        time.sleep(2)  # let callbacks settle

        # Switch to Deep Analysis tab.
        try:
            page.get_by_text("Deep Analysis", exact=True).first.click()
            time.sleep(2)
        except Exception as e:  # noqa: BLE001
            errors.append(f"[test] could not click Deep Analysis: {e}")

        # Change the run selector to a different option.
        try:
            page.locator("#an-run input, #an-run").first.click()
            time.sleep(0.5)
            opts = page.locator("[role=option]")
            if opts.count() > 1:
                opts.nth(1).click()
                time.sleep(2)
        except Exception as e:  # noqa: BLE001
            errors.append(f"[test] could not change run selector: {e}")

        # Coach tab (display only — don't click the slow generate buttons).
        try:
            page.get_by_text("Coach", exact=True).first.click()
            time.sleep(1.5)
        except Exception as e:  # noqa: BLE001
            errors.append(f"[test] could not click Coach: {e}")

        # Back to Overview.
        try:
            page.get_by_text("Overview", exact=True).first.click()
            time.sleep(1)
        except Exception as e:  # noqa: BLE001
            errors.append(f"[test] could not click Overview: {e}")

        scrape_overlay()
        browser.close()

    # De-duplicate while preserving order.
    seen, uniq = set(), []
    for e in errors:
        if e not in seen:
            seen.add(e)
            uniq.append(e)

    if uniq:
        print(f"FAIL — {len(uniq)} unique console issue(s):")
        for e in uniq:
            print("  •", e)
        return 1
    print("PASS — no console errors/warnings.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
