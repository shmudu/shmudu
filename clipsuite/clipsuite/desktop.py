"""ClipSuite as a Mac app: the editor in its own window (pywebview), with the phone link still working.

  clipsuite app                       run it from Terminal
  bash setup/make_mac_app.sh          build ClipSuite.app for your Dock / Applications

While the window is open the Mac is kept awake, and jobs keep running. Closing the window
stops ClipSuite (and any render in progress).
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import threading
import webbrowser

from . import server


def main(port: int = 8765) -> None:
    httpd, local, phone = server.start("0.0.0.0", port)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    print(f"ClipSuite running at {local}\nPhone (same Wi-Fi): {phone}", flush=True)

    awake = None
    if platform.system() == "Darwin" and shutil.which("caffeinate"):
        awake = subprocess.Popen(["caffeinate", "-i", "-w", str(os.getpid())])

    try:
        import webview  # type: ignore
    except ImportError:
        print("pywebview isn't installed (pip install pywebview); opening your browser instead.", flush=True)
        webbrowser.open(local)
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
    else:
        webview.create_window("ClipSuite", local, width=1240, height=900, min_size=(420, 600))
        webview.start()  # returns when the window is closed
    finally:
        httpd.shutdown()
        if awake:
            awake.terminate()


if __name__ == "__main__":
    main()
