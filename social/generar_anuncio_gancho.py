# -*- coding: utf-8 -*-
"""
generar_anuncio_gancho.py -- Fase 1 del plan de crecimiento organico
(ver plan_crecimiento_organico.md).

A diferencia de generar_post_diario.py (recap transparente de
ganados/perdidos), esto es un anuncio de gancho: una sola pieza fuerte,
pensada para llamar la atencion de alguien que hoy sigue a un "tipster"
informal y no le esta funcionando. No lista picks individuales ni
resultados -- es puro hook + prueba social (winrate real) + CTA.

Pensado para: post fijado / portada de perfil / primera pieza a mostrar
en redes, y tambien como creativo base si mas adelante se decide correr
pauta paga (Fase 5 del plan: solo se paga por boostear algo que ya
funciona organicamente, no se parte de cero).

Genera 2 variantes de headline (A y B) en 2 formatos cada una:
  - Cuadrado 1080x1080 (Facebook / Instagram feed)
  - Vertical 1080x1920 (Instagram Stories/Reels, TikTok)

Uso:
    python social/generar_anuncio_gancho.py

Salida: Data/social/anuncios/<variante>_<formato>.png
"""
import csv
import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont

RAIZ = os.path.dirname(os.path.abspath(__file__))
RAIZ_PIPELINE = os.path.dirname(RAIZ)
HISTORIAL_CSV = os.path.join(RAIZ_PIPELINE, "Data", "historial_picks.csv")
SALIDA = os.path.join(RAIZ_PIPELINE, "Data", "social", "anuncios")

# Paleta exacta de la web (frontend/app/globals.css).
BG = "#081210"
BG_CLARO = "#0f1f1b"  # = --surface, usado para el degradado de fondo
FG = "#f4fff0"
ACCENT = "#c8ff3d"
BORDER = "#1c332c"

FUENTE_DIR = "/usr/share/fonts/truetype/dejavu"
FUENTE_BOLD = os.path.join(FUENTE_DIR, "DejaVuSans-Bold.ttf")
FUENTE_REG = os.path.join(FUENTE_DIR, "DejaVuSans.ttf")

# Dos variantes de headline -- misma prueba social (winrate real), gancho
# distinto. "A" es la frase que diste tal cual, pulida para caber en el
# formato; "B" es una alternativa mas corta por si conviene probar cual
# engancha mas (A/B real, no solo teorico -- se puede medir con el
# alcance/guardados de cada post).
VARIANTES = {
    "a": {
        "headline": "¿CANSADO DE TIPSTERS\nQUE NO ACIERTAN?",
        "subrayado": "TIPSTERS",
        "subheadline": "Pronósticos basados en un modelo estadístico real,\nno en corazonadas.",
        "cta": "EMPIEZA GRATIS HOY",
    },
    "b": {
        "headline": "DEJA DE APOSTAR\nA CIEGAS",
        "subrayado": "CIEGAS",
        "subheadline": "En SportPicks Ligas cada pick sale de un modelo\ncon historial 100% público.",
        "cta": "VER PRONÓSTICOS DE HOY",
    },
}


def stats_historicas():
    with open(HISTORIAL_CSV, encoding="utf-8") as f:
        filas = list(csv.DictReader(f))
    ganados = sum(1 for f_ in filas if f_["estado"] == "Ganado")
    perdidos = sum(1 for f_ in filas if f_["estado"] == "Perdido")
    liquidados = ganados + perdidos
    winrate = round(100 * ganados / liquidados, 1) if liquidados else None
    return {"liquidados": liquidados, "winrate": winrate}


def _fuente(tam, bold=True):
    return ImageFont.truetype(FUENTE_BOLD if bold else FUENTE_REG, tam)


def _envolver(draw, texto, fuente, ancho_max):
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


def _ajustar_fuente_a_ancho(draw, texto, ancho_max, tam_inicial, tam_minimo=28, bold=True, max_lineas=3):
    """Encuentra el tamaño de fuente mas grande (bajando de a poco desde
    tam_inicial) tal que el texto, envuelto automaticamente, entre en
    ancho_max sin superar max_lineas -- reemplaza los saltos de linea
    manuales fijos, que se salian del lienzo con textos largos como
    "¿CANSADO DE TIPSTERS" a fuentes grandes."""
    texto_plano = texto.replace("\n", " ")
    for tam in range(tam_inicial, tam_minimo - 1, -2):
        fuente = _fuente(tam, bold=bold)
        lineas = _envolver(draw, texto_plano, fuente, ancho_max)
        if len(lineas) <= max_lineas:
            return fuente, lineas
    return _fuente(tam_minimo, bold=bold), _envolver(draw, texto_plano, _fuente(tam_minimo, bold=bold), ancho_max)


