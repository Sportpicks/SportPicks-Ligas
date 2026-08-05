# -*- coding: utf-8 -*-
"""
generar_mensaje_telegram.py -- Fase 3 del plan de crecimiento organico:
canal de difusion de Telegram (el canal real que usa Antonio; reemplaza
al script anterior generar_mensaje_whatsapp.py, pensado por error para
un WhatsApp Channel que no es el que esta activo).

A diferencia de WhatsApp Channels (sin API publica gratuita), Telegram
SI tiene una Bot API oficial, gratuita y simple para publicar en un
canal: se crea un bot con @BotFather, se lo agrega como administrador
del canal, y se llama a api.telegram.org/bot<token>/sendMessage con el
chat_id del canal. Por eso este script soporta DOS modos:

  1. Manual (default, sin configuracion): genera el texto en un .txt
     listo para copiar/pegar, igual que el resto de piezas de Fase 1/3.
     Sin negritas via asteriscos -- a diferencia de WhatsApp, los
     clientes de Telegram NO renderizan *texto* como negrita al pegarlo
     a mano en el cuadro de mensaje, asi que copiar/pegar con asteriscos
     los mostraria literales. Este modo usa mayusculas/emoji para
     enfasis en su lugar.

  2. Automatico (opcional): si TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID
     estan en el .env, publica directo en el canal via Bot API con
     parse_mode=HTML (ahi si se ve la negrita real). No se activa solo
     con tener el .env -- hay que llamar a publicar_automatico() o
     correr el script con --publicar.

Fuente de datos: Data/picks_hoy.json (el mismo JSON que ya alimenta la
seccion "Picks gratis de hoy" de la landing via sync_a_backend.py) --
no se inventa ni se recalcula nada, es exactamente lo que ya es publico
en la web.

Uso:
    python social/generar_mensaje_telegram.py              # solo genera el .txt
    python social/generar_mensaje_telegram.py --publicar    # ademas publica si hay credenciales

Salida: Data/social/telegram/<fecha>/mensaje.txt
"""
import json
import os
import sys
from datetime import date, datetime

RAIZ = os.path.dirname(os.path.abspath(__file__))
RAIZ_PIPELINE = os.path.dirname(RAIZ)
PICKS_HOY_JSON = os.path.join(RAIZ_PIPELINE, "Data", "picks_hoy.json")
SALIDA_BASE = os.path.join(RAIZ_PIPELINE, "Data", "social", "telegram")
ENV_PATH = os.path.join(RAIZ_PIPELINE, ".env")

BASE_URL = "https://sportpicks-suscripcion.vercel.app"


