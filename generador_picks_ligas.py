# -*- coding: utf-8 -*-
"""
generador_picks_ligas.py
Generador de picks multi-liga para SportPicks-Ligas
"""
import os, sys, json, math
import pandas as pd
from datetime import datetime, timezone, timedelta

RAIZ = os.path.dirname(os.path.abspath(__file__))
os.chdir(RAIZ)
sys.path.insert(0, RAIZ)
from configuracion import (ZONA_PERU, CUOTA_MIN_PUBLICO, CUOTA_MIN_PREMIUM,
                            PROB_MIN_PUBLICO, PROB_MIN_PREMIUM, MAX_PICKS_PUBLICO)
from modelo_prediccion import predecir_jornada, normalizar_nombre

PERU_TZ = timezone(timedelta(hours=ZONA_PERU))

def hoy_peru():
    return datetime.now(PERU_TZ).strftime('%Y-%m-%d')

def generar_candidatos(pred, cuotas):
    """Genera lista de picks candidatos para un partido"""
    candidatos = []
    local = pred['local']
    visitante = pred['visitante']
    partido = f"{local} vs {visitante}"

    def add(mercado, prob, cuota, emoji, categoria, descripcion):
        if cuota < 1.30 or prob < 50:
            return
        ev = round((prob/100) - (1/cuota), 3)
        candidatos.append({
            'partido': partido,
            'local': local,
            'visitante': visitante,
            'liga': pred.get('liga', ''),
            'liga_nombre': pred.get('liga_nombre', ''),
            'fecha': pred.get('fecha', ''),
            'hora': pred.get('hora', ''),
            'mercado': mercado,
            'prob': prob,
            'cuota': cuota,
            'cuota_display': cuota,
            'ev': ev,
            'emoji': emoji,
            'categoria': categoria,
            'descripcion': descripcion,
            'fuente': 'real' if cuota > 0 else 'estimada',
            'tipo': 'individual',
            'estado': 'Pendiente',
            'ganancia': 0,
            'stake': 0,
        })

    # ── Goles ──
    if cuotas.get('c1', 0) > 1.30:
        add(f'Victoria {local}', pred['p1'], cuotas['c1'], '⚽', '1X2',
            f'xG {pred["xg_l"]:.2f} — modelo {pred["p1"]}%')
    if cuotas.get('cx', 0) > 1.30:
        add('Empate', pred['px'], cuotas['cx'], '🤝', '1X2',
            f'xG total {pred["xg_l"]+pred["xg_v"]:.2f}')
    if cuotas.get('c2', 0) > 1.30:
        add(f'Victoria {visitante}', pred['p2'], cuotas['c2'], '⚽', '1X2',
            f'xG {pred["xg_v"]:.2f} — modelo {pred["p2"]}%')
    if cuotas.get('over_2.5', 0) > 1.30:
        add('Más de 2.5 goles', pred['over_2.5'], cuotas['over_2.5'], '🥅', 'Goles',
            f'xG total {pred["xg_l"]+pred["xg_v"]:.2f}')
    if cuotas.get('under_2.5', 0) > 1.30:
        add('Menos de 2.5 goles', pred['under_2.5'], cuotas['under_2.5'], '🔒', 'Goles',
            f'xG total {pred["xg_l"]+pred["xg_v"]:.2f}')

    # ── BTTS ──
    btts_si = pred.get('btts_si', 0)
    btts_no = pred.get('btts_no', 0)
    # Estimar cuotas BTTS si no están disponibles
    if btts_si > 0:
        cuota_btts_si = cuotas.get('btts_si', round(100/btts_si, 2) if btts_si > 0 else 0)
        cuota_btts_no = cuotas.get('btts_no', round(100/btts_no, 2) if btts_no > 0 else 0)
        if cuota_btts_si > 1.30:
            add('Ambos anotan - Sí', btts_si, cuota_btts_si, '⚽', 'Goles',
                f'Prob BTTS: {btts_si}%')
        if cuota_btts_no > 1.30 and btts_no > 45:
            add('Ambos anotan - No', btts_no, cuota_btts_no, '🔒', 'Goles',
                f'Prob BTTS No: {btts_no}%')

    # ── Doble oportunidad ──
    p1x = round(pred['p1'] + pred['px'], 1)
    px2 = round(pred['px'] + pred['p2'], 1)
    cuota_1x = round(1/(p1x/100) * 0.90, 2) if p1x > 0 else 0
    cuota_x2 = round(1/(px2/100) * 0.90, 2) if px2 > 0 else 0
    if cuota_1x > 1.30 and p1x > 60:
        add(f'1X — {local} o Empate', p1x, cuota_1x, '🛡️', 'Doble Op.',
            f'Sin derrota {local}: {p1x}%')
    if cuota_x2 > 1.30 and px2 > 60:
        add(f'X2 — Empate o {visitante}', px2, cuota_x2, '🛡️', 'Doble Op.',
            f'Sin derrota {visitante}: {px2}%')

    return candidatos

