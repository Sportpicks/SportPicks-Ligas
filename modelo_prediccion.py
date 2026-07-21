# -*- coding: utf-8 -*-
"""
modelo_prediccion.py
Modelo predictivo multi-liga para SportPicks-Ligas
XGBoost + Dixon-Coles + Monte Carlo 10K
"""
import os, sys, json, math, warnings
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta

warnings.filterwarnings('ignore')
RAIZ = os.path.dirname(os.path.abspath(__file__))
os.chdir(RAIZ)
sys.path.insert(0, RAIZ)
from configuracion import ZONA_PERU

PERU_TZ = timezone(timedelta(hours=ZONA_PERU))

def hoy_peru():
    return datetime.now(PERU_TZ).strftime('%Y-%m-%d')

def poisson_prob(lam, k):
    try:
        return math.exp(-lam) * lam**k / math.factorial(k)
    except:
        return 0.0

def prob_over(lam, linea):
    k_max = int(linea)
    return round((1 - sum(poisson_prob(lam, k) for k in range(k_max+1)))*100, 1)

def prob_under(lam, linea):
    return round(100 - prob_over(lam, linea), 1)

def normalizar_nombre(nombre):
    """
    TheStatsAPI es fuente unica para historico.csv y proximos.csv -- los
    nombres de equipo ya son consistentes entre ambos, no hace falta
    mapear entre fuentes distintas. Se mantiene como identidad para no
    romper los imports existentes (generador_picks_ligas.py, logger_predicciones.py).
    """
    return nombre

def calcular_stats_equipo(df, equipo, n_partidos=8, con_detalle=False):
    """
    Calcula stats promedio (bruto, sin ajustar por rival) de un equipo
    en sus últimos N partidos.
    Si con_detalle=True, además devuelve la lista partido a partido
    (rival, gol_favor, gol_contra) — la usa calcular_stats_equipo_sos()
    para el ajuste por fortaleza de rival (SoS).
    """
    como_local = df[df['local'] == equipo].tail(n_partidos)
    como_visita = df[df['visitante'] == equipo].tail(n_partidos)

    goles_favor = []
    goles_contra = []
    detalle = []

    def es_valido(val):
        try:
            if val is None or val == '': return False
            float(val)
            return True
        except: return False

    for _, p in como_local.iterrows():
        if es_valido(p['goles_l']) and es_valido(p['goles_v']):
            gf, gc = int(float(p['goles_l'])), int(float(p['goles_v']))
            goles_favor.append(gf)
            goles_contra.append(gc)
            detalle.append({'rival': p['visitante'], 'gol_favor': gf, 'gol_contra': gc})

    for _, p in como_visita.iterrows():
        if es_valido(p['goles_v']) and es_valido(p['goles_l']):
            gf, gc = int(float(p['goles_v'])), int(float(p['goles_l']))
            goles_favor.append(gf)
            goles_contra.append(gc)
            detalle.append({'rival': p['local'], 'gol_favor': gf, 'gol_contra': gc})

    if not goles_favor:
        # Default conservador para equipos sin historial
        base = {'ataque': 1.0, 'defensa': 1.0, 'partidos': 0}
        return (base, []) if con_detalle else base

    resultado = {
        'ataque':   round(np.mean(goles_favor), 3),
        'defensa':  round(np.mean(goles_contra), 3),
        'partidos': len(goles_favor),
        'goles_favor_prom': round(np.mean(goles_favor), 2),
        'goles_contra_prom': round(np.mean(goles_contra), 2),
    }
    return (resultado, detalle) if con_detalle else resultado

# Clamp del factor de ajuste SoS — evita sobreajuste cuando el rival
# tiene pocos partidos (muestra chica → defensa/ataque bruto ruidoso).
# Calibrado por retrodicción (backtest_sos.py, n=770 partidos, historico.csv):
# con 0.60-1.60 el modelo empeoraba en las 3 métricas (brier/mse/acierto 1X2).
# Con 0.85-1.18 mejora brier (-0.001) y acierto 1X2 (+0.78pp), MSE goles
# prácticamente plano (+0.005, dentro del ruido de muestra).
SOS_FACTOR_MIN = 0.85
SOS_FACTOR_MAX = 1.18

