# -*- coding: utf-8 -*-
"""
Motore di post-processing, anonimizzazione reversibile e de-anonimizzazione.
"""
import re
from typing import List, Dict, Any, Tuple


# Pattern strutturati aggiuntivi (telefoni anche in formato WHOIS +39.3886924177, date ISO/IT, indirizzi)
_EXTRA_REGEX_RULES: List[Tuple[str, re.Pattern]] = [
    (
        "DATETIME",
        re.compile(r"\b\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?\b"),
    ),
    (
        "DATE",
        re.compile(r"\b(?:\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4})\b"),
    ),
    (
        "PHONENUMBER",
        re.compile(
            r"(?<!\w)(?:\+39[\.\s\-]?\d{2,4}[\.\s\-]?\d{5,8}|\+\d{1,3}\.\d{6,12}|(?:\+39\s*)?3\d{2}[\s\.\-]?\d{6,7}|0\d{1,3}[\s\.\-]?\d{5,8})(?!\w)"
        ),
    ),
    (
        "ADDRESS",
        re.compile(
            r"\b(?:viale|via|piazza|piazzale|corso|largo|vicolo|strada|contrada|borgo|lungotevere|lungomare|circonvallazione)\s+[A-Za-zÀ-ÿ0-9'\.\-\s]{2,45}?(?:\s*[-,]\s*\d{5}\s+[A-Za-zÀ-ÿ'\-\s]{2,25}(?:\s*\([A-Z]{2}\))?|\s*,\s*\d{1,4}[A-Za-z]?\b)",
            re.IGNORECASE,
        ),
    ),
]

# Tipi che per natura DEVONO contenere cifre (o simboli specifici); se il modello
# etichetta solo lettere (es. "Reg" in "RegCode" come PHONENUMBER), e' un falso positivo.
_TIPI_NUMERICI = {
    "PHONENUMBER",
    "PHONEIMEI",
    "CREDITCARDNUMBER",
    "CREDITCARDCVV",
    "ACCOUNTNUMBER",
    "ZIPCODE",
    "PIN",
    "AGE",
    "AMOUNT",
    "BUILDINGNUMBER",
    "SSN",
}

# Tipi di entita' che ha senso propagare su occorrenze identiche nel testo
_TIPI_PROPAGABILI = {
    "FIRSTNAME",
    "LASTNAME",
    "MIDDLENAME",
    "COMPANYNAME",
    "USERNAME",
    "EMAIL",
    "CODICE_FISCALE",
    "PARTITA_IVA",
    "IBAN",
    "PHONENUMBER",
}


def _normalizza_chiave(valore: str, tipo: str) -> Tuple[str, str]:
    """Chiave case-insensitive e senza spazi ai bordi (e spazi multipli interni normalizzati)."""
    return (tipo.upper().strip(), re.sub(r"\s+", " ", valore.strip()).lower())


def _stessa_parola(testo: str, fine_a: int, inizio_b: int, val_b: str) -> bool:
    """
    Determina se due span toccano o spezzano la stessa parola (es. 'Pale' + '##strina').
    """
    if val_b.startswith("##"):
        if inizio_b <= fine_a:
            return True
    if inizio_b < fine_a:
        return True
    if inizio_b == fine_a:
        if fine_a > 0 and inizio_b < len(testo):
            c_left = testo[fine_a - 1]
            c_right = testo[inizio_b]
            if c_left.isalnum() and c_right.isalnum():
                return True
    return False


def _espandi_a_parola_intera(testo: str, inizio: int, fine: int, tipo: str) -> Tuple[int, int]:
    """
    Se il modello ha predetto solo un frammento subword (es. 'Mann' dentro 'Mannucci' dove '##ucci'
    aveva score < 0.5, oppure '##6-11-13...' dentro '2026-11-13...'), espande gli indici fino ai
    confini naturali del token continuo nel testo.
    """
    n = len(testo)
    s, e = inizio, fine

    if tipo in ("DATE", "DATETIME", "TIME"):
        # Per date/orari espandi su cifre, '-', '/', ':', '+', '.', 'T', 'Z'
        while s > 0 and (testo[s - 1].isalnum() or testo[s - 1] in "-/:+.TZ"):
            s -= 1
        while e < n and (testo[e].isalnum() or testo[e] in "-/:+.TZ"):
            e += 1
        return s, e

    # Per parole alfabetiche/alfanumeriche: se il taglio cade in mezzo a caratteri alfanumerici contigui,
    # espandi fino al confine della parola
    while s > 0 and testo[s - 1].isalnum() and testo[s].isalnum():
        s -= 1
    while e < n and e > 0 and testo[e - 1].isalnum() and testo[e].isalnum():
        e += 1
    return s, e


