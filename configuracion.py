# -*- coding: utf-8 -*-
"""
configuracion.py
Configuración central de SportPicks-Ligas
"""
import os
import csv

RAIZ = os.path.dirname(os.path.abspath(__file__))

# ── APIs ──
API_THESTATS = 'fapi_xsedmwUExuZrMwSQnNXUS790890Bxbvp'

# ── Ligas prioritarias ──
# Set curado de 15 ligas para SportPicks-Ligas (reemplaza el listado
# dinamico de las 149 competiciones de Data/thestats_ligas.csv). Clave:
# codigo corto interno; 'id' es el competition_id real de TheStatsAPI.
THESTATS_LIGAS_PRIORITARIAS = {
    'ARG': {'id': 'comp_4540',   'nombre': 'Liga Profesional Argentina', 'emoji': '🇦🇷'},
    'BSA': {'id': 'comp_4795',   'nombre': 'Brasileirão Série A',        'emoji': '🇧🇷'},
    'COL': {'id': 'comp_720692', 'nombre': 'Primera A Colombia',         'emoji': '🇨🇴'},
    'CAF': {'id': 'comp_08478',  'nombre': 'CAF Champions League',       'emoji': '🌍'},
    'CLB': {'id': 'comp_0499',   'nombre': 'CONMEBOL Libertadores',      'emoji': '🏆'},
    'CSU': {'id': 'comp_1615',   'nombre': 'CONMEBOL Sudamericana',      'emoji': '🏆'},
    'DAN': {'id': 'comp_7938',   'nombre': 'Danish Superliga',           'emoji': '🇩🇰'},
    'NOR': {'id': 'comp_1992',   'nombre': 'Eliteserien',                'emoji': '🇳🇴'},
    'LP1': {'id': 'comp_6981',   'nombre': 'Liga 1 Perú',                'emoji': '🇵🇪'},
    'MXA': {'id': 'comp_298265', 'nombre': 'Liga MX Apertura',           'emoji': '🇲🇽'},
    'ECU': {'id': 'comp_1917',   'nombre': 'LigaPro Serie A Ecuador',    'emoji': '🇪🇨'},
    'SCO': {'id': 'comp_6387',   'nombre': 'Scottish Premiership',       'emoji': '🏴󠁧󠁢󠁳󠁣󠁴󠁿'},
    'UCL': {'id': 'comp_3498',   'nombre': 'UEFA Champions League',      'emoji': '⭐'},
    'UEL': {'id': 'comp_7739',   'nombre': 'UEFA Europa League',         'emoji': '🥈'},
    'UCO': {'id': 'comp_408698', 'nombre': 'UEFA Conference League',     'emoji': '🇪🇺'},
    'MLS': {'id': 'comp_9799',   'nombre': 'MLS',                       'emoji': '🇺🇸'},
}

# LIGAS: clave = competition_id de TheStatsAPI (p.ej. 'comp_9799'), para
# que coincida con el valor 'liga' que descargar_partidos.py escribe en
# historico.csv/proximos.csv. Cada entrada agrega 'codigo' (el codigo
# corto de arriba, para mostrar en la web/logs) y las capacidades de la
# competicion (has_team_stats/odds_available/xg_available/...) leidas de
# Data/thestats_ligas.csv, si el archivo existe.
def _cargar_capacidades():
    ruta = os.path.join(RAIZ, 'Data', 'thestats_ligas.csv')
    capacidades = {}
    if not os.path.exists(ruta):
        return capacidades
    with open(ruta, encoding='utf-8') as f:
        for row in csv.DictReader(f):
            capacidades[row['id']] = row
    return capacidades

def _bool(v):
    return str(v).strip().lower() == 'true'

def _construir_ligas():
    capacidades = _cargar_capacidades()
    ligas = {}
    for codigo, info in THESTATS_LIGAS_PRIORITARIAS.items():
        comp_id = info['id']
        fila = capacidades.get(comp_id, {})
        ligas[comp_id] = {
            'codigo':              codigo,
            'nombre':              info['nombre'],
            'emoji':               info['emoji'],
            'pais':                fila.get('country') or None,
            'confederacion':       fila.get('confederation') or None,
            'tipo':                fila.get('type'),
            'has_team_stats':      _bool(fila.get('has_team_stats', 'False')),
            'has_player_stats':    _bool(fila.get('has_player_stats', 'False')),
            'xg_available':        _bool(fila.get('xg_available', 'False')),
            'odds_available':      _bool(fila.get('odds_available', 'False')),
            'live_odds_available': _bool(fila.get('live_odds_available', 'False')),
            'activa':              True,
        }
    return ligas

