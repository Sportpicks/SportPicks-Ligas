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
PROB_MIN_PUBLICO  = 60   # %
PROB_MIN_PREMIUM  = 75   # %
CUOTA_MIN_PUBLICO = 1.50
CUOTA_MIN_PREMIUM = 1.60
MAX_PICKS_PUBLICO = 3
