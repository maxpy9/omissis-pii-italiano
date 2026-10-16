# -*- coding: utf-8 -*-
"""
Gestione della persistenza su disco delle sessioni (mappature segnaposto -> valore originale).
Ogni salvataggio imposta i permessi 0600 (e ACL ristretta all'utente corrente su Windows).
"""
import json
import os
import stat
import subprocess
import uuid
from datetime import datetime
from typing import Dict, Any

SESSIONS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sessions_data.json")


def _applica_permessi_0600(filepath: str) -> None:
    """Imposta permessi 0600 sul file JSON (e restringe ACL all'utente corrente su Windows)."""
    try:
        os.chmod(filepath, stat.S_IRUSR | stat.S_IWUSR)  # 0o600
    except Exception:
        pass
    if os.name == "nt":
        utente = os.environ.get("USERNAME")
        if utente:
            try:
                subprocess.run(
                    ["icacls", filepath, "/inheritance:r", "/grant:r", f"{utente}:(R,W)"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
            except Exception:
                pass


class SessionStore:
    def __init__(self, filepath: str = SESSIONS_FILE):
        self.filepath = filepath
        self.data: Dict[str, Any] = {"active_session_id": None, "sessions": {}}
        self._load()

    def _load(self) -> None:
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict) and "sessions" in loaded:
                    self.data = loaded
            except Exception:
                pass
        if not self.data["sessions"]:
            self.create_session("Sessione Principale")
        elif self.data.get("active_session_id") not in self.data["sessions"]:
            self.data["active_session_id"] = next(iter(self.data["sessions"].keys()))
            self._save()

    def _save(self) -> None:
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        fd = os.open(self.filepath, flags, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        _applica_permessi_0600(self.filepath)

    def list_sessions(self) -> Dict[str, Any]:
        return {
            "active_session_id": self.data.get("active_session_id"),
            "sessions": self.data["sessions"],
        }

    def get_session(self, session_id: str) -> Dict[str, Any] | None:
        return self.data["sessions"].get(session_id)

    def create_session(self, nome: str | None = None) -> Dict[str, Any]:
        sid = str(uuid.uuid4())[:8]
        ora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if not nome or not nome.strip():
            nome = f"Sessione {len(self.data['sessions']) + 1}"
        sess = {
            "id": sid,
            "nome": nome.strip(),
            "creata_il": ora,
            "aggiornata_il": ora,
            "mappatura": {},
            "ultimo_testo_originale": "",
            "ultimo_testo_anonimizzato": "",
        }
        self.data["sessions"][sid] = sess
        self.data["active_session_id"] = sid
        self._save()
        return sess

    def select_session(self, session_id: str) -> Dict[str, Any]:
        if session_id not in self.data["sessions"]:
            raise KeyError("Sessione non trovata")
        self.data["active_session_id"] = session_id
        self._save()
        return self.data["sessions"][session_id]

    def rename_session(self, session_id: str, nuovo_nome: str) -> Dict[str, Any]:
        if session_id not in self.data["sessions"]:
            raise KeyError("Sessione non trovata")
        self.data["sessions"][session_id]["nome"] = nuovo_nome.strip() or "Sessione"
        self.data["sessions"][session_id]["aggiornata_il"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._save()
        return self.data["sessions"][session_id]

    def update_session_mapping(
        self,
        session_id: str,
        mappatura: Dict[str, str],
        testo_originale: str | None = None,
        testo_anonimizzato: str | None = None,
    ) -> Dict[str, Any]:
        if session_id not in self.data["sessions"]:
            raise KeyError("Sessione non trovata")
        sess = self.data["sessions"][session_id]
        sess["mappatura"] = mappatura
        if testo_originale is not None:
            sess["ultimo_testo_originale"] = testo_originale
        if testo_anonimizzato is not None:
            sess["ultimo_testo_anonimizzato"] = testo_anonimizzato
        sess["aggiornata_il"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._save()
        return sess

    def clear_session(self, session_id: str) -> Dict[str, Any]:
        """Svuota la mappatura e i testi della sessione corrente."""
        if session_id not in self.data["sessions"]:
            raise KeyError("Sessione non trovata")
        sess = self.data["sessions"][session_id]
        sess["mappatura"] = {}
        sess["ultimo_testo_originale"] = ""
        sess["ultimo_testo_anonimizzato"] = ""
        sess["aggiornata_il"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._save()
        return sess

    def delete_session(self, session_id: str) -> Dict[str, Any]:
        if session_id not in self.data["sessions"]:
            raise KeyError("Sessione non trovata")
        del self.data["sessions"][session_id]
        if not self.data["sessions"]:
            self.create_session("Sessione Principale")
        elif self.data.get("active_session_id") == session_id:
            self.data["active_session_id"] = next(iter(self.data["sessions"].keys()))
        self._save()
        return self.list_sessions()