def seleccionar_picks(todos, max_publico=3):
    """Selecciona picks públicos y premium"""
    # Filtrar por EV positivo y prob mínima
    validos = [pk for pk in todos
               if pk['prob'] >= PROB_MIN_PUBLICO
               and pk['cuota'] >= CUOTA_MIN_PUBLICO
               and pk['ev'] > 0]

    # Ordenar por EV
    validos.sort(key=lambda x: (x['prob'], x['ev']), reverse=True)

    # PREMIUM PRIMERO — seleccionar antes que el público
    premium = seleccionar_premium(todos, [])
    mercados_premium = set(pk['mercado'] for pk in premium)
    partidos_premium = set(pk['partido'].split(' + ')[0] for pk in premium)

    # Panel público — max 3, diversidad, excluir mercados del premium
    publicos = []
    partidos_usados = {}
    categorias_usadas = {}

    for pk in validos:
        if len(publicos) >= max_publico:
            break
        partido = pk['partido']
        cat = pk['categoria']

        # No usar el mercado exacto del premium
        if pk['mercado'] in mercados_premium:
            continue
        # Max 1 pick por partido
        if partidos_usados.get(partido, 0) >= 1:
            continue
        # Max 2 picks de misma categoría
        if categorias_usadas.get(cat, 0) >= 2:
            continue
        # No duplicar mercado
        if pk['mercado'] in [p['mercado'] for p in publicos]:
            continue

        publicos.append(pk)
        partidos_usados[partido] = partidos_usados.get(partido, 0) + 1
        categorias_usadas[cat] = categorias_usadas.get(cat, 0) + 1

    return publicos, premium

