# -*- coding: utf-8 -*-
"""
generar_anuncio_producto.py -- Fase 1 del plan de crecimiento organico.

Segunda iteracion del anuncio de gancho (ver generar_anuncio_gancho.py),
despues de que Antonio compartio un ejemplo real de un competidor
(PropsBR) como referencia: en vez de un titular + un numero de winrate
en %, lo que convence es un "mockup" de producto -- un panel que parece
screenshot real de la app, lleno de picks en verde, con cantidad de
aciertos (no porcentaje) como prueba social, mas bullets de features y
un CTA en caja. Formato calcado del ejemplo (headline blanco+verde,
panel oscuro con filas de picks, 3 bullets con icono circular, caja de
CTA con flecha, disclaimer chico abajo).

Diferencia clave vs. copiar al competidor: los picks que se muestran en
el panel son REALES (los ultimos ganados de Data/historial_picks.csv),
no inventados -- y la prueba social es una cantidad real de aciertos,
no una cifra de odds combinada armada para la pieza.

Uso:
    python social/generar_anuncio_producto.py

Salida: Data/social/anuncios/producto_<formato>.png
"""
import csv
import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont

RAIZ = os.path.dirname(os.path.abspath(__file__))
RAIZ_PIPELINE = os.path.dirname(RAIZ)
HISTORIAL_CSV = os.path.join(RAIZ_PIPELINE, "Data", "historial_picks.csv")
SALIDA = os.path.join(RAIZ_PIPELINE, "Data", "social", "anuncios")

BG = "#081210"
BG_CLARO = "#0f1f1b"
FG = "#f4fff0"
ACCENT = "#c8ff3d"
SURFACE = "#0f1f1b"
BORDER = "#1c332c"
# Texto secundario (liga/mercado, descripciones de bullets, disclaimer) --
# BORDER (#1c332c) es un color de LINEA, casi negro sobre SURFACE/BG;
# usarlo como texto lo dejaba practicamente ilegible. MUTED es un
# verde-grisaceo claro, con contraste real pero mas discreto que FG.
MUTED = "#9fb8ad"

FUENTE_DIR = "/usr/share/fonts/truetype/dejavu"
FUENTE_BOLD = os.path.join(FUENTE_DIR, "DejaVuSans-Bold.ttf")
FUENTE_REG = os.path.join(FUENTE_DIR, "DejaVuSans.ttf")

MAX_FILAS_PANEL = 4

BULLETS = [
    ("MODELO REAL", "Dixon-Coles + Monte Carlo sobre goles, córners y forma reciente."),
    ("DATOS DIARIOS", "Pronósticos nuevos antes de cada fecha, no reciclados."),
    ("HISTORIAL PÚBLICO", "Nada se esconde: cada pick queda registrado y verificable."),
]

HEADLINE_BLANCO = "PRONÓSTICOS"
HEADLINE_VERDE = "QUE SÍ ACIERTAN"
TAGLINE = "MÁS DATOS. MÁS CONFIANZA."
CTA_TEXTO = "EMPIEZA GRATIS · GANA CONFIANZA"


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


def _ancho_texto(draw, texto, fuente):
    bbox = draw.textbbox((0, 0), texto, font=fuente)
    return bbox[2] - bbox[0]


def _alto_texto(draw, texto, fuente):
    bbox = draw.textbbox((0, 0), texto, font=fuente)
    return bbox[3] - bbox[1]


def cargar_picks_recientes():
    with open(HISTORIAL_CSV, encoding="utf-8") as f:
        filas = list(csv.DictReader(f))
    ganados = [f_ for f_ in filas if f_["estado"] == "Ganado"]
    ganados.sort(key=lambda f_: f"{f_['fecha']} {f_['hora']}", reverse=True)
    return ganados[:MAX_FILAS_PANEL], len(ganados)


def _fondo_degradado(ancho, alto):
    img = Image.new("RGB", (ancho, alto), BG)
    top = tuple(int(BG[i:i + 2], 16) for i in (1, 3, 5))
    mid = tuple(int(BG_CLARO[i:i + 2], 16) for i in (1, 3, 5))
    for y in range(alto):
        t = y / alto
        peso_centro = 1 - abs(t - 0.42) * 1.6
        peso_centro = max(0, min(1, peso_centro))
        color = tuple(int(top[i] + (mid[i] - top[i]) * peso_centro * 0.7) for i in range(3))
        ImageDraw.Draw(img).line([(0, y), (ancho, y)], fill=color)
    return img


