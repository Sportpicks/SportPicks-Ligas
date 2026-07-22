# -*- coding: utf-8 -*-
"""
check_red_cards.py
Diagnostico de una sola vez para la tarea #22 (tarjetas rojas como
covariable): confirma si TheStatsAPI expone el campo 'red_cards' bajo
'overview' en /matches/{id}/stats, igual que expone 'yellow_cards',
'fouls', etc. No se puede verificar desde el sandbox de Cowork (sin
salida a internet hacia la API real) -- correr esto en tu maquina.

Uso:
    python check_red_cards.py
"""
import sys
sys.path.insert(0, '.')
from configuracion import API_THESTATS, LIGAS
from thestats_client import TheStatsClient, TheStatsAPIError
from datetime import datetime, timedelta

def main():
    client = TheStatsClient(API_THESTATS)
    hoy = datetime.now().date()
    hace_10 = (hoy - timedelta(days=10)).isoformat()

    encontrados = 0
    revisados = 0

    for liga_id, cfg in LIGAS.items():
        if not cfg.get('has_team_stats'):
            continue
        try:
            partidos = client.get_matches(
                liga_id, status='finished',
                date_from=hace_10, date_to=hoy.isoformat(),
            )
        except TheStatsAPIError as e:
            print(f'  ⚠️ {cfg["nombre"]}: {e}')
            continue

        for m in partidos[:3]:  # con 2-3 partidos por liga alcanza para confirmar
            revisados += 1
            try:
                stats = client.get_match_stats(m['id'])
            except TheStatsAPIError as e:
                print(f'    ⚠️ stats {m["id"]}: {e}')
                continue
            ov = (stats or {}).get('overview') or {}
            local = m['home_team']['name']
            visitante = m['away_team']['name']
            if 'red_cards' in ov:
                rc = ov['red_cards']
                print(f'  ✅ {cfg["nombre"]}: {local} vs {visitante} -- red_cards presente: {rc}')
                encontrados += 1
            else:
                claves = list(ov.keys())
                print(f'  ❌ {cfg["nombre"]}: {local} vs {visitante} -- sin red_cards. Claves disponibles: {claves}')

        if revisados >= 15:  # no gastar de mas la cuota de la API, con esto alcanza
            break

    print(f'\n📊 Resumen: {encontrados}/{revisados} partidos con campo red_cards presente.')
    if encontrados == 0:
        print('   → TheStatsAPI NO expone tarjetas rojas. Cerrar tarea #22 como no viable con esta fuente.')
    else:
        print('   → Campo confirmado. Se puede avanzar con la tarea #22 (ver nota de diseño abajo).')

if __name__ == '__main__':
    main()
