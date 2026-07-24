# -*- coding: utf-8 -*-
"""
sync_a_backend.py
Publica Data/picks_hoy.json + Data/historial_picks.csv en el backend de
suscripcion (Repo/backend), via POST /api/internal/sync-picks. Ese backend
es el que sirve /panel detras del paywall en el sitio nuevo (Vercel) --
este pipeline (GitHub Actions, ver .github/workflows/pipeline_diario.yml)
sigue siendo la unica fuente de verdad de los datos; el backend solo los
guarda para servirlos, no los recalcula.

Requiere dos variables de entorno (secrets de GitHub Actions):
  BACKEND_SYNC_URL     -- ej. https://tu-api.up.railway.app/api/internal/sync-picks
  BACKEND_SYNC_SECRET  -- debe coincidir con SYNC_SHARED_SECRET del backend

Si cualquiera de las dos falta, el script no falla el pipeline (exit 0,
solo se imprime un aviso) -- antes de que el backend este desplegado en
Railway, este paso es un no-op intencional, no un error.
"""
import json
import os
import sys

import pandas as pd
import requests

RAIZ = os.path.dirname(os.path.abspath(__file__))
os.chdir(RAIZ)

RUTA_PICKS_HOY = "Data/picks_hoy.json"
RUTA_HISTORIAL = "Data/historial_picks.csv"


def _cargar_picks_hoy() -> dict:
    with open(RUTA_PICKS_HOY, encoding="utf-8") as f:
        return json.load(f)


def _cargar_historial() -> list[dict]:
    df = pd.read_csv(RUTA_HISTORIAL)
    # pandas representa celdas vacias como NaN (float) -- json.dumps con
    # NaN produce el token literal "NaN", que NO es JSON valido (rompe en
    # cualquier parser estricto, incluido el de JS en el navegador). Se
    # convierte a None explicitamente antes de serializar.
    df = df.where(pd.notnull(df), None)
    return df.to_dict(orient="records")


def main() -> int:
    url = os.environ.get("BACKEND_SYNC_URL", "").strip()
    secreto = os.environ.get("BACKEND_SYNC_SECRET", "").strip()

    if not url or not secreto:
        print(
            "sync_a_backend: BACKEND_SYNC_URL o BACKEND_SYNC_SECRET no configurados -- "
            "omitiendo sync (no-op, no es un error mientras el backend no este desplegado)."
        )
        return 0

    if not os.path.exists(RUTA_PICKS_HOY) or not os.path.exists(RUTA_HISTORIAL):
        print(f"sync_a_backend: falta {RUTA_PICKS_HOY} o {RUTA_HISTORIAL} -- nada que sincronizar.")
        return 0

    payload = {
        "picks_hoy": _cargar_picks_hoy(),
        "historial": _cargar_historial(),
    }

    try:
        resp = requests.post(
            url,
            json=payload,
            headers={"X-Sync-Secret": secreto},
            timeout=30,
        )
    except requests.RequestException as e:
        # Fallo de red hacia Railway no debe tumbar el pipeline diario entero
        # (los picks ya se generaron y commitearon a git antes de este paso) --
        # se imprime el error para diagnostico pero se sale con codigo != 0
        # solo para que el step de Actions quede visible en rojo (ya corre
        # con continue-on-error: true en el workflow).
        print(f"sync_a_backend: error de red al contactar el backend: {e}", file=sys.stderr)
        return 1

    if resp.status_code != 200:
        print(f"sync_a_backend: backend respondio {resp.status_code}: {resp.text[:500]}", file=sys.stderr)
        return 1

    print(f"sync_a_backend: OK -- {resp.json()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
