# -*- coding: utf-8 -*-
"""
generar_prompts_ia.py -- reemplaza el enfoque de generar_post_diario.py
(imagenes armadas con PIL) por prompts de texto listos para generar la
pieza con IA (Nano Banana Pro para las imagenes, Flow/Veo para el
video), por instruccion explicita de Antonio.

Regla fija de contenido (ajustada el 01/08/2026, reemplaza la version
anterior de 3 ganados + 1 perdido): se generan DOS piezas separadas
cada dia:

1. Recap de ganados: los 4 picks GANADOS mas recientes, tomados del
   pool "es_mejor_apuesta" (no solo del panel publico curado, que rara
   vez liquida 4 en un mismo dia -- el pool de mejor-apuesta es mucho
   mas amplio y siempre tiene material reciente real, sin inventar
   nada). Antes se mezclaban ganados de hace mas de una semana porque
   el panel publico liquida solo 2-3 picks/dia; con este pool mas
   amplio los 4 ganados salen casi siempre del dia anterior o, como
   maximo, de los 2-3 dias previos.
2. Picks de hoy: hasta 4 picks pendientes de jugar (los del panel
   publico + el premium del dia, que normalmente suman exactamente 4),
   ordenados por confianza (probabilidad) descendente -- gancho de
   "actua hoy", separado del recap para no mezclar resultados ya
   jugados con partidos que todavia no se juegan.

Fuente: Data/historial_picks.csv y Data/picks_hoy.json, mismos datos
que ya alimenta la web y el resto del pipeline de contenido -- no se
inventa nada.

Uso:
    python social/generar_prompts_ia.py

Salida: Data/social/<fecha>/prompts_ia.txt con las dos piezas
completas (imagen vertical, imagen cuadrada, video solo para el recap,
captions de las 3 plataformas y texto alternativo, para cada pieza).
"""
import json
import os
import sys
from datetime import date

import pandas as pd

RAIZ = os.path.dirname(os.path.abspath(__file__))
RAIZ_PIPELINE = os.path.dirname(RAIZ)
HISTORIAL_CSV = os.path.join(RAIZ_PIPELINE, "Data", "historial_picks.csv")
PICKS_HOY_JSON = os.path.join(RAIZ_PIPELINE, "Data", "picks_hoy.json")
SALIDA_BASE = os.path.join(RAIZ_PIPELINE, "Data", "social")

sys.path.insert(0, RAIZ)

BASE_URL = "https://sportpicks-suscripcion.vercel.app"


def _link_utm(plataforma, campana):
    return f"{BASE_URL}/?utm_source={plataforma}&utm_medium=social&utm_campaign={campana}"


PALETA = {
    "bg": "#081210",
    "accent": "#c8ff3d",
    "fg": "#f4fff0",
    "surface": "#0f1f1b",
    "border": "#1c332c",
    "rojo": "#ff6b6b",
}


def _seleccionar_ganados():
    """4 picks GANADOS mas recientes del pool 'es_mejor_apuesta' (mucho
    mas amplio que el panel publico curado, que liquida solo 2-3
    picks/dia y rara vez llega a 4 ganados en un mismo dia). Prioriza
    los que tienen cuota real registrada."""
    df = pd.read_csv(HISTORIAL_CSV)
    liq = df[df["estado"].isin(["Ganado", "Perdido"]) & (df["es_mejor_apuesta"] == True)].copy()  # noqa: E712
    liq["fecha_dt"] = pd.to_datetime(liq["fecha"])
    liq = liq.sort_values(["fecha_dt", "registrado_en"], ascending=False)

    ganados = liq[liq["estado"] == "Ganado"]
    con_cuota = ganados[ganados["cuota"].notna()]
    resto = ganados[ganados["cuota"].isna()]
    return pd.concat([con_cuota, resto]).head(4)


