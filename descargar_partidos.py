# -*- coding: utf-8 -*-
"""
descargar_partidos.py
Descarga partidos, estadisticas y cuotas usando exclusivamente TheStatsAPI.

Dos modos independientes (uno u otro, no ambos):

  --historico   Descarga stats de partidos TERMINADOS de los ultimos 365
                dias. Pensado para correr una sola vez por liga -- usa
                checkpointing (Data/descarga_checkpoint.json) para saltar
                ligas ya completadas y poder reanudar entre sesiones.
                Cada sesion tiene un limite de tiempo (--session-minutos,
                default 120) acorde al rate limit real de la API.

  --diario      Descarga solo los proximos 7 dias + cuotas (sin stats
                historicos). Pensado para correr todos los dias (p.ej. en
                GitHub Actions). Por defecto procesa las ligas de
                configuracion.LIGAS (el set curado de 15 ligas prioritarias
                de SportPicks-Ligas). Calibrado empiricamente (test MLS+BSA,
                2026-07-20): ~53 llamadas para 2 ligas => ~26.5 llamadas/liga
                en promedio, variable segun el calendario de la semana.

Uso:
    python descargar_partidos.py --historico [--session-minutos 120]
    python descargar_partidos.py --diario
    python descargar_partidos.py --diario --comp-ids comp_9799,comp_4795   (prueba)
"""
import os, sys, csv, json, time, argparse
from datetime import datetime, timezone, timedelta

RAIZ = os.path.dirname(os.path.abspath(__file__))
os.chdir(RAIZ)
sys.path.insert(0, RAIZ)
from configuracion import API_THESTATS, LIGAS, ZONA_PERU
from thestats_client import TheStatsClient, TheStatsAPIError

try:
    sys.stdout.reconfigure(line_buffering=True)
except AttributeError:
    pass

PERU_TZ = timezone(timedelta(hours=ZONA_PERU))

CHECKPOINT_PATH = 'Data/descarga_checkpoint.json'

# Calibracion de estimaciones: segundos por llamada real observados contra
# el rate limit del servidor (~12 req / ventana de ~60s), y promedio de
# llamadas por liga en modo historico calibrado con el test inicial
# MLS (422) + BSA (429) del 2026-07-20. Se recalibra solo con datos reales
# de checkpoint.historico en cuanto hay al menos una liga completada.
SEGUNDOS_POR_LLAMADA_EST = 5.5
PROMEDIO_LLAMADAS_LIGA_DEFAULT = 425
# Promedio de llamadas/liga en modo diario, calibrado con el test MLS+BSA
# del 2026-07-20 (53 llamadas / 2 ligas = 26.5). Varia con el calendario
# de esa semana; solo se usa para la estimacion previa, no es un limite.
PROMEDIO_LLAMADAS_DIARIO_LIGA = 26.5

COLUMNAS_HIST = [
    'liga', 'liga_nombre', 'fecha', 'hora_peru', 'local', 'visitante',
    'goles_l', 'goles_v', 'resultado', 'estado', 'jornada', 'fase', 'fuente',
    'xg_l', 'xg_v', 'corners_l', 'corners_v', 'shots_l', 'shots_v',
    'shots_on_target_l', 'shots_on_target_v', 'fouls_l', 'fouls_v',
    'yellow_cards_l', 'yellow_cards_v',
]

COLUMNAS_PROX = [
    'liga', 'liga_nombre', 'fecha', 'hora_peru', 'local', 'visitante',
    'goles_l', 'goles_v', 'resultado', 'estado', 'jornada', 'fase', 'fuente',
    'c1', 'cx', 'c2', 'over_2.5', 'under_2.5', 'btts_si', 'btts_no',
    'corners_over_8.5', 'corners_over_9.5',
    # Línea VARIABLE por partido (a diferencia de corners, que casi siempre
    # usa 8.5/9.5 fijas) — se guarda la línea real junto con el precio, y el
    # modelo calcula la prob. Over para ESA línea específica, no una fija.
    # Solo Bet365 los cotiza (confirmado por exploración manual de /odds);
    # total_cards además es intermitente, no siempre está disponible.
    'shots_linea', 'shots_over_precio',
    'sot_linea', 'sot_over_precio',
    'cards_linea', 'cards_over_precio',
]