def _icono_barras(draw, x, y, escala, color):
    """Icono de 3 barras ascendentes -- mismo lenguaje visual que el
    logo de PropsBR (barras), pero generico/propio, no una copia de su
    marca."""
    anchos_barra = int(8 * escala)
    gap = int(5 * escala)
    alturas = [0.5, 0.8, 1.1]
    base_y = y + int(24 * escala)
    for i, h in enumerate(alturas):
        bx = x + i * (anchos_barra + gap)
        by = base_y - int(24 * escala * h)
        draw.rounded_rectangle([bx, by, bx + anchos_barra, base_y], radius=anchos_barra // 2, fill=color)


def _icono_check(draw, cx, cy, radio, color_circulo, color_check):
    draw.ellipse([cx - radio, cy - radio, cx + radio, cy + radio], fill=color_circulo)
    # Palomita simple con dos segmentos de linea.
    draw.line(
        [(cx - radio * 0.5, cy), (cx - radio * 0.1, cy + radio * 0.4), (cx + radio * 0.55, cy - radio * 0.4)],
        fill=color_check, width=max(2, int(radio * 0.28)), joint="curve",
    )


def _mini_barras(draw, x, y, ancho, alto, prob, color):
    """Grupo de barritas tipo mini-grafico -- la altura de cada barra
    aumenta con la probabilidad del pick, asi que no es decorativo al
    azar sino que refleja el dato real (mas parecido al "SCORE" con
    graficas de barras del ejemplo de referencia)."""
    n = 5
    ancho_barra = ancho / n * 0.55
    gap = ancho / n * 0.45
    nivel = max(0.25, min(1.0, prob / 100))
    for i in range(n):
        factor = nivel * (0.4 + 0.6 * (i + 1) / n)
        h = alto * min(1.0, factor)
        bx = x + i * (ancho_barra + gap)
        by = y + (alto - h)
        draw.rounded_rectangle([bx, by, bx + ancho_barra, y + alto], radius=2, fill=color)


def _panel_picks(draw, x0, y0, ancho, picks, ganados_total, compacto=False):
    """Dibuja el panel tipo "screenshot de producto" con los picks
    recientes en verde -- reemplaza el numero de winrate en % (que un
    usuario nuevo no sabe interpretar) por una cantidad de aciertos
    (concreta, facil de leer de un vistazo) mas la sensacion de "todo
    sale positivo" que pedia Antonio. `compacto` aprieta filas/paddings
    para el formato feed (4:5), mas bajo que el vertical de Stories."""
    pad = 24 if compacto else 32
    alto_header = 70 if compacto else 78
    alto_fila = 96 if compacto else 118
    alto_footer = 96 if compacto else 110
    alto_panel = alto_header + alto_fila * len(picks) + alto_footer + pad
    draw.rounded_rectangle([x0, y0, x0 + ancho, y0 + alto_panel], radius=28, fill=SURFACE, outline=BORDER, width=2)

    # Header del panel -- logo chico + titulo, como la barra superior de
    # una app real.
    _icono_barras(draw, x0 + pad, y0 + 20, 1.0, ACCENT)
    fuente_marca = _fuente(26)
    draw.text((x0 + pad + 42, y0 + 22), "SportPicks Ligas", font=fuente_marca, fill=FG)
    fuente_sub = _fuente(20, bold=False)
    draw.text((x0 + pad, y0 + alto_header - 6), "Pronósticos recientes · EV positivo", font=fuente_sub, fill=FG)

    y = y0 + alto_header + (10 if compacto else 14)
    fuente_partido = _fuente(22 if compacto else 25)
    fuente_meta = _fuente(17 if compacto else 19, bold=False)
    fuente_prob = _fuente(26 if compacto else 30)
    y_partido, y_meta, y_prob, y_icono = (10, 38, 16, 32) if compacto else (14, 46, 22, 40)
    for pick in picks:
        draw.line([(x0 + pad, y), (x0 + ancho - pad, y)], fill=BORDER, width=1)
        partido = f"{pick['local']} vs {pick['visitante']}"
        if len(partido) > 34:
            partido = partido[:31] + "..."
        draw.text((x0 + pad, y + y_partido), partido, font=fuente_partido, fill=FG)
        meta = f"{pick['liga_nombre']} · {pick['mercado']}"
        if len(meta) > 46:
            meta = meta[:43] + "..."
        draw.text((x0 + pad, y + y_meta), meta, font=fuente_meta, fill=MUTED)

        # Check + probabilidad a la derecha.
        prob = float(pick["prob"])
        prob_txt = f"{prob:.0f}%"
        ancho_prob = _ancho_texto(draw, prob_txt, fuente_prob)
        x_prob = x0 + ancho - pad - ancho_prob - 44
        _icono_check(draw, x0 + ancho - pad - 20, y + y_icono, 14 if compacto else 16, ACCENT, BG)
        draw.text((x_prob, y + y_prob), prob_txt, font=fuente_prob, fill=ACCENT)

        # Mini-barras a la izquierda de la prob, reflejando el dato.
        _mini_barras(draw, x_prob - 130, y + y_icono - 6, 110, 28 if compacto else 34, prob, ACCENT)

        y += alto_fila

    # Footer del panel -- cantidad de aciertos, NO porcentaje.
    footer_y = y + 10
    draw.rounded_rectangle(
        [x0 + pad // 2, footer_y, x0 + ancho - pad // 2, footer_y + alto_footer - 20],
        radius=16, fill=BG,
    )
    fuente_num = _fuente(40 if compacto else 46)
    fuente_num_label = _fuente(18 if compacto else 20, bold=False)
    num_txt = f"{ganados_total}"
    label_txt = "PRONÓSTICOS ACERTADOS Y CONTANDO"
    ancho_num = _ancho_texto(draw, num_txt, fuente_num)
    ancho_label = _ancho_texto(draw, label_txt, fuente_num_label)
    cx_footer = x0 + ancho // 2
    total_ancho = ancho_num + 16 + ancho_label
    y_footer_texto = footer_y + (18 if compacto else 24)
    draw.text((cx_footer - total_ancho / 2, y_footer_texto), num_txt, font=fuente_num, fill=ACCENT)
    draw.text(
        (cx_footer - total_ancho / 2 + ancho_num + 16, y_footer_texto + 14),
        label_txt, font=fuente_num_label, fill=FG,
    )

    return alto_panel


def _bullet(draw, x0, y0, ancho, titulo, descripcion, compacto=False):
    radio = 24 if compacto else 28
    cx_icono = x0 + radio + 4
    cy_icono = y0 + radio + 4
    draw.ellipse(
        [cx_icono - radio, cy_icono - radio, cx_icono + radio, cy_icono + radio],
        outline=ACCENT, width=3,
    )
    _icono_check(draw, cx_icono, cy_icono, 12 if compacto else 14, ACCENT, BG)

    x_texto = x0 + radio * 2 + 28
    fuente_titulo = _fuente(24 if compacto else 28)
    draw.text((x_texto, y0 - 4), titulo, font=fuente_titulo, fill=FG)
    fuente_desc = _fuente(18 if compacto else 21, bold=False)
    lineas = _envolver(draw, descripcion, fuente_desc, ancho - (x_texto - x0) - 10)
    gap_titulo = 32 if compacto else 38
    alto_linea = 24 if compacto else 28
    dy = y0 - 4 + gap_titulo
    for linea in lineas:
        draw.text((x_texto, dy), linea, font=fuente_desc, fill=MUTED)
        dy += alto_linea
    return max(radio * 2 + 10, dy - y0 + 10)


def _dibujar_bloque(draw, y0, cx, ancho, alto, picks, ganados_total, compacto=False):
    y = y0

    fuente_marca = _fuente(int(ancho * (0.026 if compacto else 0.03)))
    marca = "SPORTPICKS LIGAS"
    draw.text((cx - _ancho_texto(draw, marca, fuente_marca) / 2, y), marca, font=fuente_marca, fill=ACCENT)
    y += _alto_texto(draw, marca, fuente_marca) + int(alto * (0.02 if compacto else 0.035))

    fuente_h1 = _fuente(int(ancho * (0.075 if compacto else 0.09)))
    draw.text((cx - _ancho_texto(draw, HEADLINE_BLANCO, fuente_h1) / 2, y), HEADLINE_BLANCO, font=fuente_h1, fill=FG)
    y += _alto_texto(draw, HEADLINE_BLANCO, fuente_h1) + 6
    draw.text((cx - _ancho_texto(draw, HEADLINE_VERDE, fuente_h1) / 2, y), HEADLINE_VERDE, font=fuente_h1, fill=ACCENT)
    y += _alto_texto(draw, HEADLINE_VERDE, fuente_h1) + int(alto * (0.012 if compacto else 0.02))

    if not compacto:
        fuente_tag = _fuente(int(ancho * 0.026), bold=False)
        draw.text((cx - _ancho_texto(draw, TAGLINE, fuente_tag) / 2, y), TAGLINE, font=fuente_tag, fill=FG)
        y += _alto_texto(draw, TAGLINE, fuente_tag) + int(alto * 0.04)
    else:
        y += int(alto * 0.015)

    ancho_panel = ancho - int(ancho * 0.12)
    x0_panel = cx - ancho_panel / 2
    alto_panel = _panel_picks(draw, x0_panel, y, ancho_panel, picks, ganados_total, compacto=compacto)
    y += alto_panel + int(alto * (0.025 if compacto else 0.04))

    ancho_bullets = ancho - int(ancho * 0.14)
    x0_bullets = cx - ancho_bullets / 2
    for titulo, desc in BULLETS:
        alto_b = _bullet(draw, x0_bullets, y, ancho_bullets, titulo, desc, compacto=compacto)
        y += alto_b + int(alto * (0.01 if compacto else 0.018))
    y += int(alto * (0.01 if compacto else 0.02))

    return y


def _dibujar_cta(draw, y, cx, ancho):
    fuente_cta = _fuente(int(ancho * 0.032))
    ancho_txt = _ancho_texto(draw, CTA_TEXTO, fuente_cta)
    pad_x, pad_y = 40, 26
    box_ancho = ancho - int(ancho * 0.12)
    x0 = cx - box_ancho / 2
    alto_caja = _alto_texto(draw, CTA_TEXTO, fuente_cta) + pad_y * 2
    draw.rounded_rectangle([x0, y, x0 + box_ancho, y + alto_caja], radius=16, outline=ACCENT, width=3)
    draw.text((cx - ancho_txt / 2, y + pad_y), CTA_TEXTO, font=fuente_cta, fill=ACCENT)
    return alto_caja


def _render(ancho, alto, picks, ganados_total):
    img = _fondo_degradado(ancho, alto).convert("RGBA")
    resplandor = Image.new("RGBA", (ancho, alto), (0, 0, 0, 0))
    draw_r = ImageDraw.Draw(resplandor)
    r, g, b = tuple(int(ACCENT[i:i + 2], 16) for i in (1, 3, 5))
    draw_r.ellipse(
        [ancho // 2 - ancho * 0.6, alto * 0.02, ancho // 2 + ancho * 0.6, alto * 0.5],
        fill=(r, g, b, 22),
    )
    resplandor = resplandor.filter(ImageFilter.GaussianBlur(80))
    img = Image.alpha_composite(img, resplandor)
    draw = ImageDraw.Draw(img)
    cx = ancho // 2

    margen_superior = int(alto * 0.045)
    margen_inferior = int(alto * 0.05)

    # Formato feed (1080x1350, ratio 1.25) es mucho mas bajo que el
    # vertical de historias (1080x1920, ratio 1.78) -- con el mismo
    # contenido completo no entra, asi que en ratios "achatados" se usa
    # una version compacta (paddings/fuentes mas chicas, sin tagline).
    compacto = (alto / ancho) < 1.4

    # Doble pasada: medir el bloque completo (marca+headline+panel+bullets)
    # para centrarlo junto con el CTA dentro del lienzo -- incluso con
    # todo este contenido, el formato vertical 1080x1920 deja mas espacio
    # del que ocupa el bloque a tamaños legibles, y sin centrar queda
    # descompensado como en la primera version del anuncio de gancho.
    img_medida = Image.new("RGB", (ancho, alto), BG)
    draw_medida = ImageDraw.Draw(img_medida)
    y_fin_medido = _dibujar_bloque(draw_medida, margen_superior, cx, ancho, alto, picks, ganados_total, compacto=compacto)
    alto_cta_medido = _dibujar_cta(draw_medida, y_fin_medido, cx, ancho)
    alto_disclaimer_reservado = int(alto * 0.06)
    alto_bloque_total = (y_fin_medido - margen_superior) + alto_cta_medido

    espacio_disponible = alto - margen_superior - margen_inferior - alto_disclaimer_reservado
    offset = max(0, (espacio_disponible - alto_bloque_total) // 2)

    y_fin = _dibujar_bloque(draw, margen_superior + offset, cx, ancho, alto, picks, ganados_total, compacto=compacto)
    cta_y = y_fin + int(alto * 0.015)
    _dibujar_cta(draw, cta_y, cx, ancho)

    dy = alto - int(alto * 0.02)
    fuente_disc = _fuente(int(ancho * 0.017), bold=False)
    disc_txt = "Análisis estadístico, no garantía de resultado. Juega con responsabilidad. +18."
    lineas_disc = _envolver(draw, disc_txt, fuente_disc, ancho - 160)
    for linea in reversed(lineas_disc):
        ancho_l = _ancho_texto(draw, linea, fuente_disc)
        draw.text((cx - ancho_l / 2, dy - _alto_texto(draw, linea, fuente_disc)), linea, font=fuente_disc, fill=MUTED)
        dy -= _alto_texto(draw, linea, fuente_disc) + 6

    return img.convert("RGB")


BASE_URL = "https://sportpicks-suscripcion.vercel.app"
CANAL_WHATSAPP_URL = "https://whatsapp.com/channel/0029VbCjgNuEwEjpU2PsOl0p"

# Hashtags diferenciados por plataforma -- no el mismo bloque de 5 en las
# 3 redes. En Facebook el hashtag casi no aporta alcance (el algoritmo
# prioriza engagement en paginas/grupos, no busqueda por tag), asi que
# se usa solo 1 de marca. En Instagram y TikTok si hay busqueda por tag,
# pero conviene que sean terminos con volumen real (no solo la marca) y
# relacionados al contenido de la pieza esa semana.
HASHTAGS_FACEBOOK = ["#SportPicksLigas"]
HASHTAGS_INSTAGRAM = [
    "#PronosticosDeportivos", "#ApuestasDeportivas", "#FutbolPeru",
    "#EstadisticasFutbol", "#SportPicksLigas",
]
HASHTAGS_TIKTOK = ["#PronosticosFutbol", "#ApuestasDeportivas", "#FutbolPeru"]

# Hashtags de liga -- se agregan si el contenido mostrado esa semana
# incluye picks de esas ligas, para no repetir siempre el mismo bloque
# generico sin relacion con el partido real de la pieza.
HASHTAGS_POR_LIGA = {
    "Liga MX Apertura": "#LigaMX",
    "Primera A Colombia": "#FutbolColombiano",
    "Liga Profesional Argentina": "#FutbolArgentino",
    "Liga 1 Perú": "#LigaPeruana",
    "Brasileirão Série A": "#Brasileirao",
    "LigaPro Serie A Ecuador": "#FutbolEcuatoriano",
    "MLS": "#MLS",
    "UEFA Champions League": "#ChampionsLeague",
}


def _link_utm(fuente, campana):
    return f"{BASE_URL}/?utm_source={fuente}&utm_medium=social&utm_campaign={campana}"


def generar_caption(ganados_total, picks=None):
    """Texto listo para copiar/pegar en Facebook, Instagram y TikTok --
    mismo gancho que la imagen (cantidad de aciertos, no porcentaje),
    sin prometer resultados garantizados. Cada plataforma lleva su
    propio link con UTM (para poder medir en Vercel Analytics que
    plataforma trae trafico real) y su propio set de hashtags -- no el
    mismo bloque copiado en las 3 redes."""
    from datetime import date

    campana = f"anuncio_producto_{date.today().isocalendar()[0]}-W{date.today().isocalendar()[1]:02d}"
    link_fb = _link_utm("facebook", campana)
    link_ig = _link_utm("instagram", campana)
    link_tk = _link_utm("tiktok", campana)

    ligas_del_post = {p["liga_nombre"] for p in (picks or []) if p.get("liga_nombre") in HASHTAGS_POR_LIGA}
    tags_liga = [HASHTAGS_POR_LIGA[liga] for liga in ligas_del_post]

    tags_ig = " ".join((HASHTAGS_INSTAGRAM + tags_liga)[:5])
    tags_tk = " ".join((HASHTAGS_TIKTOK + tags_liga)[:5])
    tags_fb = " ".join(HASHTAGS_FACEBOOK)

    facebook = f"""¿Cansado de apostar a ciegas y no acertar ningún pick?

En SportPicks Ligas cada pronóstico sale de un modelo estadístico real (Dixon-Coles + Monte Carlo sobre goles, córners y forma reciente) -- no de la intuición de un tipster.

Ya llevamos {ganados_total} pronósticos acertados y contando, todos con historial público y verificable.

👉 Empieza gratis y revisa el historial completo: {link_fb}
📲 Picks gratis todos los días en nuestro Canal de WhatsApp: {CANAL_WHATSAPP_URL}

⚠️ Análisis estadístico, no garantía de resultado. Juega con responsabilidad. +18.

{tags_fb}"""

    instagram = f"""¿Cansado de no acertar ningún pick? 📊

Modelo real. Datos diarios. Historial público.
{ganados_total} pronósticos acertados y contando.

Empieza gratis -- actualiza el link de la bio a:
{link_ig}

📲 O únete a nuestro Canal de WhatsApp (picks gratis todos los días): {CANAL_WHATSAPP_URL}

⚠️ Contenido de análisis estadístico, no garantía de resultado. +18.

{tags_ig}"""

    tiktok = f"""Modelo real vs. tipster de siempre 👀
{ganados_total} pronósticos acertados y contando, todo público y verificable.
Link (bio/pinned comment): {link_tk}
Canal de WhatsApp (picks gratis diarios): {CANAL_WHATSAPP_URL}

⚠️ Análisis estadístico, no garantía de resultado. +18. {tags_tk}"""

    return facebook, instagram, tiktok


def main():
    picks, ganados_total = cargar_picks_recientes()
    if not picks:
        print("No hay picks ganados todavia en historial_picks.csv -- nada que generar.")
        return
    os.makedirs(SALIDA, exist_ok=True)

    # El formato feed (4:5) es mas bajo que el vertical de Stories/TikTok --
    # con las 4 filas completas el contenido no entraba (se cortaban el
    # tercer bullet y el CTA). En vez de encoger todo el texto hasta
    # volverlo ilegible, se muestran menos picks en el panel para ese
    # formato especifico; el vertical si tiene espacio de sobra para 4.
    formatos = {
        "feed_1080x1350": (1080, 1350, 3),
        "vertical_1080x1920": (1080, 1920, 4),
    }
    for nombre, (ancho, alto, n_filas) in formatos.items():
        img = _render(ancho, alto, picks[:n_filas], ganados_total)
        ruta = os.path.join(SALIDA, f"producto_{nombre}.png")
        img.save(ruta)
        print(f"Generado: {ruta}")

    facebook, instagram, tiktok = generar_caption(ganados_total, picks)
    ruta_caption = os.path.join(SALIDA, "caption.txt")
    with open(ruta_caption, "w", encoding="utf-8") as f:
        f.write("=== FACEBOOK ===\n\n")
        f.write(facebook)
        f.write("\n\n\n=== INSTAGRAM ===\n\n")
        f.write(instagram)
        f.write("\n\n\n=== TIKTOK ===\n\n")
        f.write(tiktok)
        f.write("\n")
    print(f"Generado: {ruta_caption}")


if __name__ == "__main__":
    main()