# Peso del prior (en "partidos virtuales" a la media de liga) para el
# shrinkage bayesiano de ataque/defensa. Corrige el caso de equipos con
# muestra muy chica en historico.csv (típicamente clubes de ligas no
# cubiertas por las 15 curadas, que solo aparecen por 2-6 eliminatorias
# europeas) cuyo promedio bruto no es estadísticamente confiable.
# Calibrado por retrodicción (backtest_sos.py, n=1274 partidos, barrido
# k=3/6/10/15/20/30): brier y acierto 1X2 mejoran hasta ~k=10-15 y luego
# empiezan a revertir (demasiado shrinkage aplana señal real); MSE de
# goles sigue mejorando monótonamente con k más alto pero a costa de
# aciertos. k=10 combinado con SoS (0.85-1.18) vs modelo actual sin
# ninguno de los dos: Brier -0.0086, MSE goles -0.2339, acierto 1X2 +3.77pp.
SHRINKAGE_K = 10

def aplicar_shrinkage(stats, media_liga, k=None):
    """
    Regresión bayesiana de ataque/defensa hacia la media de liga, ponderada
    por el tamaño de muestra: un equipo con pocos partidos (n chico frente
    a k) pesa poco su propio promedio bruto y queda cerca de la media de
    liga; uno con muestra robusta (n >> k) queda casi intacto.
    No modifica equipos sin historial (ya son neutros por defecto).
    k=None resuelve a SHRINKAGE_K en tiempo de llamada (no de definición),
    para que los backtests puedan barrer distintos valores de k en caliente.
    """
    if k is None:
        k = SHRINKAGE_K
    n = stats.get('partidos', 0)
    if n == 0:
        return stats
    peso_dato = n / (n + k)
    nuevo = dict(stats)
    nuevo['ataque']  = round(stats['ataque']  * peso_dato + media_liga * (1 - peso_dato), 3)
    nuevo['defensa'] = round(stats['defensa'] * peso_dato + media_liga * (1 - peso_dato), 3)
    return nuevo

def calcular_stats_equipo_sos(df, equipo, media_liga, n_partidos=8, cache=None):
    """
    Ataque/defensa ajustados por Strength of Schedule — una sola pasada
    (sin iterar hasta convergencia, a propósito: con ligas nuevas que
    todavía no tienen muchos partidos históricos, iterar tipo Massey/Colley
    arriesga sobreajuste; una pasada es más estable y suficiente mejora
    sobre el promedio plano).

    Para cada partido del equipo, pondera el gol marcado/recibido por la
    fuerza bruta (sin ajustar) del rival de ese partido, relativa a la
    media de goles de la liga:
      - Rival con defensa débil (concede mucho) → descuenta el gol marcado
        (anotarle a una defensa floja es menos meritorio).
      - Rival con ataque débil (anota poco) → penaliza más el gol recibido
        (que te haga un gol un equipo que casi no anota es peor señal
        defensiva que recibirlo de un equipo goleador).

    cache: dict opcional {equipo: stats_bruto} para memoizar entre llamadas
    dentro de la misma jornada y no recalcular el mismo rival varias veces.
    """
    if cache is None:
        cache = {}

    def raw(nombre):
        if nombre not in cache:
            cache[nombre] = calcular_stats_equipo(df, nombre, n_partidos)
        return cache[nombre]

    stats_bruto, detalle = calcular_stats_equipo(df, equipo, n_partidos, con_detalle=True)
    cache[equipo] = stats_bruto  # evita recalcular si este equipo aparece como rival de otro

    if not detalle:
        return stats_bruto  # sin historial — usar default neutro tal cual

    goles_favor_adj = []
    goles_contra_adj = []

    for d in detalle:
        rival_bruto = raw(d['rival'])
        tiene_historial = rival_bruto.get('partidos', 0) > 0
        # Shrinkage sobre el rival ANTES de usarlo como referencia: si el
        # rival tiene muestra chica (ej. 2 partidos de una eliminatoria
        # europea), su ataque/defensa bruto no debe tratarse como un hecho
        # — se regresa hacia la media de liga antes de derivar el factor.
        rival_stats = aplicar_shrinkage(rival_bruto, media_liga) if tiene_historial else rival_bruto
        defensa_rival = rival_stats['defensa'] if tiene_historial else media_liga
        ataque_rival  = rival_stats['ataque']  if tiene_historial else media_liga

        factor_def = media_liga / max(defensa_rival, 0.30)
        factor_atq = media_liga / max(ataque_rival, 0.30)
        factor_def = min(max(factor_def, SOS_FACTOR_MIN), SOS_FACTOR_MAX)
        factor_atq = min(max(factor_atq, SOS_FACTOR_MIN), SOS_FACTOR_MAX)

        goles_favor_adj.append(d['gol_favor'] * factor_def)
        goles_contra_adj.append(d['gol_contra'] * factor_atq)

    stats_sos = {
        'ataque':   round(float(np.mean(goles_favor_adj)), 3),
        'defensa':  round(float(np.mean(goles_contra_adj)), 3),
        'partidos': stats_bruto['partidos'],
        'goles_favor_prom': stats_bruto.get('goles_favor_prom'),
        'goles_contra_prom': stats_bruto.get('goles_contra_prom'),
        'ataque_bruto': stats_bruto['ataque'],
        'defensa_bruto': stats_bruto['defensa'],
    }
    # Shrinkage final sobre el propio equipo: aunque ya se ajustó por rival,
    # si SU PROPIA muestra es chica (ej. Sturm Graz con 2 partidos europeos)
    # el promedio sigue sin ser confiable — se regresa hacia la media de liga.
    stats_final = aplicar_shrinkage(stats_sos, media_liga)
    stats_final['ataque_sin_shrink'] = stats_sos['ataque']
    stats_final['defensa_sin_shrink'] = stats_sos['defensa']
    return stats_final