def _texto_multilinea_centrado(draw, cx, y, texto, fuente, fill, interlineado=1.15, resaltar=None, color_resalte=None, lineas=None):
    """Dibuja texto centrado, con opcion de resaltar una palabra
    especifica en otro color (para el gancho -- ej. "TIPSTERS" en verde
    dentro de un titular blanco). Si se pasa `lineas` ya envueltas (ver
    _ajustar_fuente_a_ancho), las usa tal cual; si no, separa por "\n"
    (para textos cortos donde el salto manual si es seguro, como el
    subtitular)."""
    lineas = lineas if lineas is not None else texto.split("\n")
    alto_linea = fuente.size * interlineado
    for linea in lineas:
        if resaltar and resaltar in linea:
            antes, despues = linea.split(resaltar, 1)
            ancho_antes = draw.textbbox((0, 0), antes, font=fuente)[2]
            ancho_resaltar = draw.textbbox((0, 0), resaltar, font=fuente)[2]
            ancho_despues = draw.textbbox((0, 0), despues, font=fuente)[2]
            ancho_total = ancho_antes + ancho_resaltar + ancho_despues
            x = cx - ancho_total / 2
            draw.text((x, y), antes, font=fuente, fill=fill)
            x += ancho_antes
            draw.text((x, y), resaltar, font=fuente, fill=color_resalte or fill)
            x += ancho_resaltar
            draw.text((x, y), despues, font=fuente, fill=fill)
        else:
            bbox = draw.textbbox((0, 0), linea, font=fuente)
            ancho = bbox[2] - bbox[0]
            draw.text((cx - ancho / 2, y), linea, font=fuente, fill=fill)
        y += alto_linea
    return y


def _fondo_degradado(ancho, alto):
    """Degradado vertical sutil BG -> BG_CLARO -> BG (mas luz al centro)
    para que no quede un plano solido -- se siente mas "anuncio" y menos
    "diapositiva"."""
    img = Image.new("RGB", (ancho, alto), BG)
    top = tuple(int(BG[i:i + 2], 16) for i in (1, 3, 5))
    mid = tuple(int(BG_CLARO[i:i + 2], 16) for i in (1, 3, 5))
    for y in range(alto):
        t = y / alto
        # Curva simple: mas parecido a BG_CLARO cerca del centro (t=0.5).
        peso_centro = 1 - abs(t - 0.5) * 2
        color = tuple(int(top[i] + (mid[i] - top[i]) * peso_centro * 0.8) for i in range(3))
        ImageDraw.Draw(img).line([(0, y), (ancho, y)], fill=color)
    return img


