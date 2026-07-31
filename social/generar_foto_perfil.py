# -*- coding: utf-8 -*-
"""
generar_foto_perfil.py -- foto de perfil unica para las 3 cuentas nuevas
(TikTok, Instagram, Facebook), pensada para reconocerse como la misma
marca en cualquier plataforma sin depender de un logo diseñado a mano.

Usa exactamente la paleta de la web (frontend/app/globals.css) y el
mismo estilo de las piezas de Fase 1 (generar_post_diario.py,
generar_anuncio_gancho.py): fondo oscuro + acento lima + tipografia
DejaVu Bold.

Diseño: circulo de fondo (se ve bien recortado en circulo por las 3
plataformas, que siempre recortan la foto de perfil asi) con las
iniciales "SP" en grande y una linea de tendencia ascendente simple
debajo -- referencia visual a "modelo estadistico", no a una pelota
generica como usan la mayoria de tipsters.

Uso:
    python social/generar_foto_perfil.py

Salida: Data/social/marca/foto_perfil.png (1080x1080)
"""
import os

from PIL import Image, ImageDraw, ImageFont

RAIZ = os.path.dirname(os.path.abspath(__file__))
RAIZ_PIPELINE = os.path.dirname(RAIZ)
SALIDA = os.path.join(RAIZ_PIPELINE, "Data", "social", "marca")

BG = "#081210"
BG_CLARO = "#0f1f1b"
FG = "#f4fff0"
ACCENT = "#c8ff3d"

FUENTE_DIR = "/usr/share/fonts/truetype/dejavu"
FUENTE_BOLD = os.path.join(FUENTE_DIR, "DejaVuSans-Bold.ttf")

TAM = 1080


def generar():
    img = Image.new("RGB", (TAM, TAM), BG)
    draw = ImageDraw.Draw(img)

    # Degradado radial sutil (centro mas claro) para que no se vea plano
    # dentro del circulo que cada plataforma recorta.
    cx, cy = TAM // 2, TAM // 2
    max_r = int(TAM * 0.72)
    bg_rgb = tuple(int(BG[i:i + 2], 16) for i in (1, 3, 5))
    claro_rgb = tuple(int(BG_CLARO[i:i + 2], 16) for i in (1, 3, 5))
    for r in range(max_r, 0, -4):
        t = 1 - (r / max_r)
        color = tuple(int(bg_rgb[i] + (claro_rgb[i] - bg_rgb[i]) * t) for i in range(3))
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)

    # Anillo de acento -- referencia al "circulo" con el que las 3
    # plataformas recortan la foto de perfil, reforzado a proposito.
    ring_r = int(TAM * 0.42)
    draw.ellipse(
        [cx - ring_r, cy - ring_r, cx + ring_r, cy + ring_r],
        outline=ACCENT, width=10,
    )

    # Iniciales "SP" centradas.
    fuente_sp = ImageFont.truetype(FUENTE_BOLD, 320)
    texto = "SP"
    bbox = draw.textbbox((0, 0), texto, font=fuente_sp)
    ancho, alto = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text((cx - ancho / 2 - bbox[0], cy - alto / 2 - bbox[1] - 60), texto, font=fuente_sp, fill=FG)

    # Linea de tendencia ascendente simple debajo de las iniciales --
    # 4 puntos subiendo de izquierda a derecha, estilo grafico de stats.
    puntos = [
        (cx - 150, cy + 160),
        (cx - 60, cy + 120),
        (cx + 40, cy + 145),
        (cx + 150, cy + 70),
    ]
    draw.line(puntos, fill=ACCENT, width=10, joint="curve")
    for x, y in puntos:
        draw.ellipse([x - 12, y - 12, x + 12, y + 12], fill=ACCENT)

    os.makedirs(SALIDA, exist_ok=True)
    ruta = os.path.join(SALIDA, "foto_perfil.png")
    img.save(ruta)
    print(f"Generado: {ruta}")


if __name__ == "__main__":
    generar()