BOOKMAKERS_PREFERIDOS = ('Pinnacle', 'Bet365')


# ── Utilidades de fecha/CSV/checkpoint ──────────────────────────────

def hoy_peru():
    return datetime.now(PERU_TZ).date()


def utc_a_peru(utc_date_str):
    dt_utc = datetime.fromisoformat(utc_date_str.replace('Z', '+00:00'))
    dt_peru = dt_utc.astimezone(PERU_TZ)
    return dt_peru.strftime('%Y-%m-%d'), dt_peru.strftime('%H:%M')


def _num(x):
    return x if x is not None else ''


def crear_csv_vacio(ruta, columnas):
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, 'w', newline='', encoding='utf-8') as f:
        csv.DictWriter(f, fieldnames=columnas).writeheader()


def append_csv(ruta, filas, columnas):
    if not filas:
        return
    existe = os.path.exists(ruta)
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=columnas)
        if not existe:
            writer.writeheader()
        for fila in filas:
            writer.writerow(fila)


def cargar_checkpoint(ruta):
    if os.path.exists(ruta):
        with open(ruta, encoding='utf-8') as f:
            return json.load(f)
    return {'historico': {}}


def guardar_checkpoint(ruta, cp):
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, 'w', encoding='utf-8') as f:
        json.dump(cp, f, indent=2, ensure_ascii=False)


# ── Filas de salida ──────────────────────────────────────────────────

def fila_historico(liga_id, liga_cfg, m, stats):
    fecha, hora = utc_a_peru(m['utc_date'])
    gl, gv = m['score']['home'], m['score']['away']
    ov = (stats or {}).get('overview') or {}

    def par(campo):
        # ov.get(campo, {}) NO alcanza cuando la clave existe pero vale
        # None (json null) -- pasa con partidos sin stats completos.
        d = (ov.get(campo) or {}).get('all') or {}
        return d.get('home'), d.get('away')

    xg_l, xg_v = par('expected_goals')
    cor_l, cor_v = par('corner_kicks')
    sh_l, sh_v = par('total_shots')
    sot_l, sot_v = par('shots_on_target')
    fo_l, fo_v = par('fouls')
    yc_l, yc_v = par('yellow_cards')

    return {
        'liga': liga_id, 'liga_nombre': liga_cfg['nombre'],
        'fecha': fecha, 'hora_peru': hora,
        'local': m['home_team']['name'], 'visitante': m['away_team']['name'],
        'goles_l': _num(gl), 'goles_v': _num(gv),
        'resultado': f'{gl}-{gv}' if gl is not None else '',
        'estado': m['status'],
        'jornada': _num(m.get('matchday')),
        'fase': m.get('stage_name') or '',
        'fuente': 'thestatsapi',
        'xg_l': _num(xg_l), 'xg_v': _num(xg_v),
        'corners_l': _num(cor_l), 'corners_v': _num(cor_v),
        'shots_l': _num(sh_l), 'shots_v': _num(sh_v),
        'shots_on_target_l': _num(sot_l), 'shots_on_target_v': _num(sot_v),
        'fouls_l': _num(fo_l), 'fouls_v': _num(fo_v),
        'yellow_cards_l': _num(yc_l), 'yellow_cards_v': _num(yc_v),
    }


def _orden_bookmakers(bookmakers):
    por_nombre = {b['bookmaker']: b for b in bookmakers}
    orden = [n for n in BOOKMAKERS_PREFERIDOS if n in por_nombre]
    orden += [n for n in por_nombre if n not in BOOKMAKERS_PREFERIDOS]
    return por_nombre, orden


