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
                            PROB_MIN_PUBLICO, PROB_MIN_PREMIUM, MAX_PICKS_PUBLICO, LIGAS)
from modelo_prediccion import predecir_jornada, normalizar_nombre

PERU_TZ = timezone(timedelta(hours=ZONA_PERU))

def hoy_peru():
    return datetime.now(PERU_TZ).strftime('%Y-%m-%d')

# Divergencia máxima (en puntos porcentuales) entre la prob. del modelo y
# la prob. implícita en las cuotas reales (sin vig) antes de descartar un
# candidato. Caso real que motivó esto: equipos con 0 partidos en
# historico.csv (ej. FC Thun, GNK Dinamo Zagreb) heredan el default neutro
# (ataque=defensa=1.0) y el modelo puede terminar 45pp desalineado del
# mercado — el shrinkage bayesiano no corrige esto porque no hay dato real
# con el cual mezclar el prior cuando partidos=0. Una brecha de esa
# magnitud en un mercado líquido es evidencia de un input roto, no de una
# ineficiencia real explotable.
DIVERGENCIA_MAX_PP = 30

def _prob_mercado_devigged(cuota_pick, cuotas_grupo):
    """
    Probabilidad "justa" que implica el mercado para un mercado de N vías,
    normalizando el overround (vig) del bookmaker.
    cuotas_grupo: todas las cuotas reales del mismo mercado (ej. [c1,cx,c2]
    para 1X2, [over,under] para goles).
    Devuelve None si no hay cuotas reales suficientes para calcularlo.
    """
    validas = [c for c in cuotas_grupo if c and c > 1.0]
    if cuota_pick <= 1.0 or len(validas) < 2:
        return None
    overround = sum(1 / c for c in validas)
    if overround <= 0:
        return None
    return (1 / cuota_pick) / overround * 100

def generar_candidatos(pred, cuotas):
    """Genera lista de picks candidatos para un partido"""
    candidatos = []
    local = pred['local']
    visitante = pred['visitante']
    partido = f"{local} vs {visitante}"
    descartados_divergencia = []

    def add(mercado, prob, cuota, emoji, categoria, descripcion, cuotas_grupo=None):
        if cuota < 1.30 or prob < 50:
            return
        if cuotas_grupo:
            prob_mercado = _prob_mercado_devigged(cuota, cuotas_grupo)
            if prob_mercado is not None and abs(prob - prob_mercado) > DIVERGENCIA_MAX_PP:
                descartados_divergencia.append(
                    f'{mercado} ({partido}): modelo {prob:.1f}% vs mercado {prob_mercado:.1f}% '
                    f'(brecha {abs(prob-prob_mercado):.1f}pp)'
                )
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
    grupo_1x2 = [cuotas.get('c1', 0), cuotas.get('cx', 0), cuotas.get('c2', 0)]
    grupo_ou25 = [cuotas.get('over_2.5', 0), cuotas.get('under_2.5', 0)]

    if cuotas.get('c1', 0) > 1.30:
        add(f'Victoria {local}', pred['p1'], cuotas['c1'], '⚽', '1X2',
            f'xG {pred["xg_l"]:.2f} — modelo {pred["p1"]}%', cuotas_grupo=grupo_1x2)
    if cuotas.get('cx', 0) > 1.30:
        add('Empate', pred['px'], cuotas['cx'], '🤝', '1X2',
            f'xG total {pred["xg_l"]+pred["xg_v"]:.2f}', cuotas_grupo=grupo_1x2)
    if cuotas.get('c2', 0) > 1.30:
        add(f'Victoria {visitante}', pred['p2'], cuotas['c2'], '⚽', '1X2',
            f'xG {pred["xg_v"]:.2f} — modelo {pred["p2"]}%', cuotas_grupo=grupo_1x2)
    if cuotas.get('over_2.5', 0) > 1.30:
        add('Más de 2.5 goles', pred['over_2.5'], cuotas['over_2.5'], '🥅', 'Goles',
            f'xG total {pred["xg_l"]+pred["xg_v"]:.2f}', cuotas_grupo=grupo_ou25)
    if cuotas.get('under_2.5', 0) > 1.30:
        add('Menos de 2.5 goles', pred['under_2.5'], cuotas['under_2.5'], '🔒', 'Goles',
            f'xG total {pred["xg_l"]+pred["xg_v"]:.2f}', cuotas_grupo=grupo_ou25)

    # ── BTTS ──
    btts_si = pred.get('btts_si', 0)
    btts_no = pred.get('btts_no', 0)
    # cuotas reales de mercado (si TheStatsAPI las trajo) vs. estimadas del
    # propio modelo (100/prob) — el filtro de divergencia solo tiene sentido
    # contra una cuota REAL; comparar el modelo contra su propia estimación
    # nunca dispararía la brecha, así que solo se pasa cuotas_grupo cuando
    # el valor viene de mercado.
    btts_si_real = cuotas.get('btts_si', 0)
    btts_no_real = cuotas.get('btts_no', 0)
    grupo_btts = [btts_si_real, btts_no_real] if (btts_si_real and btts_no_real) else None
    if btts_si > 0:
        cuota_btts_si = btts_si_real or (round(100/btts_si, 2) if btts_si > 0 else 0)
        cuota_btts_no = btts_no_real or (round(100/btts_no, 2) if btts_no > 0 else 0)
        if cuota_btts_si > 1.30:
            add('Ambos anotan - Sí', btts_si, cuota_btts_si, '⚽', 'Goles',
                f'Prob BTTS: {btts_si}%', cuotas_grupo=grupo_btts)
        if cuota_btts_no > 1.30 and btts_no > 45:
            add('Ambos anotan - No', btts_no, cuota_btts_no, '🔒', 'Goles',
                f'Prob BTTS No: {btts_no}%', cuotas_grupo=grupo_btts)

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
    # NOTA: 1X/X2 usan una cuota sintética derivada del propio modelo
    # (1/prob * 0.90), no una cuota real de mercado — el filtro de
    # divergencia no aplica aquí porque compararía el modelo contra sí
    # mismo. Es una limitación conocida, distinta a la de este fix.

    for aviso in descartados_divergencia:
        print(f'  ⚠️ Descartado por divergencia vs mercado: {aviso}')

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
         and 1.20 <= pk['cuota'] <= 3.00
         and pk['mercado'] not in mercados_excluidos],
        key=lambda x: x['prob'], reverse=True
    )

    # NOTA: no se generan combinadas del mismo partido (bet builder / SGP).
    # Cualquier par de mercados del mismo partido está estadísticamente
    # correlacionado en algún grado (goles ↔ resultado, goles ↔ doble
    # oportunidad, BTTS ↔ goles...) y la lista de exclusiones puntuales que
    # había antes (over/under contradictorios, BTTS-goles) dejaba huecos —
    # el caso real detectado: "Menos de 2.5" + "X2" no estaba excluido, y la
    # cuota combinada (producto de las dos cuotas de mercado) tampoco es una
    # cotización real de ningún bookmaker, así que el EV que salía de ahí
    # era ilusorio. Regla de diseño: solo combinar mercados de PARTIDOS
    # DISTINTOS (Paso 1 abajo), que sí son estadísticamente independientes.
    mejor = None
    mejor_prob = 0

    # Paso 1: combinada multi-partido (mercados de partidos distintos —
    # independientes entre sí, sin riesgo de correlación intra-partido)
    if not mejor:
        pks_multi = [pk for pk in candidatos if pk['mercado'] not in mercados_excluidos]
        for i, pk1 in enumerate(pks_multi):
            for pk2 in pks_multi[i+1:]:
                if pk1['partido'] == pk2['partido']:
                    continue  # nunca combinar mercados del mismo partido
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

    # Paso 2: pick individual premium — cualquier pick con buena prob y cuota >= 1.60
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

