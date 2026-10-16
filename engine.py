# -*- coding: utf-8 -*-
"""
Motore di post-processing, anonimizzazione reversibile e de-anonimizzazione.
"""
import re
from typing import List, Dict, Any, Tuple


def _normalizza_chiave(valore: str, tipo: str) -> Tuple[str, str]:
    """Chiave case-insensitive e senza spazi ai bordi (e spazi multipli interni normalizzati)."""
    return (tipo.upper().strip(), re.sub(r"\s+", " ", valore.strip()).lower())


def _stessa_parola(testo: str, fine_a: int, inizio_b: int, val_b: str) -> bool:
    """
    Determina se due span toccano o spezzano la stessa parola (es. 'Pale' + '##strina').
    """
    if val_b.startswith("##"):
        # Se il secondo frammento inizia con ## ed e' immediatamente adiacente (o sovrapposto)
        if inizio_b <= fine_a:
            return True
    if inizio_b < fine_a:
        # Sovrapposti
        return True
    if inizio_b == fine_a:
        # Adiacenti senza spazio in mezzo: se entrambi i lati sono caratteri di parola, fanno parte della stessa parola
        if fine_a > 0 and inizio_b < len(testo):
            c_left = testo[fine_a - 1]
            c_right = testo[inizio_b]
            if c_left.isalnum() and c_right.isalnum():
                return True
    return False


def post_processa_rilevamenti(testo: str, raw_dets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Corregge i bug noti del modello prima di sostituire:
      1. Rimuove il prefisso '##' dai frammenti e riallinea il valore allo slice del testo.
      2. Unisce gli span adiacenti o sovrapposti del modello che toccano la stessa parola
         (es. CITY='Pale' e STATE='##strina' -> 'Palestrina').
      3. In caso di sovrapposizione fa vincere SEMPRE fonte='regex' su fonte='modello';
         tra span della stessa fonte tiene lo span piu' lungo (o con score maggiore a parita').
      4. Scarta i rilevamenti di 1-2 caratteri che non vengano dallo strato regex.
    """
    if not raw_dets:
        return []

    regex_dets = []
    model_dets = []

    for d in raw_dets:
        copia = dict(d)
        copia["inizio"] = int(copia["inizio"])
        copia["fine"] = int(copia["fine"])
        copia["score"] = float(copia.get("score", 1.0))
        val_raw = str(copia.get("valore", ""))
        copia["_had_hash"] = val_raw.startswith("##")
        # Pulisci ## dal valore ma usa sempre la sottostringa esatta del testo
        pulito = val_raw.lstrip("#").strip()
        slice_testo = testo[copia["inizio"]:copia["fine"]]
        copia["valore"] = slice_testo if slice_testo else pulito

        if copia.get("fonte") == "regex":
            regex_dets.append(copia)
        else:
            model_dets.append(copia)

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
            # Sovrapposizione tra due rilevamenti del modello:
            # Se toccano la stessa parola (es. subword spezzata parzialmente sovrapposta), estendi;
            # altrimenti tieni lo span piu' lungo
            len_prev = prev["fine"] - prev["inizio"]
            len_cur = cur["fine"] - cur["inizio"]
            # Verifica se formano un'unica parola continua senza spazi
            span_unito = testo[min(prev["inizio"], cur["inizio"]):max(prev["fine"], cur["fine"])]
            if not re.search(r"\s", span_unito):
                nuovo_inizio = min(prev["inizio"], cur["inizio"])
                nuovo_fine = max(prev["fine"], cur["fine"])
                # Scegli il tipo del frammento piu' lungo o con score piu' alto
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
            # Adiacenti sulla stessa parola (es. "Pale" [0:4] + "##strina" [4:10])
            len_prev = prev["fine"] - prev["inizio"]
            len_cur = cur["fine"] - cur["inizio"]
            # Manteniamo il tipo del primo frammento se non e' molto piu' corto, oppure quello piu' lungo/confidente
            if len_cur > len_prev * 2 and cur["score"] > prev["score"]:
                prev["tipo"] = cur["tipo"]
            prev["fine"] = cur["fine"]
            prev["valore"] = testo[prev["inizio"]:prev["fine"]]
            prev["score"] = (prev["score"] + cur["score"]) / 2.0
        else:
            merged_model.append(cur)

    # Espandi eventualmente ai confini della stessa parola se il modello ha lasciato 1-2 lettere attaccate?
    # No, seguiamo rigorosamente le regole specificate:
    # - unisci gli span adiacenti o sovrapposti che toccano la stessa parola
    # - togli il prefisso "##" dai frammenti
    # - scarta i rilevamenti di 1-2 caratteri che non vengano dallo strato regex
    # - in caso di sovrapposizione tieni lo span piu' lungo, e in ogni caso fai vincere fonte='regex' su fonte='modello'

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
    #    e scarta i rilevamenti modello di 1-2 caratteri.
    final_dets: List[Dict[str, Any]] = list(merged_regex)
    for m in merged_model:
        m.pop("_had_hash", None)
        val_clean = m["valore"].replace("##", "").strip()
        m["valore"] = testo[m["inizio"]:m["fine"]].replace("##", "")
        if len(val_clean) <= 2:
            continue
        # Controlla sovrapposizione con qualsiasi regex
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

    # Propaga i valori gia' rilevati (es. un nome proprio riconosciuto in un punto del testo
    # ma perso dal modello in un'altra frase dello stesso testo) su tutte le occorrenze
    # a parola intera (case-insensitive) non ancora coperte.
    coperti = set()
    for d in final_dets:
        coperti.update(range(d["inizio"], d["fine"]))

    valori_noti: Dict[str, Dict[str, Any]] = {}
    for d in final_dets:
        v_clean = d["valore"].strip()
        if len(v_clean) >= 3 and v_clean.lower() not in valori_noti:
            valori_noti[v_clean.lower()] = d

    aggiunti: List[Dict[str, Any]] = []
    for norm_v, ref_d in valori_noti.items():
        val_orig = ref_d["valore"].strip()
        pat = re.compile(r"(?<!\w)" + re.escape(val_orig) + r"(?!\w)", re.IGNORECASE)
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

    # Ricostruisci indice inverso (valore_norm -> segnaposto) e contatori per tipo dalla mappatura esistente
    val_to_placeholder: Dict[str, str] = {}
    contatori_tipo: Dict[str, int] = {}

    for ph, orig_val in mappatura.items():
        # ph ha formato [TIPO_N]
        m = re.match(r"^\[([A-Z0-9_]+)_(\d+)\]$", ph.strip())
        if m:
            t_name = m.group(1)
            idx_num = int(m.group(2))
            contatori_tipo[t_name] = max(contatori_tipo.get(t_name, 0), idx_num)
        norm_v = orig_val.strip().lower()
        if norm_v not in val_to_placeholder:
            val_to_placeholder[norm_v] = ph

    # Ordina i rilevamenti in ordine di apparizione nel testo per assegnare i numeri progressivi in modo naturale
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

    # Sostituzione nel testo partendo dagli offset piu' alti verso i piu' bassi
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
    # Costruisci lookup canonico: chiave normalizzata -> (chiave_originale, valore_originale)
    def _canon_token(tok: str) -> str:
        # Rimuove [ ], converte spazi/trattini in '_', uppercase
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

    # Regex che cattura potenziali segnaposto del tipo [QUALCOSA_1] o [ QUALCOSA 1 ]
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