def _picks_de_hoy():
    """Hasta 4 picks pendientes de hoy (publicos + premium de
    Data/picks_hoy.json, que normalmente ya suman 4 entre ambos),
    ordenados por probabilidad/confianza descendente. Cada item es un
    dict plano -- puede ser un pick individual o una combinada premium
    (con 'picks_combo')."""
    if not os.path.exists(PICKS_HOY_JSON):
        return []
    with open(PICKS_HOY_JSON, encoding="utf-8") as f:
        data = json.load(f)
    candidatos = list(data.get("publicos", [])) + list(data.get("premium", []))
    candidatos.sort(key=lambda p: p.get("prob", 0), reverse=True)
    return candidatos[:4]


def _linea_pick(row):
    cuota_txt = f" — cuota @{row['cuota']}" if pd.notna(row["cuota"]) else ""
    return (
        f"{row['local']} vs {row['visitante']} ({row['liga_nombre']}) — "
        f"{row['mercado']}{cuota_txt} — {row['prob']}% prob."
    )


def _linea_pick_hoy(item):
    cuota = item.get("cuota_display", item.get("cuota"))
    if item.get("picks_combo"):
        # Combinada premium -- dos partidos distintos, no un solo local/visitante.
        return f"Combinada: {item['descripcion']} — cuota @{cuota} — {item['prob']}% prob."
    return (
        f"{item['local']} vs {item['visitante']} ({item['liga_nombre']}) — "
        f"{item['mercado']} — cuota @{cuota} — {item['prob']}% prob."
    )


def _prompt_imagen_ganados(ganados, formato):
    lineas = "\n".join(
        f'   Pick {i+1} (GANADO): "{_linea_pick(r)}"' for i, (_, r) in enumerate(ganados.iterrows())
    )

    if formato == "vertical":
        layout = (
            "Formato vertical 1080x1920 (para Instagram/TikTok Reels y Stories). "
            "Las 4 tarjetas de picks apiladas en una sola columna, de arriba a abajo."
        )
    else:
        layout = (
            "Formato cuadrado 1080x1080 (para feed de Facebook/Instagram). "
            "Las 4 tarjetas de picks en una cuadricula 2x2, para aprovechar el espacio cuadrado."
        )

    return f"""IDIOMA -- INSTRUCCIÓN CRÍTICA, LÉELA DOS VECES: esta imagen es para
un público 100% hispanohablante. TODO el texto debe quedar en ESPAÑOL,
sin excepción. Cada frase entre comillas más abajo (títulos, etiquetas
y las 4 líneas de picks) es el texto FINAL, letra por letra -- no es
una descripción para que tú traduzcas o adaptes, es el texto literal
que debe aparecer renderizado en la imagen. NO generes ninguna palabra
en inglés en ningún lugar: ni "WON", ni "GOALS", ni "CORNERS", ni
"ODDS", ni "PROB", ni "LATEST PICKS", ni "HISTORY", ni "LINK IN BIO",
ni ninguna otra traducción de las palabras españolas "GANADO", "goles",
"córners", "cuota", "prob.", "Nuestros últimos picks ganados",
"Historial completo público -- link en la bio". Copia el español tal
cual está escrito, con tildes y todo.

Diseña una imagen para redes sociales de la marca de análisis deportivo
"SportPicks Ligas". Estilo minimalista, oscuro, tipo dashboard/app de
datos deportivos.

{layout}

Paleta EXACTA (respetar los códigos hex):
- Fondo: verde muy oscuro casi negro {PALETA['bg']}
- Acento (títulos y dato clave): verde lima brillante {PALETA['accent']}
- Texto secundario: blanco hueso {PALETA['fg']}
- Tarjetas: verde apenas más claro que el fondo {PALETA['surface']}, borde sutil {PALETA['border']}

Contenido exacto a mostrar, de arriba a abajo, EN ESPAÑOL (no agregues
texto que no esté en esta lista):

1. Título grande en acento lima: "SPORTPICKS LIGAS"
2. Subtítulo en blanco: "Nuestros últimos picks ganados"
3. Cuatro tarjetas redondeadas, una por pick, cada una con: una etiqueta
   pequeña a la izquierda ("GANADO" en lima sobre fondo oscuro -- en
   español, nunca "WON"), el nombre del partido en blanco bold, el
   nombre de la liga/competición en gris pequeño debajo del partido, y
   debajo el mercado + cuota + probabilidad en gris claro, EN ESPAÑOL
   (recuerda: nada de "goals", "corners", "odds", "prob" en inglés). Si
   una tarjeta no trae cuota en el texto de abajo, NO escribas "s/d" ni
   inventes un número -- en esa tarjeta muestra solo mercado +
   probabilidad, sin el dato de cuota (es normal que no todas las
   tarjetas tengan cuota). El texto entre comillas de cada línea es
   literal, cópialo tal cual, no lo traduzcas:

{lineas}
4. Al final, separado por una línea delgada horizontal: en blanco
   "Historial completo público -- link en la bio", y en el texto más
   pequeño de toda la imagen (última línea, gris tenue): "+18 · Análisis
   estadístico, no garantía de resultado. Juega con responsabilidad."
   NO muestres ningún porcentaje de acierto ni cantidad de picks
   liquidados en esta imagen -- ese dato no debe aparecer en ningún
   lugar.

RECORDATORIO FINAL DE IDIOMA: antes de generar, revisa que ningún texto
de la imagen haya quedado en inglés. Si dudas de una palabra, déjala en
español.

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


def _prompt_imagen_hoy(picks_hoy, formato):
    lineas = "\n".join(
        f'   Pick {i+1}: "{_linea_pick_hoy(p)}"' for i, p in enumerate(picks_hoy)
    )
    n = len(picks_hoy)

    if formato == "vertical":
        layout = (
            "Formato vertical 1080x1920 (para Instagram/TikTok Reels y Stories). "
            f"Las {n} tarjetas apiladas en una sola columna, de arriba a abajo."
        )
    else:
        layout = (
            "Formato cuadrado 1080x1080 (para feed de Facebook/Instagram). "
            f"Las {n} tarjetas en una cuadricula 2x2 (o la distribución más pareja "
            f"posible para {n} elementos), para aprovechar el espacio cuadrado."
        )

    return f"""IDIOMA -- INSTRUCCIÓN CRÍTICA, LÉELA DOS VECES: esta imagen es para
