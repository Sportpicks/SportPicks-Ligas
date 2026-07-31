# -*- coding: utf-8 -*-
"""
generar_logo_v2.py -- segunda pasada del logo de marca, mas cuidada que
la version inicial (generar_foto_perfil.py: "SP" + circulo simple).

Genera 3 variantes para elegir, todas 1080x1080, misma paleta de la web
(fondo #081210, acento lima #c8ff3d, texto #f4fff0):

  a_squircle : monograma "S" solo, estilo icono de app moderno
               (Slack/Stripe/Spotify) -- el que mejor escala a tamano
               chico de foto de perfil circular.
  b_crest    : escudo circular con "SPL" + linea de tendencia, version
               mas pulida del logo anterior (mejor tipografia/proporcion,
               sombra sutil para dar profundidad).
  c_hexagono : insignia hexagonal con "SPL", esquinas mas "deportivas"
               (estilo crest de equipo/analytics), barras ascendentes
               integradas en la base.

Uso:
    python social/generar_logo_v2.py

Salida: Data/social/marca/logo_a_squircle.png
        Data/social/marca/logo_b_crest.png
        Data/social/marca/logo_c_hexagono.png
"""
import math
import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont

RAIZ = os.path.dirname(os.path.abspath(__file__))
RAIZ_PIPELINE = os.path.dirname(RAIZ)
SALIDA = os.path.join(RAIZ_PIPELINE, "Data", "social", "marca")

BG = "#081210"
BG_CLARO = "#132821"
FG = "#f4fff0"
ACCENT = "#c8ff3d"
ACCENT_OSCURO = "#8fc925"  # sombra del acento, para dar profundidad sin salir de paleta

FUENTE_DIR = "/usr/share/fonts/truetype/dejavu"
FUENTE_BOLD = os.path.join(FUENTE_DIR, "DejaVuSans-Bold.ttf")

TAM = 1080
SS = 4  # supersampling: se dibuja a 4x y se reduce al final -> bordes limpios