def dixon_coles_xg(ataque_l, defensa_l, ataque_v, defensa_v,
                    media_goles_liga=1.35, factor_local=1.10, fase='regular'):
    """
    Calcula xG esperado usando Dixon-Coles corregido
    - ataque/defensa ya están en escala de goles reales por partido
    - Formula: xG_l = (atq_l/media) * (def_v/media) * media * factor_local
    - factor_local: ventaja de jugar en casa
    - fase: 'regular', 'playoffs', 'eliminatoria'
    """
    # Factor de ajuste por fase
    factor_fase = {
        'regular':      1.00,
        'playoffs':     0.90,
        'eliminatoria': 0.85,
        'grupos':       0.95,
    }.get(fase, 1.00)

    # Fórmula correcta Dixon-Coles normalizada por media de liga
    m = max(media_goles_liga, 0.80)
    xg_l = (ataque_l / m) * (defensa_v / m) * m * factor_local * factor_fase
    xg_v = (ataque_v / m) * (defensa_l / m) * m / factor_local * factor_fase

    # Límites razonables
    xg_l = max(0.30, min(xg_l, 3.00))
    xg_v = max(0.20, min(xg_v, 2.80))

    return round(xg_l, 3), round(xg_v, 3)

def monte_carlo_partido(xg_l, xg_v, n=10000, shrinkage=0.10):
    """
    Simula N partidos con distribución Poisson
    shrinkage: reduce sobreconfianza — empuja probs hacia 33% (baseline)
    Calibrado con retrodicción: modelo sobreestima en rango 50-70%
    """
    np.random.seed(42)
    goles_l = np.random.poisson(xg_l, n)
    goles_v = np.random.poisson(xg_v, n)

    p1_raw = (goles_l > goles_v).mean()
    px_raw = (goles_l == goles_v).mean()
    p2_raw = (goles_l < goles_v).mean()

    # Shrinkage hacia baseline (33%) para corregir sobreconfianza
    baseline = 1/3
    p1 = round((p1_raw * (1 - shrinkage) + baseline * shrinkage) * 100, 1)
    px = round((px_raw * (1 - shrinkage) + baseline * shrinkage) * 100, 1)
    p2 = round((p2_raw * (1 - shrinkage) + baseline * shrinkage) * 100, 1)

    totales = goles_l + goles_v
    over15 = round((totales > 1.5).mean() * 100, 1)
    over25 = round((totales > 2.5).mean() * 100, 1)
    over35 = round((totales > 3.5).mean() * 100, 1)
    under25 = round(100 - over25, 1)

    btts = round(((goles_l > 0) & (goles_v > 0)).mean() * 100, 1)

    # Marcador más probable
    from collections import Counter
    marcadores = Counter(zip(goles_l.tolist(), goles_v.tolist()))
    marcador_top = marcadores.most_common(3)

    return {
        'p1': p1, 'px': px, 'p2': p2,
        'over_1.5': over15, 'over_2.5': over25, 'over_3.5': over35,
        'under_2.5': under25, 'btts_si': btts, 'btts_no': round(100-btts, 1),
        'marcador_prob': [{'marcador': f'{m[0]}-{m[1]}', 'prob': round(c/n*100, 1)}
                          for m, c in marcador_top],
    }