un público 100% hispanohablante. TODO el texto debe quedar en ESPAÑOL,
sin excepción. Cada frase entre comillas más abajo (títulos, etiquetas
y las {n} líneas de picks) es el texto FINAL, letra por letra -- no es
una descripción para que tú traduzcas o adaptes, es el texto literal
que debe aparecer renderizado en la imagen. NO generes ninguna palabra
en inglés en ningún lugar: ni "TODAY", ni "GOALS", ni "CORNERS", ni
"ODDS", ni "PROB", ni "COMBINED", ni "FREE PICKS", ni "LINK IN BIO", ni
ninguna otra traducción de las palabras españolas "HOY", "goles",
"córners", "cuota", "prob.", "Combinada", "Picks de hoy", "Picks
gratis todos los días -- link en la bio". Copia el español tal cual
está escrito, con tildes y todo.

Diseña una imagen para redes sociales de la marca de análisis deportivo
"SportPicks Ligas". Estilo minimalista, oscuro, tipo dashboard/app de
datos deportivos.

{layout}

Paleta EXACTA (respetar los códigos hex):
- Fondo: verde muy oscuro casi negro {PALETA['bg']}
- Acento (títulos, etiqueta "HOY" y dato clave): verde lima brillante {PALETA['accent']}
- Texto secundario: blanco hueso {PALETA['fg']}
- Tarjetas: verde apenas más claro que el fondo {PALETA['surface']}, borde en acento lima {PALETA['accent']} (más marcado que el borde gris normal, porque estos partidos todavía no se juegan)