def _resplandor(ancho, alto, cx, cy, radio, color, opacidad):
    """Elipse de acento difuminada detras del titular -- da sensacion de
    foco/spotlight sin necesitar assets externos."""
    capa = Image.new("RGBA", (ancho, alto), (0, 0, 0, 0))
    draw = ImageDraw.Draw(capa)
    r, g, b = tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))
    draw.ellipse([cx - radio, cy - radio, cx + radio, cy + radio], fill=(r, g, b, opacidad))
    capa = capa.filter(ImageFilter.GaussianBlur(radio // 2))
    return capa


def _dibujar_bloque_principal(draw, y0, cx, ancho, alto, v, stats):
    """Marca + titular + subtitular + sello de prueba social, a partir de
    y0. Devuelve el y final -- se usa dos veces (una de solo medicion,
    sobre un draw descartable, y otra real) para poder centrar todo el
    bloque verticalmente en el formato vertical, que si no queda con un
    hueco grande entre el sello y el boton de CTA."""
    y = y0
    marca = "SPORTPICKS LIGAS"
    fuente_marca = _fuente(int(ancho * 0.032))
    bbox = draw.textbbox((0, 0), marca, font=fuente_marca)
    draw.text((cx - (bbox[2] - bbox[0]) / 2, y), marca, font=fuente_marca, fill=ACCENT)
    y += (bbox[3] - bbox[1]) + int(alto * 0.06)

    margen_titular = int(ancho * 0.08)
    fuente_titular, lineas_titular = _ajustar_fuente_a_ancho(
        draw, v["headline"], ancho - 2 * margen_titular, tam_inicial=int(ancho * 0.095),
    )
    y = _texto_multilinea_centrado(
        draw, cx, y, v["headline"], fuente_titular, FG,
        resaltar=v["subrayado"], color_resalte=ACCENT, lineas=lineas_titular,
    )
    y += int(alto * 0.03)

    fuente_sub = _fuente(int(ancho * 0.034), bold=False)
    y = _texto_multilinea_centrado(draw, cx, y, v["subheadline"], fuente_sub, FG, interlineado=1.3)
    y += int(alto * 0.05)

    winrate_txt = f"{stats['winrate']}%" if stats["winrate"] is not None else "--"
    sello_txt1 = f"{winrate_txt} DE ACIERTO"
    sello_txt2 = f"{stats['liquidados']} picks liquidados · historial público"
    fuente_sello1 = _fuente(int(ancho * 0.05))
    fuente_sello2 = _fuente(int(ancho * 0.024), bold=False)
    bbox1 = draw.textbbox((0, 0), sello_txt1, font=fuente_sello1)
    bbox2 = draw.textbbox((0, 0), sello_txt2, font=fuente_sello2)
    ancho_sello = max(bbox1[2] - bbox1[0], bbox2[2] - bbox2[0]) + 100
    alto_sello = 150
    sello_x0 = cx - ancho_sello / 2
    draw.rounded_rectangle(
        [sello_x0, y, sello_x0 + ancho_sello, y + alto_sello],
        radius=18, outline=ACCENT, width=3, fill=BG,
    )
    draw.text((cx - (bbox1[2] - bbox1[0]) / 2, y + 24), sello_txt1, font=fuente_sello1, fill=ACCENT)
    draw.text((cx - (bbox2[2] - bbox2[0]) / 2, y + 24 + (bbox1[3] - bbox1[1]) + 14), sello_txt2, font=fuente_sello2, fill=FG)
    y += alto_sello
    return y


def _render(variante_id, ancho, alto, stats):
    v = VARIANTES[variante_id]
    img = _fondo_degradado(ancho, alto).convert("RGBA")

    resplandor = _resplandor(ancho, alto, ancho // 2, int(alto * 0.38), int(ancho * 0.55), ACCENT, 40)
    img = Image.alpha_composite(img, resplandor)
    draw = ImageDraw.Draw(img)
    cx = ancho // 2

    margen_superior = int(alto * 0.07)
    gap_cta = int(alto * 0.05)
    alto_cta = 92
    footer_y = alto - int(alto * 0.16)  # tope inferior del bloque (antes de CTA fijo + dominio/disclaimer)

    # Primera pasada, solo para medir cuanto ocupa marca+titular+sub+sello
    # -- en el formato vertical (1080x1920) sobra mucho mas espacio que en
    # el cuadrado, y sin este centrado el CTA quedaba pegado al fondo con
    # un vacio enorme en el medio.
    img_medida = Image.new("RGB", (ancho, alto), BG)
    draw_medida = ImageDraw.Draw(img_medida)
    y_medido = _dibujar_bloque_principal(draw_medida, margen_superior, cx, ancho, alto, v, stats)
    alto_bloque_total = (y_medido - margen_superior) + gap_cta + alto_cta
    espacio_disponible = footer_y - margen_superior
    offset_centrado = max(0, (espacio_disponible - alto_bloque_total) // 2) if alto > ancho else 0

    y = _dibujar_bloque_principal(draw, margen_superior + offset_centrado, cx, ancho, alto, v, stats)

    # CTA -- boton solido, para que se lea como anuncio y no como texto suelto.
    cta_y = y + gap_cta
    fuente_cta = _fuente(int(ancho * 0.036))
    bbox_cta = draw.textbbox((0, 0), v["cta"], font=fuente_cta)
    ancho_cta = (bbox_cta[2] - bbox_cta[0]) + 120
    cta_x0 = cx - ancho_cta / 2
    draw.rounded_rectangle(
        [cta_x0, cta_y, cta_x0 + ancho_cta, cta_y + alto_cta], radius=alto_cta // 2, fill=ACCENT,
    )
    draw.text(
        (cx - (bbox_cta[2] - bbox_cta[0]) / 2, cta_y + (alto_cta - (bbox_cta[3] - bbox_cta[1])) / 2 - bbox_cta[1]),
        v["cta"], font=fuente_cta, fill=BG,
    )

    # Dominio + disclaimer, discreto, pegado al fondo.
    pie_y = alto - int(alto * 0.055)
    fuente_pie = _fuente(int(ancho * 0.022), bold=False)
    pie_txt = "sportpicksligas.com"
    bbox_pie = draw.textbbox((0, 0), pie_txt, font=fuente_pie)
    draw.text((cx - (bbox_pie[2] - bbox_pie[0]) / 2, pie_y), pie_txt, font=fuente_pie, fill=FG)

    fuente_disclaimer = _fuente(int(ancho * 0.016), bold=False)
    disclaimer_txt = "Análisis estadístico, no garantía de resultado. Juega con responsabilidad. +18."
    lineas_disc = _envolver(draw, disclaimer_txt, fuente_disclaimer, ancho - 160)
    dy = alto - int(alto * 0.025)
    for linea in reversed(lineas_disc):
        bbox_d = draw.textbbox((0, 0), linea, font=fuente_disclaimer)
        draw.text((cx - (bbox_d[2] - bbox_d[0]) / 2, dy), linea, font=fuente_disclaimer, fill=BORDER)
        dy -= (bbox_d[3] - bbox_d[1]) + 6

    return img.convert("RGB")


def main():
    stats = stats_historicas()
    os.makedirs(SALIDA, exist_ok=True)

    formatos = {"cuadrado_1080x1080": (1080, 1080), "vertical_1080x1920": (1080, 1920)}
    for variante_id in VARIANTES:
        for nombre_formato, (ancho, alto) in formatos.items():
            img = _render(variante_id, ancho, alto, stats)
            ruta = os.path.join(SALIDA, f"variante_{variante_id}_{nombre_formato}.png")
            img.save(ruta)
            print(f"Generado: {ruta}")


if __name__ == "__main__":
    main()
