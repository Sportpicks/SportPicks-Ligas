# -*- coding: utf-8 -*-
"""
descargar_thestats_ligas.py
Lista todas las competiciones disponibles en TheStatsAPI (paginando hasta
la ultima pagina) y las guarda en Data/thestats_ligas.csv
"""
import os, sys, time, csv
import requests

RAIZ = os.path.dirname(os.path.abspath(__file__))
os.chdir(RAIZ)
sys.path.insert(0, RAIZ)
from configuracion import API_THESTATS

BASE_URL = 'https://api.thestatsapi.com/api/football/competitions'
COLUMNAS = [
    'id', 'name', 'country', 'confederation', 'type',
    'has_team_stats', 'has_player_stats', 'xg_available',
    'odds_available', 'live_odds_available',
]

def obtener_todas_competiciones():
    headers = {'Authorization': f'Bearer {API_THESTATS}'}
    competiciones = []
    page = 1
    total_pages = None

    while True:
        r = requests.get(BASE_URL, headers=headers, params={'page': page}, timeout=15)
        r.raise_for_status()
        body = r.json()

        datos = body.get('data', [])
        competiciones.extend(datos)

        meta = body.get('meta', {})
        total_pages = meta.get('total_pages', page)
        print(f'  Pagina {page}/{total_pages}: {len(datos)} competiciones')

        if page >= total_pages:
            break
        page += 1
        time.sleep(0.5)

    return competiciones

def main():
    print('\n' + '='*60)
    print('  THESTATSAPI — Listado de competiciones')
    print('='*60)

    competiciones = obtener_todas_competiciones()

    os.makedirs('Data', exist_ok=True)
    ruta = 'Data/thestats_ligas.csv'
    with open(ruta, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNAS)
        writer.writeheader()
        for c in competiciones:
            writer.writerow({col: c.get(col) for col in COLUMNAS})

    print(f'\n✅ {len(competiciones)} competiciones → {ruta}')

if __name__ == '__main__':
    main()