Contenido exacto a mostrar, de arriba a abajo, EN ESPAÑOL (no agregues
texto que no esté en esta lista):

1. Título grande en acento lima: "SPORTPICKS LIGAS"
2. Subtítulo en blanco: "Picks de hoy"
3. {n} tarjetas redondeadas con borde en acento lima, una por pick, cada
   una con: una etiqueta pequeña a la izquierda que diga "HOY" en acento
   lima sobre fondo oscuro (nunca "GANADO"/"PERDIDO" -- estos partidos
   todavía no se juegan), el nombre del partido (o de la combinada) en
   blanco bold, el nombre de la liga/competición en gris pequeño debajo
   del partido, y debajo el mercado + cuota + probabilidad en gris
   claro, EN ESPAÑOL. El texto entre comillas de cada línea es literal,
   cópialo tal cual, no lo traduzcas:

{lineas}
4. Al final, separado por una línea delgada horizontal: en blanco
   "Picks gratis todos los días -- link en la bio", y en el texto más
   pequeño de toda la imagen (última línea, gris tenue): "+18 · Análisis
   estadístico, no garantía de resultado. Juega con responsabilidad."

RECORDATORIO FINAL DE IDIOMA: antes de generar, revisa que ningún texto
de la imagen haya quedado en inglés. Si dudas de una palabra, déjala en
español.

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
  responsabilidad" -- no es opcional, debe verse en la imagen, no solo
  en el caption.
- NO fotos de personas reales ni rostros, NO marcas de agua de ningún
  tipo.

Tipografía sans-serif bold y moderna (estilo Inter/Poppins), sin
serifas. Composición limpia tipo app fintech/dashboard, buen espaciado,
jerarquía visual clara."""


def _prompt_video():
    return """IDIOMA: si el modelo agrega cualquier texto, subtítulo o voz en off,
debe estar en ESPAÑOL -- no en inglés. Preferible que no agregue texto
nuevo en absoluto (ver abajo).

Usa la imagen vertical del RECAP DE GANADOS (formato 1080x1920) como
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


def _texto_ligas(ligas):
    if not ligas:
        return "varias ligas"
    if len(ligas) == 1:
        return ligas[0]
    if len(ligas) == 2:
        return f"{ligas[0]} y {ligas[1]}"
    return ", ".join(ligas[:-1]) + f" y {ligas[-1]}"


def _ligas_de_ganados(ganados):
    vistas = []
    for _, r in ganados.iterrows():
        if r["liga_nombre"] not in vistas:
            vistas.append(r["liga_nombre"])
    return vistas


def _ligas_de_hoy(picks_hoy):
    vistas = []
    for p in picks_hoy:
        liga = p.get("liga_nombre")
        if liga and liga != "Multi-liga" and liga not in vistas:
            vistas.append(liga)
    return vistas


# Hashtags fijos por plataforma -- separados de los de liga (que si
# cambian dia a dia segun que competiciones aparezcan). Nunca se usa la
# palabra "apuesta(s)" en un hashtag (mismo criterio de cumplimiento que
# las imagenes) -- "juegaresponsable" es la unica excepcion, porque es
# la etiqueta estandar de juego responsable, no promocional.
HASHTAGS_LIGA = {
    "Brasileirão Série A": "#Brasileirao",
    "Liga Profesional Argentina": "#LigaArgentina",
    "CONMEBOL Sudamericana": "#CopaSudamericana",
    "CONMEBOL Libertadores": "#CopaLibertadores",
    "UEFA Champions League": "#ChampionsLeague",
    "UEFA Europa League": "#EuropaLeague",
    "UEFA Conference League": "#ConferenceLeague",
    "Major League Soccer": "#MLS",
}


