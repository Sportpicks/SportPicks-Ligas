# -*- coding: utf-8 -*-
"""
generar_prompts_ia.py -- reemplaza el enfoque de generar_post_diario.py
(imagenes armadas con PIL) por prompts de texto listos para generar la
pieza con IA (Nano Banana Pro para las imagenes, Flow/Veo para el
video), por instruccion explicita de Antonio.

Regla fija de contenido (de ahora en adelante, todos los dias): NO se
muestran los resultados del ultimo dia tal cual salieron -- se arma
siempre una seleccion curada de TODO el historial: los 3 picks ganados
mas recientes + el pick perdido mas reciente (los 4 mas nuevos posibles
de cada tipo, priorizando que tengan cuota real registrada). Objetivo:
prueba social consistente (mayoria de aciertos visibles) sin ocultar
que tambien se pierde -- transparencia sin que un dia malo puntual
opaque el track record real.

Fuente: Data/historial_picks.csv, mismos datos que ya alimenta la web
y el resto del pipeline de contenido -- no se inventa nada.

Uso:
    python social/generar_prompts_ia.py

Salida: Data/social/<fecha>/prompts_ia.txt (prompt de imagen vertical,
prompt de imagen cuadrada, prompt de video) + caption.txt (se genera
igual que antes, via generar_post_diario.generar_caption, reutilizado
para no duplicar logica).
"""
import os
import sys
from datetime import date, datetime

import pandas as pd

RAIZ = os.path.dirname(os.path.abspath(__file__))
RAIZ_PIPELINE = os.path.dirname(RAIZ)
HISTORIAL_CSV = os.path.join(RAIZ_PIPELINE, "Data", "historial_picks.csv")
SALIDA_BASE = os.path.join(RAIZ_PIPELINE, "Data", "social")

sys.path.insert(0, RAIZ)
from generar_post_diario import generar_caption, stats_historicas  # noqa: E402

PALETA = {
    "bg": "#081210",
    "accent": "#c8ff3d",
    "fg": "#f4fff0",
    "surface": "#0f1f1b",
    "border": "#1c332c",
    "rojo": "#ff6b6b",
}


def _seleccionar_picks():
    """3 ganados + 1 perdido mas recientes, priorizando los que tienen
    cuota real registrada (algunos picks del log interno de 'mejor
    apuesta' no la traen) -- si no hay 3/1 con cuota, completa con los
    que no la tengan para no dejar el post vacio."""
    df = pd.read_csv(HISTORIAL_CSV)
    liq = df[df["estado"].isin(["Ganado", "Perdido"]) & (df["es_publico"] == True)].copy()  # noqa: E712
    liq["fecha_dt"] = pd.to_datetime(liq["fecha"])
    liq = liq.sort_values(["fecha_dt", "registrado_en"], ascending=False)

    def _mejores(sub, n):
        con_cuota = sub[sub["cuota"].notna()]
        resto = sub[sub["cuota"].isna()]
        return pd.concat([con_cuota, resto]).head(n)

    ganados = _mejores(liq[liq["estado"] == "Ganado"], 3)
    perdidos = _mejores(liq[liq["estado"] == "Perdido"], 1)
    return ganados, perdidos


def _linea_pick(row):
    cuota = f"@{row['cuota']}" if pd.notna(row["cuota"]) else "s/d"
    return (
        f"{row['local']} vs {row['visitante']} ({row['liga_nombre']}) — "
        f"{row['mercado']} — cuota {cuota} — {row['prob']}% prob."
    )