def main(fecha=None, dias=3, solo_hoy=False):
    if fecha is None:
        fecha = hoy_peru()

    print(f'\n{"="*60}')
    print(f'  GENERADOR DE PICKS — SportPicks Ligas')
    print(f'  Fecha: {fecha}')
    if solo_hoy:
        print(f'  Modo: SOLO HOY (excluye partidos de otros días)')
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

    # Modo --solo-hoy: descarta candidatos de otros días antes de seleccionar
    todos_multi = todos  # conserva el pool completo de {dias} días para el fallback
    fallback_multi_dia = False

    if solo_hoy:
        todos = [pk for pk in todos if pk.get('fecha', '') == fecha]
        print(f'   Solo-hoy: {len(todos)}/{len(todos_multi)} candidatos son de {fecha}')

    # Seleccionar picks
    publicos, premium = seleccionar_picks(todos)

    # Fallback: si solo-hoy no alcanza para armar panel público, ampliar al rango de {dias} días
    if solo_hoy and len(publicos) == 0 and not premium:
        print(f'⚠️  Solo-hoy sin picks suficientes para {fecha} — fallback a rango de {dias} días')
        fallback_multi_dia = True
        todos = todos_multi
        publicos, premium = seleccionar_picks(todos)

    # Mostrar panel
    print(f'\n📋 PANEL PÚBLICO ({len(publicos)} picks):')
    for i, pk in enumerate(publicos, 1):
        liga_emoji = LIGAS.get(pk['liga'], {}).get('emoji', '⚽')
        pk_fecha = pk.get('fecha', '')
        etiqueta_fecha = f'HOY ({pk_fecha})' if pk_fecha == fecha else pk_fecha
        print(f'   #{i} {liga_emoji} [{pk["categoria"]}] {pk["mercado"]} — {etiqueta_fecha}')
        print(f'      {pk["partido"]} | {pk["prob"]:.1f}% | @{pk["cuota"]:.2f} EV:{pk["ev"]:+.1%}')

    print(f'\n💎 PANEL PREMIUM ({len(premium)} picks):')
    for pk in premium:
        pk_fecha = pk.get('fecha', '')
        etiqueta_fecha = f'HOY ({pk_fecha})' if pk_fecha == fecha else pk_fecha
        print(f'   #1 {pk["emoji"]} {pk["mercado"]} — {etiqueta_fecha}')
        print(f'      {pk["partido"]} | {pk["prob"]:.1f}% | @{pk["cuota"]:.2f}')

    # Guardar picks del día
    picks_data = {
        'fecha': fecha,
        'generado': datetime.now(PERU_TZ).isoformat(),
        'solo_hoy': solo_hoy,
        'fallback_multi_dia': fallback_multi_dia,
        'publicos': publicos,
        'premium': premium,
        'todos_candidatos': todos,
    }
    os.makedirs('Data', exist_ok=True)
    with open('Data/picks_hoy.json', 'w', encoding='utf-8') as f:
        json.dump(picks_data, f, ensure_ascii=False, indent=2, default=str)
    print(f'\n✅ Picks guardados en Data/picks_hoy.json')

if __name__ == '__main__':
    solo_hoy_flag = '--solo-hoy' in sys.argv
    main(solo_hoy=solo_hoy_flag)
