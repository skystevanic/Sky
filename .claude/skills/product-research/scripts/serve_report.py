#!/usr/bin/env python3
"""Serve the interactive report on this computer only, so it can open in a side panel or a browser tab.

  python3 serve_report.py <run>            (serves <run>/report-web on http://localhost:8765, or the next free port)

Nothing leaves the computer: it listens on 127.0.0.1 only. Stop it with Ctrl+C (or stop the background job).
A side panel that refuses big local files (the Claude desktop app's limit is 512 KB) opens this address happily.
"""
import functools
import http.server
import os
import socket
import sys


def free_port(start=8765):
    for port in range(start, start + 40):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return 0


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    folder = os.path.join(os.path.abspath(sys.argv[1]), "report-web")
    if not os.path.exists(os.path.join(folder, "index.html")):
        print("No interactive report here yet. Build it first: python3 build_report.py <run>/report.json --web")
        sys.exit(1)
    port = int(sys.argv[2]) if len(sys.argv) > 2 else free_port()
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=folder)
    print("Interactive report: http://localhost:%d/   (this computer only; Ctrl+C to stop)" % port)
    sys.stdout.flush()
    http.server.ThreadingHTTPServer(("127.0.0.1", port), handler).serve_forever()


if __name__ == "__main__":
    main()
