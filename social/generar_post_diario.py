# -*- coding: utf-8 -*-
"""
generar_post_diario.py -- Fase 1 del plan de crecimiento organico
(ver plan_crecimiento_organico.md): motor de contenido semi-automatico.

Lee Data/historial_picks.csv (la misma fuente que ya alimenta el
dashboard publico de la web) y genera, para el ultimo dia con picks
liquidados:

  1. Una imagen cuadrada 1080x1080 (Facebook / Instagram feed).
  2. Una imagen vertical 1080x1920 (Instagram Stories/Reels, TikTok
     como post estatico).
  3. Un archivo de texto con 2 variantes de caption (Facebook e
     Instagram) listas para copiar/pegar.

Uso:
    python social/generar_post_diario.py

Salida: Data/social/<fecha>/ (imagenes + caption.txt). No modifica nada
mas del pipeline -- es de solo lectura sobre historial_picks.csv.

No requiere credenciales ni conexion a internet: todo el dato ya vive
en el CSV que el pipeline diario mantiene. Antonio revisa la carpeta de
salida y publica manualmente (no hay integracion de publicacion directa
a Meta/TikTok -- no existe conector para eso, ver conversacion previa).
"""
import csv
import os
from collections import defaultdict
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont

RAIZ = os.path.dirname(os.path.abspath(__file__))
RAIZ_PIPELINE = os.path.dirname(RAIZ)
HISTORIAL_CSV = os.path.join(RAIZ_PIPELINE, "Data", "historial_picks.csv")
SALIDA_BASE = os.path.join(RAIZ_PIPELINE, "Data", "social")

# Paleta exacta de la web (frontend/app/globals.css) -- mismo tema en
# todo el contenido de marca, sitio y redes.
BG = "#081210"
FG = "#f4fff0"
ACCENT = "#c8ff3d"
SURFACE = "#0f1f1b"
BORDER = "#1c332c"
ROJO_PERDIDO = "#ff6b6b"  # no esta en la paleta del sitio (que no marca
# perdidos con color propio), pero aqui ayuda a distinguir de un vistazo
# en un formato de imagen fija donde no hay hover ni texto adicional.

FUENTE_DIR = "/usr/share/fonts/truetype/dejavu"
FUENTE_BOLD = os.path.join(FUENTE_DIR, "DejaVuSans-Bold.ttf")
FUENTE_REG = os.path.join(FUENTE_DIR, "DejaVuSans.ttf")

MAX_PICKS_MOSTRADOS = 6


