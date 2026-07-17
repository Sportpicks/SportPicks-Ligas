# -*- coding: utf-8 -*-
"""
descargar_partidos.py
Descarga partidos y resultados de todas las ligas activas
via football-data.org y The Odds API
"""
import os, sys, json, requests, time
from datetime import datetime, timezone, timedelta
import pandas as pd

RAIZ = os.path.dirname(os.path.abspath(__file__))
os.chdir(RAIZ)
sys.path.insert(0, RAIZ)
from configuracion import API_FOOTBALL_DATA, API_ODDS, LIGAS, NOMBRES_ES, ZONA_PERU

PERU_TZ = timezone(timedelta(hours=ZONA_PERU))

def hoy_peru():
    return datetime.now(PERU_TZ).strftime('%Y-%m-%d')

def nombre_es(nombre_en):
    return NOMBRES_ES.get(nombre_en, nombre_en)

def descargar_fd(liga_key, liga_cfg, temporada='2025'):
    """Descarga partidos de football-data.org"""
    fd_id = liga_cfg.get('fd_id')
    if not fd_id:
        return []

    partidos = []
    try:
        r = requests.get(
            f'https://api.football-data.org/v4/competitions/{fd_id}/matches',
            headers={'X-Auth-Token': API_FOOTBALL_DATA},
            params={'season': temporada},
            timeout=15
        )
        if r.status_code != 200:
            print(f'    ⚠️ FD {liga_cfg["nombre"]}: {r.status_code}')
            return []

        for m in r.json().get('matches', []):
            fecha = m['utcDate'][:10]
            # Convertir hora UTC a Perú
            dt_utc = datetime.fromisoformat(m['utcDate'].replace('Z','+00:00'))
            dt_peru = dt_utc.astimezone(PERU_TZ)
            hora_peru = dt_peru.strftime('%H:%M')

            local_en = m['homeTeam']['name']
            visit_en = m['awayTeam']['name']
            score = m.get('score', {})
            ft = score.get('fullTime', {})
            gl = ft.get('home')
            gv = ft.get('away')

            partidos.append({
                'liga':      liga_key,
                'liga_nombre': liga_cfg['nombre'],
                'fecha':     fecha,
                'hora_peru': hora_peru,
                'local':     nombre_es(local_en),
                'visitante': nombre_es(visit_en),
                'goles_l':   gl if gl is not None else '',
                'goles_v':   gv if gv is not None else '',
                'resultado': f'{gl}-{gv}' if gl is not None else '',
                'estado':    m.get('status', 'SCHEDULED'),
                'jornada':   m.get('matchday', ''),
                'fase':      m.get('stage', ''),
                'fuente':    'football-data',
            })

        print(f'    ✅ {liga_cfg["nombre"]}: {len(partidos)} partidos')

    except Exception as e:
        print(f'    ❌ Error FD {liga_cfg["nombre"]}: {e}')

    return partidos

