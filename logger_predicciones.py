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
    """Carga o crea un log CSV"""
    if os.path.exists(path):
        return pd.read_csv(path)
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
    Registra el resultado real después del partido
    """
    df = cargar_log(LOG_RESULT, COLS_RESULT)

    # Verificar si ya existe
    mask = (
        (df['fecha'] == fecha) &
        (df['local'] == local) &
        (df['visitante'] == visitante)
    )
    if mask.any():
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
        elif cmd == 'calibrar':
            calcular_mse()
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
