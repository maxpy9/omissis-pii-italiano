# -*- coding: utf-8 -*-
"""
FASE 4.1 — Script di test del giro completo (testo -> anonimizza -> de-anonimizza == originale)
e verifica dei requisiti critici di post-processing e segnaposto reversibili.
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "pii-italiano-v2"))
sys.path.insert(0, MODEL_DIR)

from pii_ibrido import PIIDetector
from engine import post_processa_rilevamenti, applica_anonimizzazione, deanonimizza_testo


def esegui_test():
    print("=== Caricamento modello PIIDetector ===")
    detector = PIIDetector(MODEL_DIR, device=-1)

    # Caso 1: Due persone diverse con vari dati strutturati
    testo_due_persone = (
        "Il contratto è stipulato tra Marco Rossi (CF RSSMRA85T10A562S, email marco.rossi@example.it, "
        "IBAN IT60X0542811101000000123456) e Giulia Bianchi (P.IVA 12345678903, tel 333 4567890)."
    )

    # Caso 2: Stessa persona nominata tre volte a distanza nel testo (anche con case diverso nei test di motore)
    testo_stessa_persona_3_volte = (
        "Ho parlato con Marco ieri mattina. Nel pomeriggio Marco ha confermato il bonifico "
        "all'IBAN IT60X0542811101000000123456, e infine Marco ha inviato la ricevuta a marco.rossi@example.it."
    )

    # Caso 3: Combinato complesso (due persone diverse + stessa persona ripetuta 3 volte)
    testo_combinato = (
        "Gentile Marco Rossi, ti confermo che Luca Verdi ha ricevuto la pratica. "
        "Marco dovrà firmare il modulo insieme a Luca Verdi entro venerdì, "
        "altrimenti Marco non potrà procedere."
    )

    casi = [
        ("Caso 1 — Due persone diverse", testo_due_persone),
        ("Caso 2 — Stessa persona nominata tre volte", testo_stessa_persona_3_volte),
        ("Caso 3 — Due persone + persona ripetuta tre volte", testo_combinato),
    ]

    for titolo, testo_orig in casi:
        print(f"\n--- {titolo} ---")
        raw_dets = detector.analizza(testo_orig)
        dets = post_processa_rilevamenti(testo_orig, raw_dets)
        testo_anon, mappatura, _ = applica_anonimizzazione(testo_orig, dets)
        esito_deanon = deanonimizza_testo(testo_anon, mappatura)
        testo_ripristinato = esito_deanon["testo_ripristinato"]

        print(f"Originale     : {testo_orig}")
        print(f"Anonimizzato  : {testo_anon}")
        print(f"Mappatura     : {mappatura}")
        print(f"Ripristinato  : {testo_ripristinato}")
        assert testo_ripristinato == testo_orig, (
            f"ERRORE roundtrip!\nAtteso:  {testo_orig}\nOttenuto:{testo_ripristinato}"
        )
        assert esito_deanon["segnaposto_sconosciuti"] == [], "Non devono esserci segnaposto sconosciuti"
        assert esito_deanon["segnaposto_mancanti"] == [], "Non devono esserci segnaposto mancanti"
        print("Esito         : OK (Round-trip ESATTO al 100%)")

    # Verifica specifica per Caso 2: "Marco" ripetuto 3 volte deve avere lo STESSO segnaposto tutte e 3 le volte
    raw_2 = detector.analizza(testo_stessa_persona_3_volte)
    dets_2 = post_processa_rilevamenti(testo_stessa_persona_3_volte, raw_2)
    anon_2, map_2, _ = applica_anonimizzazione(testo_stessa_persona_3_volte, dets_2)
    marco_phs = [k for k, v in map_2.items() if v.lower() == "marco"]
    assert len(marco_phs) == 1, f"'Marco' deve avere un solo segnaposto univoco, trovati: {marco_phs}"
    assert anon_2.count(marco_phs[0]) == 3, (
        f"Il segnaposto {marco_phs[0]} deve comparire 3 volte nel testo anonimizzato, trovato {anon_2.count(marco_phs[0])} volte"
    )
    print(f"\nVerifica ripetizione 3 volte: '{marco_phs[0]}' compare esattamente 3 volte -> OK")

    # Verifica post-processing bug noto (Palestrina = CITY:'Pale' + STATE:'##strina', scarto 1-2 char non regex, priorita' regex)
    testo_bug = "Abito a Palestrina in provincia di RM, CF RSSMRA85T10A562S."
    finti_raw = [
        {"tipo": "CITY", "valore": "Pale", "inizio": 8, "fine": 12, "fonte": "modello", "score": 0.91},
        {"tipo": "STATE", "valore": "##strina", "inizio": 12, "fine": 18, "fonte": "modello", "score": 0.88},
        {"tipo": "STATE", "valore": "RM", "inizio": 35, "fine": 37, "fonte": "modello", "score": 0.75},  # 2 char modello -> scartato
        {"tipo": "CODICE_FISCALE", "valore": "RSSMRA85T10A562S", "inizio": 42, "fine": 58, "fonte": "regex", "score": 1.0},
        {"tipo": "USERNAME", "valore": "RSSMRA85", "inizio": 42, "fine": 50, "fonte": "modello", "score": 0.99},  # sovrapposto a regex -> scartato
    ]
    puliti = post_processa_rilevamenti(testo_bug, finti_raw)
    valori_puliti = [(d["tipo"], d["valore"], d["fonte"]) for d in puliti]
    print(f"Verifica post-processing Palestrina/2char/regex: {valori_puliti}")
    assert any(d["valore"] == "Palestrina" for d in puliti), "Palestrina non unita correttamente!"
    assert not any(d["valore"] == "RM" for d in puliti), "Rilevamento modello di 2 caratteri non scartato!"
    assert not any(d["valore"] == "RSSMRA85" for d in puliti), "Sovrapposizione modello su regex non scartata!"

    # Verifica tolleranza case/spazi in de-anonimizzazione e avvisi
    ris_tolleranza = deanonimizza_testo(
        "Ciao [ firstname_1 ], il tuo codice è [IBAN 1] e un tag ignoto [CITY_99].",
        {"[FIRSTNAME_1]": "Marco", "[IBAN_1]": "IT60X0542811101000000123456", "[EMAIL_1]": "marco@example.it"},
    )
    assert "Ciao Marco, il tuo codice è IT60X0542811101000000123456" in ris_tolleranza["testo_ripristinato"]
    assert "[CITY_99]" in ris_tolleranza["segnaposto_sconosciuti"]
    assert "[EMAIL_1]" in ris_tolleranza["segnaposto_mancanti"]
    print("Verifica tolleranza case/spazi e avvisi segnaposto sconosciuti/mancanti -> OK")

    print("\n=== TUTTI I TEST SUPERATI CON SUCCESSO ===")


if __name__ == "__main__":
    esegui_test()