def _precio(nodo):
    if not nodo:
        return ''
    v = nodo.get('last_seen')
    try:
        return round(float(v), 2) if v is not None else ''
    except (TypeError, ValueError):
        return ''


def _buscar_precio(bookmakers, market_key, *path):
    """
    Busca un precio en <market_key> siguiendo <path> (claves anidadas,
    p.ej. 'home' o '2.5','over'), probando cada bookmaker en orden de
    preferencia (Pinnacle > Bet365 > resto) hasta encontrar un valor.
    No asume que un solo bookmaker cubre todos los mercados/lineas.
    """
    por_nombre, orden = _orden_bookmakers(bookmakers)
    for nombre in orden:
        nodo = por_nombre[nombre]['markets'].get(market_key, {})
        for clave in path:
            if not isinstance(nodo, dict):
                nodo = None
                break
            nodo = nodo.get(clave)
        precio = _precio(nodo) if isinstance(nodo, dict) else ''
        if precio != '':
            return precio
    return ''


def _buscar_precio_linea_dinamica(bookmakers, market_key, lado='over'):
    """
    Para mercados con línea VARIABLE por partido (a diferencia de
    match_corners, que casi siempre trae 8.5/9.5 fijas): match_shots,
    match_shots_on_target y total_cards. Cada partido puede traer una línea
    distinta (ej. 22.5, 23.5, 26.5 en tiros totales), así que en vez de
    buscar una clave fija se toma la única línea que haya bajo ese
    market_key, del lado pedido.
    Devuelve (linea: float|None, precio: str|'').
    """
    por_nombre, orden = _orden_bookmakers(bookmakers)
    for nombre in orden:
        nodo = por_nombre[nombre]['markets'].get(market_key, {})
        if not isinstance(nodo, dict) or not nodo:
            continue
        for linea_str, lados in nodo.items():
            if not isinstance(lados, dict):
                continue
            precio = _precio(lados.get(lado))
            if precio != '':
                try:
                    return float(linea_str), precio
                except (TypeError, ValueError):
                    continue
    return None, ''


def fila_proximos(liga_id, liga_cfg, m, odds):
    fecha, hora = utc_a_peru(m['utc_date'])
    bookmakers = (odds or {}).get('bookmakers', [])

    shots_linea, shots_precio = _buscar_precio_linea_dinamica(bookmakers, 'match_shots', 'over')
    sot_linea, sot_precio = _buscar_precio_linea_dinamica(bookmakers, 'match_shots_on_target', 'over')
    cards_linea, cards_precio = _buscar_precio_linea_dinamica(bookmakers, 'total_cards', 'over')

    return {
        'liga': liga_id, 'liga_nombre': liga_cfg['nombre'],
        'fecha': fecha, 'hora_peru': hora,
        'local': m['home_team']['name'], 'visitante': m['away_team']['name'],
        'goles_l': '', 'goles_v': '', 'resultado': '',
        'estado': m['status'],
        'jornada': _num(m.get('matchday')),
        'fase': m.get('stage_name') or '',
        'fuente': 'thestatsapi',
        'c1': _buscar_precio(bookmakers, 'match_odds', 'home'),
        'cx': _buscar_precio(bookmakers, 'match_odds', 'draw'),
        'c2': _buscar_precio(bookmakers, 'match_odds', 'away'),
        'shots_linea': shots_linea if shots_linea is not None else '',
        'shots_over_precio': shots_precio,
        'sot_linea': sot_linea if sot_linea is not None else '',
        'sot_over_precio': sot_precio,
        'cards_linea': cards_linea if cards_linea is not None else '',
        'cards_over_precio': cards_precio,
        'over_2.5': _buscar_precio(bookmakers, 'total_goals', '2.5', 'over'),
        'under_2.5': _buscar_precio(bookmakers, 'total_goals', '2.5', 'under'),
        'btts_si': _buscar_precio(bookmakers, 'btts', 'yes'),
        'btts_no': _buscar_precio(bookmakers, 'btts', 'no'),
        'corners_over_8.5': _buscar_precio(bookmakers, 'match_corners', '8.5', 'over'),
        'corners_over_9.5': _buscar_precio(bookmakers, 'match_corners', '9.5', 'over'),
    }


