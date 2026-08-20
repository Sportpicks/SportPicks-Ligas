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
                            PROB_MIN_PUBLICO, PROB_MIN_PREMIUM, MAX_PICKS_PUBLICO, LIGAS,
                            EV_MIN_PUBLICO, EV_MIN_PREMIUM, EV_MAX_PUBLICO, EV_MAX_PREMIUM,
                            CATEGORIAS_EXCLUIDAS)
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

# Zona intermedia (20-30pp): en vez de todo-o-nada, se blendea la prob. del
# modelo con la implícita de mercado en vez de descartar directo. Debajo de
# BLEND_MIN_PP se confía 100% en el modelo (la brecha entra en el ruido
# normal de que el modelo vea algo que el mercado aún no descontó). Encima
# de DIVERGENCIA_MAX_PP se sigue descartando entero (esa magnitud es
# evidencia de input roto, no de señal real — ver nota arriba). Peso de
# mercado modesto (30%): el objetivo es amortiguar output claramente
# desalineado, no reemplazar el modelo por el mercado.
DIVERGENCIA_BLEND_MIN_PP = 20
PESO_MERCADO_EN_BLEND = 0.30

# LIGAS_BAJO_VIGILANCIA: ligas donde el modelo demostró calibración
# consistentemente mala en 3 métricas independientes (auditoría
# 10/08/2026, 761 picks liquidados) y necesitan un piso más alto antes
# de llegar a público/premium, en vez de confiar en que el filtro
# genérico (PROB_MIN_PUBLICO/EV_MIN_PUBLICO) las bloquee por accidente.
# Caso real: Brasileirão Série A (comp_4795) -- accuracy_1x2 36.4% y
# accuracy_over25 39.4% en calibracion.json (los más bajos de las 15
# ligas activas), sesgo_goles +0.63 (el más alto, ya con
# factor_correccion=0.773 aplicado -- la corrección más fuerte del
# sistema), y aun así el acierto real de sus picks de Goles (el único
# mercado de esta liga elegible para público/premium, ver
# CATEGORIAS_EXCLUIDAS) quedó en 48.3% (n=29) vs 57.1% del mismo mercado
# en el resto de ligas. En la práctica el filtro genérico ya venía
# bloqueando casi todo (solo 4 de 54 candidatos de Brasileirão llegaron
# a público/premium en la ventana auditada, y esos 4 eran de antes del
# fix de CATEGORIAS_EXCLUIDAS) -- esto lo hace explícito y a prueba de
# que un cambio futuro en los pisos genéricos vuelva a dejarla pasar.
# margen_prob/margen_ev se suman encima del piso normal (público o
# premium según corresponda). margen_prob rebajado de 15 a 8 el
# 10/08/2026, junto con la calibración de probabilidad: con el techo real
# de prob calibrada en ~68% (ver PROB_MIN_PUBLICO en configuracion.py),
# +15pp sobre el piso ya rebajado habría vuelto la barrera literalmente
# inalcanzable (piso + margen > el máximo que el modelo puede mostrar) --
# código muerto en la práctica. +8pp sigue siendo una barrera fuerte
# (solo el bloque de prob calibrada más alto la alcanza) pero no
# imposible por construcción.
LIGAS_BAJO_VIGILANCIA = {
    'comp_4795': {'margen_prob': 8, 'margen_ev': 0.05, 'nombre': 'Brasileirão Série A'},

    # Sumadas el 19/08/2026 (auditoría de rendimiento, caída de acierto en
    # mejor_apuesta 55.8%→47.1% en las últimas 2 semanas, ver hilo del
    # 19/08 y tarea #154). Desglose por liga_nombre en Goles/mejor_apuesta
    # mostró que UEFA Conference League, UEFA Europa League y CONMEBOL
    # Sudamericana concentran la caída, con el mercado 'Menos de 2.5
    # goles' derrumbándose específicamente ahí (55.7%→40.0%, n=70→30)
    # mientras 'Más de 2.5' se mantuvo estable. Hipótesis con evidencia
    # coherente (no solo estadística: mecanismo futbolístico identificado):
    # julio/inicios de agosto son las rondas CLASIFICATORIAS de estas
    # copas -- equipos grandes vs semiprofesionales, partidos desparejos y
    # predeciblemente bajos en goles. A mediados de agosto avanzan a
    # rondas con rivales más parejos (playoff/fase de grupos), los
    # partidos se abren, y esa ventaja se evapora. La calibración por liga
    # (Bloque B, ver tarea #152) no distingue todavía "misma liga, etapa
    # distinta" -- ver Fase 2 pendiente (particionar por stage/round
    # cuando se confirme qué campos expone TheStatsAPI). Mientras tanto,
    # piso reforzado como torniquete, mismo margen que Brasileirão.
    'comp_408698': {'margen_prob': 8, 'margen_ev': 0.05, 'nombre': 'UEFA Conference League'},
    'comp_7739':   {'margen_prob': 8, 'margen_ev': 0.05, 'nombre': 'UEFA Europa League'},
    'comp_1615':   {'margen_prob': 8, 'margen_ev': 0.05, 'nombre': 'CONMEBOL Sudamericana'},

    # Ligas nuevas (LaLiga 13/08, Saudi/Eredivisie/Portugal 15/08) --
    # vigilancia PREVENTIVA, no por mala calibración confirmada (la
    # muestra es todavía mínima: 3-6 picks liquidados cada una a la
    # fecha, ver tarea #154). Mismo criterio que se aplicó a Brasileirão
    # en su momento: mejor pagar el costo de un piso más alto mientras
    # acumulan muestra propia que dejarlas competir en igualdad de
    # condiciones sin evidencia todavía de que su calibración sea buena.
    # Revisar y sacar de esta lista cuando cada una acumule >=30-50
    # picks liquidados propios y el acierto real sostenga el piso normal.
    'comp_8814':  {'margen_prob': 8, 'margen_ev': 0.05, 'nombre': 'LaLiga'},
    'comp_45025': {'margen_prob': 8, 'margen_ev': 0.05, 'nombre': 'Saudi Pro League'},
    'comp_3809':  {'margen_prob': 8, 'margen_ev': 0.05, 'nombre': 'Eredivisie'},
    'comp_8385':  {'margen_prob': 8, 'margen_ev': 0.05, 'nombre': 'Liga Portugal'},

    # 20/08/2026: CAF Champions League -- DORMIDA, no evidencia-driven como
    # las de arriba. comp_08478 NO está en Data/partidos/proximos.csv (no
    # se generan candidatos para ella hoy) y tiene 0 filas en
    # historial_picks.csv (nunca produjo un pick público/premium/mejor_
    # apuesta) -- este margen no tiene ningún efecto mientras siga así, es
    # precaución estructural pura. Se agrega ahora porque el análisis de
    # la columna `fase` de historico.csv (ver tarea Bloque B) mostró que
    # tiene la MISMA firma qualifying-pesada que motivó esta lista (92/154
    # partidos con fase='qualifying', 59.7% -- proporción más alta que
    # incluso Conference League). Sin esto, el día que vuelva a aparecer
    # en proximos.csv (temporada CAF suele reactivarse en el año) quedaría
    # compitiendo con el piso normal hasta que otra auditoría manual la
    # detecte semanas después -- exactamente el patrón que causó la Fase 1
    # de este parche. Revisar cuando acumule muestra propia real.
    'comp_08478': {'margen_prob': 8, 'margen_ev': 0.05, 'nombre': 'CAF Champions League'},
}

