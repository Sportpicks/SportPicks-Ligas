# -*- coding: utf-8 -*-
"""
configuracion.py
Configuración central de SportPicks-Ligas
"""

# ── APIs ──
API_FOOTBALL_DATA = 'cce6c60e411047abb142e005de2d957a'
API_ODDS          = '622b4b772a4d155e032de1c17a83e41a'

# ── Ligas configuradas ──
LIGAS = {
    'UCL': {
        'nombre':    'UEFA Champions League',
        'emoji':     '🇪🇺',
        'fd_id':     2001,
        'odds_key':  'soccer_uefa_champions_league',
        'activa':    True,
    },
    'CSU': {
        'nombre':    'Copa Sudamericana',
        'emoji':     '🏆',
        'fd_id':     None,
        'odds_key':  'soccer_conmebol_copa_sudamericana',
        'activa':    True,
    },
    'CLB': {
        'nombre':    'Copa Libertadores',
        'emoji':     '🏆',
        'fd_id':     2152,
        'odds_key':  'soccer_conmebol_copa_libertadores',
        'activa':    True,
    },
    'BSA': {
        'nombre':    'Brasileirao Serie A',
        'emoji':     '🇧🇷',
        'fd_id':     2013,
        'odds_key':  'soccer_brazil_campeonato',
        'activa':    True,
    },
    'MLS': {
        'nombre':    'MLS Major League Soccer',
        'emoji':     '🇺🇸',
        'fd_id':     None,
        'odds_key':  'soccer_usa_mls',
        'activa':    True,
    },
    'LP1': {
        'nombre':    'Liga 1 Clausura Peru',
        'emoji':     '🇵🇪',
        'fd_id':     None,
        'odds_key':  'soccer_peru_primera_division',
        'activa':    True,
    },
}

# ── Nombres en español ──
NOMBRES_ES = {
    # Champions
    'Real Madrid': 'Real Madrid', 'Barcelona': 'Barcelona',
    'Manchester City': 'Manchester City', 'Arsenal': 'Arsenal',
    'Bayern Munich': 'Bayern Múnich', 'Borussia Dortmund': 'Dortmund',
    'Paris Saint-Germain FC': 'PSG', 'Juventus': 'Juventus',
    'Inter Milan': 'Inter', 'AC Milan': 'AC Milan',
    'Liverpool FC': 'Liverpool', 'Chelsea FC': 'Chelsea',
    'Atletico Madrid': 'Atlético Madrid', 'Sevilla FC': 'Sevilla',
    # Copa Lib / Sud
    'Flamengo': 'Flamengo', 'River Plate': 'River Plate',
    'Boca Juniors': 'Boca Juniors', 'Palmeiras': 'Palmeiras',
    'Fluminense': 'Fluminense', 'São Paulo': 'São Paulo',
    # MLS
    'LA Galaxy': 'LA Galaxy', 'LAFC': 'LAFC',
    'Atlanta United': 'Atlanta United', 'Seattle Sounders': 'Seattle Sounders',
    # Liga 1
    'Alianza Lima': 'Alianza Lima', 'Universitario': 'Universitario',
    'Sporting Cristal': 'Sporting Cristal', 'Melgar': 'Melgar',
}

# ── Zonas horarias ──
ZONA_PERU = -5  # UTC-5

# ── Reglas de picks ──
PROB_MIN_PUBLICO  = 60   # %
PROB_MIN_PREMIUM  = 75   # %
CUOTA_MIN_PUBLICO = 1.50
CUOTA_MIN_PREMIUM = 1.60
MAX_PICKS_PUBLICO = 3