def _rilevamento_modello_valido(valore: str, tipo: str) -> bool:
    """
    Scarta falsi positivi evidenti del modello (es. 'Reg' classificato come PHONENUMBER).
    """
    v = valore.strip()
    if len(v) <= 2:
        return False

    t = tipo.upper()
    if t in _TIPI_NUMERICI:
        cifre = sum(1 for c in v if c.isdigit())
        if t == "PHONENUMBER" and cifre < 6:
            return False
        if cifre == 0:
            return False

    if t == "EMAIL" and "@" not in v:
        return False

    if t in ("DATE", "DATETIME", "TIME"):
        cifre = sum(1 for c in v if c.isdigit())
        if cifre == 0 and not re.search(
            r"\b(?:gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre|luned[iì]|marted[iì]|mercoled[iì]|gioved[iì]|venerd[iì]|sabato|domenica)\b",
            v,
            re.IGNORECASE,
        ):
            return False

    return True


def post_processa_rilevamenti(testo: str, raw_dets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Corregge i bug noti del modello prima di sostituire:
      1. Aggiunge rilevamenti strutturati ad alta precisione (telefoni +39..., date ISO, indirizzi completi).
      2. Rimuove il prefisso '##' dai frammenti, unisce gli span sulla stessa parola ed espande
         i subword troncati dal filtro di soglia (es. 'Mann' -> 'Mannucci', '##6-11-13...' -> '2026-11-13...').
      3. Scarta i rilevamenti del modello incoerenti col tipo (es. 'Reg' come PHONENUMBER) o di 1-2 caratteri.
      4. In caso di sovrapposizione fa vincere SEMPRE fonte='regex' su fonte='modello';
         tra span della stessa fonte tiene lo span piu' lungo.
    """
    regex_dets: List[Dict[str, Any]] = []
    model_dets: List[Dict[str, Any]] = []

    for d in (raw_dets or []):
        copia = dict(d)
        copia["inizio"] = int(copia["inizio"])
        copia["fine"] = int(copia["fine"])
        copia["score"] = float(copia.get("score", 1.0))
        val_raw = str(copia.get("valore", ""))
        copia["_had_hash"] = val_raw.startswith("##")
        pulito = val_raw.lstrip("#").strip()
        slice_testo = testo[copia["inizio"]:copia["fine"]]
        copia["valore"] = slice_testo if slice_testo else pulito

        if copia.get("fonte") == "regex":
            regex_dets.append(copia)
        else:
            model_dets.append(copia)

    # Aggiungi regole regex strutturate supplementari (telefoni, date ISO, indirizzi italiani)
    for nome_regola, rx in _EXTRA_REGEX_RULES:
        for m in rx.finditer(testo):
            regex_dets.append({
                "tipo": nome_regola,
                "valore": m.group().strip(),
                "inizio": m.start(),
                "fine": m.end(),
                "fonte": "regex",
                "score": 1.0,
            })

    # 1. Ordina i rilevamenti del modello per inizio, poi lunghezza decrescente
    model_dets.sort(key=lambda x: (x["inizio"], -(x["fine"] - x["inizio"])))

    # 2. Unisci gli span adiacenti o sovrapposti del modello che toccano la stessa parola
    merged_model: List[Dict[str, Any]] = []
    for cur in model_dets:
        if not merged_model:
            merged_model.append(cur)
            continue
        prev = merged_model[-1]
        raw_val_cur = "##" + cur["valore"] if cur.get("_had_hash") else cur["valore"]

        if cur["inizio"] < prev["fine"]:
            len_prev = prev["fine"] - prev["inizio"]
            len_cur = cur["fine"] - cur["inizio"]
            span_unito = testo[min(prev["inizio"], cur["inizio"]):max(prev["fine"], cur["fine"])]
            if not re.search(r"\s", span_unito):
                nuovo_inizio = min(prev["inizio"], cur["inizio"])
                nuovo_fine = max(prev["fine"], cur["fine"])
                if len_cur > len_prev or (len_cur == len_prev and cur["score"] > prev["score"]):
                    prev["tipo"] = cur["tipo"]
                prev["inizio"] = nuovo_inizio
                prev["fine"] = nuovo_fine
                prev["valore"] = testo[nuovo_inizio:nuovo_fine]
                prev["score"] = max(prev["score"], cur["score"])
            else:
                if len_cur > len_prev or (len_cur == len_prev and cur["score"] > prev["score"]):
                    merged_model[-1] = cur
        elif _stessa_parola(testo, prev["fine"], cur["inizio"], raw_val_cur):
            len_prev = prev["fine"] - prev["inizio"]
            len_cur = cur["fine"] - cur["inizio"]
            if len_cur > len_prev * 2 and cur["score"] > prev["score"]:
                prev["tipo"] = cur["tipo"]
            prev["fine"] = cur["fine"]
            prev["valore"] = testo[prev["inizio"]:prev["fine"]]
            prev["score"] = (prev["score"] + cur["score"]) / 2.0
        else:
            merged_model.append(cur)

    # 2b. Espandi i rilevamenti del modello ai confini della parola intera se erano subword troncati
    #     (es. "Mann" in "Mannucci" o "##6-11-13..." in "2026-11-13...")
    expanded_model: List[Dict[str, Any]] = []
    for m in merged_model:
        s_exp, e_exp = _espandi_a_parola_intera(testo, m["inizio"], m["fine"], m["tipo"])
        # Se pero' la parola intera e' un composto tipo "RegCode" e il modello aveva preso solo "Reg"
        # come PHONENUMBER, la validazione successiva (_rilevamento_modello_valido) lo scartera' comunque.
        m["inizio"] = s_exp
        m["fine"] = e_exp
        m["valore"] = testo[s_exp:e_exp]
        if expanded_model and m["inizio"] <= expanded_model[-1]["fine"]:
            prev = expanded_model[-1]
            nuovo_s = min(prev["inizio"], m["inizio"])
            nuovo_e = max(prev["fine"], m["fine"])
            prev["inizio"] = nuovo_s
            prev["fine"] = nuovo_e
            prev["valore"] = testo[nuovo_s:nuovo_e]
            prev["score"] = max(prev["score"], m["score"])
        else:
            expanded_model.append(m)

    # 3. Risolvi sovrapposizioni tra regex_dets stessi (tieni il piu' lungo)
    regex_dets.sort(key=lambda x: (x["inizio"], -(x["fine"] - x["inizio"])))
    merged_regex: List[Dict[str, Any]] = []
    for r in regex_dets:
        if not merged_regex:
            merged_regex.append(r)
            continue
        prev = merged_regex[-1]
        if r["inizio"] < prev["fine"]:
            if (r["fine"] - r["inizio"]) > (prev["fine"] - prev["inizio"]):
                merged_regex[-1] = r
        else:
            merged_regex.append(r)

    # 4. Fai vincere SEMPRE fonte='regex' su fonte='modello' in caso di sovrapposizione,
    #    e scarta i rilevamenti modello invalidi o di 1-2 caratteri.
    final_dets: List[Dict[str, Any]] = list(merged_regex)
    for m in expanded_model:
        m.pop("_had_hash", None)
        val_clean = m["valore"].replace("##", "").strip()
        m["valore"] = testo[m["inizio"]:m["fine"]].replace("##", "")
        if not _rilevamento_modello_valido(val_clean, m["tipo"]):
            continue
        overlaps_regex = any(
            not (m["fine"] <= r["inizio"] or m["inizio"] >= r["fine"])
            for r in merged_regex
        )
        if overlaps_regex:
            continue
        final_dets.append(m)

    for r in final_dets:
        r.pop("_had_hash", None)

    final_dets.sort(key=lambda x: x["inizio"])

    # 5. Propaga i valori gia' rilevati con alta confidenza (es. un nome proprio riconosciuto in un punto
    #    del testo ma perso dal modello in un'altra frase) SOLO su parole autonome (non unite da trattini).
    coperti = set()
    for d in final_dets:
        coperti.update(range(d["inizio"], d["fine"]))

    valori_noti: Dict[str, Dict[str, Any]] = {}
    for d in final_dets:
        if d["tipo"].upper() not in _TIPI_PROPAGABILI:
            continue
        if d.get("fonte") != "regex" and float(d.get("score", 0.0)) < 0.75:
            continue
        v_clean = d["valore"].strip()
        if len(v_clean) >= 3 and v_clean.lower() not in valori_noti:
            valori_noti[v_clean.lower()] = d

    aggiunti: List[Dict[str, Any]] = []
    for norm_v, ref_d in valori_noti.items():
        val_orig = ref_d["valore"].strip()
        # Evita match parziali dentro token separati da trattino o punto (es. REGISTER-REG)
        pat = re.compile(r"(?<![\w\-])" + re.escape(val_orig) + r"(?![\w\-])", re.IGNORECASE)
        for m in pat.finditer(testo):
            s, e = m.start(), m.end()
            if not (set(range(s, e)) & coperti):
                coperti.update(range(s, e))
                aggiunti.append({
                    "tipo": ref_d["tipo"],
                    "valore": testo[s:e],
                    "inizio": s,
                    "fine": e,
                    "fonte": ref_d["fonte"],
                    "score": ref_d["score"],
                })

    if aggiunti:
        final_dets.extend(aggiunti)
        final_dets.sort(key=lambda x: x["inizio"])

    return final_dets


def applica_anonimizzazione(
    testo: str,
    rilevamenti: List[Dict[str, Any]],
    mappatura_esistente: Dict[str, str] | None = None,
    esclusi_indices: List[int] | None = None,
) -> Tuple[str, Dict[str, str], List[Dict[str, Any]]]:
    """
    Sostituisce i rilevamenti non esclusi con segnaposto numerati reversibili:
      - Ogni valore distinto riceve [TIPO_1], [TIPO_2], ecc.
      - Lo stesso valore (case-insensitive, trim spazi ai bordi) riceve SEMPRE lo stesso segnaposto.
      - Sostituzione eseguita dagli offset piu' alti verso i piu' bassi.
    Restituisce: (testo_anonimizzato, mappatura_aggiornata, rilevamenti_arricchiti)
    """
    mappatura: Dict[str, str] = dict(mappatura_esistente) if mappatura_esistente else {}
    esclusi_set = set(esclusi_indices or [])

    val_to_placeholder: Dict[str, str] = {}
    contatori_tipo: Dict[str, int] = {}

    for ph, orig_val in mappatura.items():
        m = re.match(r"^\[([A-Z0-9_]+)_(\d+)\]$", ph.strip())
        if m:
            t_name = m.group(1)
            idx_num = int(m.group(2))
            contatori_tipo[t_name] = max(contatori_tipo.get(t_name, 0), idx_num)
        norm_v = orig_val.strip().lower()
        if norm_v not in val_to_placeholder:
            val_to_placeholder[norm_v] = ph

    dets_ordinati = sorted(enumerate(rilevamenti), key=lambda pair: pair[1]["inizio"])
    arricchiti: List[Dict[str, Any]] = []

    for idx_orig, d in dets_ordinati:
        item = dict(d)
        item["id_rilevamento"] = idx_orig
        item["escluso"] = idx_orig in esclusi_set
        val_originale = testo[item["inizio"]:item["fine"]]
        item["valore"] = val_originale
        norm_v = val_originale.strip().lower()

        if item["escluso"]:
            item["segnaposto"] = val_to_placeholder.get(norm_v, None)
            arricchiti.append(item)
            continue

        if norm_v in val_to_placeholder:
            ph = val_to_placeholder[norm_v]
        else:
            tipo_clean = re.sub(r"[^A-Z0-9_]", "_", str(item["tipo"]).upper().strip())
            prossimo = contatori_tipo.get(tipo_clean, 0) + 1
            contatori_tipo[tipo_clean] = prossimo
            ph = f"[{tipo_clean}_{prossimo}]"
            val_to_placeholder[norm_v] = ph
            mappatura[ph] = val_originale.strip() if val_originale.strip() else val_originale

        item["segnaposto"] = ph
        arricchiti.append(item)

    out = testo
    for item in sorted(arricchiti, key=lambda x: -x["inizio"]):
        if item["escluso"] or not item.get("segnaposto"):
            continue
        out = out[:item["inizio"]] + item["segnaposto"] + out[item["fine"]:]

    return out, mappatura, arricchiti


def deanonimizza_testo(
    testo_con_segnaposto: str,
    mappatura: Dict[str, str],
) -> Dict[str, Any]:
    """
    Ripristina i valori originali al posto dei segnaposto.
    - Tollera differenze di maiuscole/minuscole e spazi dentro le parentesi quadre
      (es. '[ firstname_1 ]', '[FIRSTNAME 1]', '[firstname_1]').
    - Segnala:
        1) segnaposto trovati nel testo ma NON presenti nella mappatura (sconosciuti)
        2) segnaposto presenti nella mappatura ma NON comparsi nella risposta (mancanti)
    """
    def _canon_token(tok: str) -> str:
        interno = tok.strip()
        if interno.startswith("[") and interno.endswith("]"):
            interno = interno[1:-1]
        interno = re.sub(r"[\s\-_]+", "_", interno.strip()).upper()
        return interno

    lookup: Dict[str, Tuple[str, str]] = {}
    for k, v in mappatura.items():
        lookup[_canon_token(k)] = (k, v)

    usati_canon = set()
    sconosciuti: List[str] = []

    pattern = re.compile(r"\[\s*([A-Za-z][A-Za-z0-9_\s\-]*?[_\s\-]\d+)\s*\]")

    def _replacer(match: re.Match) -> str:
        raw_tok = match.group(0)
        c_key = _canon_token(raw_tok)
        if c_key in lookup:
            usati_canon.add(c_key)
            return lookup[c_key][1]
        else:
            if raw_tok not in sconosciuti:
                sconosciuti.append(raw_tok)
            return raw_tok

    testo_ripristinato = pattern.sub(_replacer, testo_con_segnaposto)

    mancanti = [
        orig_k for c_key, (orig_k, _) in lookup.items()
        if c_key not in usati_canon
    ]

    return {
        "testo_ripristinato": testo_ripristinato,
        "segnaposto_sconosciuti": sconosciuti,
        "segnaposto_mancanti": mancanti,
        "sostituzioni_effettuate": len(usati_canon),
    }