def _pasa_vigilancia_liga(pk, prob_min_base, ev_min_base):
    """True si el pick pasa el piso reforzado de su liga (si aplica) o si
    la liga no está en LIGAS_BAJO_VIGILANCIA (caso normal)."""
    vig = LIGAS_BAJO_VIGILANCIA.get(pk.get('liga'))
    if not vig:
        return True
    return pk['prob'] >= prob_min_base + vig['margen_prob'] and pk['ev'] >= ev_min_base + vig['margen_ev']

CALIB_PROB_JSON = os.path.join(RAIZ, 'Data', 'calibracion_prob.json')
_CALIB_PROB_CACHE = None

def _cargar_calibracion_prob():
    """Carga (una sola vez por proceso) el dict {categoria: {n, breakpoints}}
    generado por logger_predicciones.py calcular_calibracion_prob().
    Devuelve {} si el archivo no existe todavía (primera corrida antes de
    que el pipeline lo genere) -- en ese caso _calibrar_prob() es no-op.

    Refactor 18/08/2026: antes el JSON era un array plano de breakpoints
    (una sola curva pooled). Ahora está anidado por categoría con una
    entrada 'Global' de fallback -- ver logger_predicciones.calcular_calibracion_prob
    para el detalle completo. Si el archivo en disco todavía tiene el
    formato viejo (plano, sin clave 'categorias' -- puede pasar en el
    primer ciclo del pipeline tras este despliegue, antes de que
    calibrar-prob regenere el archivo), se ignora y se trata como si no
    hubiera calibración todavía (no-op) en vez de reventar."""
    global _CALIB_PROB_CACHE
    if _CALIB_PROB_CACHE is not None:
        return _CALIB_PROB_CACHE
    if not os.path.exists(CALIB_PROB_JSON):
        _CALIB_PROB_CACHE = {}
        return _CALIB_PROB_CACHE
    with open(CALIB_PROB_JSON, encoding='utf-8') as f:
        data = json.load(f)
    _CALIB_PROB_CACHE = data.get('categorias', {})
    return _CALIB_PROB_CACHE

