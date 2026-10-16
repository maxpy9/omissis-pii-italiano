# -*- coding: utf-8 -*-
"""
FASE 4.2 — Comando singolo di avvio che fa partire il server locale (127.0.0.1:8000)
e apre automaticamente il browser non appena il modello e' pronto.
"""
import threading
import time
import urllib.request
import webbrowser
import uvicorn

from app import app

URL = "http://127.0.0.1:8000"


def _apri_browser_quando_pronto():
    for _ in range(60):
        try:
            with urllib.request.urlopen(f"{URL}/api/health", timeout=1) as resp:
                if resp.status == 200:
                    print(f"[Omissis] Apertura browser su {URL}")
                    webbrowser.open(URL)
                    return
        except Exception:
            time.sleep(0.5)


if __name__ == "__main__":
    threading.Thread(target=_apri_browser_quando_pronto, daemon=True).start()
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
