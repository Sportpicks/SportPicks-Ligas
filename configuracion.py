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

# ── Nombres en español / normalización ──
# Clave: nombre de la Odds API → valor: nombre del histórico (football-data.org)
NOMBRES_ES = {
    # Champions League
    'Real Madrid': 'Real Madrid', 'Barcelona': 'FC Barcelona',
    'Manchester City': 'Manchester City FC', 'Arsenal': 'Arsenal FC',
    'Bayern Munich': 'FC Bayern München', 'Borussia Dortmund': 'Borussia Dortmund',
    'Paris Saint-Germain FC': 'Paris Saint-Germain FC',
    'Juventus': 'Juventus FC', 'Inter Milan': 'FC Internazionale Milano',
    'AC Milan': 'AC Milan', 'Liverpool FC': 'Liverpool FC',
    'Chelsea FC': 'Chelsea FC', 'Atletico Madrid': 'Club Atlético de Madrid',

    # Brasileirao — Odds API → football-data.org
    'Flamengo':          'CR Flamengo',
    'Fluminense':        'Fluminense FC',
    'Botafogo':          'Botafogo FR',
    'Palmeiras':         'SE Palmeiras',
    'Corinthians':       'SC Corinthians Paulista',
    'Sao Paulo':         'São Paulo FC',
    'Internacional':     'SC Internacional',
    'Grêmio':            'Grêmio FBPA',
    'Atletico Mineiro':  'CA Mineiro',
    'Bragantino-SP':     'RB Bragantino',
    'Cruzeiro':          'Cruzeiro EC',
    'Bahia':             'EC Bahia',
    'Vitoria':           'EC Vitória',
    'Mirassol':          'Mirassol FC',
    'Atletico Paranaense': 'Club Athletico Paranaense',
    'Chapecoense':       'Chapecoense',
    'Coritiba':          'Coritiba FC',
    'Remo':              'Clube do Remo',

    # Copa Libertadores / Sudamericana — Odds API → football-data.org
    'River Plate':                'CA River Plate',
    'Boca Juniors':               'CA Boca Juniors',
    'Racing Club':                'Racing Club',
    'Estudiantes':                'Estudiantes de La Plata',
    'Estudiantes La Plata':       'Estudiantes de La Plata',
    'Nacional':                   'Club Nacional',
    'Club Nacional':              'Club Nacional',
    'Nacional de Montevideo':     'Club Nacional de Football',
    'CA Tigre':                   'CA Tigre',
    'CA Tigre BA':                'CA Tigre',
    'Santos FC':                  'Santos FC',
    'Santos':                     'Santos FC',
    'Universidad César Vallejo':  'Club Universitario de Deportes',
    'UCV FC':                     'Club Universitario de Deportes',
    'Flamengo-RJ':                'CR Flamengo',
    'Fluminense-RJ':              'Fluminense FC',
    'Corinthians-SP':             'SC Corinthians Paulista',
    'Palmeiras-SP':               'SE Palmeiras',
    'LDU Quito':                  'LDU de Quito',
    'Independiente del Valle':    'CAR Independiente del Valle',
    'Deportes Tolima':            'CD Tolima',
    'Sporting Cristal':           'CS Cristal',
    'Cerro Porteño':              'Club Cerro Porteño',
    'Platense':                   'Club Platense',
    'Vasco da Gama':              'CR Vasco da Gama',
    'Independiente Medellín':     'CDC Atlético Nacional',
    'Boca Juniors':               'CA Boca Juniors',
    "O'Higgins":                 "CD O'Higgins",
    'Lanus':                      'CA Lanus',
    'Rosario Central':            'CA Rosario Central',
    'Coquimbo Unido':             'CD Coquimbo Unido',
    'Independiente Rivadavia':    'Independiente Rivadavia',
    'Universidad Católica (CHI)': 'CD Universidad Católica',
    'Caracas FC':                 'Carabobo FC',
    'Club Cienciano':             'Club Cienciano',
    'Grêmio':                     'Grêmio FBPA',
    # CSU adicionales
    'Atletico Mineiro':           'CA Mineiro',
    'Flamengo':                   'CR Flamengo',
    'Internacional':              'SC Internacional',
    'Sao Paulo':                  'São Paulo FC',
    'Vasco':                      'CR Vasco da Gama',

    # MLS — Odds API → API-Football (histórico)
    'LA Galaxy':                  'Los Angeles Galaxy',
    'Los Angeles FC':             'Los Angeles FC',
    'LAFC':                       'Los Angeles FC',
    'Seattle Sounders FC':        'Seattle Sounders',
    'Portland Timbers':           'Portland Timbers',
    'Atlanta United FC':          'Atlanta United FC',
    'Nashville SC':               'Nashville SC',
    'Columbus Crew SC':           'Columbus Crew',
    'New York City FC':           'New York City FC',
    'New England Revolution':     'New England Revolution',
    'Charlotte FC':               'Charlotte',
    'CF Montréal':                'CF Montreal',
    'CF Montreal':                'CF Montreal',
    'Toronto FC':                 'Toronto FC',
    'Chicago Fire FC':            'Chicago Fire',
    'Chicago Fire':               'Chicago Fire',
    'Vancouver Whitecaps FC':     'Vancouver Whitecaps',
    'St. Louis City SC':          'St. Louis City',
    'Sporting Kansas City':       'Sporting Kansas City',
    'Inter Miami CF':             'Inter Miami',
    'Inter Miami':                'Inter Miami',
    'Austin FC':                  'Austin',
    'D.C. United':                'DC United',
    'DC United':                  'DC United',
    'FC Cincinnati':              'FC Cincinnati',
    'FC Dallas':                  'FC Dallas',
    'Houston Dynamo':             'Houston Dynamo',
    'Minnesota United FC':        'Minnesota United FC',
    'Colorado Rapids':            'Colorado Rapids',
    'Real Salt Lake':             'Real Salt Lake',
    'San Jose Earthquakes':       'San Jose Earthquakes',
    'New York Red Bulls':         'New York Red Bulls',
    'Orlando City SC':            'Orlando City SC',
    'Philadelphia Union':         'Philadelphia Union',

    # Liga 1 Perú
    'Alianza Lima':      'Alianza Lima',
    'Universitario':     'Universitario de Deportes',
    'Sporting Cristal':  'Sporting Cristal',
    'Melgar':            'FBC Melgar',
    'Cienciano':         'Cienciano',
    'Cesar Vallejo':     'Universidad César Vallejo',
}

# Mapa inverso: histórico → normalizado (para buscar stats)
NOMBRES_HIST = {v: v for v in NOMBRES_ES.values()}
NOMBRES_HIST.update({v: k for k, v in NOMBRES_ES.items()})

# ── Zonas horarias ──
ZONA_PERU = -5  # UTC-5

# ── Reglas de picks ──
PROB_MIN_PUBLICO  = 60   # %
PROB_MIN_PREMIUM  = 75   # %
CUOTA_MIN_PUBLICO = 1.50
CUOTA_MIN_PREMIUM = 1.60
MAX_PICKS_PUBLICO = 3
