# -*- coding: utf-8 -*-
"""
thestats_client.py
Cliente reutilizable para TheStatsAPI (https://api.thestatsapi.com).

Endpoints confirmados empiricamente contra la API real (no hay
documentacion oficial disponible en el proyecto):

  GET /football/competitions                                  (paginado)
  GET /football/competitions/{competition_id}                  (incluye current_season_id)
  GET /football/competitions/{competition_id}/seasons
  GET /football/competitions/{competition_id}/seasons/{season_id}/standings
  GET /football/matches?competition_id&season_id&status&date_from&date_to&page&per_page
  GET /football/matches/{match_id}/stats
  GET /football/matches/{match_id}/odds
  GET /football/matches/{match_id}/lineups

  NOTA sobre injuries: se probaron /teams/{id}/injuries,
  /injuries?team_id=, /team-injuries?team_id= (con y sin season_id) y
  todas devuelven 404 "Route not found". Esta API no expone un
  endpoint de lesiones en ninguna ruta razonable probada. get_injuries()
  queda implementado contra la ruta mas plausible (/teams/{id}/injuries)
  pero lanzara TheStatsAPIError si de verdad no existe -- no se debe
  asumir que funciona sin volver a verificarlo.

per_page maximo confirmado: 100 (per_page=500 responde 400 BAD_REQUEST).
"""
import time
import collections
import requests


class TheStatsAPIError(Exception):
    def __init__(self, status_code, code, message):
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(f'[{status_code}] {code}: {message}')