def descargar_odds_partidos(liga_key, liga_cfg):
    """Descarga partidos próximos con cuotas de The Odds API"""
    odds_key = liga_cfg.get('odds_key')
    if not odds_key:
        return []

    partidos = []
    try:
        r = requests.get(
            f'https://api.the-odds-api.com/v4/sports/{odds_key}/odds/',
            params={
                'apiKey': API_ODDS,
                'regions': 'eu',
                'markets': 'h2h,totals',
                'oddsFormat': 'decimal',
            },
            timeout=15
        )
        if r.status_code != 200:
            print(f'    ⚠️ Odds {liga_cfg["nombre"]}: {r.status_code}')
            return []

        for p in r.json():
            fecha_utc = p['commence_time'][:10]
            dt_utc = datetime.fromisoformat(p['commence_time'].replace('Z','+00:00'))
            dt_peru = dt_utc.astimezone(PERU_TZ)
            hora_peru = dt_peru.strftime('%H:%M')
            fecha_peru = dt_peru.strftime('%Y-%m-%d')

            local_en = p['home_team']
            visit_en = p['away_team']

            # Cuotas promedio
            c1s, cxs, c2s = [], [], []
            over25s, under25s = [], []
            for bk in p.get('bookmakers', []):
                for mkt in bk.get('markets', []):
                    if mkt['key'] == 'h2h':
                        outs = {o['name']: o['price'] for o in mkt['outcomes']}
                        if local_en in outs:  c1s.append(outs[local_en])
                        if 'Draw' in outs:    cxs.append(outs['Draw'])
                        if visit_en in outs:  c2s.append(outs[visit_en])
                    elif mkt['key'] == 'totals':
                        for o in mkt['outcomes']:
                            if o.get('point') == 2.5:
                                if o['name'] == 'Over':  over25s.append(o['price'])
                                else: under25s.append(o['price'])

            partidos.append({
                'liga':        liga_key,
                'liga_nombre': liga_cfg['nombre'],
                'fecha':       fecha_peru,
                'hora_peru':   hora_peru,
                'local':       nombre_es(local_en),
                'visitante':   nombre_es(visit_en),
                'goles_l':     '',
                'goles_v':     '',
                'resultado':   '',
                'estado':      'SCHEDULED',
                'c1':          round(sum(c1s)/len(c1s), 2) if c1s else 0,
                'cx':          round(sum(cxs)/len(cxs), 2) if cxs else 0,
                'c2':          round(sum(c2s)/len(c2s), 2) if c2s else 0,
                'over_2.5':    round(sum(over25s)/len(over25s), 2) if over25s else 0,
                'under_2.5':   round(sum(under25s)/len(under25s), 2) if under25s else 0,
                'fuente':      'odds-api',
            })

        print(f'    ✅ Odds {liga_cfg["nombre"]}: {len(partidos)} partidos próximos')

    except Exception as e:
        print(f'    ❌ Error Odds {liga_cfg["nombre"]}: {e}')

    return partidos

def main():
    print('\n' + '='*60)
    print('  DESCARGA DE PARTIDOS — SportPicks Ligas')
    print('='*60)
    print(f'  Fecha Perú: {hoy_peru()}')

    todos_partidos = []
    partidos_con_cuotas = []

    for key, cfg in LIGAS.items():
        if not cfg['activa']:
            continue
        print(f'\n  {cfg["emoji"]} {cfg["nombre"]}:')

        # Descargar de football-data.org
        if cfg.get('fd_id'):
            pts = descargar_fd(key, cfg, '2025')
            todos_partidos.extend(pts)
            time.sleep(0.5)

        # Descargar cuotas de Odds API
        if cfg.get('odds_key'):
            pts_odds = descargar_odds_partidos(key, cfg)
            partidos_con_cuotas.extend(pts_odds)
            time.sleep(0.3)

    # Guardar partidos históricos
    if todos_partidos:
        df = pd.DataFrame(todos_partidos)
        os.makedirs('Data/partidos', exist_ok=True)
        df.to_csv('Data/partidos/historico.csv', index=False)
        print(f'\n✅ Histórico: {len(df)} partidos → Data/partidos/historico.csv')

    # Guardar próximos con cuotas
    if partidos_con_cuotas:
        df_odds = pd.DataFrame(partidos_con_cuotas)
        df_odds.to_csv('Data/partidos/proximos.csv', index=False)
        print(f'✅ Próximos: {len(df_odds)} partidos → Data/partidos/proximos.csv')

        print(f'\n📅 PRÓXIMOS PARTIDOS:')
        hoy = hoy_peru()
        proximos = df_odds[df_odds['fecha'] >= hoy].sort_values('fecha').head(15)
        for _, p in proximos.iterrows():
            print(f'  {p["fecha"]} {p["hora_peru"]} | {p["liga"]:3} | {p["local"]} vs {p["visitante"]}')
            if p.get('c1', 0) > 0:
                print(f'         Cuotas: {p["local"]} @{p["c1"]} | X @{p["cx"]} | {p["visitante"]} @{p["c2"]}')

    print('\n' + '='*60)

if __name__ == '__main__':
    main()
