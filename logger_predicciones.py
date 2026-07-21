# -*- coding: utf-8 -*-
"""
logger_predicciones.py
Sistema de logging de predicciones vs resultados reales
Calcula MSE y recalibra parámetros Dixon-Coles por liga
"""
import os, sys, json
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta

RAIZ = os.path.dirname(os.path.abspath(__file__))
os.chdir(RAIZ)
sys.path.insert(0, RAIZ)
from configuracion import ZONA_PERU, LIGAS

PERU_TZ = timezone(timedelta(hours=ZONA_PERU))

LOG_PRED   = os.path.join(RAIZ, 'Data', 'predicciones_log.csv')
LOG_RESULT = os.path.join(RAIZ, 'Data', 'resultados_log.csv')
CALIB_JSON = os.path.join(RAIZ, 'Data', 'calibracion.json')

# ── Columnas del log de predicciones ──
COLS_PRED = [
    'fecha', 'hora', 'liga', 'local', 'visitante',
    'xg_l', 'xg_v', 'xg_total',
    'prob_1', 'prob_x', 'prob_2',
    'prob_over_25', 'prob_under_25', 'prob_btts_si',
    'cuota_1', 'cuota_x', 'cuota_2',
    'cuota_over_25', 'cuota_under_25',
    'generado_en',
    # Closing Line Value: cuota "de cierre" (aproximada, ver
    # registrar_cierre_desde_proximos) vs la cuota de publicación de arriba.
    # Señal de calidad de modelo independiente del resultado final del
    # partido — si el mercado se mueve a favor del pick (cuota baja) después
    # de publicado, es evidencia de que el modelo vio algo real antes que
    # el mercado terminara de descontarlo.
    'cuota_1_cierre', 'cuota_x_cierre', 'cuota_2_cierre',
    'cuota_over_25_cierre', 'cuota_under_25_cierre',
    'clv_1x2_pct', 'cierre_registrado_en',
]

# ── Columnas del log de resultados ──
COLS_RESULT = [
    'fecha', 'liga', 'local', 'visitante',
    'goles_l_real', 'goles_v_real', 'goles_total_real',
    'resultado_real',  # '1', 'X', '2'
    'over_25_real',    # True/False
    'btts_real',       # True/False
    'registrado_en',
]

def cargar_log(path, cols):
    """
    Carga o crea un log CSV. Si el CSV existente es de una versión anterior
    del schema (ej. antes de agregar las columnas de CLV), agrega las
    columnas faltantes como NaN en vez de romper -- migración silenciosa
    hacia adelante sin perder filas existentes.
    """
    if os.path.exists(path):
        df = pd.read_csv(path)
        for c in cols:
            if c not in df.columns:
                df[c] = pd.NA
        return df
    return pd.DataFrame(columns=cols)

