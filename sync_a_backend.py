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
import math
import os
import sys
import time
from typing import Any

import pandas as pd
import requests

RAIZ = os.path.dirname(os.path.abspath(__file__))
os.chdir(RAIZ)

RUTA_PICKS_HOY = "Data/picks_hoy.json"
RUTA_HISTORIAL = "Data/historial_picks.csv"


def _sanear_json(valor: Any) -> Any:
    """Reemplaza recursivamente NaN/Infinity/-Infinity por None.

    BUG REAL encontrado en produccion (24/07/2026), segunda vuelta: el fix
    original solo saneaba el historial (via pandas). Pero json.load() de la
    stdlib de Python ACEPTA por defecto los literales no estandar NaN,
    Infinity y -Infinity (son una extension de Python, no JSON valido) --
    asi que si generador_picks_ligas.py escribio un 'ev' o similar en
    Infinity (division entre cero en algun caso raro) dentro de
    Data/picks_hoy.json, _cargar_picks_hoy() lo carga sin quejarse, y recien
    revienta despues, cuando `requests` intenta re-serializar el payload a
    JSON estricto para el POST. Mismo mensaje de error, origen distinto. Se
    sanea de forma recursiva y generica (dict/list/float) para cubrir
    picks_hoy.json ademas del historial, sin depender de que columna
    especifica tenga el problema.
    """
    if isinstance(valor, float):
        return None if (math.isnan(valor) or math.isinf(valor)) else valor
    if isinstance(valor, dict):
        return {k: _sanear_json(v) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_sanear_json(v) for v in valor]
    return valor


def _cargar_picks_hoy() -> dict:
    with open(RUTA_PICKS_HOY, encoding="utf-8") as f:
        return _sanear_json(json.load(f))


def _cargar_historial() -> list[dict]:
    df = pd.read_csv(RUTA_HISTORIAL)
    # pandas representa celdas vacias como NaN (float) -- json.dumps con
    # NaN produce el token literal "NaN", que NO es JSON valido (rompe en
    # cualquier parser estricto, incluido el de JS en el navegador). Se
    # convierte a None explicitamente antes de serializar.
    #
    # BUG REAL encontrado en produccion (24/07/2026): pd.notnull() NO
    # detecta +-Infinity como "nulo" (infinito no es lo mismo que NaN para
    # pandas), asi que un valor infinito en alguna columna numerica (ej. un
    # 'ev' calculado con una division por cero en algun caso raro) pasaba
    # este filtro intacto. `requests` rechaza json=payload con Infinity
    # dentro (no es JSON valido) con el error "Out of range float values
    # are not JSON compliant" -- justo lo que fallo en el workflow. Se
    # reemplazan +-inf por None ANTES del filtro de NaN, cubriendo los dos
    # casos.
    df = df.replace([float("inf"), float("-inf")], None)
    df = df.where(pd.notnull(df), None)
    return _sanear_json(df.to_dict(orient="records"))


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

    # Render free tier suspende el servicio tras ~15 min sin trafico -- el
    # primer request que lo despierta ("cold start") puede tardar 50s+ en
    # responder mientras el contenedor arranca, muy por encima de un timeout
    # de 30s (BUG REAL en produccion 24/07/2026: "Read timed out" tras
    # resolver el bug de Infinity). Se sube el timeout a 90s y se reintenta
    # una vez mas si el primer intento truena por timeout/conexion --
    # el segundo intento ya encuentra el servicio despierto.
    intentos = 2
    for intento in range(1, intentos + 1):
        try:
            resp = requests.post(
                url,
                json=payload,
                headers={"X-Sync-Secret": secreto},
                timeout=90,
            )
            break
        except requests.RequestException as e:
            if intento < intentos:
                print(
                    f"sync_a_backend: intento {intento}/{intentos} fallo ({e}) -- "
                    "probablemente cold start de Render, reintentando..."
                )
                time.sleep(5)
                continue
            # Fallo de red persistente no debe tumbar el pipeline diario entero
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