def seleccionar_premium(todos, mercados_excluidos):
    """Busca la mejor combinada para el premium"""
    # Picks con prob alta y cuota baja — candidatos para combinada
    candidatos = sorted(
        [pk for pk in todos
         if pk['prob'] >= 60
         and 1.20 <= pk['cuota'] <= 2.00
         and pk['mercado'] not in mercados_excluidos
         and pk['ev'] > -0.05],  # solo picks con valor razonable
        key=lambda x: x['prob'], reverse=True
    )

    # Buscar mejor combinada del mismo partido
    mejor = None
    mejor_prob = 0

    partidos = list(dict.fromkeys(pk['partido'] for pk in candidatos))
    for partido in partidos:
        pks = [pk for pk in candidatos if pk['partido'] == partido]
        for i, pk1 in enumerate(pks):
            for pk2 in pks[i+1:]:
                m1 = pk1['mercado'].lower()
                m2 = pk2['mercado'].lower()
                # Evitar contradictorios y correlacionados
                if ('más de' in m1 and 'menos de' in m2) or ('menos de' in m1 and 'más de' in m2):
                    continue
                if m1 == m2:
                    continue
                # Evitar picks muy correlacionados
                if 'menos de 2.5' in m1 and 'ambos anotan - no' in m2:
                    continue
                if 'menos de 2.5' in m2 and 'ambos anotan - no' in m1:
                    continue
                if 'más de 2.5' in m1 and 'ambos anotan - sí' in m2:
                    continue
                if 'más de 2.5' in m2 and 'ambos anotan - sí' in m1:
                    continue
                cuota_combo = round(pk1['cuota'] * pk2['cuota'], 2)
                if cuota_combo < CUOTA_MIN_PREMIUM:
                    continue
                prob_combo = round(pk1['prob'] * pk2['prob'] / 100, 1)
                # Solo combinar si la prob combinada es >= 52%
                if prob_combo < 40:
                    continue
                if prob_combo > mejor_prob:
                    mejor_prob = prob_combo
                    mejor = {
                        'partido': partido,
                        'local': pk1['local'],
                        'visitante': pk1['visitante'],
                        'liga': pk1['liga'],
                        'liga_nombre': pk1['liga_nombre'],
                        'fecha': pk1['fecha'],
                        'hora': pk1['hora'],
                        'mercado': f"Combinada: {pk1['mercado']} + {pk2['mercado']}",
                        'prob': prob_combo,
                        'cuota': cuota_combo,
                        'cuota_display': cuota_combo,
                        'ev': round((prob_combo/100) * cuota_combo - 1, 3),
                        'emoji': '🎯',
                        'categoria': 'Combinada',
                        'descripcion': f"{pk1['mercado']} ({pk1['prob']:.0f}%) × {pk2['mercado']} ({pk2['prob']:.0f}%)",
                        'fuente': 'real',
                        'tipo': 'premium',
                        'estado': 'Pendiente',
                        'ganancia': 0,
                        'stake': 0,
                        'picks_combo': [
                            {'mercado': pk1['mercado'], 'cuota': pk1['cuota']},
                            {'mercado': pk2['mercado'], 'cuota': pk2['cuota']},
                        ]
                    }

    # Paso 2: si no hay combinada del mismo partido, buscar combinada multi-partido
    if not mejor:
        pks_multi = [pk for pk in candidatos if pk['mercado'] not in mercados_excluidos]
        for i, pk1 in enumerate(pks_multi):
            for pk2 in pks_multi[i+1:]:
                if pk1['partido'] == pk2['partido']:
                    continue  # ya probamos mismo partido arriba
                m1 = pk1['mercado'].lower()
                m2 = pk2['mercado'].lower()
                cuota_combo = round(pk1['cuota'] * pk2['cuota'], 2)
                if cuota_combo < CUOTA_MIN_PREMIUM:
                    continue
                prob_combo = round(pk1['prob'] * pk2['prob'] / 100, 1)
                if prob_combo < 40:
                    continue
                if prob_combo > mejor_prob:
                    mejor_prob = prob_combo
                    mejor = {
                        'partido': f"{pk1['partido']} + {pk2['partido']}",
                        'local': pk1['local'],
                        'visitante': pk1['visitante'],
                        'liga': pk1['liga'],
                        'liga_nombre': 'Multi-liga',
                        'fecha': pk1['fecha'],
                        'hora': pk1['hora'],
                        'mercado': f"Combinada: {pk1['mercado']} ({pk1['partido'].split(' vs ')[0]}) + {pk2['mercado']} ({pk2['partido'].split(' vs ')[0]})",
                        'prob': prob_combo,
                        'cuota': cuota_combo,
                        'cuota_display': cuota_combo,
                        'ev': round((prob_combo/100) * cuota_combo - 1, 3),
                        'emoji': '🎯',
                        'categoria': 'Combinada',
                        'descripcion': f"{pk1['mercado']} @{pk1['cuota']} × {pk2['mercado']} @{pk2['cuota']}",
                        'fuente': 'real',
                        'tipo': 'premium',
                        'estado': 'Pendiente',
                        'ganancia': 0,
                        'stake': 0,
                        'picks_combo': [
                            {'partido': pk1['partido'], 'mercado': pk1['mercado'], 'cuota': pk1['cuota']},
                            {'partido': pk2['partido'], 'mercado': pk2['mercado'], 'cuota': pk2['cuota']},
                        ]
                    }

    # Paso 3: pick individual premium — cualquier pick con buena prob y cuota >= 1.60
    if not mejor:
        for pk in sorted(todos, key=lambda x: (x['prob'], x['ev']), reverse=True):
            if (pk['prob'] >= 65
                and pk['cuota'] >= CUOTA_MIN_PREMIUM
                and pk['mercado'] not in mercados_excluidos):
                pk['tipo'] = 'premium'
                return [pk]
        # Último recurso — mejor pick disponible con cuota >= 1.50
        for pk in sorted(todos, key=lambda x: x['prob'], reverse=True):
            if (pk['prob'] >= 62
                and pk['cuota'] >= 1.50
                and pk['mercado'] not in mercados_excluidos):
                pk['tipo'] = 'premium'
                return [pk]

    return [mejor] if mejor else []