# ── Modo diario ──────────────────────────────────────────────────────

def correr_diario(client, ligas, ruta_prox):
    llamadas_est = len(ligas) * PROMEDIO_LLAMADAS_DIARIO_LIGA
    minutos_est = llamadas_est * SEGUNDOS_POR_LLAMADA_EST / 60
    print(f'\n📅 Modo DIARIO — {len(ligas)} ligas, estimado ~{llamadas_est:.0f} llamadas '
          f'(~{minutos_est:.0f} min) — variable según partidos de la semana; se muestra el real al final')

    crear_csv_vacio(ruta_prox, COLUMNAS_PROX)  # snapshot fresco cada dia
    hoy = hoy_peru()
    en_7_dias = hoy + timedelta(days=7)
    llamadas_inicio = client.total_requests
    total_prox = total_con_cuotas = 0

    for liga_id, cfg in ligas.items():
        print(f'\n  {cfg["nombre"]} ({liga_id}):')
        try:
            proximos = client.get_matches(
                liga_id, status='scheduled',
                date_from=hoy.isoformat(), date_to=en_7_dias.isoformat(),
            )
        except TheStatsAPIError as e:
            print(f'    ⚠️ {e}')
            continue

        filas, n_cuotas = [], 0
        for m in proximos:
            odds = None
            if cfg.get('odds_available') and m.get('odds_available'):
                try:
                    odds = client.get_match_odds(m['id'])
                    n_cuotas += 1
                except TheStatsAPIError:
                    pass
            filas.append(fila_proximos(liga_id, cfg, m, odds))

        append_csv(ruta_prox, filas, COLUMNAS_PROX)
        total_prox += len(filas)
        total_con_cuotas += n_cuotas
        print(f'    ✅ {len(filas)} próximos, {n_cuotas} con cuotas')

    llamadas_usadas = client.total_requests - llamadas_inicio
    print(f'\n✅ Modo diario: {total_prox} próximos ({total_con_cuotas} con cuotas), '
          f'{llamadas_usadas} llamadas reales → {ruta_prox}')


# ── Modo historico ───────────────────────────────────────────────────

def _claves_existentes(ruta_hist, liga_id):
    """(fecha, local, visitante) ya guardados para esta liga en historico.csv -- para resumir a mitad de liga sin duplicar."""
    claves = set()
    if not os.path.exists(ruta_hist):
        return claves
    with open(ruta_hist, encoding='utf-8') as f:
        for row in csv.DictReader(f):
            if row.get('liga') == liga_id:
                claves.add((row.get('fecha'), row.get('local'), row.get('visitante')))
    return claves


