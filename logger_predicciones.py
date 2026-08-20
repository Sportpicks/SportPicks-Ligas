# -*- coding: utf-8 -*-
"""
logger_predicciones.py
Sistema de logging de predicciones vs resultados reales
Calcula MSE y recalibra parámetros Dixon-Coles por liga
"""
import os, sys, json, re
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta

RAIZ = os.path.dirname(os.path.abspath(__file__))
os.chdir(RAIZ)
sys.path.insert(0, RAIZ)
from configuracion import ZONA_PERU, LIGAS, CATEGORIAS_EXCLUIDAS

PERU_TZ = timezone(timedelta(hours=ZONA_PERU))

LOG_PRED   = os.path.join(RAIZ, 'Data', 'predicciones_log.csv')
LOG_RESULT = os.path.join(RAIZ, 'Data', 'resultados_log.csv')
CALIB_JSON = os.path.join(RAIZ, 'Data', 'calibracion.json')
CALIB_PROB_JSON = os.path.join(RAIZ, 'Data', 'calibracion_prob.json')
# Log append-only (una línea por corrida del pipeline) para auditar cuándo
# cada categoría cruza CALIBRACION_PROB_MIN_N_CATEGORIA y gana su propia
# curva isotónica -- ver calcular_calibracion_prob() más abajo. Sin esto,
# el único rastro del cruce quedaba enterrado en logs de GitHub Actions
# que rotan; con esto queda en el repo, versionado, consultable con
# pandas/jq en cualquier momento.
CALIB_PROB_HISTORIAL_JSONL = os.path.join(RAIZ, 'Data', 'calibracion_prob_historial.jsonl')

# ── Columnas del log de predicciones ──
COLS_PRED = [
    'fecha', 'hora', 'liga', 'local', 'visitante',
    'xg_l', 'xg_v', 'xg_total',
    'prob_1', 'prob_x', 'prob_2',
    'prob_over_25', 'prob_under_25', 'prob_btts_si',
    'cuota_1', 'cuota_x', 'cuota_2',
    'cuota_over_25', 'cuota_under_25',
    'generado_en',
    # Closing Line Value: cuota "de cierre" (aproximada, ver
    # registrar_cierre_desde_proximos) vs la cuota de publicación de arriba.
    # Señal de calidad de modelo independiente del resultado final del
    # partido — si el mercado se mueve a favor del pick (cuota baja) después
    # de publicado, es evidencia de que el modelo vio algo real antes que
    # el mercado terminara de descontarlo.
    'cuota_1_cierre', 'cuota_x_cierre', 'cuota_2_cierre',
    'cuota_over_25_cierre', 'cuota_under_25_cierre',
    'clv_1x2_pct', 'cierre_registrado_en',
    # 18/08/2026: extensión de CLV a Goles (95.4% del volumen elegible,
    # ver auditoría de calibración por categoría) -- cuota_over_25_cierre/
    # cuota_under_25_cierre ya se capturaban desde el CLV original pero
    # quedaban sin usar. clv_over25_pct y clv_under25_pct se calculan por
    # separado (no un solo 'clv_ou25_pct' promediando lados) porque son
    # dos lados de la misma línea con lecturas de CLV potencialmente
    # distintas -- guardar ambos permite, más adelante, cruzar contra
    # historial_picks.csv y usar el lado que corresponda al pick real
    # (Más/Menos de 2.5), en vez de asumir un solo lado como proxy fijo
    # (que es lo que hace clv_1x2_pct hoy con 'cuota_1', una limitación
    # conocida y no resuelta en este cambio).
    # bookmaker_1x2_cierre / bookmaker_ou25_cierre: de qué casa vino la
    # cuota "de cierre" (ver descargar_partidos._buscar_precio_full) --
    # permite filtrar el análisis de CLV por fuente ("solo Pinnacle") en
    # vez de mezclar bookmakers sin dejar rastro. No se captura el
    # bookmaker de PUBLICACIÓN todavía (auto_registrar_predicciones no lo
    # trackea) -- queda en el backlog: sin eso, filtrar solo por
    # bookmaker_cierre no garantiza "mismo libro en ambos extremos", solo
    # "el cierre fue de una fuente confiable".
    'clv_over25_pct', 'clv_under25_pct',
    'bookmaker_1x2_cierre', 'bookmaker_ou25_cierre',
    # 20/08/2026: fase cruda de la API (stage_name vía proximos.csv ->
    # pred['fase'] en modelo_prediccion.py), sin bucketizar. La lógica de
    # agrupar en 'qualifying' vs 'main_draw' vive en el futuro motor de
    # calibración por fase (Bloque B), no aquí -- este log guarda la
    # verdad cruda tal cual viene de TheStatsAPI ('qualifying',
    # 'round_of_16', '' si no aplica).
    'fase',
]

# ── Columnas del log de resultados ──
COLS_RESULT = [
    'fecha', 'liga', 'local', 'visitante',
    'goles_l_real', 'goles_v_real', 'goles_total_real',
    'resultado_real',  # '1', 'X', '2'
    'over_25_real',    # True/False
    'btts_real',       # True/False
    'registrado_en',
    # Fase 2 (liquidación de córners/tiros/tarjetas/faltas en el historial
    # de picks): stats reales por partido, pedidas a TheStatsAPI vía
    # get_match_stats() en sincronizar_resultados(). Pueden quedar NaN si
    # el partido no tiene stats completos en la API (mismo caso que ya
    # maneja fila_historico() en descargar_partidos.py) -- en ese caso
    # _evaluar_mercado() sigue devolviendo None y el pick queda 'Sin datos'.
    'corners_l_real', 'corners_v_real',
    'shots_l_real', 'shots_v_real',
    'shots_on_target_l_real', 'shots_on_target_v_real',
    'fouls_l_real', 'fouls_v_real',
    'cards_l_real', 'cards_v_real',  # tarjetas amarillas (igual que el modelo, ver modelo_prediccion.py:600)
    'stats_registrados_en',
]

def cargar_log(path, cols):
    """
    Carga o crea un log CSV. Si el CSV existente es de una versión anterior
    del schema (ej. antes de agregar las columnas de CLV), agrega las
    columnas faltantes como NaN en vez de romper -- migración silenciosa
    hacia adelante sin perder filas existentes.
    """
    if os.path.exists(path):
        df = pd.read_csv(path)
        for c in cols:
            if c not in df.columns:
                df[c] = pd.NA
        return df
    return pd.DataFrame(columns=cols)