def predecir_partido(local, visitante, df_historico, liga_key,
                     cuotas=None, fase='regular', cache_sos=None):
    """Genera predicción completa para un partido"""
    # Media de goles de la liga (promedio por EQUIPO, no total del partido)
    # Medias por liga — representan goles promedio POR EQUIPO
    # NO modificar para calibrar — usar factor_escala en dixon_coles_xg
    # Claves = competition_id de TheStatsAPI. Ligas sin calibracion propia
    # caen al default de .get() (1.25) -- las 9 ligas nuevas del set de
    # 15 (ARG/COL/CAF/DAN/NOR/MXA/ECU/SCO/UCO) todavia no tienen
    # retrodiccion historica, asi que usan ese valor neutro a proposito.
    media_defaults = {
        'comp_4795': 1.25,  # BSA
        'comp_9799': 1.40,  # MLS
        'comp_3498': 1.35,  # UCL
        'comp_0499': 1.15,  # CLB
        'comp_1615': 1.10,  # CSU
        'comp_6981': 1.05,  # LP1
    }
    # Factor de escala por liga — calibrado con retrodicción histórica.
    # Corrige subestimación sin afectar la distribución 1X2.
    # BSA sesgo -0.079 → +6%, MLS sesgo -0.107 → +8%, CLB sesgo -0.336 → +20%
    # Ligas sin calibracion propia caen al default de .get() (1.0, neutro).
    factor_escala_liga = {
        'comp_4795': 1.06,  # BSA
        'comp_9799': 1.08,  # MLS
        'comp_3498': 1.05,  # UCL
        'comp_0499': 1.20,  # CLB
        'comp_1615': 1.15,  # CSU
        'comp_6981': 1.10,  # LP1
    }
    df_liga = df_historico[df_historico['liga'] == liga_key].copy()
    try:
        gl = pd.to_numeric(df_liga['goles_l'], errors='coerce').dropna()
        gv = pd.to_numeric(df_liga['goles_v'], errors='coerce').dropna()
        if len(gl) > 20:
            media_goles = round((gl.mean() + gv.mean()) / 2, 3)
            media_goles = max(0.70, min(media_goles, 1.80))
        else:
            media_goles = media_defaults.get(liga_key, 1.25)
    except:
        media_goles = media_defaults.get(liga_key, 1.25)

    # Calcular stats — ataque/defensa ajustados por Strength of Schedule
    # (necesita media_goles ya calculada como referencia de fortaleza de rival)
    stats_l = calcular_stats_equipo_sos(df_historico, local, media_goles, cache=cache_sos)
    stats_v = calcular_stats_equipo_sos(df_historico, visitante, media_goles, cache=cache_sos)

    # xG Dixon-Coles
    xg_l, xg_v = dixon_coles_xg(
        stats_l['ataque'], stats_l['defensa'],
        stats_v['ataque'], stats_v['defensa'],
        media_goles_liga=media_goles,
        fase=fase
    )
    # Aplicar factor de escala por liga para corregir subestimación de goles
    # Se aplica DESPUÉS de calcular probs 1X2 para no afectar calibración
    escala = factor_escala_liga.get(liga_key, 1.0)
    xg_l_scaled = round(xg_l * escala, 3)
    xg_v_scaled = round(xg_v * escala, 3)

    # Simulación Monte Carlo — usar xG original para probs 1X2
    sim = monte_carlo_partido(xg_l, xg_v)
    # Recalcular Over/Under y BTTS con xG escalado (más preciso para goles)
    sim_scaled = monte_carlo_partido(xg_l_scaled, xg_v_scaled)
    sim['over_1.5']  = sim_scaled['over_1.5']
    sim['over_2.5']  = sim_scaled['over_2.5']
    sim['over_3.5']  = sim_scaled['over_3.5']
    sim['under_2.5'] = sim_scaled['under_2.5']
    sim['btts_si']   = sim_scaled['btts_si']
    sim['btts_no']   = sim_scaled['btts_no']

    resultado = {
        'local': local,
        'visitante': visitante,
        'liga': liga_key,
        'xg_l': xg_l_scaled,
        'xg_v': xg_v_scaled,
        'fase': fase,
        **sim,
        'stats_l': stats_l,
        'stats_v': stats_v,
    }

    # Agregar EV si hay cuotas
    if cuotas:
        resultado['ev_1'] = round((sim['p1']/100) - (1/cuotas['c1']), 3) if cuotas.get('c1', 0) > 0 else 0
        resultado['ev_x'] = round((sim['px']/100) - (1/cuotas['cx']), 3) if cuotas.get('cx', 0) > 0 else 0
        resultado['ev_2'] = round((sim['p2']/100) - (1/cuotas['c2']), 3) if cuotas.get('c2', 0) > 0 else 0

        if cuotas.get('over_2.5', 0) > 0:
            resultado['ev_over25'] = round((sim['over_2.5']/100) - (1/cuotas['over_2.5']), 3)
        if cuotas.get('under_2.5', 0) > 0:
            resultado['ev_under25'] = round((sim['under_2.5']/100) - (1/cuotas['under_2.5']), 3)

    return resultado

