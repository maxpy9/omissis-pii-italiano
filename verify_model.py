# -*- coding: utf-8 -*-
import sys
import time
import json

MODEL_DIR = r"C:\omissis\pii-italiano-v2"
sys.path.insert(0, MODEL_DIR)

from pii_ibrido import PIIDetector

t0 = time.perf_counter()
d = PIIDetector(MODEL_DIR, device=-1)
t_load = time.perf_counter() - t0
print(f"Caricamento modello completato in {t_load:.2f} s\n")

frasi = [
    "Mi chiamo Marco Rossi, IBAN IT60X0542811101000000123456, tel 333 4567890.",
    "Codice fiscale RSSMRA85T10A562S, email marco.rossi@example.it, P.IVA 12345678903.",
    "Oggi piove molto e domani forse smette: qui non c'e' nessun dato personale.",
]

for i, frase in enumerate(frasi, 1):
    t1 = time.perf_counter()
    ris = d.analizza(frase)
    dt = (time.perf_counter() - t1) * 1000
    print(f"--- Frase {i} ({dt:.1f} ms) ---")
    print(f"Testo: {frase}")
    print(f"Rilevamenti ({len(ris)}):")
    for r in ris:
        print(" ", json.dumps(r, ensure_ascii=False))
    print()