class TheStatsClient:
    BASE_URL = 'https://api.thestatsapi.com/api/football'
    MAX_PER_PAGE = 100

    def __init__(self, api_key, max_req_per_seg=5, max_retries=5, timeout=15):
        self.api_key = api_key
        self.max_req_per_seg = max_req_per_seg
        self.max_retries = max_retries
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({'Authorization': f'Bearer {api_key}'})
        # timestamps (monotonic) de las ultimas peticiones, para el techo local (max_req_per_seg)
        self._timestamps = collections.deque()
        # estado del rate limit real del servidor, leido de los headers
        # x-ratelimit-remaining / x-ratelimit-reset de la ultima respuesta.
        # Confirmado empiricamente: x-ratelimit-limit=12 con ventana ~60s,
        # muy por debajo de cualquier limite razonable de req/seg -- por
        # eso el throttle real se basa en estos headers, no en un req/seg fijo.
        self._rate_remaining = None
        self._rate_reset = None
        self._ultimo_envio = None  # time.time() del ultimo request enviado, para repartir la cuota
        # contador de peticiones HTTP realmente enviadas (incluye reintentos),
        # usado para calibrar estimaciones de llamadas/tiempo en el pipeline.
        self.total_requests = 0

    # ── Infraestructura ──────────────────────────────────────────

    def _esperar_turno(self):
        """
        Bloquea por el techo local (max_req_per_seg) y por el rate limit real
        del servidor. En vez de disparar peticiones a maxima velocidad hasta
        que remaining llega a 0 (lo que vacia la cuota en rafaga y despues
        obliga a esperar la ventana completa), reparte las peticiones
        restantes uniformemente en el tiempo que falta para el reset -- eso
        evita la mayoria de los 429 en vez de solo recuperarse de ellos.
        """
        ahora_mono = time.monotonic()
        while self._timestamps and ahora_mono - self._timestamps[0] >= 1.0:
            self._timestamps.popleft()
        if len(self._timestamps) >= self.max_req_per_seg:
            espera = 1.0 - (ahora_mono - self._timestamps[0])
            if espera > 0:
                time.sleep(espera)

        ahora = time.time()
        if self._rate_remaining is not None and self._rate_reset:
            tiempo_restante = self._rate_reset - ahora
            if self._rate_remaining <= 0:
                if tiempo_restante > 0:
                    print(f'    ⏳ cuota agotada — esperando {tiempo_restante:.0f}s a que reinicie', flush=True)
                    time.sleep(tiempo_restante + 0.5)
            elif tiempo_restante > 0 and self._ultimo_envio is not None:
                intervalo_ideal = tiempo_restante / self._rate_remaining
                transcurrido = ahora - self._ultimo_envio
                espera = intervalo_ideal - transcurrido
                if espera > 0:
                    time.sleep(espera)

        self._timestamps.append(time.monotonic())
        self._ultimo_envio = time.time()

    def _guardar_rate_limit(self, headers):
        remaining = headers.get('x-ratelimit-remaining')
        reset = headers.get('x-ratelimit-reset')
        if remaining is not None:
            try:
                self._rate_remaining = int(remaining)
            except ValueError:
                pass
        if reset is not None:
            try:
                self._rate_reset = float(reset)
            except ValueError:
                pass

    def _request(self, path, params=None):
        url = f'{self.BASE_URL}{path}'
        intento = 0
        while True:
            self._esperar_turno()
            try:
                r = self._session.get(url, params=params, timeout=self.timeout)
                self.total_requests += 1
            except requests.RequestException:
                intento += 1
                if intento > self.max_retries:
                    raise
                time.sleep(min(2 ** intento, 30))
                continue

            self._guardar_rate_limit(r.headers)

            if r.status_code in (429, 503):
                intento += 1
                if intento > self.max_retries:
                    r.raise_for_status()
                retry_after = r.headers.get('Retry-After')
                espera = float(retry_after) if retry_after else min(2 ** intento, 30)
                print(f'    ⏳ {r.status_code} en {path} — reintento {intento}/{self.max_retries} en {espera:.0f}s', flush=True)
                time.sleep(espera)
                continue

            if not r.ok:
                try:
                    err = r.json().get('error', {})
                except ValueError:
                    err = {}
                raise TheStatsAPIError(
                    r.status_code,
                    err.get('code', 'UNKNOWN'),
                    err.get('message', r.text[:200]),
                )

            return r.json()

    def _paginar(self, path, params):
        params = dict(params or {})
        params.setdefault('per_page', self.MAX_PER_PAGE)
        page = 1
        resultado = []
        while True:
            params['page'] = page
            body = self._request(path, params)
            datos = body.get('data', [])
            resultado.extend(datos)
            meta = body.get('meta', {})
            total_pages = meta.get('total_pages', page)
            if page >= total_pages:
                break
            page += 1
        return resultado

    # ── Endpoints ─────────────────────────────────────────────────

    def get_competitions(self):
        """Lista TODAS las competiciones disponibles, paginando hasta la ultima pagina."""
        return self._paginar('/competitions', {})

    def get_competition(self, comp_id):
        """Detalle de una competicion (incluye current_season_id)."""
        return self._request(f'/competitions/{comp_id}')['data']

    def get_seasons(self, comp_id):
        """Lista de temporadas de una competicion (mas reciente primero)."""
        return self._request(f'/competitions/{comp_id}/seasons')['data']

    def get_matches(self, comp_id, season_id=None, status=None,
                     date_from=None, date_to=None):
        """
        Lista partidos de una competicion, paginando hasta la ultima pagina.
        season_id es opcional: si se omite, la API busca en todas las temporadas.
        status: 'scheduled' | 'finished' (u otros valores soportados por la API).
        date_from / date_to: 'YYYY-MM-DD', filtran por utc_date.
        """
        params = {'competition_id': comp_id}
        if season_id:
            params['season_id'] = season_id
        if status:
            params['status'] = status
        if date_from:
            params['date_from'] = date_from
        if date_to:
            params['date_to'] = date_to
        return self._paginar('/matches', params)

    def get_match_stats(self, match_id):
        """Estadisticas de equipo de un partido (posesion, xG, tiros, corners, faltas, tarjetas...)."""
        return self._request(f'/matches/{match_id}/stats')['data']

    def get_match_odds(self, match_id):
        """Cuotas de casas de apuestas disponibles para un partido."""
        return self._request(f'/matches/{match_id}/odds')['data']

    def get_lineups(self, match_id):
        """Alineaciones (titulares/suplentes) de un partido."""
        return self._request(f'/matches/{match_id}/lineups')['data']

    def get_injuries(self, team_id):
        """
        Lesiones de un equipo. NO CONFIRMADO: todas las rutas probadas
        (/teams/{id}/injuries, /injuries?team_id=, /team-injuries?team_id=)
        devolvieron 404 "Route not found" en las pruebas realizadas.
        Se deja esta ruta como mejor intento; puede lanzar TheStatsAPIError.
        """
        return self._request(f'/teams/{team_id}/injuries')['data']

    def get_standings(self, comp_id, season_id=None):
        """Tabla de posiciones. Si season_id es None, usa la temporada actual de la competicion."""
        if not season_id:
            season_id = self.get_competition(comp_id)['current_season_id']
        return self._request(f'/competitions/{comp_id}/seasons/{season_id}/standings')['data']
