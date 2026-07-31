# -*- coding: utf-8 -*-
"""
generar_logo_v4_escudo.py -- version "escudo/badge" inspirada en la
referencia que mostro Antonio (balon 3D, tablero tactico, grafico de
barras, texto metalico con bisel).

Aviso honesto incluido a proposito en el propio nombre del modulo: esto
NO reproduce el efecto foto-realista/cromado de la referencia -- PIL
(la libreria de dibujo disponible aqui) solo hace formas vectoriales
planas, no renders 3D, biseles metalicos ni texturas de balon foto-
realistas. Esta es una interpretacion "flat design" de la MISMA
composicion (escudo, balon, tablero tactico, barras, estrellas,
subtitulos) pero sin el acabado 3D/cromado. Para ese acabado exacto
hace falta un generador de imagenes por IA (Midjourney/DALL-E/Canva
Magic Media) -- ver generar_logo_v4_prompt_ia.txt con un prompt listo
para eso si se prefiere ese camino.

Uso:
    python social/generar_logo_v4_escudo.py

Salida: Data/social/marca/logo_v4_escudo.png (1080x1080)
"""
import math
import os

from PIL import Image, ImageDraw, ImageFont

RAIZ = os.path.dirname(os.path.abspath(__file__))
RAIZ_PIPELINE = os.path.dirname(RAIZ)
SALIDA = os.path.join(RAIZ_PIPELINE, "Data", "social", "marca")

BG = "#050a08"
FG = "#f4fff0"
ACCENT = "#c8ff3d"
ACCENT_OSCURO = "#5a7a1a"
GRIS = "#d9dfda"
GRIS_OSCURO = "#8a938c"

FUENTE_DIR = "/usr/share/fonts/truetype/dejavu"
FUENTE_BOLD = os.path.join(FUENTE_DIR, "DejaVuSans-Bold.ttf")

SS = 3


def _texto_centrado(draw, cx, cy, texto, fuente, fill):
    bbox = draw.textbbox((0, 0), texto, font=fuente)
    ancho, alto = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text((cx - ancho / 2 - bbox[0], cy - alto / 2 - bbox[1]), texto, font=fuente, fill=fill)
    return ancho


def _fuente(tam):
    return ImageFont.truetype(FUENTE_BOLD, int(tam))


def _puntos_escudo(cx, top, w, h):
    """Silueta de escudo: top plano con esquinas redondeadas, lados que
    se curvan hacia adentro y terminan en punta abajo."""
    puntos = []
    n = 40
    for i in range(n + 1):
        t = i / n  # 0..1 a lo largo del lado derecho, de arriba a abajo
        x = cx + w / 2 * (1 - 0.55 * (t ** 1.6))
        y = top + h * t
        puntos.append((x, y))
    puntos.append((cx, top + h * 1.06))  # punta inferior
    for i in range(n + 1):
        t = 1 - i / n
        x = cx - w / 2 * (1 - 0.55 * (t ** 1.6))
        y = top + h * t
        puntos.append((x, y))
    return puntos


def _balon(draw, cx, cy, r):
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=GRIS, outline=BG, width=int(r * 0.05))
    # pentagono central
    pent = []
    for i in range(5):
        ang = math.radians(-90 + i * 72)
        pent.append((cx + r * 0.42 * math.cos(ang), cy + r * 0.42 * math.sin(ang)))
    draw.polygon(pent, fill="#111111")
    # gajos oscuros alrededor, tipo balon clasico
    for i in range(5):
        ang = math.radians(-90 + i * 72 + 36)
        px = cx + r * 0.78 * math.cos(ang)
        py = cy + r * 0.78 * math.sin(ang)
        draw.ellipse([px - r * 0.16, py - r * 0.16, px + r * 0.16, py + r * 0.16], fill="#111111")
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline="#111111", width=max(2, int(r * 0.035)))


def _tablero_tactico(draw, cx, cy, w, h):
    """X's, O's y flecha punteada -- version simplificada del icono de
    pizarra tactica de la referencia."""
    draw.ellipse([cx - w * 0.42, cy - h * 0.30, cx - w * 0.26, cy - h * 0.14], outline=ACCENT, width=4)
    x0, y0 = cx + w * 0.05, cy - h * 0.35
    d = w * 0.09
    draw.line([(x0 - d, y0 - d), (x0 + d, y0 + d)], fill=ACCENT, width=5)
    draw.line([(x0 - d, y0 + d), (x0 + d, y0 - d)], fill=ACCENT, width=5)
    # flecha punteada curva simple
    puntos = []
    n = 10
    for i in range(n):
        t = i / (n - 1)
        x = cx - w * 0.3 + t * w * 0.75
        y = cy + h * 0.05 - math.sin(t * math.pi) * h * 0.28
        puntos.append((x, y))
    for i in range(0, len(puntos) - 1, 2):
        draw.line([puntos[i], puntos[i + 1]], fill=ACCENT, width=4)
    ax, ay = puntos[-1]
    draw.polygon([(ax, ay - 10), (ax + 16, ay), (ax, ay + 10)], fill=ACCENT)


