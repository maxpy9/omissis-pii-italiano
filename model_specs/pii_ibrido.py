# -*- coding: utf-8 -*-
"""
Rilevatore PII italiano - sistema ibrido.
  1) regex + checksum -> identificatori strutturati (IBAN, codice fiscale, carta, P.IVA)
  2) modello encoder  -> nomi, indirizzi, citta', testo libero
Il layer regex ha SEMPRE la precedenza: dove trova qualcosa, il modello viene ignorato.

Uso:
    from pii_ibrido import PIIDetector
    d = PIIDetector("/content/drive/MyDrive/pii-italiano-v2")
    for e in d.analizza("Mi chiamo Marco Rossi, IBAN IT60X0542811101000000123456"):
        print(e)
    print(d.anonimizza("Mi chiamo Marco Rossi"))
"""
import re
from transformers import pipeline

_ODD = {"0":1,"1":0,"2":5,"3":7,"4":9,"5":13,"6":15,"7":17,"8":19,"9":21,
        "A":1,"B":0,"C":5,"D":7,"E":9,"F":13,"G":15,"H":17,"I":19,"J":21,
        "K":2,"L":4,"M":18,"N":20,"O":11,"P":3,"Q":6,"R":8,"S":12,"T":14,
        "U":16,"V":10,"W":22,"X":25,"Y":24,"Z":23}
_EVEN = {c: (int(c) if c.isdigit() else ord(c) - 65)
         for c in "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"}
_REM = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _cifre(s):
    return re.sub(r"\D", "", s)


def luhn(s):
    d = [int(c) for c in _cifre(s)]
    if not (13 <= len(d) <= 19):
        return False
    tot, par = 0, len(d) % 2
    for i, n in enumerate(d):
        if i % 2 == par:
            n *= 2
            if n > 9:
                n -= 9
        tot += n
    return tot % 10 == 0


def iban_ok(s):
    s = re.sub(r"\s", "", s).upper()
    if not re.fullmatch(r"[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}", s):
        return False
    r = s[4:] + s[:4]
    return int("".join(str(int(c, 36)) for c in r)) % 97 == 1


def cf_ok(s):
    s = s.upper()
    if not re.fullmatch(r"[A-Z0-9]{16}", s):
        return False
    tot = sum(_ODD[c] if i % 2 == 0 else _EVEN[c] for i, c in enumerate(s[:15]))
    return _REM[tot % 26] == s[15]


def piva_ok(s):
    s = _cifre(s)
    if len(s) != 11:
        return False
    tot = 0
    for i, c in enumerate(s[:10]):
        n = int(c)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        tot += n
    return (10 - tot % 10) % 10 == int(s[10])


REGOLE = [
    ("CODICE_FISCALE",
     re.compile(r"\b[A-Za-z]{6}[0-9]{2}[A-Za-z][0-9]{2}[A-Za-z][0-9]{3}[A-Za-z]\b"), cf_ok),
    ("IBAN",
     re.compile(r"\b[A-Za-z]{2}[0-9]{2}[A-Za-z0-9]{11,30}\b"), iban_ok),
    ("CARTA_CREDITO",
     re.compile(r"[0-9][0-9 \-]{11,21}[0-9]"), luhn),
    ("PARTITA_IVA",
     re.compile(r"\b[0-9]{11}\b"), piva_ok),
    ("EMAIL",
     re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b"), lambda s: True),
]


class PIIDetector:
    def __init__(self, percorso, device=-1, soglia=0.5):
        self.soglia = soglia
        self.nlp = pipeline("token-classification", model=percorso,
                            tokenizer=percorso, aggregation_strategy="simple",
                            device=device)

    def _regex(self, testo):
        trovati = []
        for nome, rx, check in REGOLE:
            for m in rx.finditer(testo):
                if check(m.group()):
                    trovati.append({"tipo": nome, "valore": m.group().strip(),
                                    "inizio": m.start(), "fine": m.end(),
                                    "fonte": "regex", "score": 1.0})
        trovati.sort(key=lambda x: (x["inizio"], -(x["fine"] - x["inizio"])))
        out, fine = [], -1
        for t in trovati:
            if t["inizio"] >= fine:
                out.append(t)
                fine = t["fine"]
        return out

    def analizza(self, testo):
        det = self._regex(testo)
        coperti = set()
        for d in det:
            coperti.update(range(d["inizio"], d["fine"]))
        for e in self.nlp(testo):
            if e["score"] < self.soglia:
                continue
            if set(range(e["start"], e["end"])) & coperti:
                continue
            det.append({"tipo": e["entity_group"], "valore": e["word"],
                        "inizio": e["start"], "fine": e["end"],
                        "fonte": "modello", "score": float(e["score"])})
        det.sort(key=lambda x: x["inizio"])
        return det

    def anonimizza(self, testo):
        out = testo
        for e in sorted(self.analizza(testo), key=lambda x: -x["inizio"]):
            out = out[:e["inizio"]] + "[" + e["tipo"] + "]" + out[e["fine"]:]
        return out
