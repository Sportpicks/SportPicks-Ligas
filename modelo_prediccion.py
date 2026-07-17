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
from configuracion import ZONA_PERU, NOMBRES_ES

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
    """Convierte nombre de Odds API al nombre del histórico"""
    return NOMBRES_ES.get(nombre, nombre)

def calcular_stats_equipo(df, equipo, n_partidos=8):
    """Calcula stats promedio de un equipo en sus últimos N partidos"""
    # Intentar con nombre original y normalizado
    nombre_hist = normalizar_nombre(equipo)
    
    for nom in [equipo, nombre_hist]:
        como_local = df[df['local'] == nom].tail(n_partidos)
        como_visita = df[df['visitante'] == nom].tail(n_partidos)
        if len(como_local) + len(como_visita) > 0:
            break

    goles_favor = []
    goles_contra = []

    def es_valido(val):
        try:
            if val is None or val == '': return False
            float(val)
            return True
        except: return False

    for _, p in como_local.iterrows():
        if es_valido(p['goles_l']) and es_valido(p['goles_v']):
            goles_favor.append(int(float(p['goles_l'])))
            goles_contra.append(int(float(p['goles_v'])))

    for _, p in como_visita.iterrows():
        if es_valido(p['goles_v']) and es_valido(p['goles_l']):
            goles_favor.append(int(float(p['goles_v'])))
            goles_contra.append(int(float(p['goles_l'])))

    if not goles_favor:
        # Default conservador para equipos sin historial
        return {'ataque': 1.0, 'defensa': 1.0, 'partidos': 0}

    return {
        'ataque':   round(np.mean(goles_favor), 3),
        'defensa':  round(np.mean(goles_contra), 3),
        'partidos': len(goles_favor),
        'goles_favor_prom': round(np.mean(goles_favor), 2),
        'goles_contra_prom': round(np.mean(goles_contra), 2),
    }

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

def monte_carlo_partido(xg_l, xg_v, n=10000):
    """Simula N partidos con distribución Poisson"""
    np.random.seed(42)
    goles_l = np.random.poisson(xg_l, n)
    goles_v = np.random.poisson(xg_v, n)

    p1 = round((goles_l > goles_v).mean() * 100, 1)
    px = round((goles_l == goles_v).mean() * 100, 1)
    p2 = round((goles_l < goles_v).mean() * 100, 1)

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
                     cuotas=None, fase='regular'):
    """Genera predicción completa para un partido"""
    # Calcular stats
    stats_l = calcular_stats_equipo(df_historico, local)
    stats_v = calcular_stats_equipo(df_historico, visitante)

    # Media de goles de la liga
    df_liga = df_historico[df_historico['liga'] == liga_key].copy()
    df_liga = df_liga[df_liga['goles_l'].apply(lambda x: str(x).isdigit())]
    if len(df_liga) > 10:
        media_goles = (pd.to_numeric(df_liga['goles_l'], errors='coerce').mean() +
                       pd.to_numeric(df_liga['goles_v'], errors='coerce').mean())
        media_goles = max(0.8, min(media_goles, 2.5))
    else:
        # Defaults por liga
        media_defaults = {
            'BSA': 2.50, 'MLS': 2.80, 'UCL': 2.70,
            'CLB': 2.30, 'CSU': 2.20, 'LP1': 2.10,
        }
        media_goles = media_defaults.get(liga_key, 2.50)

    # xG Dixon-Coles
    xg_l, xg_v = dixon_coles_xg(
        stats_l['ataque'], stats_l['defensa'],
        stats_v['ataque'], stats_v['defensa'],
        media_goles_liga=media_goles,
        fase=fase
    )

    # Simulación Monte Carlo
    sim = monte_carlo_partido(xg_l, xg_v)

    resultado = {
        'local': local,
        'visitante': visitante,
        'liga': liga_key,
        'xg_l': xg_l,
        'xg_v': xg_v,
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
    partidos_hoy = df_prox[df_prox['fecha'] >= fecha].sort_values('fecha').head(20)

    predicciones = []

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

        # Determinar fase
        fase = 'eliminatoria' if liga in ['UCL', 'CLB', 'CSU'] else 'regular'

        # Normalizar nombres para buscar en histórico
        local_hist = normalizar_nombre(local)
        visit_hist = normalizar_nombre(visitante)
        pred = predecir_partido(local_hist, visit_hist, df_hist, liga, cuotas, fase)
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