def _hashtags(ligas, n_max):
    base = ["#SportPicksLigas", "#Futbol", "#PronosticosFutbol", "#AnalisisDeportivo", "#DatosDeportivos"]
    de_liga = [HASHTAGS_LIGA[l] for l in ligas if l in HASHTAGS_LIGA]
    todos = base + de_liga
    vistos, resultado = set(), []
    for h in todos:
        if h not in vistos:
            vistos.add(h)
            resultado.append(h)
    return resultado[:n_max]


def _alt_text_ganados(ganados):
    partes = [f"{r['local']} vs {r['visitante']} (ganado)" for _, r in ganados.iterrows()]
    return (
        "Tarjetas de picks de fútbol ganados recientes del modelo estadístico "
        f"SportPicks Ligas: {', '.join(partes)}, con cuotas y probabilidad de cada pick."
    )


def _alt_text_hoy(picks_hoy):
    partes = []
    for p in picks_hoy:
        if p.get("picks_combo"):
            partes.append(p["descripcion"])
        else:
            partes.append(f"{p['local']} vs {p['visitante']}")
    return (
        "Picks de fútbol pendientes de hoy del modelo estadístico SportPicks Ligas: "
        f"{', '.join(partes)}, con cuotas y probabilidad de cada pick."
    )


def generar_captions_ganados(ganados):
    ligas = _ligas_de_ganados(ganados)
    texto_ligas = _texto_ligas(ligas)
    campana = f"picks_ganados_{date.today().isoformat()}"

    tiktok = (
        f"Repaso de nuestros últimos picks ganados 📊 {texto_ligas}.\n\n"
        f"Historial completo (con lo que sale bien y lo que sale mal) en el link de la bio ⚽\n\n"
        f"⚠️ Análisis estadístico, no garantía de resultado. Juega con responsabilidad. +18.\n\n"
        + " ".join(_hashtags(ligas, 5))
    )

    instagram = (
        f"📊 Así venimos: nuestros últimos 4 picks ganados en {texto_ligas}.\n\n"
        f"👉 Historial completo (transparente, con lo bueno y lo malo) en el link de la bio.\n\n"
        f"⚠️ Análisis estadístico, no garantía de resultado. Juega con responsabilidad. +18.\n\n"
        f".\n.\n.\n"
        + " ".join(_hashtags(ligas, 12) + ["#JuegaResponsable"])
    )

    link_fb = _link_utm("facebook", campana)
    facebook = (
        f"📊 Nuestros últimos 4 picks ganados -- {texto_ligas}.\n\n"
        f"👉 Historial público completo: {link_fb}\n\n"
        f"⚠️ Análisis estadístico, no garantía de resultado. Juega con responsabilidad. +18.\n\n"
        + " ".join(_hashtags(ligas, 3))
    )

    return tiktok, instagram, facebook, _alt_text_ganados(ganados)


def generar_captions_hoy(picks_hoy):
    ligas = _ligas_de_hoy(picks_hoy)
    texto_ligas = _texto_ligas(ligas)
    campana = f"picks_hoy_{date.today().isoformat()}"

    tiktok = (
        f"🔥 Picks de hoy: {texto_ligas}.\n\n"
        f"Análisis estadístico, no corazonadas. Picks gratis en el link de la bio ⚽\n\n"
        f"⚠️ Análisis estadístico, no garantía de resultado. Juega con responsabilidad. +18.\n\n"
        + " ".join(_hashtags(ligas, 5))
    )

    instagram = (
        f"🔥 Picks de hoy para {texto_ligas}.\n\n"
        f"👉 Todos los picks gratis del día en el link de la bio.\n\n"
        f"⚠️ Análisis estadístico, no garantía de resultado. Juega con responsabilidad. +18.\n\n"
        f".\n.\n.\n"
        + " ".join(_hashtags(ligas, 12) + ["#JuegaResponsable"])
    )

    link_fb = _link_utm("facebook", campana)
    facebook = (
        f"🔥 Picks de hoy -- {texto_ligas}.\n\n"
        f"👉 Picks gratis del día: {link_fb}\n\n"
        f"⚠️ Análisis estadístico, no garantía de resultado. Juega con responsabilidad. +18.\n\n"
        + " ".join(_hashtags(ligas, 3))
    )

    return tiktok, instagram, facebook, _alt_text_hoy(picks_hoy)