def predecir_jornada(fecha=None):
    """Predice todos los partidos próximos disponibles"""
    if fecha is None:
        fecha = hoy_peru()

    print(f'\n{"="*60}')
    print(f'  PREDICCIONES — {fecha}')
    print(f'{"="*60}')

    # Cargar datos
    try:
        df_hist = pd.read_csv('Data/partidos/historico.csv')
        df_prox = pd.read_csv('Data/partidos/proximos.csv')
    except FileNotFoundError:
        print('❌ Ejecuta primero: python descargar_partidos.py')
        return []

    # Filtrar partidos del día
    partidos_hoy = df_prox[df_prox['fecha'] >= fecha].sort_values('fecha').head(100)

    predicciones = []
    cache_sos = {}  # memoiza stats brutas por equipo durante toda la jornada (SoS)

    for _, p in partidos_hoy.iterrows():
        local = p['local']
        visitante = p['visitante']
        liga = p['liga']

        cuotas = {
            'c1': p.get('c1', 0),
            'cx': p.get('cx', 0),
            'c2': p.get('c2', 0),
            'over_2.5': p.get('over_2.5', 0),
            'under_2.5': p.get('under_2.5', 0),
        }

        # Determinar fase (mismo criterio que antes, con los IDs nuevos:
        # UCL=comp_3498, CLB=comp_0499, CSU=comp_1615)
        fase = 'eliminatoria' if liga in ('comp_3498', 'comp_0499', 'comp_1615') else 'regular'

        # Normalizar nombres para buscar en histórico
        local_hist = normalizar_nombre(local)
        visit_hist = normalizar_nombre(visitante)
        pred = predecir_partido(local_hist, visit_hist, df_hist, liga, cuotas, fase, cache_sos=cache_sos)
        pred['local'] = local
        pred['visitante'] = visitante
        pred['fecha'] = p['fecha']
        pred['hora'] = p.get('hora_peru', '')
        pred['liga_nombre'] = p.get('liga_nombre', liga)
        predicciones.append(pred)

        print(f'\n  {p.get("liga_nombre", liga)} — {p["fecha"]} {p.get("hora_peru","")}')
        print(f'  {local} vs {visitante}')
        print(f'  xG: {pred["xg_l"]:.2f} - {pred["xg_v"]:.2f}')
        print(f'  Probs: {pred["p1"]}% - {pred["px"]}% - {pred["p2"]}%')
        print(f'  Over 2.5: {pred["over_2.5"]}% | BTTS: {pred["btts_si"]}%')
        if cuotas.get('c1', 0) > 0:
            print(f'  Cuotas: @{cuotas["c1"]} | @{cuotas["cx"]} | @{cuotas["c2"]}')
            if 'ev_1' in pred:
                print(f'  EV: {pred["ev_1"]:+.2f} | {pred["ev_x"]:+.2f} | {pred["ev_2"]:+.2f}')

    # Guardar predicciones
    os.makedirs('Predicciones', exist_ok=True)
    with open('Predicciones/predicciones_hoy.json', 'w', encoding='utf-8') as f:
        json.dump(predicciones, f, ensure_ascii=False, indent=2)
    print(f'\n✅ {len(predicciones)} predicciones guardadas')

    return predicciones

if __name__ == '__main__':
    predecir_jornada()
