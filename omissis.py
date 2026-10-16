# -*- coding: utf-8 -*-
"""
OMISSIS — Installer & Launcher in UN SOLO COMANDO (`python omissis.py`).

Cosa fa automaticamente quando esegui `python omissis.py`:
1. Verifica se esiste l'ambiente virtuale `venv` con PyTorch CPU, Transformers e FastAPI;
   se manca, lo crea e installa tutto nell'ordine corretto (PyTorch CPU-only -> Transformers/FastAPI).
2. Verifica se la cartella del modello `pii-italiano-v2` e' presente e completa
   (anche se annidata dentro una sottocartella estratta da uno zip);
   se manca, la cerca automaticamente in Download/Desktop/Documenti oppure la scarica
   da un URL / repository Hugging Face (configurabile anche con `--model-url` o `--hf-repo`).
3. Avvia il server locale su `http://127.0.0.1:8000` e apre automaticamente il browser.
"""
import argparse
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile

APP_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(APP_DIR)
MODEL_DIR = os.path.join(PARENT_DIR, "pii-italiano-v2")
VENV_DIR = os.path.join(APP_DIR, "venv")
REQUIRED_MODEL_FILES = [
    "model.safetensors",
    "config.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "pii_ibrido.py",
]

TRUSTED_HOSTS = [
    "--trusted-host", "pypi.org",
    "--trusted-host", "files.pythonhosted.org",
    "--trusted-host", "download.pytorch.org",
]


def _venv_python() -> str:
    if os.name == "nt":
        return os.path.join(VENV_DIR, "Scripts", "python.exe")
    return os.path.join(VENV_DIR, "bin", "python")


def _modello_completo(percorso: str) -> bool:
    if not os.path.isdir(percorso):
        return False
    # Appiattisci eventuale cartella doppia pii-italiano-v2/pii-italiano-v2
    nested = os.path.join(percorso, "pii-italiano-v2")
    if os.path.isdir(nested) and not os.path.exists(os.path.join(percorso, "model.safetensors")):
        for item in os.listdir(nested):
            shutil.move(os.path.join(nested, item), os.path.join(percorso, item))
        try:
            os.rmdir(nested)
        except OSError:
            pass
    return all(os.path.exists(os.path.join(percorso, f)) for f in REQUIRED_MODEL_FILES)


def _cerca_modello_locale() -> str | None:
    if _modello_completo(MODEL_DIR):
        return MODEL_DIR

    home = os.path.expanduser("~")
    candidati = [
        os.path.join(APP_DIR, "pii-italiano-v2"),
        os.path.join(home, "Downloads", "pii-italiano-v2"),
        os.path.join(home, "Desktop", "pii-italiano-v2"),
        os.path.join(home, "Documents", "pii-italiano-v2"),
        os.path.join(home, "OneDrive", "Desktop", "pii-italiano-v2"),
        os.path.join(home, "OneDrive", "Documents", "pii-italiano-v2"),
        r"C:\omissis\pii-italiano-v2",
    ]
    for c in candidati:
        if _modello_completo(c):
            if os.path.abspath(c) != os.path.abspath(MODEL_DIR):
                print(f"[Omissis] Trovato modello in {c}, collegamento in {MODEL_DIR}...")
                shutil.copytree(c, MODEL_DIR, dirs_exist_ok=True)
            return MODEL_DIR

    # Cerca anche eventuale archivio pii-italiano-v2.zip in Downloads/Desktop
    zip_candidati = [
        os.path.join(PARENT_DIR, "pii-italiano-v2.zip"),
        os.path.join(home, "Downloads", "pii-italiano-v2.zip"),
        os.path.join(home, "Desktop", "pii-italiano-v2.zip"),
    ]
    for z in zip_candidati:
        if os.path.isfile(z):
            print(f"[Omissis] Trovato archivio {z}, estrazione in {MODEL_DIR}...")
            os.makedirs(MODEL_DIR, exist_ok=True)
            with zipfile.ZipFile(z, "r") as zf:
                zf.extractall(MODEL_DIR)
            if _modello_completo(MODEL_DIR):
                return MODEL_DIR

    return None