def _barras(draw, cx, cy, w, h):
    alturas = [0.35, 0.55, 0.45, 0.8, 1.0]
    n = len(alturas)
    ancho_barra = w / (n * 1.6)
    espacio = ancho_barra * 0.6
    total = n * ancho_barra + (n - 1) * espacio
    x0 = cx - total / 2
    base_y = cy + h / 2
    for i, hh in enumerate(alturas):
        x = x0 + i * (ancho_barra + espacio)
        alto = h * hh
        draw.rectangle([x, base_y - alto, x + ancho_barra, base_y], fill=ACCENT)
    # flecha ascendente sobre las barras
    draw.line([(x0, base_y - h * 0.9), (x0 + total * 0.55, base_y - h * 1.15), (x0 + total, base_y - h * 1.55)],
               fill=FG, width=5, joint="curve")
    ax, ay = x0 + total, base_y - h * 1.55
    draw.polygon([(ax - 18, ay + 4), (ax + 8, ay - 14), (ax + 4, ay + 18)], fill=FG)


def generar():
    size = 1080 * SS
    img = Image.new("RGB", (size, size), BG)
    draw = ImageDraw.Draw(img)
    cx = size // 2

    # Escudo de fondo
    pts = _puntos_escudo(cx, size * 0.05, size * 0.86, size * 0.90)
    draw.polygon(pts, fill="#0c1712", outline=ACCENT_OSCURO, width=int(size * 0.006))

    # Balon arriba, superpuesto al borde del escudo
    _balon(draw, cx, size * 0.20, size * 0.145)
    draw.arc([cx - size * 0.20, size * 0.045, cx + size * 0.20, size * 0.365], 200, 340, fill=ACCENT, width=int(size * 0.012))

    # Iconos laterales
    _barras(draw, size * 0.22, size * 0.30, size * 0.22, size * 0.16)
    _tablero_tactico(draw, size * 0.80, size * 0.30, size * 0.22, size * 0.16)

    # SPORT + PICKS
    f_sport = _fuente(size * 0.135)
    f_picks = _fuente(size * 0.135)
    w_sport = draw.textbbox((0, 0), "SPORT", font=f_sport)[2]
    w_picks = draw.textbbox((0, 0), "PICKS", font=f_picks)[2]
    espacio_letras = size * 0.005
    total_w = w_sport + w_picks + espacio_letras
    x_start = cx - total_w / 2
    y_text = size * 0.455
    draw.text((x_start, y_text), "SPORT", font=f_sport, fill=GRIS)
    draw.text((x_start + w_sport + espacio_letras, y_text), "PICKS", font=f_picks, fill=ACCENT)

    # Barra divisoria + subtitulo
    barra_y = size * 0.615
    draw.rectangle([cx - size * 0.34, barra_y, cx + size * 0.34, barra_y + size * 0.052], fill="#111111")
    _texto_centrado(draw, cx, barra_y + size * 0.026, "AGENCIA DE ANÁLISIS DEPORTIVO", _fuente(size * 0.030), FG)

    _texto_centrado(draw, cx, size * 0.70, "DATOS · ANÁLISIS · PREDICCIONES", _fuente(size * 0.026), GRIS_OSCURO)

    # LIGAS + año, con estrellas (adaptado de "MUNDIAL 2026" de la
    # referencia a "LIGAS" -- la marca ya se definio como SportPicks
    # Ligas, no Mundial).
    y_ligas = size * 0.755
    _texto_centrado(draw, cx, y_ligas, "L I G A S   2 0 2 6", _fuente(size * 0.032), ACCENT)
    n_estrellas = 5
    for i in range(n_estrellas):
        t = (i - (n_estrellas - 1) / 2) / n_estrellas
        ex = cx + t * size * 0.32
        ey = y_ligas + size * 0.05
        r = size * 0.011
        pts_estrella = []
        for k in range(10):
            ang = math.radians(-90 + k * 36)
            rr = r if k % 2 == 0 else r * 0.42
            pts_estrella.append((ex + rr * math.cos(ang), ey + rr * math.sin(ang)))
        draw.polygon(pts_estrella, fill=ACCENT)

    # Monograma SP inferior
    r_sp = size * 0.052
    cy_sp = size * 0.90
    draw.ellipse([cx - r_sp, cy_sp - r_sp, cx + r_sp, cy_sp + r_sp], fill="#111111", outline=ACCENT, width=int(size * 0.006))
    _texto_centrado(draw, cx, cy_sp, "SP", _fuente(size * 0.05), ACCENT)

    img = img.resize((1080, 1080), Image.LANCZOS)
    img.save(os.path.join(SALIDA, "logo_v4_escudo.png"))
    print("Generado:", os.path.join(SALIDA, "logo_v4_escudo.png"))


if __name__ == "__main__":
    generar()
