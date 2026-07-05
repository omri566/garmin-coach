"""Desktop launcher — the entry point the double-click .app runs.

Starts the dashboard on a free local port and opens the browser. On first launch
the app shows the onboarding landing page (connect Garmin + Claude); after that
it goes straight to the dashboard.

Run locally without packaging:  python -m garmin_coach.desktop
"""
from __future__ import annotations

import socket
import threading
import webbrowser

from garmin_coach import config


def _free_port(preferred: int = 8050) -> int:
    for port in (preferred, 8051, 8052, 8060, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return s.getsockname()[1]
            except OSError:
                continue
    return preferred


def main() -> None:
    config.ensure_dirs()
    from garmin_coach.dashboard.app import app

    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    print(f"Garmin Coach → {url}")
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
