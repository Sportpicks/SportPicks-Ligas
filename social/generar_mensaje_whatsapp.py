# -*- coding: utf-8 -*-
"""
generar_mensaje_whatsapp.py -- Fase 3 del plan de crecimiento organico:
canal de difusion de WhatsApp (WhatsApp Channels).

No existe conector/API publica para publicar automaticamente en un canal
de WhatsApp (a diferencia de un bot de WhatsApp Business, que requiere
Meta Cloud API/Twilio, aprobacion y costo por mensaje -- fuera de
alcance por ahora, ver conversacion con Antonio). Este script genera el
TEXTO listo para copiar/pegar como publicacion del canal; Antonio lo
publica manualmente, igual que las piezas de Facebook/Instagram/TikTok
de la Fase 1.

Fuente de datos: Data/picks_hoy.json (el mismo JSON que ya alimenta la
seccion "Picks gratis de hoy" de la landing via sync_a_backend.py) --
no se inventa ni se recalcula nada, es exactamente lo que ya es publico
en la web.

Uso:
    python social/generar_mensaje_whatsapp.py

Salida: Data/social/whatsapp/<fecha>/mensaje.txt
"""
import json
import os
from datetime import date, datetime

RAIZ = os.path.dirname(os.path.abspath(__file__))
RAIZ_PIPELINE = os.path.dirname(RAIZ)
PICKS_HOY_JSON = os.path.join(RAIZ_PIPELINE, "Data", "picks_hoy.json")
SALIDA_BASE = os.path.join(RAIZ_PIPELINE, "Data", "social", "whatsapp")

BASE_URL = "https://sportpicks-suscripcion.vercel.app"

MESES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def _fecha_legible(fecha_iso):
    d = datetime.strptime(fecha_iso, "%Y-%m-%d")
    return f"{d.day} de {MESES[d.month - 1]}"


def _link_utm(campana):
    return f"{BASE_URL}/?utm_source=whatsapp&utm_medium=social&utm_campaign={campana}"


def cargar_picks_hoy():
    with open(PICKS_HOY_JSON, encoding="utf-8") as f:
        return json.load(f)


def _linea_pick(pick):
    emoji = pick.get("emoji", "⚽")
    partido = pick["partido"]
    mercado = pick["mercado"]
    cuota = pick.get("cuota_display", pick.get("cuota"))
    prob = pick.get("prob")
    return f"{emoji} *{partido}*\n   {mercado} · cuota @{cuota} · {prob}% prob."


def generar_mensaje(data):
    fecha_iso = data["fecha"]
    publicos = data.get("publicos", [])
    premium = data.get("premium", [])

    campana = f"picks_diarios_{date.today().isoformat()}"
    link = _link_utm(campana)

    lineas_picks = "\n\n".join(_linea_pick(p) for p in publicos)

    n_premium = len(premium)
    if n_premium:
        bloque_premium = (
            f"\n\n💎 Hay {n_premium} pick{'s' if n_premium != 1 else ''} premium más "
            f"con mejor EV, disponibles con la suscripción."
        )
    else:
        bloque_premium = ""

    mensaje = f"""📊 *SportPicks Ligas* -- Picks gratis del {_fecha_legible(fecha_iso)}

{lineas_picks}{bloque_premium}

👉 Historial público completo y picks de hoy: {link}

⚠️ Análisis estadístico, no garantía de resultado. Juega con responsabilidad. +18."""

    return mensaje


def main():
    data = cargar_picks_hoy()
    if not data.get("publicos"):
        print("No hay picks públicos en Data/picks_hoy.json todavía -- nada que generar.")
        return

    mensaje = generar_mensaje(data)

    carpeta_salida = os.path.join(SALIDA_BASE, data["fecha"])
    os.makedirs(carpeta_salida, exist_ok=True)
    ruta = os.path.join(carpeta_salida, "mensaje.txt")
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(mensaje)
        f.write("\n")

    print(f"Generado: {ruta}")
    print()
    print(mensaje)


if __name__ == "__main__":
    main()