def _calibrar_prob(prob, categoria=None):
    """
    Corrige la sobreconfianza del modelo (auditoría 10/08/2026: rango
    60-75% sobreconfiado 10-17pp frente al acierto real, Brier score 0.253
    -- ver nota larga en logger_predicciones.calcular_calibracion_prob).
    Interpola linealmente entre los breakpoints (x=prob_modelo,
    y=prob_calibrada) de la curva de `categoria` en Data/calibracion_prob.json.
    Por debajo del primer breakpoint o encima del último, se usa el valor
    calibrado del extremo más cercano (clamp) en vez de extrapolar -- no
    hay datos que respalden una extrapolación más allá del rango observado.

    Refactor 18/08/2026 (per-categoría, ver calcular_calibracion_prob):
    usa la curva propia de `categoria` si existe (>=200 muestras propias),
    si no cae a la curva 'Global' (pooled, mismo criterio que antes del
    refactor). Si tampoco hay 'Global' (archivo no generado todavía) o no
    se pasa categoria, devuelve prob sin tocar.
    """
    categorias = _cargar_calibracion_prob()
    if not categorias:
        return prob
    entrada = categorias.get(categoria) or categorias.get('Global')
    if not entrada:
        return prob
    breakpoints = entrada.get('breakpoints', [])
    if not breakpoints:
        return prob
    xs = [b['prob_modelo'] for b in breakpoints]
    ys = [b['prob_calibrada'] for b in breakpoints]
    if prob <= xs[0]:
        return ys[0]
    if prob >= xs[-1]:
        return ys[-1]
    for i in range(len(xs) - 1):
        if xs[i] <= prob <= xs[i+1]:
            if xs[i+1] == xs[i]:
                return ys[i]
            t = (prob - xs[i]) / (xs[i+1] - xs[i])
            return round(ys[i] + t * (ys[i+1] - ys[i]), 1)
    return prob  # inalcanzable en la práctica, por completitud