def _scarica_modello(model_url: str | None, hf_repo: str | None, venv_py: str) -> None:
    os.makedirs(MODEL_DIR, exist_ok=True)
    if model_url:
        zip_path = os.path.join(PARENT_DIR, "pii-italiano-v2-download.zip")
        print(f"[Omissis] Download del modello da {model_url} ...")
        urllib.request.urlretrieve(model_url, zip_path)
        print("[Omissis] Estrazione archivio del modello...")
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(MODEL_DIR)
        os.remove(zip_path)
        _modello_completo(MODEL_DIR)
        return

    if hf_repo:
        print(f"[Omissis] Download del modello da Hugging Face ({hf_repo})...")
        cmd = [
            venv_py, "-c",
            (
                "from huggingface_hub import snapshot_download; "
                f"snapshot_download(repo_id={hf_repo!r}, local_dir={MODEL_DIR!r})"
            ),
        ]
        subprocess.check_call(cmd)
        _modello_completo(MODEL_DIR)


def _assicura_venv_e_dipendenze() -> str:
    vpy = _venv_python()
    if not os.path.exists(vpy):
        print(f"[Omissis] Creazione ambiente virtuale in {VENV_DIR}...")
        subprocess.check_call([sys.executable, "-m", "venv", VENV_DIR])

    # Verifica rapida se torch, transformers, fastapi, uvicorn sono gia' installati
    check_cmd = [vpy, "-c", "import torch, transformers, fastapi, uvicorn"]
    res = subprocess.run(check_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if res.returncode == 0:
        return vpy

    print("[Omissis] Installazione dipendenze (1/3): aggiornamento pip...")
    subprocess.check_call([vpy, "-m", "pip", "install", "--upgrade", "pip", *TRUSTED_HOSTS])

    print("[Omissis] Installazione dipendenze (2/3): PyTorch CPU-only (~125 MB, no CUDA)...")
    subprocess.check_call([
        vpy, "-m", "pip", "install", "torch",
        "--index-url", "https://download.pytorch.org/whl/cpu",
        *TRUSTED_HOSTS,
    ])

    print("[Omissis] Installazione dipendenze (3/3): transformers, fastapi, uvicorn[standard]...")
    subprocess.check_call([
        vpy, "-m", "pip", "install",
        "transformers", "fastapi", "uvicorn[standard]",
        *TRUSTED_HOSTS,
    ])
    return vpy


def main():
    parser = argparse.ArgumentParser(description="Omissis — Setup & Avvio in un solo comando")
    parser.add_argument("--model-url", help="URL diretto a uno zip contenente pii-italiano-v2", default=os.environ.get("OMISSIS_MODEL_URL"))
    parser.add_argument("--hf-repo", help="ID repository Hugging Face da cui scaricare il modello", default=os.environ.get("OMISSIS_HF_REPO"))
    parser.add_argument("--setup-only", action="store_true", help="Esegue solo l'installazione e la verifica senza avviare il server")
    args = parser.parse_args()

    print("=================================================================")
    print("  OMISSIS — Installer & Launcher Automatico (127.0.0.1:8000)")
    print("=================================================================")

    vpy = _assicura_venv_e_dipendenze()

    percorso_modello = _cerca_modello_locale()
    if not percorso_modello and (args.model_url or args.hf_repo):
        _scarica_modello(args.model_url, args.hf_repo, vpy)
        percorso_modello = _cerca_modello_locale()

    if not percorso_modello:
        print("\n[ERRORE] Cartella 'pii-italiano-v2' non trovata o incompleta.")
        print(f"Posiziona 'pii-italiano-v2' (o 'pii-italiano-v2.zip') in {PARENT_DIR} oppure in Downloads,")
        print("oppure avvia con: python omissis.py --model-url <URL_ZIP> (o --hf-repo <UTENTE/REPO>)")
        sys.exit(1)

    print(f"[Omissis] Ambiente e modello verificati in: {percorso_modello}")

    if args.setup_only:
        print("[Omissis] Setup completato con successo (--setup-only).")
        return

    print("[Omissis] Avvio del server locale su http://127.0.0.1:8000 ...")
    subprocess.check_call([vpy, os.path.join(APP_DIR, "start.py")], cwd=APP_DIR)


if __name__ == "__main__":
    main()