def main():
    ganados = _seleccionar_ganados()
    if len(ganados) < 4:
        print(f"Solo hay {len(ganados)} picks ganados en el pool 'es_mejor_apuesta' -- necesito 4.")
        return

    picks_hoy = _picks_de_hoy()
    if not picks_hoy:
        print("No hay picks pendientes para hoy todavía en Data/picks_hoy.json (¿corrió el pipeline?).")
        return

    fecha_iso = date.today().isoformat()
    carpeta_salida = os.path.join(SALIDA_BASE, fecha_iso)
    os.makedirs(carpeta_salida, exist_ok=True)

    prompt_vertical_g = _prompt_imagen_ganados(ganados, "vertical")
    prompt_cuadrado_g = _prompt_imagen_ganados(ganados, "cuadrado")
    prompt_video = _prompt_video()
    tiktok_g, instagram_g, facebook_g, alt_g = generar_captions_ganados(ganados)

    prompt_vertical_h = _prompt_imagen_hoy(picks_hoy, "vertical")
    prompt_cuadrado_h = _prompt_imagen_hoy(picks_hoy, "cuadrado")
    tiktok_h, instagram_h, facebook_h, alt_h = generar_captions_hoy(picks_hoy)

    ruta = os.path.join(carpeta_salida, "prompts_ia.txt")
    with open(ruta, "w", encoding="utf-8") as f:
        f.write("############################################\n")
        f.write("# PIEZA 1: RECAP DE GANADOS (4 picks ya jugados)\n")
        f.write("############################################\n\n")
        f.write("=== PROMPT IMAGEN VERTICAL (Nano Banana Pro) — TikTok/Reels/Stories ===\n\n")
        f.write(prompt_vertical_g)
        f.write("\n\n\n=== PROMPT IMAGEN CUADRADA (Nano Banana Pro) — Facebook/Instagram feed ===\n\n")
        f.write(prompt_cuadrado_g)
        f.write("\n\n\n=== PROMPT VIDEO (Flow) — usar la imagen vertical del recap como fotograma inicial ===\n\n")
        f.write(prompt_video)
        f.write("\n\n\n=== CAPTION TIKTOK ===\n\n")
        f.write(tiktok_g)
        f.write("\n\n\n=== CAPTION INSTAGRAM ===\n\n")
        f.write(instagram_g)
        f.write("\n\n\n=== CAPTION FACEBOOK ===\n\n")
        f.write(facebook_g)
        f.write("\n\n\n=== TEXTO ALTERNATIVO (accesibilidad + SEO) ===\n\n")
        f.write(alt_g)

        f.write("\n\n\n############################################\n")
        f.write("# PIEZA 2: PICKS DE HOY (pendientes de jugar)\n")
        f.write("############################################\n\n")
        f.write("=== PROMPT IMAGEN VERTICAL (Nano Banana Pro) — TikTok/Reels/Stories ===\n\n")
        f.write(prompt_vertical_h)
        f.write("\n\n\n=== PROMPT IMAGEN CUADRADA (Nano Banana Pro) — Facebook/Instagram feed ===\n\n")
        f.write(prompt_cuadrado_h)
        f.write("\n\n\n=== CAPTION TIKTOK ===\n\n")
        f.write(tiktok_h)
        f.write("\n\n\n=== CAPTION INSTAGRAM ===\n\n")
        f.write(instagram_h)
        f.write("\n\n\n=== CAPTION FACEBOOK ===\n\n")
        f.write(facebook_h)
        f.write("\n\n\n=== TEXTO ALTERNATIVO (accesibilidad + SEO) ===\n\n")
        f.write(alt_h)
        f.write("\n")

    print(f"Generado: {ruta}")


if __name__ == "__main__":
    main()