def descargar_historico_liga(client, liga_id, cfg, inicio_sesion, limite, ruta_hist):
    """
    Descarga y GUARDA cada partido individualmente (append inmediato a
    ruta_hist) a medida que se procesa -- si la sesion se corta a mitad
    de liga, el progreso ya hecho queda en el CSV. La proxima sesion lee
    _claves_existentes() y salta lo ya descargado en vez de reintentar
    la liga entera.
    Devuelve (nuevos_esta_sesion, completa). completa=False => faltan
    partidos por bajar, seguira en la proxima sesion (no checkpointear).
    """
    if not cfg.get('has_team_stats'):
        return 0, True

    hoy = hoy_peru()
    hace_365 = (hoy - timedelta(days=365)).isoformat()
    try:
        terminados = client.get_matches(
            liga_id, status='finished',
            date_from=hace_365, date_to=hoy.isoformat(),
        )
    except TheStatsAPIError as e:
        print(f'    ⚠️ matches: {e} — se reintentará en la próxima sesión')
        return 0, False

    ya = _claves_existentes(ruta_hist, liga_id)
    nuevos = 0
    ultimo_heartbeat = time.monotonic()

    for i, m in enumerate(terminados, 1):
        if time.monotonic() - inicio_sesion > limite:
            return nuevos, False

        fecha, _hora = utc_a_peru(m['utc_date'])
        clave = (fecha, m['home_team']['name'], m['away_team']['name'])
        if clave in ya:
            continue

        stats = None
        try:
            stats = client.get_match_stats(m['id'])
        except TheStatsAPIError:
            pass
        fila = fila_historico(liga_id, cfg, m, stats)
        append_csv(ruta_hist, [fila], COLUMNAS_HIST)
        ya.add(clave)
        nuevos += 1

        # Heartbeat: sin esto, una liga sin 429 no imprime nada durante
        # toda su descarga (10-25+ min) y algo en el entorno mata
        # procesos en background que quedan callados demasiado tiempo.
        if time.monotonic() - ultimo_heartbeat > 30:
            print(f'    … {i}/{len(terminados)} partidos revisados ({nuevos} nuevos guardados)', flush=True)
            ultimo_heartbeat = time.monotonic()

    return nuevos, True


def correr_historico(client, ligas, ruta_hist, session_minutos, ruta_checkpoint):
    cp = cargar_checkpoint(ruta_checkpoint)
    completadas = cp.setdefault('historico', {})
    pendientes = {k: v for k, v in ligas.items() if k not in completadas}

    llamadas_previas = [c['llamadas'] for c in completadas.values() if c.get('llamadas')]
    promedio = (sum(llamadas_previas) / len(llamadas_previas)) if llamadas_previas else PROMEDIO_LLAMADAS_LIGA_DEFAULT
    fuente_promedio = 'calibrado con ligas ya completadas' if llamadas_previas else 'estimado con el test inicial MLS/BSA'

    llamadas_restantes_est = len(pendientes) * promedio
    horas_restantes_est = llamadas_restantes_est * SEGUNDOS_POR_LLAMADA_EST / 3600
    ligas_por_sesion_exacto = (session_minutos * 60 / SEGUNDOS_POR_LLAMADA_EST) / promedio

    print('\n📊 Estimación (modo HISTÓRICO):')
    print(f'   Ligas completadas: {len(completadas)}/{len(ligas)}')
    print(f'   Ligas pendientes: {len(pendientes)}')
    print(f'   Promedio llamadas/liga: ~{promedio:.0f} ({fuente_promedio})')
    print(f'   Llamadas estimadas restantes (todas las sesiones): ~{llamadas_restantes_est:.0f}')
    print(f'   Tiempo estimado restante (todas las sesiones): ~{horas_restantes_est:.1f} horas')
    if ligas_por_sesion_exacto < 1:
        minutos_para_una_liga = promedio * SEGUNDOS_POR_LLAMADA_EST / 60
        print(f'   Esta sesión (~{session_minutos} min) NO alcanza para completar ni una liga '
              f'(se necesitan ~{minutos_para_una_liga:.0f} min/liga en promedio) — quedará "incompleta" y se reintentará')
    else:
        print(f'   Esta sesión (~{session_minutos} min) alcanzaría para ~{int(ligas_por_sesion_exacto)} liga(s) más')

    if not pendientes:
        print('\n✅ No hay ligas pendientes — el histórico ya está completo según el checkpoint.')
        return

    if not os.path.exists(ruta_hist):
        crear_csv_vacio(ruta_hist, COLUMNAS_HIST)

    inicio_sesion = time.monotonic()
    limite = session_minutos * 60
    procesadas_sesion = 0

    nuevos_sesion_total = 0

    for liga_id, cfg in pendientes.items():
        if time.monotonic() - inicio_sesion > limite:
            print(f'\n⏰ Límite de sesión ({session_minutos} min) alcanzado — deteniendo. Checkpoint guardado, reanuda con el mismo comando.')
            break

        print(f'\n  {cfg["nombre"]} ({liga_id}):')
        llamadas_antes = client.total_requests
        nuevos, completa = descargar_historico_liga(client, liga_id, cfg, inicio_sesion, limite, ruta_hist)
        llamadas_liga = client.total_requests - llamadas_antes
        nuevos_sesion_total += nuevos

        if not completa:
            print(f'    ⏸️ liga incompleta ({nuevos} partidos nuevos guardados esta sesión, ya en historico.csv) '
                  f'— continúa exactamente donde quedó en la próxima sesión, sin duplicar')
            break

        total_liga = len(_claves_existentes(ruta_hist, liga_id))
        completadas[liga_id] = {
            'partidos': total_liga,
            'llamadas': llamadas_liga,
            'fecha': datetime.now(PERU_TZ).isoformat(),
        }
        guardar_checkpoint(ruta_checkpoint, cp)
        procesadas_sesion += 1
        print(f'    ✅ {total_liga} partidos con stats ({llamadas_liga} llamadas esta sesión) → checkpoint guardado')

    print(f'\n✅ Sesión terminada: {procesadas_sesion} liga(s) nueva(s) completada(s), {nuevos_sesion_total} partidos nuevos guardados en total.')
    print(f'   Total acumulado: {len(completadas)}/{len(ligas)} ligas en checkpoint.')
    if len(completadas) < len(ligas):
        print(f'   Corré el mismo comando de nuevo para continuar con las {len(ligas) - len(completadas)} ligas restantes.')


