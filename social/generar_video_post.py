# -*- coding: utf-8 -*-
"""
generar_video_post.py -- paso tecnico pendiente del documento de
estrategia (docs/estrategia/estrategia_redes_sociales.docx, seccion 11):
convierte la imagen vertical que ya genera generar_post_diario.py
(Data/social/<fecha>/post_vertical_1080x1920.png) en un video corto
(.mp4) listo para subir a TikTok/Reels, sin grabar ni editar nada a
mano.

Efecto: zoom lento tipo Ken Burns (via el filtro zoompan de ffmpeg)
sobre la imagen fija, con fade-in/fade-out. No hay voz ni musica (no hay
TTS ni banco de audio disponible en este entorno) -- el video sale mudo,
lo cual es normal para este formato: la mayoria de TikTok/Reels se ve
sin sonido, y el contenido aqui es 100% texto/datos en pantalla, no
depende de narracion.

Requiere que generar_post_diario.py ya se haya corrido para la fecha
(usa su salida, no regenera la imagen).

Uso:
    python social/generar_post_diario.py      # genera las imagenes primero
    python social/generar_video_post.py       # convierte a video el ultimo dia disponible
    python social/generar_video_post.py 2026-07-30   # o una fecha especifica

Salida: Data/social/<fecha>/post_video_1080x1920.mp4 (9-10s, 1080x1920,
30fps, sin audio -- las plataformas aceptan video mudo sin problema).
"""
import os
import subprocess
import sys

RAIZ = os.path.dirname(os.path.abspath(__file__))
RAIZ_PIPELINE = os.path.dirname(RAIZ)
SALIDA_BASE = os.path.join(RAIZ_PIPELINE, "Data", "social")

DURACION_SEG = 9
FPS = 30
ANCHO, ALTO = 1080, 1920


def _ultima_fecha_disponible():
    """Si no se pasa fecha por CLI, usa la carpeta mas reciente que ya
    tenga post_vertical_1080x1920.png generado por generar_post_diario.py."""
    if not os.path.isdir(SALIDA_BASE):
        return None
    candidatas = sorted(
        d for d in os.listdir(SALIDA_BASE)
        if os.path.isfile(os.path.join(SALIDA_BASE, d, "post_vertical_1080x1920.png"))
    )
    return candidatas[-1] if candidatas else None


def generar_video(fecha_iso):
    carpeta = os.path.join(SALIDA_BASE, fecha_iso)
    img_entrada = os.path.join(carpeta, "post_vertical_1080x1920.png")
    if not os.path.exists(img_entrada):
        print(f"No existe {img_entrada}. Corre primero: python social/generar_post_diario.py")
        return None

    video_salida = os.path.join(carpeta, "post_video_1080x1920.mp4")
    total_frames = DURACION_SEG * FPS

    # zoompan: zoom lento de 1.0 a ~1.12 a lo largo de todo el clip
    # (Ken Burns). d= numero de frames del efecto (todo el clip, ya que
    # es una sola imagen fija). s= resolucion de salida.
    # fade in/out: primeros/ultimos 0.5s, evita el corte seco al hacer
    # scroll en el feed.
    zoom_expr = f"zoompan=z='min(zoom+0.0015,1.12)':d={total_frames}:s={ANCHO}x{ALTO}:fps={FPS}"
    fade_expr = f"fade=t=in:st=0:d=0.5,fade=t=out:st={DURACION_SEG - 0.5}:d=0.5"

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", img_entrada,
        "-t", str(DURACION_SEG),
        "-vf", f"{zoom_expr},{fade_expr},format=yuv420p",
        "-r", str(FPS),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        video_salida,
    ]
    resultado = subprocess.run(cmd, capture_output=True, text=True)
    if resultado.returncode != 0:
        print("Error de ffmpeg:")
        print(resultado.stderr[-2000:])
        return None

    return video_salida


def main():
    fecha_iso = sys.argv[1] if len(sys.argv) > 1 else _ultima_fecha_disponible()
    if not fecha_iso:
        print("No hay ninguna carpeta en Data/social/ con post_vertical_1080x1920.png todavia.")
        print("Corre primero: python social/generar_post_diario.py")
        return

    video = generar_video(fecha_iso)
    if video:
        print(f"Generado: {video}")
        print(f"Duracion: {DURACION_SEG}s, {ANCHO}x{ALTO}, {FPS}fps, sin audio.")
        print("Listo para subir a TikTok/Reels/Instagram Stories.")


if __name__ == "__main__":
    main()
