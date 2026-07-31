# -*- coding: utf-8 -*-
"""
generar_logo_v3.py -- tercera pasada del logo: nombre completo
"SportPicks Ligas" (no solo "SPL"), con un tratamiento mas dinamico/
llamativo que las variantes anteriores (generar_logo_v2.py).

Genera 2 piezas:
  logo_v3_cuadrado.png  1080x1080  -- para foto de perfil (TikTok/IG/FB/
                                      Telegram), nombre completo apilado.
  logo_v3_banner.png    1500x500   -- portada/banner (Facebook cover,
                                      encabezado de canal de Telegram),
                                      mismo lockup en horizontal.

Tratamiento: fondo partido en diagonal (dos tonos del mismo verde,
nunca un color ajeno a la paleta), una franja lima en diagonal tipo
"cinta" para dar energia/movimiento, "SportPicks" en blanco grande y
"LIGAS" en una placa lima inclinada (paralelogramo) -- el contraste
inclinado es lo que lee como "deportivo/dinamico" sin salirse de la
paleta ya establecida en toda la marca.

Uso:
    python social/generar_logo_v3.py
"""
import os

from PIL import Image, ImageDraw, ImageFont

RAIZ = os.path.dirname(os.path.abspath(__file__))
RAIZ_PIPELINE = os.path.dirname(RAIZ)
SALIDA = os.path.join(RAIZ_PIPELINE, "Data", "social", "marca")

BG = "#081210"
BG_CLARO = "#16302a"
FG = "#f4fff0"
ACCENT = "#c8ff3d"
ACCENT_OSCURO = "#7fae1f"

FUENTE_DIR = "/usr/share/fonts/truetype/dejavu"
FUENTE_BOLD = os.path.join(FUENTE_DIR, "DejaVuSans-Bold.ttf")

SS = 3  # supersampling


def _texto_centrado(draw, cx, cy, texto, fuente, fill):
    bbox = draw.textbbox((0, 0), texto, font=fuente)
    ancho, alto = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text((cx - ancho / 2 - bbox[0], cy - alto / 2 - bbox[1]), texto, font=fuente, fill=fill)
    return ancho, alto


def _ajustar_fuente(draw, texto, ancho_max, tam_inicial, minimo=10):
    tam = tam_inicial
    while tam > minimo:
        f = ImageFont.truetype(FUENTE_BOLD, tam)
        bbox = draw.textbbox((0, 0), texto, font=f)
        if bbox[2] - bbox[0] <= ancho_max:
            return f
        tam -= 2
    return ImageFont.truetype(FUENTE_BOLD, minimo)


def _fondo_diagonal(w, h):
    img = Image.new("RGB", (w, h), BG)
    draw = ImageDraw.Draw(img)
    # Corte diagonal: mitad superior-derecha un tono mas claro.
    draw.polygon([(0, 0), (w, 0), (w, h * 0.55), (0, h * 0.95)], fill=BG_CLARO)
    # Cinta lima diagonal, semitransparente vía capa aparte para que no
    # tape el texto (se dibuja detras del texto igual, pero mas fina).
    cinta = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    cd = ImageDraw.Draw(cinta)
    grosor = h * 0.16
    cd.polygon(
        [
            (-w * 0.1, h * 0.62), (w * 1.1, h * 0.18),
            (w * 1.1, h * 0.18 + grosor), (-w * 0.1, h * 0.62 + grosor),
        ],
        fill=(*[int(ACCENT[i:i + 2], 16) for i in (1, 3, 5)], 40),
    )
    img = Image.alpha_composite(img.convert("RGBA"), cinta).convert("RGB")
    return img