# ── Main ──────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    modo = ap.add_mutually_exclusive_group(required=True)
    modo.add_argument('--historico', action='store_true', help='Descarga stats de partidos terminados (checkpointed, por sesiones)')
    modo.add_argument('--diario', action='store_true', help='Descarga proximos 7 dias + cuotas (rapido, para correr cada dia)')
    ap.add_argument('--comp-ids', help='Lista de competition_id separados por coma (subconjunto de prueba, sobreescribe el default de cada modo)')
    ap.add_argument('--session-minutos', type=int, default=120, help='Solo --historico: minutos maximos por sesion')
    ap.add_argument('--historico-out', default='Data/partidos/historico.csv')
    ap.add_argument('--proximos-out', default='Data/partidos/proximos.csv')
    ap.add_argument('--checkpoint-out', default=CHECKPOINT_PATH, help='Solo --historico: ruta del checkpoint (usar una de prueba evita marcar ligas como completadas sin datos reales en el historico de produccion)')
    args = ap.parse_args()

    if args.comp_ids:
        ids = [c.strip() for c in args.comp_ids.split(',')]
        ligas = {k: LIGAS[k] for k in ids if k in LIGAS}
        faltantes = set(ids) - set(ligas)
        if faltantes:
            print(f'⚠️ comp_ids no encontrados en LIGAS: {faltantes}')
    else:
        ligas = LIGAS  # las 15 ligas prioritarias de configuracion.py, en ambos modos

    print('\n' + '=' * 60)
    print(f'  SportPicks Ligas — TheStatsAPI — modo {"DIARIO" if args.diario else "HISTÓRICO"}')
    print('=' * 60)
    print(f'  Fecha Perú: {hoy_peru()}')
    print(f'  Ligas objetivo: {len(ligas)}')

    client = TheStatsClient(API_THESTATS)

    if args.diario:
        correr_diario(client, ligas, args.proximos_out)
    else:
        correr_historico(client, ligas, args.historico_out, args.session_minutos, args.checkpoint_out)

    print('\n' + '=' * 60)


if __name__ == '__main__':
    main()