def main(fecha=None, dias=2):
    if fecha is None:
        fecha = hoy_peru()

    print(f'\n{"="*60}')
    print(f'  GENERADOR DE PICKS — SportPicks Ligas')
    print(f'  Fecha: {fecha}')
    print(f'{"="*60}')

    # Obtener predicciones solo para hoy y mañana
    from datetime import datetime, timedelta
    fecha_dt = datetime.strptime(fecha, '%Y-%m-%d')
    fecha_fin = (fecha_dt + timedelta(days=dias)).strftime('%Y-%m-%d')
    print(f'  Rango: {fecha} → {fecha_fin}')

    # Obtener predicciones
    predicciones = predecir_jornada(fecha)
    # Filtrar solo partidos en el rango
    predicciones = [p for p in predicciones
                   if fecha <= p.get('fecha', '') <= fecha_fin]
    print(f'  Partidos en rango: {len(predicciones)}')

    if not predicciones:
        print('❌ Sin predicciones disponibles')
        return

    # Cargar cuotas de proximos.csv
    try:
        df_prox = pd.read_csv('Data/partidos/proximos.csv')
        df_prox_hoy = df_prox[df_prox['fecha'] >= fecha]
    except:
        df_prox_hoy = pd.DataFrame()

    # Generar candidatos por partido
    todos = []
    for pred in predicciones:
        # Buscar cuotas del partido
        local_norm = normalizar_nombre(pred['local'])
        visit_norm = normalizar_nombre(pred['visitante'])

        cuotas = {
            'c1': pred.get('c1', 0),
            'cx': pred.get('cx', 0),
            'c2': pred.get('c2', 0),
            'over_2.5': pred.get('over_2.5', 0),
            'under_2.5': pred.get('under_2.5', 0),
        }

        # Buscar en df_prox si hay cuotas
        if not df_prox_hoy.empty:
            mask = ((df_prox_hoy['local'].apply(normalizar_nombre) == local_norm) &
                    (df_prox_hoy['visitante'].apply(normalizar_nombre) == visit_norm))
            if mask.any():
                row = df_prox_hoy[mask].iloc[0]
                cuotas = {
                    'c1': row.get('c1', 0),
                    'cx': row.get('cx', 0),
                    'c2': row.get('c2', 0),
                    'over_2.5': row.get('over_2.5', 0),
                    'under_2.5': row.get('under_2.5', 0),
                }

        candidatos = generar_candidatos(pred, cuotas)
        todos.extend(candidatos)

    print(f'\n✅ Total candidatos: {len(todos)}')

    # Seleccionar picks
    publicos, premium = seleccionar_picks(todos)

    # Mostrar panel
    print(f'\n📋 PANEL PÚBLICO ({len(publicos)} picks):')
    for i, pk in enumerate(publicos, 1):
        liga_emoji = {'BSA':'🇧🇷','MLS':'🇺🇸','CSU':'🏆','CLB':'🏆','UCL':'🇪🇺','LP1':'🇵🇪'}.get(pk['liga'],'⚽')
        print(f'   #{i} {liga_emoji} [{pk["categoria"]}] {pk["mercado"]}')
        print(f'      {pk["partido"]} | {pk["prob"]:.1f}% | @{pk["cuota"]:.2f} EV:{pk["ev"]:+.1%}')

    print(f'\n💎 PANEL PREMIUM ({len(premium)} picks):')
    for pk in premium:
        print(f'   #1 {pk["emoji"]} {pk["mercado"]}')
        print(f'      {pk["partido"]} | {pk["prob"]:.1f}% | @{pk["cuota"]:.2f}')

    # Guardar picks del día
    picks_data = {
        'fecha': fecha,
        'generado': datetime.now(PERU_TZ).isoformat(),
        'publicos': publicos,
        'premium': premium,
        'todos_candidatos': todos,
    }
    os.makedirs('Data', exist_ok=True)
    with open('Data/picks_hoy.json', 'w', encoding='utf-8') as f:
        json.dump(picks_data, f, ensure_ascii=False, indent=2, default=str)
    print(f'\n✅ Picks guardados en Data/picks_hoy.json')

if __name__ == '__main__':
    main()