LIGAS = _construir_ligas()

# ── Zonas horarias ──
ZONA_PERU = -5  # UTC-5

# ── Reglas de picks ──
# PROB_MIN_PUBLICO/PROB_MIN_PREMIUM rebajados (10/08/2026, junto con la
# calibración de probabilidad -- ver logger_predicciones.calcular_calibracion_prob
# y generador_picks_ligas._calibrar_prob): la auditoría de modelo del
# 10/08/2026 encontró que el modelo estaba sobreconfiado 10-17pp en el
# rango 60-75%, y con la corrección aplicada el techo real de probabilidad
# calibrada quedó en ~68% (nunca 90% como mostraba antes). Dejar estos
# pisos en 60/75 sobre la escala calibrada habría dejado el sitio casi sin
# picks públicos/premium la mayoría de los días (backtest contra 741 picks
# históricos: de 158 candidatos que pasaban el piso viejo, solo 5 hubieran
# pasado el mismo piso sobre la prob calibrada). Los valores nuevos son
# _calibrar_prob(60)=55.4 y _calibrar_prob(75)=63.4 redondeados -- mismo
# criterio de selectividad que antes, expresado en la escala honesta.
PROB_MIN_PUBLICO  = 55   # %
PROB_MIN_PREMIUM  = 63   # %
CUOTA_MIN_PUBLICO = 1.50
CUOTA_MIN_PREMIUM = 1.60
MAX_PICKS_PUBLICO = 3

# Piso mínimo de EV -- antes el filtro era solo "ev > 0", que deja pasar
# EVs de +0.1-0.8% indistinguibles del propio ruido del pipeline: la
# simulación Monte Carlo (n=10000) tiene un error estándar de ~0.5pp en la
# probabilidad estimada (sqrt(p(1-p)/n)), que se traslada 1:1 al EV; sumale
# la aproximación de SoS/shrinkage y el margen (vig) típico de un
# bookmaker líquido (2-5%), y un EV por debajo de este piso no es una
# ventaja real explotable, es ruido de modelo. Premium más exigente por
# ser el producto de pago.
EV_MIN_PUBLICO  = 0.03   # 3%
EV_MIN_PREMIUM  = 0.05   # 5%

# Categorías de mercado descartadas -- auditoría de calibración del
# 31/07/2026 (410 picks liquidados, vs. los 180 de la auditoría anterior):
# '1X2' rindió 44.9% de acierto real (n=49) y 'Tiros' 40.9% (n=22), ambos
# muy por debajo del promedio general (54.4%) y de los mercados de Goles
# (57.1%, n=282) y Córners (57.1%, n=35), que sí sostienen su calibración
# con muestra grande. Mismo criterio que tarjetas rojas (descartado antes
# por costo/beneficio): en vez de mantener mercados con acierto real por
# debajo de la media mientras se investiga la causa, se descartan por
# completo del panel público y como patas de combinadas premium. Revisar
# cuando acumulen más muestra o se identifique y corrija la causa de la
# sobreconfianza del modelo en estos dos mercados.
CATEGORIAS_EXCLUIDAS = {'1X2', 'Tiros'}

# Techo máximo de EV -- auditoría de modelo del 25/07/2026 (180 picks
# liquidados, segunda vuelta tras la primera del 24/07 con 125): el bucket
# de EV 20-30% dio 26.7% de acierto real (15 picks) y el de 30%+ dio 22.2%
# (9 picks) -- ambos muy por debajo del promedio general (~51.7%), y el
# patrón se sostuvo IGUAL de mal entre las dos auditorías con muestras
# crecientes (13→15 y 7→9 picks respectivamente), lo cual ya descarta que
# sea ruido de muestra chica. Un EV informado por encima de este techo no
# es evidencia de una ventaja real explotable -- es la misma señal que
# motivó el fix de la fórmula de EV del 24/07: cuanto más diverge el
# modelo del mercado, más probable es que sea un error de calibración del
# modelo (equipos con poco historial, ligas de sample pequeño) que una
# ineficiencia real del bookmaker. Picks con EV por encima de este techo
# se descartan en vez de publicarse -- ver seleccionar_picks() y
# seleccionar_premium() en generador_picks_ligas.py.
EV_MAX_PUBLICO  = 0.20   # 20%
EV_MAX_PREMIUM  = 0.20   # 20%
