# -*- coding: utf-8 -*-
"""
Server FastAPI locale per anonimizzazione e de-anonimizzazione PII in italiano.
- Ascolta ESCLUSIVAMENTE su 127.0.0.1
- Carica il modello UNA sola volta all'avvio del server (lifespan)
- Nessuna chiamata di rete in uscita, nessuna CDN esterna
"""
import os
import sys
from contextlib import asynccontextmanager
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel, Field

# Percorso del modello accanto a omissis-app
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "pii-italiano-v2"))
if MODEL_DIR not in sys.path:
    sys.path.insert(0, MODEL_DIR)

from pii_ibrido import PIIDetector
from engine import post_processa_rilevamenti, applica_anonimizzazione, deanonimizza_testo
from sessions_store import SessionStore

detector: Optional[PIIDetector] = None
store = SessionStore()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global detector
    print(f"[Omissis] Caricamento modello PII da {MODEL_DIR} su CPU...")
    detector = PIIDetector(MODEL_DIR, device=-1)
    print("[Omissis] Modello caricato e pronto.")
    yield


app = FastAPI(
    title="Omissis — Anonimizzatore PII Italiano Locale",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
)


class AnonimizzaRequest(BaseModel):
    testo: str = Field(default="")
    session_id: Optional[str] = None
    esclusi_indices: List[int] = Field(default_factory=list)
    rilevamenti_precalcolati: Optional[List[Dict[str, Any]]] = None
    mantieni_mappatura_precedente: bool = True


class DeanonimizzaRequest(BaseModel):
    testo: str = Field(default="")
    session_id: Optional[str] = None


class SessionCreateRequest(BaseModel):
    nome: Optional[str] = None


class SessionRenameRequest(BaseModel):
    nome: str


@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = os.path.join(BASE_DIR, "index.html")
    with open(html_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.get("/logo.jpg")
async def get_logo():
    logo_path = os.path.join(BASE_DIR, "logo.jpg")
    if os.path.exists(logo_path):
        return FileResponse(logo_path, media_type="image/jpeg")
    raise HTTPException(status_code=404, detail="Logo non trovato")


@app.get("/api/health")
async def health():
    return {"status": "ok", "model_loaded": detector is not None}


@app.get("/api/sessions")
async def get_sessions():
    return store.list_sessions()


@app.post("/api/sessions")
async def create_session(req: SessionCreateRequest):
    sess = store.create_session(req.nome)
    return {"session": sess, "state": store.list_sessions()}


@app.post("/api/sessions/{session_id}/select")
async def select_session(session_id: str):
    try:
        sess = store.select_session(session_id)
        return {"session": sess, "state": store.list_sessions()}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.put("/api/sessions/{session_id}/rename")
async def rename_session(session_id: str, req: SessionRenameRequest):
    try:
        sess = store.rename_session(session_id, req.nome)
        return {"session": sess, "state": store.list_sessions()}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/sessions/{session_id}/clear")
async def clear_session(session_id: str):
    try:
        sess = store.clear_session(session_id)
        return {"session": sess, "state": store.list_sessions()}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    try:
        state = store.delete_session(session_id)
        return {"state": state}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/anonimizza")
async def api_anonimizza(req: AnonimizzaRequest):
    if detector is None:
        raise HTTPException(status_code=503, detail="Modello non ancora caricato")

    sid = req.session_id or store.list_sessions().get("active_session_id")
    sess = store.get_session(sid) if sid else None
    if not sess:
        sess = store.create_session("Sessione Principale")
        sid = sess["id"]

    # Se il client ci passa i rilevamenti gia' calcolati (es. quando l'utente spunta/despunta una casella
    # di esclusione senza cambiare il testo), evitiamo di rieseguire il modello.
    if req.rilevamenti_precalcolati is not None:
        dets_puliti = req.rilevamenti_precalcolati
    else:
        raw_dets = detector.analizza(req.testo) if req.testo.strip() else []
        dets_puliti = post_processa_rilevamenti(req.testo, raw_dets)

    mappatura_base = sess["mappatura"] if req.mantieni_mappatura_precedente else {}

    testo_anon, nuova_mappatura, arricchiti = applica_anonimizzazione(
        testo=req.testo,
        rilevamenti=dets_puliti,
        mappatura_esistente=mappatura_base,
        esclusi_indices=req.esclusi_indices,
    )

    sess_aggiornata = store.update_session_mapping(
        session_id=sid,
        mappatura=nuova_mappatura,
        testo_originale=req.testo,
        testo_anonimizzato=testo_anon,
    )

    return {
        "session_id": sid,
        "testo_originale": req.testo,
        "testo_anonimizzato": testo_anon,
        "rilevamenti": arricchiti,
        "mappatura": nuova_mappatura,
        "session": sess_aggiornata,
    }


@app.post("/api/deanonimizza")
async def api_deanonimizza(req: DeanonimizzaRequest):
    sid = req.session_id or store.list_sessions().get("active_session_id")
    sess = store.get_session(sid) if sid else None
    if not sess:
        raise HTTPException(status_code=404, detail="Sessione non trovata")

    risultato = deanonimizza_testo(req.testo, sess.get("mappatura", {}))
    return {
        "session_id": sid,
        "mappatura": sess.get("mappatura", {}),
        **risultato,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