def guardar_log(df, path):
    """Guarda el log CSV"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    df.to_csv(path, index=False)

def registrar_prediccion(pred, cuotas=None):
    """
    Registra una predicción antes del partido
    pred: dict con xg_l, xg_v, p1, px, p2, etc.
    """
    df = cargar_log(LOG_PRED, COLS_PRED)

    # Verificar si ya existe
    mask = (
        (df['fecha'] == pred.get('fecha', '')) &
        (df['local'] == pred.get('local', '')) &
        (df['visitante'] == pred.get('visitante', ''))
    )
    if mask.any():
        return False  # ya registrado

    cuotas = cuotas or {}
    nueva_fila = {
        'fecha':         pred.get('fecha', ''),
        'hora':          pred.get('hora', ''),
        'liga':          pred.get('liga', ''),
        'local':         pred.get('local', ''),
        'visitante':     pred.get('visitante', ''),
        'xg_l':          pred.get('xg_l', 0),
        'xg_v':          pred.get('xg_v', 0),
        'xg_total':      round(pred.get('xg_l', 0) + pred.get('xg_v', 0), 3),
        'prob_1':        pred.get('p1', 0),
        'prob_x':        pred.get('px', 0),
        'prob_2':        pred.get('p2', 0),
        'prob_over_25':  pred.get('over_2.5', 0),
        'prob_under_25': pred.get('under_2.5', 0),
        'prob_btts_si':  pred.get('btts_si', 0),
        'cuota_1':       cuotas.get('c1', 0),
        'cuota_x':       cuotas.get('cx', 0),
        'cuota_2':       cuotas.get('c2', 0),
        'cuota_over_25': cuotas.get('over_2.5', 0),
        'cuota_under_25':cuotas.get('under_2.5', 0),
        'generado_en':   datetime.now(PERU_TZ).isoformat(),
    }

    df = pd.concat([df, pd.DataFrame([nueva_fila])], ignore_index=True)
    guardar_log(df, LOG_PRED)
    return True

def registrar_resultado(fecha, liga, local, visitante, goles_l, goles_v):
    """
    Registra el resultado real después del partido.
    Idempotente: si ya existe una fila igual (mismo marcador), no reescribe
    el CSV ni cuenta como registro nuevo — importante para sincronizar_resultados(),
    que re-consulta la misma ventana de días cada vez que corre.
    Devuelve True solo si insertó una fila nueva o actualizó un marcador distinto.
    """
    df = cargar_log(LOG_RESULT, COLS_RESULT)

    # Verificar si ya existe
    mask = (
        (df['fecha'] == fecha) &
        (df['local'] == local) &
        (df['visitante'] == visitante)
    )
    if mask.any():
        existente = df.loc[mask].iloc[0]
        sin_cambios = (
            str(existente.get('goles_l_real')) == str(goles_l) and
            str(existente.get('goles_v_real')) == str(goles_v)
        )
        if sin_cambios:
            return False  # ya estaba registrado con el mismo marcador

        # Actualizar
        df.loc[mask, 'goles_l_real'] = goles_l
        df.loc[mask, 'goles_v_real'] = goles_v
        df.loc[mask, 'goles_total_real'] = goles_l + goles_v
        df.loc[mask, 'resultado_real'] = '1' if goles_l > goles_v else ('X' if goles_l == goles_v else '2')
        df.loc[mask, 'over_25_real'] = goles_l + goles_v > 2.5
        df.loc[mask, 'btts_real'] = goles_l > 0 and goles_v > 0
        df.loc[mask, 'registrado_en'] = datetime.now(PERU_TZ).isoformat()
    else:
        nueva_fila = {
            'fecha':           fecha,
            'liga':            liga,
            'local':           local,
            'visitante':       visitante,
            'goles_l_real':    goles_l,
            'goles_v_real':    goles_v,
            'goles_total_real': goles_l + goles_v,
            'resultado_real':  '1' if goles_l > goles_v else ('X' if goles_l == goles_v else '2'),
            'over_25_real':    goles_l + goles_v > 2.5,
            'btts_real':       goles_l > 0 and goles_v > 0,
            'registrado_en':   datetime.now(PERU_TZ).isoformat(),
        }
        df = pd.concat([df, pd.DataFrame([nueva_fila])], ignore_index=True)

    guardar_log(df, LOG_RESULT)
    print(f'✅ Resultado registrado: {local} {goles_l}-{goles_v} {visitante}')
    return True

def calcular_mse():
    """
    Calcula MSE y métricas de calibración por liga
    Compara predicciones vs resultados reales
    """
    df_pred = cargar_log(LOG_PRED, COLS_PRED)
    df_res  = cargar_log(LOG_RESULT, COLS_RESULT)

    if len(df_pred) == 0 or len(df_res) == 0:
        print('⚠️ Sin datos suficientes para calibrar')
        return {}

    # Merge predicciones con resultados
    df = pd.merge(
        df_pred, df_res,
        on=['fecha', 'liga', 'local', 'visitante'],
        how='inner'
    )

    if len(df) == 0:
        print('⚠️ Sin partidos con predicción Y resultado')
        return {}

    print(f'\n📊 ANÁLISIS DE CALIBRACIÓN ({len(df)} partidos)')
    print('='*60)

    calibracion = {}

    for liga in df['liga'].unique():
        df_l = df[df['liga'] == liga].copy()
        n = len(df_l)
        if n < 3:
            continue

        # MSE de goles totales
        mse_goles = float(np.mean((df_l['xg_total'] - df_l['goles_total_real'])**2))
        mae_goles = float(np.mean(np.abs(df_l['xg_total'] - df_l['goles_total_real'])))

        # Accuracy 1X2
        df_l['pred_resultado'] = df_l.apply(
            lambda r: '1' if r['prob_1'] >= r['prob_x'] and r['prob_1'] >= r['prob_2']
                      else ('X' if r['prob_x'] >= r['prob_2'] else '2'), axis=1
        )
        accuracy_1x2 = float((df_l['pred_resultado'] == df_l['resultado_real']).mean() * 100)

        # Accuracy Over/Under 2.5
        df_l['pred_over25'] = df_l['prob_over_25'] >= 50
        accuracy_over25 = float((df_l['pred_over25'] == df_l['over_25_real']).mean() * 100)

        # Sesgo: ¿sobreestima o subestima goles?
        sesgo = float((df_l['xg_total'] - df_l['goles_total_real']).mean())

        # Factor de corrección sugerido
        media_pred = float(df_l['xg_total'].mean())
        media_real = float(df_l['goles_total_real'].mean())
        factor_corr = round(media_real / media_pred, 3) if media_pred > 0 else 1.0

        calibracion[liga] = {
            'partidos':        n,
            'mse_goles':       round(mse_goles, 3),
            'mae_goles':       round(mae_goles, 3),
            'sesgo_goles':     round(sesgo, 3),
            'accuracy_1x2':    round(accuracy_1x2, 1),
            'accuracy_over25': round(accuracy_over25, 1),
            'media_xg_pred':   round(media_pred, 3),
            'media_goles_real':round(media_real, 3),
            'factor_correccion': factor_corr,
        }

        liga_nombre = LIGAS.get(liga, {}).get('nombre', liga)
        print(f'\n  {liga_nombre} ({n} partidos):')
        print(f'    MSE goles:      {mse_goles:.3f}')
        print(f'    MAE goles:      {mae_goles:.3f}')
        print(f'    Sesgo:          {sesgo:+.3f} ({"sobreestima" if sesgo > 0 else "subestima"})')
        print(f'    Accuracy 1X2:   {accuracy_1x2:.1f}%')
        print(f'    Accuracy O/U:   {accuracy_over25:.1f}%')
        print(f'    xG pred promedio: {media_pred:.2f} | Real: {media_real:.2f}')
        print(f'    Factor corrección sugerido: {factor_corr:.3f}')

        if abs(sesgo) > 0.5:
            if sesgo > 0:
                print(f'    ⚠️ Modelo SOBREESTIMA goles — reducir media_goles en {abs(sesgo):.2f}')
            else:
                print(f'    ⚠️ Modelo SUBESTIMA goles — aumentar media_goles en {abs(sesgo):.2f}')

    # Guardar calibración
    with open(CALIB_JSON, 'w', encoding='utf-8') as f:
        json.dump(calibracion, f, ensure_ascii=False, indent=2)
    print(f'\n✅ Calibración guardada en {CALIB_JSON}')

    return calibracion

def sincronizar_resultados(dias_atras=4):
    """
    Trae partidos FINALIZADOS de las ligas cubiertas (configuracion.LIGAS)
    de los últimos `dias_atras` días desde TheStatsAPI y los registra en
    resultados_log.csv, para poder cruzarlos contra predicciones_log.csv
    y recalibrar el modelo (calcular_mse()).

    Usa el mismo cliente/API que descargar_partidos.py, así que los nombres
    de equipo y competition_id coinciden exactamente con los que ya quedaron
    en predicciones_log.csv (evita el mismatch de nombres que existía en
    los registros manuales previos a la migración a TheStatsAPI).
    """
    from configuracion import API_THESTATS
    from thestats_client import TheStatsClient, TheStatsAPIError
    from descargar_partidos import utc_a_peru

    hoy = datetime.now(PERU_TZ).date()
    date_from = (hoy - timedelta(days=dias_atras)).isoformat()
    date_to = hoy.isoformat()

    client = TheStatsClient(API_THESTATS)
    revisados = 0
    registrados = 0

    print(f'\n🔄 Sincronizando resultados finalizados ({date_from} → {date_to})')

    for liga_id, cfg in LIGAS.items():
        try:
            finalizados = client.get_matches(
                liga_id, status='finished',
                date_from=date_from, date_to=date_to,
            )
        except TheStatsAPIError as e:
            print(f'  ⚠️ {cfg.get("nombre", liga_id)}: {e}')
            continue

        nuevos_liga = 0
        for m in finalizados:
            score = m.get('score') or {}
            gl, gv = score.get('home'), score.get('away')
            if gl is None or gv is None:
                continue

            fecha, _hora = utc_a_peru(m['utc_date'])
            local = m['home_team']['name']
            visitante = m['away_team']['name']
            revisados += 1

            if registrar_resultado(fecha, liga_id, local, visitante, int(gl), int(gv)):
                registrados += 1
                nuevos_liga += 1

        if finalizados:
            print(f'  {cfg.get("nombre", liga_id)}: {len(finalizados)} finalizados, {nuevos_liga} nuevos')

    print(f'\n✅ Sync resultados: {revisados} finalizados revisados, {registrados} nuevos en {LOG_RESULT}')
    return registrados

def registrar_cierre_desde_proximos():
    """
    Snapshot de cuota "de cierre" para partidos de HOY que ya tienen una
    predicción registrada (de un día anterior) pero todavía no un cierre.
    Usa la cuota más reciente de proximos.csv, refrescada por
    descargar_partidos.py --diario que corre justo antes en el pipeline
    diario -- es la cuota más cercana al kickoff disponible con la
    arquitectura actual de snapshots diarios (no hay polling en tiempo
    real de odds). Es una APROXIMACIÓN de Closing Line Value, no el cierre
    exacto de ningún bookmaker: sirve como proxy de si el mercado se movió
    a favor o en contra del pick entre publicación y el día del partido.
    """
    df_pred = cargar_log(LOG_PRED, COLS_PRED)
    if len(df_pred) == 0:
        print('⚠️ Sin predicciones registradas aún')
        return 0
    try:
        df_prox = pd.read_csv(os.path.join(RAIZ, 'Data', 'partidos', 'proximos.csv'))
    except FileNotFoundError:
        print('⚠️ Sin Data/partidos/proximos.csv -- corré descargar_partidos.py --diario primero')
        return 0

    hoy = datetime.now(PERU_TZ).strftime('%Y-%m-%d')
    sin_cierre = df_pred['cuota_1_cierre'].isna() if 'cuota_1_cierre' in df_pred else pd.Series(True, index=df_pred.index)
    pendientes = df_pred[(df_pred['fecha'] == hoy) & sin_cierre]
    actualizados = 0

    for idx, row in pendientes.iterrows():
        mask = ((df_prox['local'] == row['local']) &
                (df_prox['visitante'] == row['visitante']) &
                (df_prox['fecha'] == row['fecha']))
        if not mask.any():
            continue
        prox = df_prox[mask].iloc[0]
        c1c = prox.get('c1', 0) or None
        cxc = prox.get('cx', 0) or None
        c2c = prox.get('c2', 0) or None
        df_pred.loc[idx, 'cuota_1_cierre'] = c1c
        df_pred.loc[idx, 'cuota_x_cierre'] = cxc
        df_pred.loc[idx, 'cuota_2_cierre'] = c2c
        df_pred.loc[idx, 'cuota_over_25_cierre'] = prox.get('over_2.5', 0) or None
        df_pred.loc[idx, 'cuota_under_25_cierre'] = prox.get('under_2.5', 0) or None

        c1_pub = row.get('cuota_1', 0)
        if c1_pub and c1c:
            # CLV positivo = la cuota bajó (mercado se movió a favor del
            # pick) entre publicación y cierre -- señal de que el modelo
            # capturó algo real antes de que el mercado terminara de
            # ajustarse. Negativo = el mercado se movió en contra.
            df_pred.loc[idx, 'clv_1x2_pct'] = round((float(c1_pub) / float(c1c) - 1) * 100, 2)
        df_pred.loc[idx, 'cierre_registrado_en'] = datetime.now(PERU_TZ).isoformat()
        actualizados += 1

    if actualizados:
        guardar_log(df_pred, LOG_PRED)
    print(f'✅ CLV: {actualizados} cierre(s) registrado(s) para partidos de hoy')
    return actualizados

def calcular_clv_resumen():
    """
    Resumen de Closing Line Value acumulado -- CLV promedio positivo y
    consistente en el tiempo es la señal estándar de la industria de que un
    modelo tiene edge real, independiente de si los resultados puntuales
    salieron a favor o en contra (varianza de corto plazo).
    """
    df_pred = cargar_log(LOG_PRED, COLS_PRED)
    con_clv = df_pred.dropna(subset=['clv_1x2_pct']) if 'clv_1x2_pct' in df_pred else df_pred.iloc[0:0]
    if len(con_clv) == 0:
        print('⚠️ Sin datos de CLV todavía -- corré registrar-cierre unos días')
        return {}
    clv_prom = float(con_clv['clv_1x2_pct'].mean())
    pct_positivo = float((con_clv['clv_1x2_pct'] > 0).mean() * 100)
    print(f'\n📈 CLV RESUMEN ({len(con_clv)} picks con cierre registrado)')
    print(f'   CLV promedio: {clv_prom:+.2f}%')
    print(f'   % de picks con CLV positivo: {pct_positivo:.1f}%')
    return {'n': len(con_clv), 'clv_promedio_pct': round(clv_prom, 2), 'pct_clv_positivo': round(pct_positivo, 1)}

def auto_registrar_predicciones(fecha=None):
    """
    Registra automáticamente las predicciones del día en el log
    Se llama desde el generador después de generar picks
    """
    from datetime import datetime, timedelta
    from modelo_prediccion import predecir_jornada, normalizar_nombre

    if fecha is None:
        fecha = datetime.now(PERU_TZ).strftime('%Y-%m-%d')

    fecha_fin = (datetime.strptime(fecha, '%Y-%m-%d') + timedelta(days=2)).strftime('%Y-%m-%d')

    try:
        df_prox = pd.read_csv(os.path.join(RAIZ, 'Data', 'partidos', 'proximos.csv'))
    except:
        return

    predicciones = predecir_jornada(fecha)
    predicciones = [p for p in predicciones if fecha <= p.get('fecha', '') <= fecha_fin]

    registradas = 0
    for pred in predicciones:
        # Buscar cuotas
        mask = (
            (df_prox['local'].apply(normalizar_nombre) == normalizar_nombre(pred['local'])) &
            (df_prox['visitante'].apply(normalizar_nombre) == normalizar_nombre(pred['visitante']))
        )
        cuotas = {}
        if mask.any():
            row = df_prox[mask].iloc[0]
            cuotas = {
                'c1': row.get('c1', 0), 'cx': row.get('cx', 0), 'c2': row.get('c2', 0),
                'over_2.5': row.get('over_2.5', 0), 'under_2.5': row.get('under_2.5', 0),
            }

        if registrar_prediccion(pred, cuotas):
            registradas += 1

    print(f'✅ {registradas} predicciones nuevas registradas en el log')

def mostrar_resumen():
    """Muestra resumen del log actual"""
    df_pred = cargar_log(LOG_PRED, COLS_PRED)
    df_res  = cargar_log(LOG_RESULT, COLS_RESULT)

    print(f'\n📋 RESUMEN DEL LOG')
    print(f'  Predicciones registradas: {len(df_pred)}')
    print(f'  Resultados registrados:   {len(df_res)}')

    if len(df_pred) > 0:
        print(f'\n  Por liga:')
        for liga, grupo in df_pred.groupby('liga'):
            nombre = LIGAS.get(liga, {}).get('nombre', liga)
            print(f'    {nombre}: {len(grupo)} predicciones')

    if len(df_res) > 0:
        print(f'\n  Últimos resultados:')
        for _, r in df_res.tail(5).iterrows():
            print(f'    {r["fecha"]} {r["local"]} {r["goles_l_real"]}-{r["goles_v_real"]} {r["visitante"]}')

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == 'registrar':
            auto_registrar_predicciones()
        elif cmd == 'sync-resultados':
            # python logger_predicciones.py sync-resultados [dias_atras]
            dias = int(sys.argv[2]) if len(sys.argv) >= 3 else 4
            sincronizar_resultados(dias_atras=dias)
        elif cmd == 'calibrar':
            calcular_mse()
        elif cmd == 'registrar-cierre':
            registrar_cierre_desde_proximos()
        elif cmd == 'clv-resumen':
            calcular_clv_resumen()
        elif cmd == 'resumen':
            mostrar_resumen()
        elif cmd == 'resultado':
            # python logger_predicciones.py resultado BSA "Fluminense FC" "RB Bragantino" 2 1
            if len(sys.argv) >= 7:
                registrar_resultado(
                    sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5],
                    int(sys.argv[6]), int(sys.argv[7])
                )
    else:
        auto_registrar_predicciones()
        mostrar_resumen()