def _placa_ligas(draw, cx, cy, ancho, alto, texto, fuente, inclinacion):
    """Paralelogramo lima con 'LIGAS' dentro -- el elemento que le da el
    caracter 'dinamico' al conjunto."""
    x0, y0 = cx - ancho / 2, cy - alto / 2
    x1, y1 = cx + ancho / 2, cy - alto / 2
    x2, y2 = cx + ancho / 2 - inclinacion, cy + alto / 2
    x3, y3 = cx - ancho / 2 - inclinacion, cy + alto / 2
    draw.polygon([(x0, y0), (x1, y1), (x2, y2), (x3, y3)], fill=ACCENT)
    _texto_centrado(draw, cx - inclinacion / 2, cy, texto, fuente, BG)


def generar_cuadrado():
    size = 1080 * SS
    img = _fondo_diagonal(size, size)
    draw = ImageDraw.Draw(img)
    cx = size // 2

    # "SportPicks" -- una palabra, ajustada para ocupar buena parte del
    # ancho pero con margen.
    fuente_sp = _ajustar_fuente(draw, "SportPicks", size * 0.86, int(size * 0.20))
    _texto_centrado(draw, cx, size * 0.415, "SportPicks", fuente_sp, FG)

    # Placa "LIGAS" inclinada debajo, mas angosta que el texto de arriba
    # a proposito -- jerarquia visual clara (nombre > categoria).
    fuente_ligas = ImageFont.truetype(FUENTE_BOLD, int(size * 0.115))
    _placa_ligas(draw, cx, size * 0.585, size * 0.46, size * 0.155, "LIGAS", fuente_ligas, size * 0.045)

    # Linea fina de tendencia bajo todo, ultimo acento de "stats".
    y = size * 0.72
    puntos = [
        (cx - size * 0.22, y + size * 0.03),
        (cx - size * 0.08, y),
        (cx + size * 0.05, y + size * 0.02),
        (cx + size * 0.22, y - size * 0.035),
    ]
    draw.line(puntos, fill=ACCENT_OSCURO, width=int(size * 0.012), joint="curve")
    r = int(size * 0.011)
    x, yy = puntos[-1]
    draw.ellipse([x - r, yy - r, x + r, yy + r], fill=ACCENT)

    # Marco fino para que se vea "cerrado" como icono de app.
    m = int(size * 0.018)
    draw.rectangle([m, m, size - m, size - m], outline=ACCENT_OSCURO, width=int(size * 0.004))

    img = img.resize((1080, 1080), Image.LANCZOS)
    img.save(os.path.join(SALIDA, "logo_v3_cuadrado.png"))


def generar_banner():
    w, h = 1500 * SS, 500 * SS
    img = _fondo_diagonal(w, h)
    draw = ImageDraw.Draw(img)

    cx = w * 0.40
    fuente_sp = _ajustar_fuente(draw, "SportPicks", w * 0.46, int(h * 0.34))
    _texto_centrado(draw, cx, h * 0.40, "SportPicks", fuente_sp, FG)

    fuente_ligas = ImageFont.truetype(FUENTE_BOLD, int(h * 0.19))
    _placa_ligas(draw, cx, h * 0.66, w * 0.24, h * 0.24, "LIGAS", fuente_ligas, h * 0.06)

    # Bloque derecho: dato de winrate, refuerza prueba social incluso en
    # el banner/portada.
    fuente_dato = ImageFont.truetype(FUENTE_BOLD, int(h * 0.16))
    fuente_sub = ImageFont.truetype(FUENTE_BOLD, int(h * 0.062))
    _texto_centrado(draw, w * 0.80, h * 0.42, "54.3%", fuente_dato, ACCENT)
    _texto_centrado(draw, w * 0.80, h * 0.62, "ACIERTO REAL · 328 PICKS", fuente_sub, FG)

    img = img.resize((1500, 500), Image.LANCZOS)
    img.save(os.path.join(SALIDA, "logo_v3_banner.png"))


def main():
    os.makedirs(SALIDA, exist_ok=True)
    generar_cuadrado()
    generar_banner()
    print("Generados logo_v3_cuadrado.png y logo_v3_banner.png en", SALIDA)


if __name__ == "__main__":
    main()