def _cargar_env(ruta):
    """Loader minimo de .env (KEY=VALUE por linea, sin comillas
    especiales) -- python-dotenv no esta instalado en este venv y no
    vale la pena agregar la dependencia solo por esto. Se usa
    unicamente para que la tarea programada (que no hereda variables
    de entorno de una sesion interactiva) encuentre las credenciales
    del bot sin tener que configurarlas a nivel de sistema operativo."""
    if not os.path.exists(ruta):
        return
    with open(ruta, encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            clave, _, valor = linea.partition("=")
            clave, valor = clave.strip(), valor.strip().strip('"').strip("'")
            os.environ.setdefault(clave, valor)


_cargar_env(ENV_PATH)

# Credenciales opcionales para el modo automatico -- nunca hardcodeadas
# aqui, se leen del entorno o de .env en la raiz del pipeline (mismo
# archivo .env que ya usa el backend, distinto solo en que aqui se
# hace un parseo minimo en vez de pydantic-settings). Si no estan, el
# script simplemente no intenta publicar y se queda en modo manual.
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")  # ej. "@sportpicksligas" o "-100123456789"

MESES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def _fecha_legible(fecha_iso):
    d = datetime.strptime(fecha_iso, "%Y-%m-%d")
    return f"{d.day} de {MESES[d.month - 1]}"


def _link_utm(campana):
    return f"{BASE_URL}/?utm_source=telegram&utm_medium=social&utm_campaign={campana}"


def cargar_picks_hoy():
    with open(PICKS_HOY_JSON, encoding="utf-8") as f:
        return json.load(f)


def _linea_pick(pick, html=False, fecha_hoy=None):
    emoji = pick.get("emoji", "⚽")
    partido = pick["partido"]
    mercado = pick["mercado"]
    cuota = pick.get("cuota_display", pick.get("cuota"))
    prob = pick.get("prob")
    nombre = f"<b>{partido}</b>" if html else partido.upper()
    # BUG REAL (05/08/2026): cuando el fallback_multi_dia de
    # generador_picks_ligas.py rellena "publicos" con partidos de otros
    # dias (porque hoy ninguno paso el piso de EV), este mensaje decia
    # "Picks gratis del <fecha_hoy>" sin aclarar que un partido en
    # particular jugaba manana o pasado -- se publico asi por error al
    # canal real de Telegram. Ahora se agrega la fecha real del partido
    # en la linea cuando difiere de fecha_hoy, sin importar si el fallback
    # esta activo o no (misma logica que PicksHoyScroll.tsx en el frontend).
    pick_fecha = pick.get("fecha")
    sufijo_fecha = ""
    if fecha_hoy and pick_fecha and pick_fecha != fecha_hoy:
        sufijo_fecha = f" ({_fecha_legible(pick_fecha)})"
    return f"{emoji} {nombre}{sufijo_fecha}\n   {mercado} · cuota @{cuota} · {prob}% prob."


def generar_mensaje(data, html=False):
    """html=False -> texto plano para copiar/pegar a mano (modo manual).
    html=True -> con tags <b> para publicar via Bot API (parse_mode=HTML)."""
    fecha_iso = data["fecha"]
    publicos = data.get("publicos", [])
    premium = data.get("premium", [])
    # Ver _linea_pick() -- si el fallback trajo partidos de otro dia, el
    # titulo tampoco debe decir "del <fecha_iso>" a secas (séria el mismo
    # error, solo que en el encabezado en vez de por partido).
    algun_otro_dia = any(p.get("fecha") and p["fecha"] != fecha_iso for p in publicos)

    campana = f"picks_diarios_{date.today().isoformat()}"
    link = _link_utm(campana)

    lineas_picks = "\n\n".join(_linea_pick(p, html=html, fecha_hoy=fecha_iso) for p in publicos)

    n_premium = len(premium)
    if n_premium:
        bloque_premium = (
            f"\n\n💎 Hay {n_premium} pick{'s' if n_premium != 1 else ''} premium más "
            f"con mejor EV, disponibles con la suscripción."
        )
    else:
        bloque_premium = ""

    titulo = "<b>📊 SportPicks Ligas</b>" if html else "📊 SPORTPICKS LIGAS"
    encabezado = (
        f"{titulo} -- Picks gratis (próximos partidos, hoy sin picks que pasen el filtro)"
        if algun_otro_dia
        else f"{titulo} -- Picks gratis del {_fecha_legible(fecha_iso)}"
    )

    mensaje = f"""{encabezado}

{lineas_picks}{bloque_premium}

👉 Historial público completo y picks de hoy: {link}

⚠️ Análisis estadístico, no garantía de resultado. Juega con responsabilidad. +18."""

    return mensaje


def publicar_automatico(mensaje_html):
    """Publica en el canal via Telegram Bot API. Requiere
    TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID en el entorno/.env y que el
    bot ya este agregado como administrador del canal (con permiso de
    publicar mensajes) -- eso se hace una sola vez a mano desde Telegram,
    no lo puede hacer este script."""
    import requests  # import local: no agrega dependencia si no se usa este modo

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Faltan TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID en el entorno -- no se publica, solo se guarda el .txt.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    resp = requests.post(url, json={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": mensaje_html,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }, timeout=15)

    if resp.status_code == 200 and resp.json().get("ok"):
        print("Publicado en el canal de Telegram.")
        return True

    print(f"Error al publicar en Telegram ({resp.status_code}): {resp.text}")
    return False


def main():
    data = cargar_picks_hoy()
    if not data.get("publicos"):
        print("No hay picks públicos en Data/picks_hoy.json todavía -- nada que generar.")
        return

    mensaje_manual = generar_mensaje(data, html=False)

    carpeta_salida = os.path.join(SALIDA_BASE, data["fecha"])
    os.makedirs(carpeta_salida, exist_ok=True)
    ruta = os.path.join(carpeta_salida, "mensaje.txt")
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(mensaje_manual)
        f.write("\n")

    print(f"Generado: {ruta}")
    print()
    print(mensaje_manual)

    if "--publicar" in sys.argv:
        mensaje_html = generar_mensaje(data, html=True)
        publicar_automatico(mensaje_html)


if __name__ == "__main__":
    main()