def guardar_log(df, path):
    """Guarda el log CSV"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    df.to_csv(path, index=False)

def registrar_prediccion(pred, cuotas=None):
    """
    Registra una predicción antes del partido
    pred: dict con xg_l, xg_v, p1, px, p2, etc.
    """
    df = cargar_log(LOG_PRED, COLS_PRED)

    # Verificar si ya existe
    mask = (
        (df['fecha'] == pred.get('fecha', '')) &
        (df['local'] == pred.get('local', '')) &
        (df['visitante'] == pred.get('visitante', ''))
    )
    if mask.any():
        return False  # ya registrado

    cuotas = cuotas or {}
    nueva_fila = {
        'fecha':         pred.get('fecha', ''),
        'hora':          pred.get('hora', ''),
        'liga':          pred.get('liga', ''),
        'local':         pred.get('local', ''),
        'visitante':     pred.get('visitante', ''),
        'xg_l':          pred.get('xg_l', 0),
        'xg_v':          pred.get('xg_v', 0),
        'xg_total':      round(pred.get('xg_l', 0) + pred.get('xg_v', 0), 3),
        'prob_1':        pred.get('p1', 0),
        'prob_x':        pred.get('px', 0),
        'prob_2':        pred.get('p2', 0),
        'prob_over_25':  pred.get('over_2.5', 0),
        'prob_under_25': pred.get('under_2.5', 0),
        'prob_btts_si':  pred.get('btts_si', 0),
        'cuota_1':       cuotas.get('c1', 0),
        'cuota_x':       cuotas.get('cx', 0),
        'cuota_2':       cuotas.get('c2', 0),
        'cuota_over_25': cuotas.get('over_2.5', 0),
        'cuota_under_25':cuotas.get('under_2.5', 0),
        'generado_en':   datetime.now(PERU_TZ).isoformat(),
        'fase':          pred.get('fase', ''),
    }

    df = pd.concat([df, pd.DataFrame([nueva_fila])], ignore_index=True)
    guardar_log(df, LOG_PRED)
    return True

STATS_COLS_MAP = {
    'corners_l': 'corners_l_real', 'corners_v': 'corners_v_real',
    'shots_l': 'shots_l_real', 'shots_v': 'shots_v_real',
    'shots_on_target_l': 'shots_on_target_l_real', 'shots_on_target_v': 'shots_on_target_v_real',
    'fouls_l': 'fouls_l_real', 'fouls_v': 'fouls_v_real',
    'yellow_cards_l': 'cards_l_real', 'yellow_cards_v': 'cards_v_real',
}

def _stats_completos(fila):
    """True si ya tenemos las 5 stats (córners/tiros/tiros al arco/faltas/tarjetas) registradas para esta fila -- para no volver a pedir get_match_stats() de un partido ya sincronizado en una corrida anterior."""
    return all(pd.notna(fila.get(col)) for col in STATS_COLS_MAP.values())

def registrar_resultado(fecha, liga, local, visitante, goles_l, goles_v, stats=None):
    """
    Registra el resultado real después del partido.
    Idempotente: si ya existe una fila igual (mismo marcador y mismas
    stats), no reescribe el CSV ni cuenta como registro nuevo — importante
    para sincronizar_resultados(), que re-consulta la misma ventana de días
    cada vez que corre.
    `stats` (opcional): dict con las claves de extraer_stats_overview() de
    descargar_partidos.py (corners_l, corners_v, shots_l, ..., yellow_cards_v)
    -- fase 2 de liquidación del historial (córners/tiros/tarjetas/faltas).
    Si una fila ya existe con stats completos, no se pisan (evita perder
    datos si una corrida futura llega sin `stats` por un fallo puntual de
    get_match_stats()).
    Devuelve True solo si insertó una fila nueva o actualizó algún campo.
    """
    df = cargar_log(LOG_RESULT, COLS_RESULT)

    # Verificar si ya existe
    mask = (
        (df['fecha'] == fecha) &
        (df['local'] == local) &
        (df['visitante'] == visitante)
    )
    cambio = False
    if mask.any():
        existente = df.loc[mask].iloc[0]
        sin_cambios_goles = (
            str(existente.get('goles_l_real')) == str(goles_l) and
            str(existente.get('goles_v_real')) == str(goles_v)
        )
        if not sin_cambios_goles:
            df.loc[mask, 'goles_l_real'] = goles_l
            df.loc[mask, 'goles_v_real'] = goles_v
            df.loc[mask, 'goles_total_real'] = goles_l + goles_v
            df.loc[mask, 'resultado_real'] = '1' if goles_l > goles_v else ('X' if goles_l == goles_v else '2')
            df.loc[mask, 'over_25_real'] = goles_l + goles_v > 2.5
            df.loc[mask, 'btts_real'] = goles_l > 0 and goles_v > 0
            df.loc[mask, 'registrado_en'] = datetime.now(PERU_TZ).isoformat()
            cambio = True

        if stats and not _stats_completos(existente):
            for campo_stats, col in STATS_COLS_MAP.items():
                valor = stats.get(campo_stats)
                if valor is not None:
                    df.loc[mask, col] = valor
            df.loc[mask, 'stats_registrados_en'] = datetime.now(PERU_TZ).isoformat()
            cambio = True

        if not cambio:
            return False  # ya estaba registrado con el mismo marcador y stats completos
    else:
        nueva_fila = {
            'fecha':           fecha,
            'liga':            liga,
            'local':           local,
            'visitante':       visitante,
            'goles_l_real':    goles_l,
            'goles_v_real':    goles_v,
            'goles_total_real': goles_l + goles_v,
            'resultado_real':  '1' if goles_l > goles_v else ('X' if goles_l == goles_v else '2'),
            'over_25_real':    goles_l + goles_v > 2.5,
            'btts_real':       goles_l > 0 and goles_v > 0,
            'registrado_en':   datetime.now(PERU_TZ).isoformat(),
        }
        if stats:
            for campo_stats, col in STATS_COLS_MAP.items():
                nueva_fila[col] = stats.get(campo_stats)
            nueva_fila['stats_registrados_en'] = datetime.now(PERU_TZ).isoformat()
        df = pd.concat([df, pd.DataFrame([nueva_fila])], ignore_index=True)

    guardar_log(df, LOG_RESULT)
    print(f'✅ Resultado registrado: {local} {goles_l}-{goles_v} {visitante}')
    return True

def calcular_mse():
    """
    Calcula MSE y métricas de calibración por liga
    Compara predicciones vs resultados reales
    """
    df_pred = cargar_log(LOG_PRED, COLS_PRED)
    df_res  = cargar_log(LOG_RESULT, COLS_RESULT)

    if len(df_pred) == 0 or len(df_res) == 0:
        print('⚠️ Sin datos suficientes para calibrar')
        return {}

    # Merge predicciones con resultados
    df = pd.merge(
        df_pred, df_res,
        on=['fecha', 'liga', 'local', 'visitante'],
        how='inner'
    )

    if len(df) == 0:
        print('⚠️ Sin partidos con predicción Y resultado')
        return {}

    print(f'\n📊 ANÁLISIS DE CALIBRACIÓN ({len(df)} partidos)')
    print('='*60)

    calibracion = {}

    for liga in df['liga'].unique():
        df_l = df[df['liga'] == liga].copy()
        n = len(df_l)
        if n < 3:
            continue

        # MSE de goles totales
        mse_goles = float(np.mean((df_l['xg_total'] - df_l['goles_total_real'])**2))
        mae_goles = float(np.mean(np.abs(df_l['xg_total'] - df_l['goles_total_real'])))

        # Accuracy 1X2
        df_l['pred_resultado'] = df_l.apply(
            lambda r: '1' if r['prob_1'] >= r['prob_x'] and r['prob_1'] >= r['prob_2']
                      else ('X' if r['prob_x'] >= r['prob_2'] else '2'), axis=1
        )
        accuracy_1x2 = float((df_l['pred_resultado'] == df_l['resultado_real']).mean() * 100)

        # Accuracy Over/Under 2.5
        df_l['pred_over25'] = df_l['prob_over_25'] >= 50
        accuracy_over25 = float((df_l['pred_over25'] == df_l['over_25_real']).mean() * 100)

        # Sesgo: ¿sobreestima o subestima goles?
        sesgo = float((df_l['xg_total'] - df_l['goles_total_real']).mean())

        # Factor de corrección sugerido
        media_pred = float(df_l['xg_total'].mean())
        media_real = float(df_l['goles_total_real'].mean())
        factor_corr = round(media_real / media_pred, 3) if media_pred > 0 else 1.0

        calibracion[liga] = {
            'partidos':        n,
            'mse_goles':       round(mse_goles, 3),
            'mae_goles':       round(mae_goles, 3),
            'sesgo_goles':     round(sesgo, 3),
            'accuracy_1x2':    round(accuracy_1x2, 1),
            'accuracy_over25': round(accuracy_over25, 1),
            'media_xg_pred':   round(media_pred, 3),
            'media_goles_real':round(media_real, 3),
            'factor_correccion': factor_corr,
        }

        liga_nombre = LIGAS.get(liga, {}).get('nombre', liga)
        print(f'\n  {liga_nombre} ({n} partidos):')
        print(f'    MSE goles:      {mse_goles:.3f}')
        print(f'    MAE goles:      {mae_goles:.3f}')
        print(f'    Sesgo:          {sesgo:+.3f} ({"sobreestima" if sesgo > 0 else "subestima"})')
        print(f'    Accuracy 1X2:   {accuracy_1x2:.1f}%')
        print(f'    Accuracy O/U:   {accuracy_over25:.1f}%')
        print(f'    xG pred promedio: {media_pred:.2f} | Real: {media_real:.2f}')
        print(f'    Factor corrección sugerido: {factor_corr:.3f}')

        if abs(sesgo) > 0.5:
            if sesgo > 0:
                print(f'    ⚠️ Modelo SOBREESTIMA goles — reducir media_goles en {abs(sesgo):.2f}')
            else:
                print(f'    ⚠️ Modelo SUBESTIMA goles — aumentar media_goles en {abs(sesgo):.2f}')

    # Guardar calibración
    with open(CALIB_JSON, 'w', encoding='utf-8') as f:
        json.dump(calibracion, f, ensure_ascii=False, indent=2)
    print(f'\n✅ Calibración guardada en {CALIB_JSON}')

    return calibracion

CALIBRACION_PROB_MIN_N = 20

def _isotonica_pava(x, y):
    """
    Regresión isotónica (Pool Adjacent Violators Algorithm) implementada a
    mano con numpy puro -- no se agrega scikit-learn como dependencia solo
    para esto (requirements.txt de este repo nunca lo tuvo, ver
    auditoría 10/08/2026). x debe venir ordenado ascendente; y son
    resultados binarios (0/1). Devuelve una lista de bloques
    [(x_medio, y_calibrada, n)] no decreciente en y_calibrada, donde
    bloques con menos de CALIBRACION_PROB_MIN_N muestras se fusionan con
    el siguiente (o el anterior, si es el último) para evitar sobreajuste
    en zonas con pocos datos -- caso real detectado en la primera corrida:
    bloques de n=1 en el extremo bajo de prob daban 0% o 100% de acierto
    por una sola muestra, ruido puro, no señal.
    """
    stack = []  # cada elemento: [suma_y, count, xs]
    for xi, yi in zip(x, y):
        stack.append([float(yi), 1, [xi]])
        while len(stack) > 1 and (stack[-2][0] / stack[-2][1]) > (stack[-1][0] / stack[-1][1]):
            s2, c2, xs2 = stack.pop()
            s1, c1, xs1 = stack.pop()
            stack.append([s1 + s2, c1 + c2, xs1 + xs2])

    fusionados = []
    actual = None
    for bloque in stack:
        actual = bloque if actual is None else [actual[0] + bloque[0], actual[1] + bloque[1], actual[2] + bloque[2]]
        if actual[1] >= CALIBRACION_PROB_MIN_N:
            fusionados.append(actual)
            actual = None
    if actual is not None:
        if fusionados:
            prev = fusionados.pop()
            actual = [prev[0] + actual[0], prev[1] + actual[1], prev[2] + actual[2]]
        fusionados.append(actual)

    return [
        (round(float(np.mean(xs)), 2), round(s / c * 100, 2), c)
        for s, c, xs in fusionados
    ]

CALIBRACION_PROB_MIN_N_CATEGORIA = 200

# ── Bloque B: bucketing de fase (ETL, no wireado a calcular_calibracion_prob
# todavía -- ver tarea #152, gateada a n>=30 en CLV de Goles) ──
#
# Copas continentales donde se documentó (auditoría 19/08/2026, tarea #154:
# caída de acierto 55.8%→47.1% en mejor_apuesta, concentrada en Conference/
# Europa/Sudamericana) o se infirió por firma estructural (CAF, 20/08/2026:
# 59.7% de sus partidos en fase='qualifying', misma forma que las de arriba)
# la dinámica "ronda clasificatoria = rival semiprofesional, alta varianza"
# vs "cuadro principal = rivales parejos". Ligas domésticas fuera de esta
# lista IGNORAN su columna 'fase' por completo -- sus playoffs de fin de
# temporada (quarter_final/semi_final/final en Brasileirão, Liga 1 Perú,
# MLS, etc., ver auditoría 20/08/2026) son un fenómeno distinto: equipos
# fuertes enfrentándose en instancia decisiva, no un desbalance de nivel.
# Mezclarlos con 'fase_previa'/'cuadro_principal' de copa introduciría
# sesgo direccional, no ruido de media cero -- destruiría el propósito de
# la calibración en vez de mejorarla.
COMPETICIONES_FASE_RELEVANTE = {
    'comp_3498',    # UEFA Champions League
    'comp_408698',  # UEFA Conference League
    'comp_7739',    # UEFA Europa League
    'comp_0499',    # CONMEBOL Libertadores
    'comp_1615',    # CONMEBOL Sudamericana
    'comp_08478',   # CAF Champions League
}

def bucketizar_fase(liga, fase):
    """
    Deriva el bucket de calibración de Bloque B a partir de (liga, fase)
    crudos. Mapeo binario dentro de la whitelist:
      - fase == 'qualifying'            -> 'fase_previa'   (alta varianza)
      - cualquier otro valor, incl. NaN -> 'cuadro_principal' (estable)
    NaN dentro de una liga de la whitelist se interpreta como fase de
    grupos: TheStatsAPI no le pone stage_name explícito a esa etapa (a
    diferencia de las rondas de eliminación directa), y esos equipos ya
    superaron la clasificatoria -- más parejos entre sí que 'fase_previa'.
    Supuesto explícito, no confirmado contra resultado real; revisar si
    Bloque B ya corriendo muestra evidencia en contra.

    Liga fuera de COMPETICIONES_FASE_RELEVANTE (doméstica): 'regular',
    sin importar el valor de fase -- ver rationale arriba.

    NO muta ni sobreescribe la columna 'fase' original de
    historial_picks.csv/predicciones_log.csv, que se preserva intacta
    para auditoría/re-derivación futura (decisión 20/08/2026: guardar la
    verdad cruda, bucketizar solo en lectura).
    """
    if liga not in COMPETICIONES_FASE_RELEVANTE:
        return 'regular'
    if fase == 'qualifying':
        return 'fase_previa'
    return 'cuadro_principal'


def agregar_fase_calibracion(df, col_liga='liga', col_fase='fase',
                              col_salida='fase_calibracion'):
    """
    Aplica bucketizar_fase() vectorizado sobre un DataFrame (ej. el
    resultado de cargar_log(LOG_PRED, COLS_PRED) o pd.read_csv sobre
    historial_picks.csv), agregando col_salida sin tocar col_fase.
    Devuelve una copia -- no muta el df de entrada.
    """
    df = df.copy()
    df[col_salida] = [bucketizar_fase(l, f) for l, f in zip(df[col_liga], df[col_fase])]
    return df


def calcular_calibracion_prob():
    """
    Calibración de probabilidad POR CATEGORÍA (isotónica) -- distinta de
    calcular_mse()/calibracion.json, que corrige el xG predicho por liga.
    Esta corrige la probabilidad final mostrada al usuario (prob_efectiva,
    post-blend) contra el acierto real.

    Refactor 18/08/2026 (auditoría de ROI real por mercado, ver
    CATEGORIAS_EXCLUIDAS en configuracion.py): hasta esta fecha se entrenaba
    UNA sola curva isotónica pooleando TODAS las categorías juntas. Con
    Goles aportando ~67% del volumen (700 de 1047 picks liquidados a la
    fecha), esa curva única quedaba dominada por el sesgo de Goles y podía
    calibrar mal categorías con distribución de acierto distinta (Córners,
    Doble Op.) -- causa raíz probable de que Córners/Doble Op. mostraran
    ROI real negativo pese a pasar el piso de EV.

    Ahora se entrena una curva por categoría, con fallback a una curva
    'Global' (la pooled de antes) para cualquier categoría que no alcance
    CALIBRACION_PROB_MIN_N_CATEGORIA=200 muestras propias -- mismo umbral
    que ya usaba la curva global antes de este refactor, aplicado ahora por
    categoría para evitar sobreajuste en categorías con poca muestra (ej.
    Doble Op. con ~34 picks liquidados a la fecha: entrenar una curva propia
    con esa muestra sería más ruido que señal, así que usa Global hasta que
    acumule 200). generador_picks_ligas._calibrar_prob(prob, categoria) hace
    ese lookup con fallback en producción.

    Origen del hallazgo original (auditoría de modelo 10/08/2026, 761 picks
    liquidados): agrupando por bucket de probabilidad, todo el rango 60-75%
    mostraba al modelo sobreconfiado de 10 a 17 puntos porcentuales frente
    al acierto real (ej. bucket 70-75%: predice 72.5%, acierto real 56.5%).
    Brier score global 0.253, prácticamente igual al de predecir siempre la
    tasa base (0.247).

    Se usa Data/historial_picks.csv (no predicciones_log.csv) a propósito:
    es la población exacta a la que se le va a aplicar esta calibración en
    producción (generador_picks_ligas.py, después del blend con mercado,
    antes de EV) -- mismo filtro cuota>=1.30/prob>=50 que ya aplica
    generar_candidatos(). Se excluyen las combinadas (categoria=
    'Combinada'): su probabilidad ya es un producto de dos patas con su
    propio factor de corrección (FACTOR_CALIBRACION_COMBO), calibrarlas
    aquí también compondría dos correcciones sobre el mismo sesgo.

    También se excluyen CATEGORIAS_EXCLUIDAS (1X2/Tiros/Tarjetas/Córners --
    ver auditorías de resultados 15/08/2026 y 18/08/2026): esas categorías
    ya no se publican (generador_picks_ligas.py) ni se eligen como
    es_mejor_apuesta (generar_web.py), pero historial_picks.csv sigue
    teniendo filas viejas de cuando sí se publicaban, con una curva de
    sesgo distinta que distorsionaría tanto la curva Global como cualquier
    curva propia si se dejaran entrar.

    No se aplica decaimiento temporal / límite de antigüedad a la muestra:
    a la fecha de este refactor historial_picks.csv cubre apenas 27 días
    (21/07 al 17/08/2026), muy por debajo de cualquier horizonte donde el
    mercado podría considerarse 'obsoleto'. Filtrar por antigüedad ahora
    reduciría aún más la muestra de categorías chicas justo cuando más la
    necesitan para salir del fallback a Global -- iría en contra del propio
    umbral de 200 que se acaba de introducir. Revisar cuando el histórico
    acumule varios meses de datos (ver hueco arriba: CALIBRACION_PROB_MIN_N_CATEGORIA).
    """
    if not os.path.exists(HISTORIAL_PATH):
        print('⚠️ Sin Data/historial_picks.csv todavía -- corré generar_web.py primero')
        return {}

    df = pd.read_csv(HISTORIAL_PATH)
    liq = df[df['estado'].isin(['Ganado', 'Perdido'])].copy()
    excluidas = CATEGORIAS_EXCLUIDAS | {'Combinada'}
    ind = liq[~liq['categoria'].isin(excluidas)].copy()

    if len(ind) < 200:
        print(f'⚠️ Solo {len(ind)} picks individuales liquidados -- se necesitan >=200 para calibrar con confianza, se deja calibracion_prob.json como está')
        return {}

    ind = ind.sort_values('prob').reset_index(drop=True)
    ind['gano'] = (ind['estado'] == 'Ganado').astype(int)

    def _entrenar(sub_df):
        bloques = _isotonica_pava(sub_df['prob'].values, sub_df['gano'].values)
        return [
            {'prob_modelo': bx, 'prob_calibrada': by, 'n': n}
            for bx, by, n in bloques
        ]

    categorias_out = {}
    # n de CADA categoría del pool elegible (tenga curva propia o no) --
    # para el log de auditoría de abajo, que necesita ver la progresión de
    # las categorías que siguen en fallback, no solo las que ya cruzaron.
    n_por_categoria = {cat: len(sub) for cat, sub in ind.groupby('categoria')}

    # Categorías que YA tenían curva propia en la corrida anterior (leído
    # de Data/calibracion_prob_historial.jsonl) -- para detectar el cruce
    # exacto de hoy comparando contra el estado de ayer. Si el log no
    # existe todavía (primera corrida de este mecanismo) o está vacío,
    # se asume vacío: cualquier categoría con curva propia hoy se reporta
    # como cruce (razonable -- es la primera vez que se audita).
    categorias_con_curva_ayer = set()
    if os.path.exists(CALIB_PROB_HISTORIAL_JSONL):
        try:
            with open(CALIB_PROB_HISTORIAL_JSONL, encoding='utf-8') as f:
                lineas = [l for l in f if l.strip()]
            if lineas:
                ultimo = json.loads(lineas[-1])
                categorias_con_curva_ayer = {
                    cat for cat, info in ultimo.get('categorias', {}).items()
                    if info.get('tiene_curva_propia')
                }
        except (json.JSONDecodeError, OSError):
            pass  # log corrupto/inaccesible -- no bloquea la calibración, solo el log de auditoría

    # Curva Global -- pooled, como antes del refactor. Sirve de fallback
    # para cualquier categoría sin muestra propia suficiente.
    breakpoints_global = _entrenar(ind)
    categorias_out['Global'] = {'n': len(ind), 'breakpoints': breakpoints_global}

    print(f'\n📊 CALIBRACIÓN DE PROBABILIDAD POR CATEGORÍA ({len(ind)} picks individuales)')
    print('='*60)
    print(f"  Global          n={len(ind):4d}  {len(breakpoints_global)} bloques")

    for categoria, sub in ind.groupby('categoria'):
        n = len(sub)
        if n < CALIBRACION_PROB_MIN_N_CATEGORIA:
            faltan = CALIBRACION_PROB_MIN_N_CATEGORIA - n
            print(f"  {categoria:15s} n={n:4d}  <{CALIBRACION_PROB_MIN_N_CATEGORIA} -- usa fallback Global (faltan {faltan})")
            continue
        sub = sub.sort_values('prob').reset_index(drop=True)
        breakpoints_cat = _entrenar(sub)
        categorias_out[categoria] = {'n': n, 'breakpoints': breakpoints_cat}
        print(f"  {categoria:15s} n={n:4d}  {len(breakpoints_cat)} bloques  (curva propia)")
        for bp in breakpoints_cat:
            gap = bp['prob_modelo'] - bp['prob_calibrada']
            print(f"      prob_modelo~{bp['prob_modelo']:5.1f}  →  prob_calibrada={bp['prob_calibrada']:5.1f}  (n={bp['n']}, gap={gap:+.1f}pp)")

    # Cruces de hoy: categorías con curva propia AHORA que ayer todavía
    # estaban en fallback Global -- el evento puntual que dispara la
    # auditoría manual de su primera curva independiente.
    categorias_con_curva_hoy = {c for c in categorias_out if c != 'Global'}
    cruces_hoy = sorted(categorias_con_curva_hoy - categorias_con_curva_ayer)
    if cruces_hoy:
        print('\n🎯 CRUCE DE UMBRAL DETECTADO -- primera curva isotónica independiente:')
        for cat in cruces_hoy:
            print(f"   {cat}: n={n_por_categoria[cat]} (>= {CALIBRACION_PROB_MIN_N_CATEGORIA}) -- revisar sus breakpoints arriba antes de confiar ciegamente en la curva nueva")

    generado_en = datetime.now(PERU_TZ).isoformat()

    with open(CALIB_PROB_JSON, 'w', encoding='utf-8') as f:
        json.dump({
            'generado_en': generado_en,
            'n_total': len(ind),
            'min_n_categoria': CALIBRACION_PROB_MIN_N_CATEGORIA,
            'categorias': categorias_out,
        }, f, ensure_ascii=False, indent=2)
    print(f'\n✅ Calibración de probabilidad guardada en {CALIB_PROB_JSON}')

    # Log append-only de auditoría (una línea JSON por corrida) -- registra
    # el n de TODAS las categorías del pool elegible (tengan curva propia o
    # no) y la lista de cruces detectados hoy. Permite reconstruir, sin
    # tocar logs de GitHub Actions, la fecha exacta en que cada categoría
    # cruzó el umbral y auditar su primera curva desde ese momento.
    entrada_historial = {
        'generado_en': generado_en,
        'n_total': len(ind),
        'min_n_categoria': CALIBRACION_PROB_MIN_N_CATEGORIA,
        'categorias': {
            cat: {'n': n, 'tiene_curva_propia': cat in categorias_con_curva_hoy}
            for cat, n in n_por_categoria.items()
        },
        'cruces_hoy': cruces_hoy,
    }
    with open(CALIB_PROB_HISTORIAL_JSONL, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entrada_historial, ensure_ascii=False) + '\n')
    print(f'📝 Registro de auditoría anexado a {CALIB_PROB_HISTORIAL_JSONL}')

    return categorias_out

def sincronizar_resultados(dias_atras=4):
    """
    Trae partidos FINALIZADOS de las ligas cubiertas (configuracion.LIGAS)
    de los últimos `dias_atras` días desde TheStatsAPI y los registra en
    resultados_log.csv, para poder cruzarlos contra predicciones_log.csv
    y recalibrar el modelo (calcular_mse()).

    Usa el mismo cliente/API que descargar_partidos.py, así que los nombres
    de equipo y competition_id coinciden exactamente con los que ya quedaron
    en predicciones_log.csv (evita el mismatch de nombres que existía en
    los registros manuales previos a la migración a TheStatsAPI).
    """
    from configuracion import API_THESTATS
    from thestats_client import TheStatsClient, TheStatsAPIError
    from descargar_partidos import utc_a_peru, extraer_stats_overview

    hoy = datetime.now(PERU_TZ).date()
    date_from = (hoy - timedelta(days=dias_atras)).isoformat()
    date_to = hoy.isoformat()

    client = TheStatsClient(API_THESTATS)
    revisados = 0
    registrados = 0
    con_stats = 0

    # Set de (fecha, local, visitante) que ya tienen las 5 stats fase-2
    # completas -- para no volver a pedir get_match_stats() de un partido
    # ya sincronizado en una corrida anterior (ahorra llamadas, el cliente
    # ya se autolimita pero no hace falta gastarlas de más).
    df_res_previo = cargar_log(LOG_RESULT, COLS_RESULT)
    ya_con_stats = set()
    if len(df_res_previo):
        for _, r in df_res_previo.iterrows():
            if _stats_completos(r):
                ya_con_stats.add((r['fecha'], r['local'], r['visitante']))

    print(f'\n🔄 Sincronizando resultados finalizados ({date_from} → {date_to})')

    for liga_id, cfg in LIGAS.items():
        try:
            finalizados = client.get_matches(
                liga_id, status='finished',
                date_from=date_from, date_to=date_to,
            )
        except TheStatsAPIError as e:
            print(f'  ⚠️ {cfg.get("nombre", liga_id)}: {e}')
            continue

        nuevos_liga = 0
        for m in finalizados:
            score = m.get('score') or {}
            gl, gv = score.get('home'), score.get('away')
            if gl is None or gv is None:
                continue

            fecha, _hora = utc_a_peru(m['utc_date'])
            local = m['home_team']['name']
            visitante = m['away_team']['name']
            revisados += 1

            stats = None
            if (fecha, local, visitante) not in ya_con_stats:
                try:
                    raw_stats = client.get_match_stats(m['id'])
                    stats = extraer_stats_overview(raw_stats)
                    if any(v is not None for v in stats.values()):
                        con_stats += 1
                except TheStatsAPIError:
                    pass  # se reintenta en la próxima corrida

            if registrar_resultado(fecha, liga_id, local, visitante, int(gl), int(gv), stats=stats):
                registrados += 1
                nuevos_liga += 1

        if finalizados:
            print(f'  {cfg.get("nombre", liga_id)}: {len(finalizados)} finalizados, {nuevos_liga} nuevos')

    print(f'\n✅ Sync resultados: {revisados} finalizados revisados, {registrados} nuevos/actualizados, '
          f'{con_stats} con stats fase-2 pedidas → {LOG_RESULT}')
    return registrados

def registrar_cierre_desde_proximos():
    """
    Snapshot de cuota "de cierre" para partidos de HOY que ya tienen una
    predicción registrada (de un día anterior) pero todavía no un cierre.
    Usa la cuota más reciente de proximos.csv, refrescada por
    descargar_partidos.py --diario que corre justo antes en el pipeline
    diario -- es la cuota más cercana al kickoff disponible con la
    arquitectura actual de snapshots diarios (no hay polling en tiempo
    real de odds). Es una APROXIMACIÓN de Closing Line Value, no el cierre
    exacto de ningún bookmaker: sirve como proxy de si el mercado se movió
    a favor o en contra del pick entre publicación y el día del partido.
    """
    df_pred = cargar_log(LOG_PRED, COLS_PRED)
    if len(df_pred) == 0:
        print('⚠️ Sin predicciones registradas aún')
        return 0
    try:
        df_prox = pd.read_csv(os.path.join(RAIZ, 'Data', 'partidos', 'proximos.csv'))
    except FileNotFoundError:
        print('⚠️ Sin Data/partidos/proximos.csv -- corré descargar_partidos.py --diario primero')
        return 0

    hoy = datetime.now(PERU_TZ).strftime('%Y-%m-%d')
    sin_cierre = df_pred['cuota_1_cierre'].isna() if 'cuota_1_cierre' in df_pred else pd.Series(True, index=df_pred.index)
    pendientes = df_pred[(df_pred['fecha'] == hoy) & sin_cierre]
    actualizados = 0

    # Columnas de texto -- si acaban de crearse (cargar_log las rellena con
    # pd.NA), pandas les infiere dtype float64 por default y asignarles un
    # string más abajo dispara FutureWarning (deprecado, será error en una
    # versión futura de pandas). Cast explícito a object antes de escribir.
    for col in ('bookmaker_1x2_cierre', 'bookmaker_ou25_cierre', 'cierre_registrado_en'):
        if col in df_pred and df_pred[col].dtype != object:
            df_pred[col] = df_pred[col].astype(object)

    for idx, row in pendientes.iterrows():
        mask = ((df_prox['local'] == row['local']) &
                (df_prox['visitante'] == row['visitante']) &
                (df_prox['fecha'] == row['fecha']))
        if not mask.any():
            continue
        prox = df_prox[mask].iloc[0]
        c1c = prox.get('c1', 0) or None
        cxc = prox.get('cx', 0) or None
        c2c = prox.get('c2', 0) or None
        overc = prox.get('over_2.5', 0) or None
        underc = prox.get('under_2.5', 0) or None
        df_pred.loc[idx, 'cuota_1_cierre'] = c1c
        df_pred.loc[idx, 'cuota_x_cierre'] = cxc
        df_pred.loc[idx, 'cuota_2_cierre'] = c2c
        df_pred.loc[idx, 'cuota_over_25_cierre'] = overc
        df_pred.loc[idx, 'cuota_under_25_cierre'] = underc
        # 18/08/2026: bookmaker de la cuota de cierre (ver
        # descargar_partidos._buscar_precio_full / COLUMNAS_PROX) -- '' si
        # proximos.csv es de antes de este cambio (columna ausente).
        df_pred.loc[idx, 'bookmaker_1x2_cierre'] = prox.get('bookmaker_1x2') or None
        df_pred.loc[idx, 'bookmaker_ou25_cierre'] = prox.get('bookmaker_ou25') or None

        c1_pub = row.get('cuota_1', 0)
        if c1_pub and c1c:
            # CLV positivo = la cuota bajó (mercado se movió a favor del
            # pick) entre publicación y cierre -- señal de que el modelo
            # capturó algo real antes de que el mercado terminara de
            # ajustarse. Negativo = el mercado se movió en contra.
            df_pred.loc[idx, 'clv_1x2_pct'] = round((float(c1_pub) / float(c1c) - 1) * 100, 2)

        # 18/08/2026: mismo cálculo para Goles (Over/Under 2.5) -- 95.4%
        # del volumen elegible tras las exclusiones de categorías (ver
        # calcular_calibracion_prob). Dos columnas separadas, no un
        # promedio: son dos lados de la misma línea, cada uno con su
        # propio CLV; se cruzan más adelante contra el pick real
        # (Más/Menos de 2.5) en historial_picks.csv en vez de asumir un
        # solo lado fijo como proxy (limitación conocida de clv_1x2_pct,
        # que siempre usa 'cuota_1' sin importar si el pick fue 1/X/2).
        over_pub = row.get('cuota_over_25', 0)
        if over_pub and overc:
            df_pred.loc[idx, 'clv_over25_pct'] = round((float(over_pub) / float(overc) - 1) * 100, 2)
        under_pub = row.get('cuota_under_25', 0)
        if under_pub and underc:
            df_pred.loc[idx, 'clv_under25_pct'] = round((float(under_pub) / float(underc) - 1) * 100, 2)

        df_pred.loc[idx, 'cierre_registrado_en'] = datetime.now(PERU_TZ).isoformat()
        actualizados += 1

    if actualizados:
        guardar_log(df_pred, LOG_PRED)
    print(f'✅ CLV: {actualizados} cierre(s) registrado(s) para partidos de hoy')
    verificar_umbral_clv_goles()
    return actualizados

# ── Alerta de umbral CLV de Goles (Tarea #152) ──
# 20/08/2026: hasta este commit, el gate n>=30 para arrancar el análisis
# de CLV como detector de señal/ruido (Track C) se chequeaba a mano --
# nadie corría clv-resumen todos los días. Mismo patrón idempotente que
# calcular_calibracion_prob() (Tarea #150): un JSONL append-only que solo
# escribe un evento nuevo la primera vez que n cruza el umbral, para no
# repetir el aviso en cada corrida diaria una vez notificado.
CLV_GOLES_MIN_N = 30
CLV_GOLES_HISTORIAL_JSONL = os.path.join(RAIZ, 'Data', 'clv_umbral_historial.jsonl')

def _muestra_clv_goles_valida():
    """
    Devuelve solo las filas de Goles útiles para validar CLV-vs-resultado
    (Tarea #152 / Track C): publicadas de verdad (es_publico, es_premium
    o es_mejor_apuesta en True), resueltas (Ganado/Perdido), y con CLV
    capturado para el lado exacto que se publicó (Más/Menos).

    CORRECCIÓN 20/08/2026: la versión anterior de verificar_umbral_clv_goles
    contaba predicciones_log['clv_over25_pct'].notna() |
    ['clv_under25_pct'].notna() a secas y llegó a n=69 -- sobreestimación
    severa por 3 motivos, descubiertos al intentar correr el cruce real
    para Track C:
      1. registrar_cierre_desde_proximos() captura AMBOS lados de la
         línea de Goles para cualquier partido con predicción registrada,
         tenga o no un pick publicado en ese mercado -- 25 de 69 filas
         eran captura informativa sin ningún pick real detrás.
      2. historial_picks.csv acumula filas "fantasma" de snapshots
         superados por _desactivar_snapshots_previos() (los 3 flags en
         False, nunca fueron el pick vigente el día del partido) --
         sin filtrar por fue_publicado se cuentan picks que nadie vio.
      3. Partidos ya con CLV capturado pero todavía sin jugar siguen
         'Pendiente' -- no aportan al cruce CLV-vs-resultado hasta
         liquidarse.
    n real verificado 20/08/2026: 13, no 69 -- y concentrado en un solo
    día (19/08), la única fecha con tiempo suficiente para tener CLV
    capturado Y ya liquidado desde que se desplegó CLV-para-Goles.
    """
    df_pred = cargar_log(LOG_PRED, COLS_PRED)
    hist = pd.read_csv(HISTORIAL_PATH)

    goles = hist[hist['mercado'].isin(['Más de 2.5 goles', 'Menos de 2.5 goles'])].copy()
    fue_publicado = goles['es_publico'] | goles['es_premium'] | goles['es_mejor_apuesta']
    resueltos = goles[goles['estado'].isin(['Ganado', 'Perdido']) & fue_publicado].copy()

    m = resueltos.merge(
        df_pred[['fecha', 'local', 'visitante', 'clv_over25_pct', 'clv_under25_pct']],
        on=['fecha', 'local', 'visitante'], how='left'
    )
    m['clv_pick'] = m.apply(
        lambda r: r['clv_over25_pct'] if r['mercado'] == 'Más de 2.5 goles'
        else (r['clv_under25_pct'] if r['mercado'] == 'Menos de 2.5 goles' else None),
        axis=1
    )
    return m[m['clv_pick'].notna()].copy()


def verificar_umbral_clv_goles():
    """
    Se llama automáticamente al final de registrar_cierre_desde_proximos(),
    que ya corre a diario en el pipeline (paso 'registrar-cierre') -- no
    requiere un paso nuevo en pipeline_diario.yml. Mismo patrón idempotente
    que calcular_calibracion_prob() (Tarea #150): solo escribe un evento
    nuevo en el JSONL la primera vez que n cruza el umbral.
    """
    muestra = _muestra_clv_goles_valida()
    n = len(muestra)
    cruzado = n >= CLV_GOLES_MIN_N

    ya_notificado = False
    if os.path.exists(CLV_GOLES_HISTORIAL_JSONL):
        with open(CLV_GOLES_HISTORIAL_JSONL, encoding='utf-8') as f:
            lineas = [l for l in f if l.strip()]
        if lineas:
            ya_notificado = json.loads(lineas[-1]).get('cruzado', False)

    if cruzado and not ya_notificado:
        registro = {
            'generado_en': datetime.now(PERU_TZ).isoformat(),
            'n_clv_goles': n, 'umbral': CLV_GOLES_MIN_N, 'cruzado': True,
        }
        os.makedirs(os.path.dirname(CLV_GOLES_HISTORIAL_JSONL), exist_ok=True)
        with open(CLV_GOLES_HISTORIAL_JSONL, 'a', encoding='utf-8') as f:
            f.write(json.dumps(registro, ensure_ascii=False) + '\n')
        print(f'🎯 UMBRAL CLV DE GOLES CRUZADO: n={n} >= {CLV_GOLES_MIN_N} -- Tarea #152 lista para arrancar')
    return n, cruzado

HISTORIAL_PATH = os.path.join(RAIZ, 'Data', 'historial_picks.csv')

# Mercados 'Más de <línea> <etiqueta>' -- fase 2 (córners/tiros/tiros al
# arco/tarjetas/faltas). El orden importa: 'tiros al arco' debe probarse
# ANTES que 'tiros' (si no, 'tiros al arco' matchearía el patrón de 'tiros'
# con la etiqueta completa colgando del número). Ver generador_picks_ligas.py
# líneas 148-187 para el texto exacto que genera cada mercado -- siempre
# 'Más de', nunca 'Menos de', para estos 5 mercados.
_MERCADOS_STATS_LINEA = [
    ('córners',        'corners_l_real',            'corners_v_real'),
    ('tiros al arco',  'shots_on_target_l_real',     'shots_on_target_v_real'),
    ('tiros',          'shots_l_real',               'shots_v_real'),
    ('tarjetas',       'cards_l_real',               'cards_v_real'),
    ('faltas',         'fouls_l_real',                'fouls_v_real'),
]

def _evaluar_mercado(mercado, local, visitante, res):
    """
    Evalúa un mercado (texto tal como lo genera generador_picks_ligas.py)
    contra la fila de resultado real correspondiente. Devuelve 'Ganado',
    'Perdido', o None si el mercado no se puede evaluar (resultado aún no
    sincronizado, o -- para córners/tiros/tarjetas/faltas -- el partido no
    trajo esas stats completas en TheStatsAPI, ver extraer_stats_overview()
    en descargar_partidos.py y sincronizar_resultados() en este archivo).
    """
    m = mercado.strip()
    resultado_real = res.get('resultado_real', '')
    if m == f'Victoria {local}':
        return 'Ganado' if resultado_real == '1' else 'Perdido'
    if m == f'Victoria {visitante}':
        return 'Ganado' if resultado_real == '2' else 'Perdido'
    if m == 'Empate':
        return 'Ganado' if resultado_real == 'X' else 'Perdido'
    if m == 'Más de 2.5 goles':
        return 'Ganado' if bool(res.get('over_25_real')) else 'Perdido'
    if m == 'Menos de 2.5 goles':
        return 'Ganado' if not bool(res.get('over_25_real')) else 'Perdido'
    if m == 'Ambos anotan - Sí':
        return 'Ganado' if bool(res.get('btts_real')) else 'Perdido'
    if m == 'Ambos anotan - No':
        return 'Ganado' if not bool(res.get('btts_real')) else 'Perdido'
    if m.startswith('1X — '):
        return 'Ganado' if resultado_real in ('1', 'X') else 'Perdido'
    if m.startswith('X2 — '):
        return 'Ganado' if resultado_real in ('X', '2') else 'Perdido'

    for etiqueta, col_l, col_v in _MERCADOS_STATS_LINEA:
        match = re.match(rf'^Más de (\d+(?:\.\d+)?) {re.escape(etiqueta)}$', m)
        if match:
            val_l, val_v = res.get(col_l), res.get(col_v)
            if pd.isna(val_l) or pd.isna(val_v):
                return None  # partido sin esa stat en la API -- queda 'Sin datos'
            linea = float(match.group(1))
            total = float(val_l) + float(val_v)
            return 'Ganado' if total > linea else 'Perdido'

    return None  # mercado no reconocido

def liquidar_historial():
    """
    Liquida (marca Ganado/Perdido/Sin datos) las filas 'Pendiente' de
    Data/historial_picks.csv contra Data/resultados_log.csv. También
    reintenta las filas ya marcadas 'Sin datos' (córners/tarjetas/tiros/
    faltas) por si sincronizar_resultados() ya trajo esas stats en una
    corrida más reciente -- fase 2 llenó resultados_log.csv con
    corners_l_real/shots_l_real/etc. después de que estas filas quedaran
    'Sin datos' bajo la fase 1, así que hace falta reevaluarlas y no solo
    las 'Pendiente' (ver _evaluar_mercado).
    Las combinadas (es_combo=True) se liquidan evaluando cada pata por
    separado (guardadas en resultado_detalle como JSON de picks_combo):
    Ganado solo si TODAS las patas ganan, Perdido si CUALQUIERA pierde.
    Nunca quedan en 'Sin datos' (si falta una pata, se dejan 'Pendiente'
    indefinidamente), así que no necesitan el reintento.
    """
    if not os.path.exists(HISTORIAL_PATH):
        print('⚠️ Sin Data/historial_picks.csv todavía -- corré generar_web.py primero')
        return 0
    df = pd.read_csv(HISTORIAL_PATH)
    for c in ('estado', 'resultado_detalle', 'liquidado_en'):
        df[c] = df[c].astype('object')  # evita FutureWarning al asignar str sobre columnas leídas como float (todo-NaN)
    df_res = cargar_log(LOG_RESULT, COLS_RESULT)
    if len(df_res) == 0:
        print('⚠️ Sin resultados sincronizados todavía -- corré sync-resultados primero')
        return 0

    def resultado_de(fecha, local, visitante):
        mask = (df_res['fecha'] == fecha) & (df_res['local'] == local) & (df_res['visitante'] == visitante)
        m = df_res[mask]
        return m.iloc[0] if len(m) else None

    pendientes = df[df['estado'].isin(['Pendiente', 'Sin datos'])]
    liquidados = 0
    ahora = datetime.now(PERU_TZ).isoformat()

    for idx, row in pendientes.iterrows():
        if row.get('es_combo'):
            try:
                legs = json.loads(row.get('resultado_detalle') or '[]')
            except (TypeError, json.JSONDecodeError):
                legs = []
            if not legs:
                continue
            estados_legs, detalle_legs, listo = [], [], True
            for leg in legs:
                partido = leg.get('partido', '')
                if ' vs ' not in partido:
                    listo = False
                    break
                loc, vis = partido.split(' vs ', 1)
                res = resultado_de(row['fecha'], loc, vis)
                if res is None:
                    listo = False
                    break
                est = _evaluar_mercado(leg.get('mercado', ''), loc, vis, res)
                if est is None:
                    listo = False
                    break
                estados_legs.append(est)
                detalle_legs.append(f"{leg.get('mercado','')}: {est}")
            if not listo:
                continue
            df.loc[idx, 'estado'] = 'Ganado' if all(e == 'Ganado' for e in estados_legs) else 'Perdido'
            df.loc[idx, 'resultado_detalle'] = ' | '.join(detalle_legs)
            df.loc[idx, 'liquidado_en'] = ahora
            liquidados += 1
            continue

        res = resultado_de(row['fecha'], row['local'], row['visitante'])
        if res is None:
            continue
        estado = _evaluar_mercado(row['mercado'], row['local'], row['visitante'], res)
        if estado is None:
            df.loc[idx, 'estado'] = 'Sin datos'
            df.loc[idx, 'liquidado_en'] = ahora
            continue
        df.loc[idx, 'estado'] = estado
        df.loc[idx, 'resultado_detalle'] = f"{row['local']} {res['goles_l_real']}-{res['goles_v_real']} {row['visitante']}"
        df.loc[idx, 'liquidado_en'] = ahora
        liquidados += 1

    df.to_csv(HISTORIAL_PATH, index=False)
    print(f'✅ Historial: {liquidados} pick(s) liquidado(s)')
    return liquidados

def calcular_clv_resumen():
    """
    Resumen de Closing Line Value acumulado -- CLV promedio positivo y
    consistente en el tiempo es la señal estándar de la industria de que un
    modelo tiene edge real, independiente de si los resultados puntuales
    salieron a favor o en contra (varianza de corto plazo).

    18/08/2026: extendido de solo 1X2 a también Goles (Over 2.5 / Under
    2.5) -- ver clv_over25_pct/clv_under25_pct en registrar_cierre_desde_proximos.
    Además reporta el desglose 'solo Pinnacle' cuando hay columna
    bookmaker_*_cierre disponible: mezclar Pinnacle/Bet365/fallback sin
    distinguir inyecta ruido de selección de bookmaker en la métrica, así
    que el corte por fuente es el número en el que más se puede confiar
    (aunque tenga menos muestra que el agregado).
    """
    df_pred = cargar_log(LOG_PRED, COLS_PRED)

    def _resumen_mercado(nombre, col_clv, col_bookmaker=None):
        if col_clv not in df_pred:
            return None
        con_clv = df_pred.dropna(subset=[col_clv])
        if len(con_clv) == 0:
            return None
        clv_prom = float(con_clv[col_clv].mean())
        pct_positivo = float((con_clv[col_clv] > 0).mean() * 100)
        print(f'\n📈 CLV {nombre} ({len(con_clv)} picks con cierre registrado)')
        print(f'   CLV promedio: {clv_prom:+.2f}%')
        print(f'   % de picks con CLV positivo: {pct_positivo:.1f}%')
        resultado = {'n': len(con_clv), 'clv_promedio_pct': round(clv_prom, 2), 'pct_clv_positivo': round(pct_positivo, 1)}

        if col_bookmaker and col_bookmaker in con_clv:
            solo_pinnacle = con_clv[con_clv[col_bookmaker] == 'Pinnacle']
            if len(solo_pinnacle) > 0:
                clv_prom_p = float(solo_pinnacle[col_clv].mean())
                pct_pos_p = float((solo_pinnacle[col_clv] > 0).mean() * 100)
                print(f'   -- solo Pinnacle (n={len(solo_pinnacle)}): CLV promedio {clv_prom_p:+.2f}%, {pct_pos_p:.1f}% positivo')
                resultado['pinnacle'] = {
                    'n': len(solo_pinnacle),
                    'clv_promedio_pct': round(clv_prom_p, 2),
                    'pct_clv_positivo': round(pct_pos_p, 1),
                }
        return resultado

    out = {}
    r_1x2 = _resumen_mercado('1X2', 'clv_1x2_pct', 'bookmaker_1x2_cierre')
    if r_1x2:
        out['1X2'] = r_1x2
    r_over = _resumen_mercado('GOLES (Over 2.5)', 'clv_over25_pct', 'bookmaker_ou25_cierre')
    if r_over:
        out['Over25'] = r_over
    r_under = _resumen_mercado('GOLES (Under 2.5)', 'clv_under25_pct', 'bookmaker_ou25_cierre')
    if r_under:
        out['Under25'] = r_under

    if not out:
        print('⚠️ Sin datos de CLV todavía -- corré registrar-cierre unos días')
    return out

def auto_registrar_predicciones(fecha=None):
    """
    Registra automáticamente las predicciones del día en el log
    Se llama desde el generador después de generar picks
    """
    from datetime import datetime, timedelta
    from modelo_prediccion import predecir_jornada, normalizar_nombre

    if fecha is None:
        fecha = datetime.now(PERU_TZ).strftime('%Y-%m-%d')

    fecha_fin = (datetime.strptime(fecha, '%Y-%m-%d') + timedelta(days=2)).strftime('%Y-%m-%d')

    try:
        df_prox = pd.read_csv(os.path.join(RAIZ, 'Data', 'partidos', 'proximos.csv'))
    except:
        return

    predicciones = predecir_jornada(fecha)
    predicciones = [p for p in predicciones if fecha <= p.get('fecha', '') <= fecha_fin]

    registradas = 0
    for pred in predicciones:
        # Buscar cuotas
        mask = (
            (df_prox['local'].apply(normalizar_nombre) == normalizar_nombre(pred['local'])) &
            (df_prox['visitante'].apply(normalizar_nombre) == normalizar_nombre(pred['visitante']))
        )
        cuotas = {}
        if mask.any():
            row = df_prox[mask].iloc[0]
            cuotas = {
                'c1': row.get('c1', 0), 'cx': row.get('cx', 0), 'c2': row.get('c2', 0),
                'over_2.5': row.get('over_2.5', 0), 'under_2.5': row.get('under_2.5', 0),
            }

        if registrar_prediccion(pred, cuotas):
            registradas += 1

    print(f'✅ {registradas} predicciones nuevas registradas en el log')

def mostrar_resumen():
    """Muestra resumen del log actual"""
    df_pred = cargar_log(LOG_PRED, COLS_PRED)
    df_res  = cargar_log(LOG_RESULT, COLS_RESULT)

    print(f'\n📋 RESUMEN DEL LOG')
    print(f'  Predicciones registradas: {len(df_pred)}')
    print(f'  Resultados registrados:   {len(df_res)}')

    if len(df_pred) > 0:
        print(f'\n  Por liga:')
        for liga, grupo in df_pred.groupby('liga'):
            nombre = LIGAS.get(liga, {}).get('nombre', liga)
            print(f'    {nombre}: {len(grupo)} predicciones')

    if len(df_res) > 0:
        print(f'\n  Últimos resultados:')
        for _, r in df_res.tail(5).iterrows():
            print(f'    {r["fecha"]} {r["local"]} {r["goles_l_real"]}-{r["goles_v_real"]} {r["visitante"]}')

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == 'registrar':
            auto_registrar_predicciones()
        elif cmd == 'sync-resultados':
            # python logger_predicciones.py sync-resultados [dias_atras]
            dias = int(sys.argv[2]) if len(sys.argv) >= 3 else 4
            sincronizar_resultados(dias_atras=dias)
        elif cmd == 'calibrar':
            calcular_mse()
        elif cmd == 'calibrar-prob':
            calcular_calibracion_prob()
        elif cmd == 'registrar-cierre':
            registrar_cierre_desde_proximos()
        elif cmd == 'clv-resumen':
            calcular_clv_resumen()
        elif cmd == 'verificar-clv-goles':
            verificar_umbral_clv_goles()
        elif cmd == 'liquidar-historial':
            liquidar_historial()
        elif cmd == 'resumen':
            mostrar_resumen()
        elif cmd == 'resultado':
            # python logger_predicciones.py resultado BSA "Fluminense FC" "RB Bragantino" 2 1
            if len(sys.argv) >= 7:
                registrar_resultado(
                    sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5],
                    int(sys.argv[6]), int(sys.argv[7])
                )
    else:
        auto_registrar_predicciones()
        mostrar_resumen()