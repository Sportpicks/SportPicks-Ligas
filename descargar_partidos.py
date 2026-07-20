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
                GitHub Actions). Por defecto usa un subconjunto reducido de
                ligas (DEFAULT_DIARIO_COMP_IDS, las 7 del pipeline original)
                en vez de las 149. Calibrado empiricamente (test MLS+BSA,
                2026-07-20): ~53 llamadas para 2 ligas => las 7 ligas
                completas usan realisticamente ~150-250 llamadas/dia
                (~15-20 min con el rate limit real de ~12 req/min), no las
                50-80 originalmente estimadas a ojo. Aceptado como costo
                operativo normal de un cron diario.

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

# Ligas que procesa el modo diario por defecto (las 7 que ya usaba el
# pipeline original). Uso real medido (2026-07-20, MLS+BSA): ~53 llamadas
# para 2 ligas => ~150-250 llamadas/dia para las 7 (~15-20 min), no 50-80.
# El modo --historico si cubre las 149 ligas del CSV, por sesiones.
DEFAULT_DIARIO_COMP_IDS = [
    'comp_3498',  # UEFA Champions League
    'comp_7739',  # UEFA Europa League
    'comp_1615',  # CONMEBOL Sudamericana
    'comp_0499',  # CONMEBOL Libertadores
    'comp_4795',  # Brasileirao Serie A
    'comp_9799',  # MLS
    'comp_6981',  # Liga 1 (Peru)
]

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
    ov = (stats or {}).get('overview', {})

    def par(campo):
        d = ov.get(campo, {}).get('all', {})
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


def fila_proximos(liga_id, liga_cfg, m, odds):
    fecha, hora = utc_a_peru(m['utc_date'])
    bookmakers = (odds or {}).get('bookmakers', [])

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

def descargar_historico_liga(client, liga_id, cfg, inicio_sesion, limite):
    """Devuelve (filas, completa). completa=False => no checkpointear, reintentar entera la proxima sesion."""
    if not cfg.get('has_team_stats'):
        return [], True

    hoy = hoy_peru()
    hace_365 = (hoy - timedelta(days=365)).isoformat()
    try:
        terminados = client.get_matches(
            liga_id, status='finished',
            date_from=hace_365, date_to=hoy.isoformat(),
        )
    except TheStatsAPIError as e:
        print(f'    ⚠️ matches: {e} — se reintentará en la próxima sesión')
        return [], False

    filas = []
    for m in terminados:
        if time.monotonic() - inicio_sesion > limite:
            return filas, False
        stats = None
        try:
            stats = client.get_match_stats(m['id'])
        except TheStatsAPIError:
            pass
        filas.append(fila_historico(liga_id, cfg, m, stats))
    return filas, True


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

    for liga_id, cfg in pendientes.items():
        if time.monotonic() - inicio_sesion > limite:
            print(f'\n⏰ Límite de sesión ({session_minutos} min) alcanzado — deteniendo. Checkpoint guardado, reanuda con el mismo comando.')
            break

        print(f'\n  {cfg["nombre"]} ({liga_id}):')
        llamadas_antes = client.total_requests
        filas, completa = descargar_historico_liga(client, liga_id, cfg, inicio_sesion, limite)

        if not completa:
            print('    ⏸️ liga incompleta (se cortó el tiempo de sesión a mitad de liga) — se reintentará entera en la próxima sesión')
            break

        append_csv(ruta_hist, filas, COLUMNAS_HIST)
        llamadas_liga = client.total_requests - llamadas_antes
        completadas[liga_id] = {
            'partidos': len(filas),
            'llamadas': llamadas_liga,
            'fecha': datetime.now(PERU_TZ).isoformat(),
        }
        guardar_checkpoint(ruta_checkpoint, cp)
        procesadas_sesion += 1
        print(f'    ✅ {len(filas)} partidos con stats ({llamadas_liga} llamadas) → checkpoint guardado')

    print(f'\n✅ Sesión terminada: {procesadas_sesion} liga(s) nueva(s) completada(s).')
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
    elif args.diario:
        ligas = {k: LIGAS[k] for k in DEFAULT_DIARIO_COMP_IDS if k in LIGAS}
    else:
        ligas = LIGAS

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