def _prompt_imagen(ganados, perdidos, hist, formato):
    lineas_g = "\n".join(f"   Pick {i+1} (GANADO): {_linea_pick(r)}" for i, (_, r) in enumerate(ganados.iterrows()))
    linea_p = "\n".join(f"   Pick 4 (PERDIDO): {_linea_pick(r)}" for _, r in perdidos.iterrows())

    if formato == "vertical":
        layout = (
            "Formato vertical 1080x1920 (para Instagram/TikTok Reels y Stories). "
            "Las 4 tarjetas de picks apiladas en una sola columna, de arriba a abajo."
        )
    else:
        layout = (
            "Formato cuadrado 1080x1080 (para feed de Facebook/Instagram). "
            "Las 4 tarjetas de picks en una cuadricula 2x2 para aprovechar el espacio cuadrado."
        )

    return f"""IDIOMA: todo el texto de esta imagen debe estar en ESPAÑOL. No traduzcas
ninguna palabra al inglés, ni siquiera "GANADO"/"PERDIDO" ni el resto de
las etiquetas -- copia el texto exactamente como aparece más abajo,
entre comillas, sin traducirlo ni parafrasearlo.

Diseña una imagen para redes sociales de la marca de análisis deportivo
"SportPicks Ligas". Estilo minimalista, oscuro, tipo dashboard/app de
datos deportivos.

{layout}

Paleta EXACTA (respetar los códigos hex):
- Fondo: verde muy oscuro casi negro {PALETA['bg']}
- Acento (títulos y dato clave): verde lima brillante {PALETA['accent']}
- Texto secundario: blanco hueso {PALETA['fg']}
- Tarjetas: verde apenas más claro que el fondo {PALETA['surface']}, borde sutil {PALETA['border']}
- Etiqueta de pick perdido: rojo suave {PALETA['rojo']}

Contenido exacto a mostrar, de arriba a abajo, EN ESPAÑOL (no agregues
texto que no esté en esta lista):

1. Título grande en acento lima: "SPORTPICKS LIGAS"
2. Subtítulo en blanco: "Nuestros últimos picks"
3. Cuatro tarjetas redondeadas, una por pick, cada una con: una etiqueta
   pequeña a la izquierda ("GANADO" en lima sobre fondo oscuro, o
   "PERDIDO" en rojo suave -- en español, nunca "WON"/"LOST"), el nombre
   del partido en blanco bold, el nombre de la liga/competición en gris
   pequeño debajo del partido, y debajo el mercado + cuota + probabilidad
   en gris claro:

{lineas_g}
{linea_p}

4. Al final, separado por una línea delgada horizontal: en blanco
   "Historial completo público -- link en la bio", y en el texto más
   pequeño de toda la imagen (última línea, gris tenue): "+18 · Análisis
   estadístico, no garantía de resultado. Juega con responsabilidad."
   NO muestres ningún porcentaje de acierto ni cantidad de picks
   liquidados en esta imagen -- ese dato no debe aparecer en ningún
   lugar.

RESTRICCIONES DE CUMPLIMIENTO (obligatorias, para no violar las reglas
de contenido de TikTok/Meta sobre juego/apuestas):
- NO incluyas logos, nombres ni menciones de ninguna casa de apuestas o
  plataforma de apuestas (Bet365, Betano, etc.) en ningún lugar de la
  imagen.
- NO uses la palabra "apuesta"/"apuestas"/"bet" en ningún texto -- usa
  siempre "pick(s)", "análisis" o "probabilidad".
- NO uses lenguaje de "ganancia garantizada", "dinero fácil" ni ningún
  texto que prometa un resultado seguro -- el enfoque es análisis
  estadístico y transparencia de resultados, no promoción de apuestas.
- NO incluyas ningún código promocional, link de registro ni llamado a
  "deposita"/"regístrate" en una casa de apuestas.
- Incluye siempre visible el disclaimer "+18" y "Juega con
  responsabilidad" del punto 4 -- no es opcional, debe verse en la
  imagen, no solo en el caption.
- NO fotos de personas reales ni rostros, NO marcas de agua de ningún
  tipo.

Tipografía sans-serif bold y moderna (estilo Inter/Poppins), sin
serifas. Composición limpia tipo app fintech/dashboard, buen espaciado,
jerarquía visual clara."""


def _prompt_video():
    return """IDIOMA: si el modelo agrega cualquier texto, subtítulo o voz en off,
debe estar en ESPAÑOL -- no en inglés. Preferible que no agregue texto
nuevo en absoluto (ver abajo).

Usa la imagen vertical generada (la de formato 1080x1920) como
fotograma inicial -- animación image-to-video, no generar desde cero.

Genera un video vertical de 8 a 10 segundos, SIN audio ni voz, para
TikTok/Reels.

Movimiento: zoom lento y constante hacia el título "SPORTPICKS LIGAS"
(efecto Ken Burns), cámara estática salvo por ese zoom suave y continuo,
sin cortes ni cambios de plano. No agregues elementos que no estén en la
imagen original -- nada de personas, balones en movimiento, ni gráficos
animados adicionales, ni texto nuevo que no estuviera ya en la imagen.
El resultado debe sentirse como una pieza de datos/dashboard, sobria y
profesional, no como un anuncio llamativo. Termina con un fundido a
negro suave en el último medio segundo.

RESTRICCIONES DE CUMPLIMIENTO (obligatorias): no agregues logos ni
menciones de casas de apuestas, no agregues la palabra "apuesta(s)"/
"bet" en ningún texto u overlay, no agregues lenguaje de "ganancia
garantizada". El disclaimer "+18 · Juega con responsabilidad" que ya
está en la imagen debe permanecer visible y legible durante todo el
video, no lo tapes ni lo recortes con el zoom."""


def main():
    ganados, perdidos = _seleccionar_picks()
    if len(ganados) < 3 or len(perdidos) < 1:
        print("No hay suficientes picks públicos liquidados todavía (necesito 3 ganados + 1 perdido).")
        return

    df = pd.read_csv(HISTORIAL_CSV)
    hist = stats_historicas(df.to_dict("records"))

    fecha_iso = date.today().isoformat()
    carpeta_salida = os.path.join(SALIDA_BASE, fecha_iso)
    os.makedirs(carpeta_salida, exist_ok=True)

    prompt_vertical = _prompt_imagen(ganados, perdidos, hist, "vertical")
    prompt_cuadrado = _prompt_imagen(ganados, perdidos, hist, "cuadrado")
    prompt_video = _prompt_video()

    ruta = os.path.join(carpeta_salida, "prompts_ia.txt")
    with open(ruta, "w", encoding="utf-8") as f:
        f.write("=== PROMPT IMAGEN VERTICAL (Nano Banana Pro) — TikTok/Reels/Stories ===\n\n")
        f.write(prompt_vertical)
        f.write("\n\n\n=== PROMPT IMAGEN CUADRADA (Nano Banana Pro) — Facebook/Instagram feed ===\n\n")
        f.write(prompt_cuadrado)
        f.write("\n\n\n=== PROMPT VIDEO (Flow) — usar la imagen vertical como fotograma inicial ===\n\n")
        f.write(prompt_video)
        f.write("\n")

    print(f"Generado: {ruta}")
    print()
    print(prompt_vertical)


if __name__ == "__main__":
    main()