def _hex_a_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _fondo_degradado(size, centro_color, borde_color):
    """Degradado radial suave, sirve de base para las 3 variantes."""
    img = Image.new("RGB", (size, size), borde_color)
    draw = ImageDraw.Draw(img)
    cx = cy = size // 2
    max_r = int(size * 0.75)
    c1 = _hex_a_rgb(centro_color)
    c2 = _hex_a_rgb(borde_color)
    for r in range(max_r, 0, -max(2, size // 300)):
        t = 1 - (r / max_r)
        color = tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
    return img


def _texto_centrado(draw, cx, cy, texto, fuente, fill):
    bbox = draw.textbbox((0, 0), texto, font=fuente)
    ancho, alto = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text((cx - ancho / 2 - bbox[0], cy - alto / 2 - bbox[1]), texto, font=fuente, fill=fill)


def _rounded_mask(size, radius):
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return mask


# ---------------------------------------------------------------- variante A
def variante_a_squircle():
    size = TAM * SS
    base = _fondo_degradado(size, BG_CLARO, BG)
    draw = ImageDraw.Draw(base)

    # Highlight superior sutil (efecto "glossy" discreto, muy usado en
    # iconos de apps premium) -- una elipse blanca muy transparente.
    highlight = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    hd = ImageDraw.Draw(highlight)
    hd.ellipse(
        [size * 0.08, -size * 0.35, size * 0.92, size * 0.55],
        fill=(255, 255, 255, 14),
    )
    base = Image.alpha_composite(base.convert("RGBA"), highlight)
    draw = ImageDraw.Draw(base)

    # Monograma "S" grande, ligeramente mas fino que bold puro para verse
    # premium en vez de "gordo".
    fuente_s = ImageFont.truetype(FUENTE_BOLD, int(size * 0.60))
    _texto_centrado(draw, size / 2, size * 0.47, "S", fuente_s, FG)

    # Acento: barra ascendente corta en la esquina superior derecha de la
    # "S", como un "tick" de crecimiento -- referencia a stats sin ser
    # literal un grafico completo.
    ax0, ay0 = size * 0.665, size * 0.31
    puntos = [
        (ax0, ay0 + size * 0.05),
        (ax0 + size * 0.045, ay0 + size * 0.02),
        (ax0 + size * 0.09, ay0 + size * 0.055),
        (ax0 + size * 0.135, ay0 - size * 0.01),
    ]
    draw.line(puntos, fill=ACCENT, width=int(size * 0.017), joint="curve")
    r = int(size * 0.013)
    x, y = puntos[-1]
    draw.ellipse([x - r, y - r, x + r, y + r], fill=ACCENT)

    mask = _rounded_mask(size, int(size * 0.22))
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(base, (0, 0), mask)
    out = out.resize((TAM, TAM), Image.LANCZOS)
    out.convert("RGB").save(os.path.join(SALIDA, "logo_a_squircle.png"))


# ---------------------------------------------------------------- variante B
def variante_b_crest():
    size = TAM * SS
    base = _fondo_degradado(size, BG_CLARO, BG).convert("RGBA")
    draw = ImageDraw.Draw(base)

    cx = cy = size // 2

    # Doble anillo -- uno grueso principal y uno fino interior, mas
    # "insignia deportiva" que un anillo simple.
    r1 = int(size * 0.415)
    r2 = int(size * 0.365)
    draw.ellipse([cx - r1, cy - r1, cx + r1, cy + r1], outline=ACCENT, width=int(size * 0.016))
    draw.ellipse([cx - r2, cy - r2, cx + r2, cy + r2], outline=ACCENT_OSCURO, width=int(size * 0.006))

    fuente_spl = ImageFont.truetype(FUENTE_BOLD, int(size * 0.30))
    _texto_centrado(draw, cx, cy - size * 0.05, "SPL", fuente_spl, FG)

    fuente_sub = ImageFont.truetype(FUENTE_BOLD, int(size * 0.052))
    _texto_centrado(draw, cx, cy + size * 0.145, "L I G A S", fuente_sub, ACCENT)

    # Linea de tendencia fina bajo el subtitulo, ligeramente curva.
    puntos = []
    n = 24
    for i in range(n):
        t = i / (n - 1)
        x = cx - size * 0.19 + t * size * 0.38
        y = cy + size * 0.225 - math.sin(t * math.pi) * size * 0.03 - t * size * 0.03
        puntos.append((x, y))
    draw.line(puntos, fill=ACCENT, width=int(size * 0.009), joint="curve")

    mask = Image.new("L", (size, size), 0)
    md = ImageDraw.Draw(mask)
    md.ellipse([0, 0, size - 1, size - 1], fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(base, (0, 0), mask)
    out = out.resize((TAM, TAM), Image.LANCZOS)
    out.convert("RGB").save(os.path.join(SALIDA, "logo_b_crest.png"))


# ---------------------------------------------------------------- variante C
def _hexagono(cx, cy, r, rotacion=90):
    puntos = []
    for i in range(6):
        ang = math.radians(rotacion + i * 60)
        puntos.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
    return puntos


def variante_c_hexagono():
    size = TAM * SS
    base = _fondo_degradado(size, BG_CLARO, BG).convert("RGBA")
    draw = ImageDraw.Draw(base)
    cx = cy = size // 2

    r_out = size * 0.42
    r_in = size * 0.375
    draw.polygon(_hexagono(cx, cy, r_out), outline=ACCENT, width=int(size * 0.016))
    draw.polygon(_hexagono(cx, cy, r_in), outline=ACCENT_OSCURO, width=int(size * 0.005))

    fuente_spl = ImageFont.truetype(FUENTE_BOLD, int(size * 0.26))
    _texto_centrado(draw, cx, cy - size * 0.08, "SPL", fuente_spl, FG)

    # Barras ascendentes integradas en la base del hexagono (estilo
    # "analytics badge").
    barras = [0.10, 0.16, 0.13, 0.22, 0.19]
    n = len(barras)
    ancho_barra = size * 0.045
    espacio = size * 0.018
    ancho_total = n * ancho_barra + (n - 1) * espacio
    x0 = cx - ancho_total / 2
    base_y = cy + size * 0.20
    for i, h in enumerate(barras):
        x = x0 + i * (ancho_barra + espacio)
        alto = size * h
        color = ACCENT if i == n - 1 else ACCENT_OSCURO
        draw.rounded_rectangle(
            [x, base_y - alto, x + ancho_barra, base_y],
            radius=ancho_barra * 0.25,
            fill=color,
        )

    mask = Image.new("L", (size, size), 0)
    md = ImageDraw.Draw(mask)
    md.polygon(_hexagono(cx, cy, size * 0.46), fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(base, (0, 0), mask)
    out = out.resize((TAM, TAM), Image.LANCZOS)
    out.convert("RGB").save(os.path.join(SALIDA, "logo_c_hexagono.png"))


def main():
    os.makedirs(SALIDA, exist_ok=True)
    variante_a_squircle()
    variante_b_crest()
    variante_c_hexagono()
    print("Generadas 3 variantes en", SALIDA)


if __name__ == "__main__":
    main()