def cargar_historial():
    with open(HISTORIAL_CSV, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def ultimo_dia_liquidado(filas):
    """Fecha mas reciente con al menos un pick Ganado/Perdido -- no se
    asume "ayer" a ciegas porque la sincronizacion de resultados puede
    tener rezago de 1-2 dias (partidos que aun no terminan, API externa
    con delay). El texto generado usa la fecha real, nunca la palabra
    "ayer" a ciegas."""
    fechas = sorted({f["fecha"] for f in filas if f["estado"] in ("Ganado", "Perdido")})
    return fechas[-1] if fechas else None


def stats_historicas(filas):
    ganados = sum(1 for f in filas if f["estado"] == "Ganado")
    perdidos = sum(1 for f in filas if f["estado"] == "Perdido")
    liquidados = ganados + perdidos
    winrate = round(100 * ganados / liquidados, 1) if liquidados else None
    return {"ganados": ganados, "perdidos": perdidos, "liquidados": liquidados, "winrate": winrate}


def fecha_legible(fecha_iso):
    meses = [
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
    ]
    d = datetime.strptime(fecha_iso, "%Y-%m-%d")
    return f"{d.day} de {meses[d.month - 1]}"


def _fuente(tam, bold=True):
    return ImageFont.truetype(FUENTE_BOLD if bold else FUENTE_REG, tam)


def _texto_centrado(draw, cx, y, texto, fuente, fill):
    bbox = draw.textbbox((0, 0), texto, font=fuente)
    ancho = bbox[2] - bbox[0]
    draw.text((cx - ancho / 2, y), texto, font=fuente, fill=fill)
    return bbox[3] - bbox[1]


def _envolver_texto(draw, texto, fuente, ancho_max):
    """Word-wrap simple -- Pillow no lo trae integrado."""
    palabras = texto.split()
    lineas, actual = [], ""
    for palabra in palabras:
        prueba = f"{actual} {palabra}".strip()
        bbox = draw.textbbox((0, 0), prueba, font=fuente)
        if bbox[2] - bbox[0] <= ancho_max or not actual:
            actual = prueba
        else:
            lineas.append(actual)
            actual = palabra
    if actual:
        lineas.append(actual)
    return lineas


def _dibujar_tarjeta_pick(draw, x, y, ancho, pick, fuente_mercado, fuente_partido, fuente_chip):
    alto = 92
    draw.rounded_rectangle([x, y, x + ancho, y + alto], radius=14, fill=SURFACE, outline=BORDER, width=2)

    gano = pick["estado"] == "Ganado"
    chip_texto = "GANADO" if gano else "PERDIDO"
    chip_color = ACCENT if gano else ROJO_PERDIDO
    chip_w = draw.textbbox((0, 0), chip_texto, font=fuente_chip)[2] + 24
    draw.rounded_rectangle(
        [x + 20, y + 16, x + 20 + chip_w, y + 16 + 30], radius=15, fill=chip_color
    )
    draw.text((x + 32, y + 21), chip_texto, font=fuente_chip, fill=BG)

    partido = f"{pick['local']} vs {pick['visitante']}"
    if len(partido) > 42:
        partido = partido[:39] + "..."
    draw.text((x + 20 + chip_w + 16, y + 20), partido, font=fuente_partido, fill=FG)

    mercado = pick["mercado"]
    if len(mercado) > 60:
        mercado = mercado[:57] + "..."
    draw.text((x + 20, y + 54), mercado, font=fuente_mercado, fill=FG)


def _dibujar_bloque_principal(draw, y0, cx, ancho, picks_dia, fecha_iso):
    """Dibuja titulo + resumen + tarjetas de picks a partir de y0 y
    devuelve el y final (para poder medir la altura del bloque en una
    primera pasada sin dibujar nada, y asi centrarlo verticalmente en el
    formato vertical -- ver _render_imagen)."""
    y = y0
    y += _texto_centrado(draw, cx, y, "SPORTPICKS LIGAS", _fuente(int(ancho * 0.045)), ACCENT) + 20
    y += _texto_centrado(
        draw, cx, y, f"Resultados del {fecha_legible(fecha_iso)}", _fuente(int(ancho * 0.03), bold=False), FG
    ) + 40

    ganados_dia = sum(1 for p in picks_dia if p["estado"] == "Ganado")
    perdidos_dia = len(picks_dia) - ganados_dia
    resumen = f"{ganados_dia} acertados / {perdidos_dia} fallados"
    y += _texto_centrado(draw, cx, y, resumen, _fuente(int(ancho * 0.032)), FG) + 36

    mostrar = picks_dia[:MAX_PICKS_MOSTRADOS]
    tarjeta_ancho = ancho - 120
    fuente_partido = _fuente(24)
    fuente_mercado = _fuente(20, bold=False)
    fuente_chip = _fuente(16)
    for pick in mostrar:
        _dibujar_tarjeta_pick(draw, 60, y, tarjeta_ancho, pick, fuente_mercado, fuente_partido, fuente_chip)
        y += 92 + 14

    restantes = len(picks_dia) - len(mostrar)
    if restantes > 0:
        y += 6
        y += _texto_centrado(
            draw, cx, y, f"+ {restantes} pick(s) mas en el historial publico", _fuente(20, bold=False), FG
        )

    return y


def _render_imagen(picks_dia, fecha_iso, hist, ancho, alto):
    img = Image.new("RGB", (ancho, alto), BG)
    draw = ImageDraw.Draw(img)
    cx = ancho // 2

    margen_superior = 70 if alto > ancho else 50
    footer_y = alto - (170 if alto > ancho else 140)

    # Primera pasada (sobre una imagen descartable) solo para medir cuanto
    # ocupa el bloque de titulo+picks -- en el formato vertical (mas alto
    # que ancho) hay mucho mas espacio disponible que contenido, y sin este
    # centrado el resultado queda con un vacio grande abajo.
    img_medida = Image.new("RGB", (ancho, alto), BG)
    draw_medida = ImageDraw.Draw(img_medida)
    y_final_medido = _dibujar_bloque_principal(draw_medida, margen_superior, cx, ancho, picks_dia, fecha_iso)
    alto_bloque = y_final_medido - margen_superior
    espacio_disponible = footer_y - margen_superior
    offset_centrado = max(0, (espacio_disponible - alto_bloque) // 2) if alto > ancho else 0

    y_final = _dibujar_bloque_principal(draw, margen_superior + offset_centrado, cx, ancho, picks_dia, fecha_iso)

    # Footer con stats historicas, pegado abajo -- separado del bloque de
    # picks del dia para que quede claro que es el track record acumulado,
    # no el resultado de ese dia especifico.
    draw.line([(60, footer_y), (ancho - 60, footer_y)], fill=BORDER, width=2)
    footer_texto_y = footer_y + 24
    winrate_txt = f"{hist['winrate']}%" if hist["winrate"] is not None else "--"
    stat_txt = f"{winrate_txt} de acierto historico -- {hist['liquidados']} picks liquidados"
    _texto_centrado(draw, cx, footer_texto_y, stat_txt, _fuente(int(ancho * 0.026)), ACCENT)
    footer_texto_y += 40
    _texto_centrado(
        draw, cx, footer_texto_y, "Historial completo publico -- sportpicksligas.com",
        _fuente(int(ancho * 0.02), bold=False), FG,
    )

    return img


def generar_caption(picks_dia, fecha_iso, hist):
    ganados_dia = sum(1 for p in picks_dia if p["estado"] == "Ganado")
    perdidos_dia = len(picks_dia) - ganados_dia
    fecha_txt = fecha_legible(fecha_iso)
    winrate_txt = f"{hist['winrate']}%" if hist["winrate"] is not None else "--"

    ejemplos = []
    for p in picks_dia[:3]:
        emoji = "✅" if p["estado"] == "Ganado" else "❌"
        ejemplos.append(f"{emoji} {p['local']} vs {p['visitante']} -- {p['mercado']}")
    bloque_ejemplos = "\n".join(ejemplos)

    facebook = f"""📊 Resultados del {fecha_txt}

{ganados_dia} acertados, {perdidos_dia} fallados. Sin filtrar los que fallaron -- el historial completo, ganes o pierdas, queda público en la web.

{bloque_ejemplos}

Track record histórico: {winrate_txt} de acierto en {hist['liquidados']} picks liquidados.

👉 Historial completo y picks gratis de hoy en sportpicksligas.com

⚠️ Análisis estadístico, no garantía de resultado. Juega con responsabilidad. +18."""

    instagram = f"""Resultados del {fecha_txt} 📊

{ganados_dia} acertados / {perdidos_dia} fallados -- transparente, sin filtrar lo que sale mal.

{bloque_ejemplos}

{winrate_txt} de acierto histórico ({hist['liquidados']} picks liquidados).

Link en la bio 👉 historial completo + picks gratis de hoy.

⚠️ Contenido de análisis estadístico, no garantía de resultado. +18.

#SportPicksLigas #PronosticosFutbol #FutbolPeru #DatosDeportivos #ApuestasResponsables"""

    return facebook, instagram


def main():
    filas = cargar_historial()
    fecha_iso = ultimo_dia_liquidado(filas)
    if not fecha_iso:
        print("No hay picks liquidados todavia en historial_picks.csv -- nada que generar.")
        return

    picks_dia = [f for f in filas if f["fecha"] == fecha_iso and f["estado"] in ("Ganado", "Perdido")]
    hist = stats_historicas(filas)

    carpeta_salida = os.path.join(SALIDA_BASE, fecha_iso)
    os.makedirs(carpeta_salida, exist_ok=True)

    img_cuadrada = _render_imagen(picks_dia, fecha_iso, hist, 1080, 1080)
    img_cuadrada.save(os.path.join(carpeta_salida, "post_cuadrado_1080x1080.png"))

    img_vertical = _render_imagen(picks_dia, fecha_iso, hist, 1080, 1920)
    img_vertical.save(os.path.join(carpeta_salida, "post_vertical_1080x1920.png"))

    facebook, instagram = generar_caption(picks_dia, fecha_iso, hist)
    with open(os.path.join(carpeta_salida, "caption.txt"), "w", encoding="utf-8") as f:
        f.write("=== FACEBOOK ===\n\n")
        f.write(facebook)
        f.write("\n\n\n=== INSTAGRAM ===\n\n")
        f.write(instagram)
        f.write("\n")

    print(f"Generado en {carpeta_salida}:")
    print("  - post_cuadrado_1080x1080.png  (Facebook / Instagram feed)")
    print("  - post_vertical_1080x1920.png  (Instagram Stories/Reels, TikTok)")
    print("  - caption.txt                  (texto listo para Facebook e Instagram)")


if __name__ == "__main__":
    main()