def _prob_mercado_devigged(cuota_pick, cuotas_grupo):
    """
    Probabilidad "justa" que implica el mercado, normalizando el overround
    (vig) del bookmaker cuando hay >=2 cuotas reales del mismo mercado
    (ej. [c1,cx,c2] para 1X2, [over,under] para goles).
    Si solo hay 1 cuota real disponible (ej. córners: TheStatsAPI solo trae
    el lado "over", no el "under"), devuelve la probabilidad implícita SIN
    de-vig — sobreestima levemente la probabilidad de mercado (incluye el
    margen del bookmaker), lo cual es conservador para el filtro de
    divergencia: si el modelo diverge de esa cifra ya "generosa", la brecha
    real contra la probabilidad justa es aún mayor.
    Devuelve None si no hay ninguna cuota real utilizable.
    """
    validas = [c for c in cuotas_grupo if c and c > 1.0]
    if cuota_pick <= 1.0 or not validas:
        return None
    if len(validas) == 1:
        return 100 / validas[0]
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
        prob_efectiva = prob
        blend_aplicado = False
        if cuotas_grupo:
            prob_mercado = _prob_mercado_devigged(cuota, cuotas_grupo)
            if prob_mercado is not None:
                brecha = abs(prob - prob_mercado)
                if brecha > DIVERGENCIA_MAX_PP:
                    descartados_divergencia.append(
                        f'{mercado} ({partido}): modelo {prob:.1f}% vs mercado {prob_mercado:.1f}% '
                        f'(brecha {brecha:.1f}pp)'
                    )
                    return
                if brecha > DIVERGENCIA_BLEND_MIN_PP:
                    # Zona 20-30pp: blend en vez de confiar 100% en el modelo
                    # o descartar entero (ver nota en DIVERGENCIA_BLEND_MIN_PP).
                    prob_efectiva = round(
                        prob * (1 - PESO_MERCADO_EN_BLEND) + prob_mercado * PESO_MERCADO_EN_BLEND, 1)
                    blend_aplicado = True
        if prob_efectiva < 50:
            return  # el blend puede bajar la prob por debajo del piso público

        # Calibración de probabilidad (auditoría 10/08/2026, refactor por
        # categoría 18/08/2026) -- ver _calibrar_prob() más arriba. Se
        # aplica DESPUÉS del blend con mercado (prob_efectiva ya incluye
        # esa corrección) y ANTES del cálculo de EV, para que el EV
        # mostrado refleje la probabilidad ya corregida y no la cruda
        # sobreconfiada. prob_pre_calibracion se guarda para poder auditar
        # el efecto de esta corrección más adelante sin perder el dato
        # original. Se pasa `categoria` para usar su curva propia si tiene
        # >=200 muestras liquidadas, si no cae a la curva Global.
        prob_pre_calibracion = prob_efectiva
        prob_efectiva = _calibrar_prob(prob_efectiva, categoria)
        if prob_efectiva < 50:
            return  # la calibración también puede bajar la prob del piso

        # BUG REAL encontrado en auditoria de modelo (24/07/2026): esta formula
        # era `prob - 1/cuota`, que NO es el valor esperado monetario estandar
        # de una apuesta (`prob*cuota - 1`) -- es ese mismo EV real dividido
        # entre la cuota. Efecto practico: con cuotas altas (favoritos de
        # mercado poco probables donde el modelo mas diverge de la cuota), el
        # EV mostrado quedaba artificialmente chico frente al EV real, y el
        # filtro EV_MIN_* terminaba exigiendo MENOS edge real cuanto mas alta
        # la cuota -- justo lo opuesto de lo prudente. Analisis de los
        # primeros 125 picks liquidados confirmo el sintoma: el bucket de EV
        # (viejo) mas alto (20%+) acerto solo 25% de las veces, peor que
        # cualquier otro bucket -- la formula estaba premiando divergencia
        # modelo-vs-mercado (a menudo error del modelo en equipos con poco
        # historial, ej. UEFA Conference League) en vez de ventaja real.
        # La combinada premium (mas abajo, seleccionar_premium) YA usaba la
        # formula correcta -- esta linea quedaba inconsistente con esa.
        ev = round((prob_efectiva/100) * cuota - 1, 3)
        candidatos.append({
            'partido': partido,
            'local': local,
            'visitante': visitante,
            'liga': pred.get('liga', ''),
            'liga_nombre': pred.get('liga_nombre', ''),
            'fase': pred.get('fase', ''),
            'fecha': pred.get('fecha', ''),
            'hora': pred.get('hora', ''),
            'mercado': mercado,
            'prob': prob_efectiva,
            'prob_modelo': prob,
            'prob_pre_calibracion': prob_pre_calibracion,
            'blend_aplicado': blend_aplicado,
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

    # ── Córners ── (TheStatsAPI solo trae la cuota del lado "over" — no hay
    # "under" real, así que el grupo de divergencia tiene 1 sola cuota; ver
    # _prob_mercado_devigged para cómo se maneja ese caso sin de-vig completo)
    if cuotas.get('corners_over_8.5', 0) > 1.30 and 'corners_over_8.5' in pred:
        add('Más de 8.5 córners', pred['corners_over_8.5'], cuotas['corners_over_8.5'], '🚩', 'Córners',
            f'Córners esperados: {pred.get("corners_l_esperado",0):.1f} + {pred.get("corners_v_esperado",0):.1f}',
            cuotas_grupo=[cuotas.get('corners_over_8.5', 0)])
    if cuotas.get('corners_over_9.5', 0) > 1.30 and 'corners_over_9.5' in pred:
        add('Más de 9.5 córners', pred['corners_over_9.5'], cuotas['corners_over_9.5'], '🚩', 'Córners',
            f'Córners esperados: {pred.get("corners_l_esperado",0):.1f} + {pred.get("corners_v_esperado",0):.1f}',
            cuotas_grupo=[cuotas.get('corners_over_9.5', 0)])

    # ── Tarjetas y tiros ── DORMIDO hasta que descargar_partidos.py capture
    # estas cuotas (línea VARIABLE por partido en Bet365 — no fija como
    # córners). El pick usa la línea REAL de ese partido (pred['*_linea_real']
    # y la prob. calculada exactamente en esa línea, pred['*_over_real']) —
    # nunca la línea de referencia fija (4.5/24.5/8.5), que es solo dato
    # informativo para la web. Mientras 'cuotas_over_precio' no llegue con
    # datos reales, estos `if` nunca se disparan.
    if cuotas.get('cards_over_precio', 0) > 1.30 and pred.get('cards_over_real') is not None:
        linea = pred['cards_linea_real']
        add(f'Más de {linea} tarjetas', pred['cards_over_real'], cuotas['cards_over_precio'], '🟨', 'Tarjetas',
            f'Tarjetas esperadas: {pred.get("cards_l_esperado",0):.1f} + {pred.get("cards_v_esperado",0):.1f}',
            cuotas_grupo=[cuotas.get('cards_over_precio', 0)])
    if cuotas.get('shots_over_precio', 0) > 1.30 and pred.get('shots_over_real') is not None:
        linea = pred['shots_linea_real']
        add(f'Más de {linea} tiros', pred['shots_over_real'], cuotas['shots_over_precio'], '🎯', 'Tiros',
            f'Tiros esperados: {pred.get("shots_l_esperado",0):.1f} + {pred.get("shots_v_esperado",0):.1f}',
            cuotas_grupo=[cuotas.get('shots_over_precio', 0)])
    if cuotas.get('sot_over_precio', 0) > 1.30 and pred.get('sot_over_real') is not None:
        linea = pred['sot_linea_real']
        add(f'Más de {linea} tiros al arco', pred['sot_over_real'], cuotas['sot_over_precio'], '🎯', 'Tiros',
            f'Tiros al arco esperados: {pred.get("sot_l_esperado",0):.1f} + {pred.get("sot_v_esperado",0):.1f}',
            cuotas_grupo=[cuotas.get('sot_over_precio', 0)])
    # Faltas — DORMIDO igual que tarjetas/tiros: la clave de mercado
    # 'total_fouls' en descargar_partidos.py es una suposición sin
    # confirmar; hasta que la próxima corrida en vivo confirme (o corrija)
    # esa clave, 'fouls_over_precio' llega vacío y este bloque nunca dispara.
    if cuotas.get('fouls_over_precio', 0) > 1.30 and pred.get('fouls_over_real') is not None:
        linea = pred['fouls_linea_real']
        add(f'Más de {linea} faltas', pred['fouls_over_real'], cuotas['fouls_over_precio'], '🟥', 'Faltas',
            f'Faltas esperadas: {pred.get("fouls_l_esperado",0):.1f} + {pred.get("fouls_v_esperado",0):.1f}',
            cuotas_grupo=[cuotas.get('fouls_over_precio', 0)])

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
    # Filtrar por EV en rango [EV_MIN_PUBLICO, EV_MAX_PUBLICO] y prob mínima.
    # El techo (EV_MAX_PUBLICO) es tan importante como el piso -- ver la nota
    # larga en configuracion.py: EV informado por encima del techo es señal
    # de error de calibración del modelo, no de ventaja real, confirmado en
    # dos auditorías consecutivas (24/07 y 25/07/2026).
    validos = [pk for pk in todos
               if pk['prob'] >= PROB_MIN_PUBLICO
               and pk['cuota'] >= CUOTA_MIN_PUBLICO
               and EV_MIN_PUBLICO <= pk['ev'] <= EV_MAX_PUBLICO
               and pk['categoria'] not in CATEGORIAS_EXCLUIDAS
               and _pasa_vigilancia_liga(pk, PROB_MIN_PUBLICO, EV_MIN_PUBLICO)]

    # Ordenar por EV
    validos.sort(key=lambda x: (x['prob'], x['ev']), reverse=True)

    # PREMIUM PRIMERO — seleccionar antes que el público
    premium = seleccionar_premium(todos, [])
    # BUG encontrado en auditoría de picks del 18/08/2026: esto era
    # `set(pk['mercado'] for pk in premium)` -- comparaba solo el NOMBRE
    # del mercado ("Menos de 2.5 goles"), no partido+mercado. Como ese
    # nombre es una etiqueta genérica que se repite en decenas de partidos
    # (Goles es ~95% del volumen elegible), en cuanto el premium del día
    # salía con un mercado de Goles, la regla de "no usar el mercado exacto
    # del premium" (pensada para evitar duplicar la MISMA pata en ambos
    # paneles) terminaba excluyendo ese mercado de TODOS los partidos del
    # público -- vació el panel público en días donde había candidatos
    # válidos de sobra (caso real: São Paulo vs Bolívar, EV +11.5%,
    # bloqueado solo porque el premium de ese día también era "Menos de
    # 2.5 goles" de otro partido). Fix: comparar por (partido, mercado).
    mercados_premium = set((pk['partido'], pk['mercado']) for pk in premium)
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

        # No usar la misma pata exacta (partido + mercado) del premium
        if (partido, pk['mercado']) in mercados_premium:
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
    # Picks con prob alta y cuota baja — candidatos para combinada.
    # PROB_MIN_PATA_PREMIUM rebajado de 68 a 58 (10/08/2026, junto con la
    # calibración de probabilidad -- ver nota larga en PROB_MIN_PUBLICO de
    # configuracion.py): 68 era un piso sobre la prob CRUDA; ahora pk['prob']
    # ya viene calibrada desde generar_candidatos(), así que el piso
    # equivalente es _calibrar_prob(68)=58.4. Mismo criterio de
    # selectividad, expresado en la escala honesta.
    PROB_MIN_PATA_PREMIUM = 58

    candidatos = sorted(
        [pk for pk in todos
         if pk['prob'] >= PROB_MIN_PATA_PREMIUM
         and 1.20 <= pk['cuota'] <= 3.00
         and pk['mercado'] not in mercados_excluidos
         and pk['categoria'] not in CATEGORIAS_EXCLUIDAS
         and _pasa_vigilancia_liga(pk, PROB_MIN_PATA_PREMIUM, EV_MIN_PREMIUM)],
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
                # Producto simple, SIN factor de corrección extra (a
                # diferencia de una versión anterior de este fix, del
                # 10/08/2026 más temprano ese mismo día -- ver historial de
                # git): pk1/pk2['prob'] ya vienen calibradas desde
                # generar_candidatos() (ver _calibrar_prob), así que la
                # sobreconfianza que ese factor corregía manualmente
                # (acierto real 42.1% vs 57.1% mostrado, n=19) ya está
                # corregida en el origen. Verificación numérica antes de
                # quitarlo: dos patas en el piso nuevo (58.4% calibrado
                # c/u) dan prob_combo=34.1, casi idéntico a lo que daba el
                # factor viejo sobre patas en el piso viejo
                # (68*68/100*0.738=34.1) -- mismo resultado por la vía
                # correcta en vez de un parche encima de probabilidades ya
                # corregidas (que las sobre-corregiría). Sigue siendo una
                # hipótesis a confirmar con combinadas liquidadas bajo este
                # esquema -- si el acierto real de las próximas combinadas
                # diverge de prob_combo, hay que revisar esto de nuevo.
                prob_combo = round(pk1['prob'] * pk2['prob'] / 100, 1)
                # Piso de prob_combo rebajado de 40 a 30 (mismo motivo: dos
                # patas en el piso nuevo de PROB_MIN_PATA_PREMIUM dan ~34,
                # un piso de 40 habría bloqueado la mayoría de las
                # combinadas típicas, no solo las débiles).
                if prob_combo < 30:
                    continue
                ev_combo = round((prob_combo/100) * cuota_combo - 1, 3)
                if ev_combo < EV_MIN_PREMIUM or ev_combo > EV_MAX_PREMIUM:
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
    # Umbrales 65->57 y 62->56 rebajados el 10/08/2026 junto con la
    # calibración de probabilidad (misma escala honesta que
    # PROB_MIN_PATA_PREMIUM más arriba -- _calibrar_prob(65)=57.1,
    # _calibrar_prob(62)=56.1).
    if not mejor:
        for pk in sorted(todos, key=lambda x: (x['prob'], x['ev']), reverse=True):
            if (pk['prob'] >= 57
                and pk['cuota'] >= CUOTA_MIN_PREMIUM
                and EV_MIN_PREMIUM <= pk['ev'] <= EV_MAX_PREMIUM
                and pk['mercado'] not in mercados_excluidos
                and pk['categoria'] not in CATEGORIAS_EXCLUIDAS
                and _pasa_vigilancia_liga(pk, 57, EV_MIN_PREMIUM)):
                pk['tipo'] = 'premium'
                return [pk]
        # Último recurso — mejor pick disponible con cuota >= 1.50
        for pk in sorted(todos, key=lambda x: x['prob'], reverse=True):
            if (pk['prob'] >= 56
                and pk['cuota'] >= 1.50
                and pk['categoria'] not in CATEGORIAS_EXCLUIDAS
                and EV_MIN_PREMIUM <= pk['ev'] <= EV_MAX_PREMIUM
                and pk['mercado'] not in mercados_excluidos
                and _pasa_vigilancia_liga(pk, 56, EV_MIN_PREMIUM)):
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
            'corners_over_8.5': 0,
            'corners_over_9.5': 0,
            'cards_over_precio': 0,   # dormido — ver nota en generar_candidatos
            'shots_over_precio': 0,
            'sot_over_precio': 0,
            'fouls_over_precio': 0,
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
                    'corners_over_8.5': row.get('corners_over_8.5', 0),
                    'corners_over_9.5': row.get('corners_over_9.5', 0),
                    'cards_linea': row.get('cards_linea', ''),
                    'cards_over_precio': row.get('cards_over_precio', 0),
                    'shots_linea': row.get('shots_linea', ''),
                    'shots_over_precio': row.get('shots_over_precio', 0),
                    'sot_linea': row.get('sot_linea', ''),
                    'sot_over_precio': row.get('sot_over_precio', 0),
                    'fouls_linea': row.get('fouls_linea', ''),
                    'fouls_over_precio': row.get('fouls_over_precio', 0),
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
