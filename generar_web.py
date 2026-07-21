# -*- coding: utf-8 -*-
"""
generar_web.py
Genera docs/index.html — web multi-liga de SportPicks (mismo estilo visual
que el proyecto Mundial 2026, adaptado a múltiples ligas de clubes).
"""
import os, sys, json
from datetime import datetime, timezone, timedelta

RAIZ = os.path.dirname(os.path.abspath(__file__))
os.chdir(RAIZ)
sys.path.insert(0, RAIZ)
from configuracion import LIGAS, ZONA_PERU

PERU_TZ = timezone(timedelta(hours=ZONA_PERU))

# Claves = competition_id de TheStatsAPI (ver configuracion.THESTATS_LIGAS_PRIORITARIAS)
LIGA_COLOR = {
    'comp_4540':   '#7dd3fc',  # ARG
    'comp_4795':   '#34d399',  # BSA
    'comp_720692': '#fde047',  # COL
    'comp_08478':  '#fb923c',  # CAF
    'comp_0499':   '#fbbf24',  # CLB
    'comp_1615':   '#f97316',  # CSU
    'comp_7938':   '#f87171',  # DAN
    'comp_1992':   '#38bdf8',  # NOR
    'comp_6981':   '#fb7185',  # LP1
    'comp_298265': '#4ade80',  # MXA
    'comp_1917':   '#facc15',  # ECU
    'comp_6387':   '#c084fc',  # SCO
    'comp_3498':   '#60a5fa',  # UCL
    'comp_408698': '#f472b6',  # UCO
    'comp_9799':   '#a78bfa',  # MLS
}
LIGA_EMOJI = {k: v['emoji'] for k, v in LIGAS.items()}
LIGA_NOMBRE = {k: v['nombre'] for k, v in LIGAS.items()}
LIGA_CODIGO = {k: v['codigo'] for k, v in LIGAS.items()}


def cargar_json(ruta, default):
    if not os.path.exists(ruta):
        return default
    with open(ruta, encoding='utf-8') as f:
        return json.load(f)


def mejor_apuesta(p):
    """Elige el mercado más recomendable de un partido a partir de las
    probabilidades y EV del modelo (1X2, over/under 2.5)."""
    local = p.get('local', '')
    visitante = p.get('visitante', '')
    candidatos = [
        ('1', f'Victoria {local}', p.get('p1', 0), p.get('ev_1', 0), '⚽', '1X2'),
        ('X', 'Empate', p.get('px', 0), p.get('ev_x', 0), '🤝', '1X2'),
        ('2', f'Victoria {visitante}', p.get('p2', 0), p.get('ev_2', 0), '⚽', '1X2'),
        ('over25', 'Más de 2.5 goles', p.get('over_2.5', 0), p.get('ev_over25', 0), '🥅', 'Goles'),
        ('under25', 'Menos de 2.5 goles', p.get('under_2.5', 0), p.get('ev_under25', 0), '🔒', 'Goles'),
    ]
    validos = [c for c in candidatos if c[2] >= 45]
    if not validos:
        validos = candidatos
    # Prioriza EV positivo más alto; si no hay, la probabilidad más alta.
    con_ev = [c for c in validos if c[3] > 0]
    elegido = max(con_ev, key=lambda c: c[3]) if con_ev else max(validos, key=lambda c: c[2])
    _, mercado, prob, ev, emoji, categoria = elegido
    if prob >= 70:
        nivel, texto = 'muy-alta', 'Alta confianza'
    elif prob >= 55:
        nivel, texto = 'alta', 'Confianza media'
    else:
        nivel, texto = 'media', 'Especulativo'
    return {
        'mercado': mercado, 'prob': round(prob, 1), 'ev': round(ev, 3),
        'emoji': emoji, 'categoria': categoria, 'nivel': nivel, 'texto': texto,
    }


def preparar_partidos(partidos):
    out = []
    for p in partidos:
        q = dict(p)
        q['liga_emoji'] = LIGA_EMOJI.get(p.get('liga'), '⚽')
        q['liga_color'] = LIGA_COLOR.get(p.get('liga'), '#60a5fa')
        q['mejor_apuesta'] = mejor_apuesta(p)
        q['marcador_prob'] = (p.get('marcador_prob') or [])[:3]
        out.append(q)
    out.sort(key=lambda p: (p.get('fecha', ''), p.get('hora', '')))
    return out


def resumen_picks(picks):
    if not picks:
        return {'n': 0, 'prob': 0, 'cuota': 0, 'ev': 0}
    n = len(picks)
    prob = round(sum(p.get('prob', 0) for p in picks) / n)
    cuota = round(sum(p.get('cuota_display', p.get('cuota', 0)) for p in picks) / n, 2)
    ev = sum(1 for p in picks if p.get('ev', 0) and p['ev'] > 0.05)
    return {'n': n, 'prob': prob, 'cuota': cuota, 'ev': ev}


CSS = """
:root{--bg:#0d1220;--panel:#161d31;--panel2:#1c2540;--tx:#eef1f8;--tx2:#9aa5c0;
--lin:#2a3554;--v:#34d399;--e:#fbbf24;--d:#fb7185;--ac:#60a5fa;--pu:#a78bfa;--or:#fb923c;--go:#ffd700}
*{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth;scroll-padding-top:60px}
body{background:var(--bg);color:var(--tx);font:15px/1.6 system-ui,sans-serif;padding-bottom:48px}
.wrap{max-width:1100px;margin:0 auto;padding:0 16px}
nav{position:sticky;top:0;z-index:50;background:rgba(13,18,32,.95);backdrop-filter:blur(8px);border-bottom:1px solid var(--lin)}
nav .wrap{display:flex;gap:4px;overflow-x:auto;padding:10px 16px;scrollbar-width:none;align-items:center}
nav a{color:var(--tx2);text-decoration:none;font-size:.83rem;font-weight:600;padding:5px 12px;border-radius:999px;white-space:nowrap}
nav a:hover{color:var(--tx);background:var(--panel2)}
nav .tg-nav{background:#0088cc;color:#fff;border-radius:6px;padding:4px 12px;font-weight:700}
.hero-wrap{background:linear-gradient(180deg,#0d1a2e 0%,#0d1220 100%);border-bottom:1px solid #1a2a44;padding:24px 0 18px}
.hero-titulo{font-size:1.5rem;font-weight:800;text-align:center;color:#eef1f8;margin-bottom:4px}
.hero-sub{font-size:.82rem;color:#9aa5c0;text-align:center;margin-bottom:16px}
.hero-btns{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:12px}
.hero-btn-pub{background:#34d399;color:#0d1220;border-radius:12px;padding:13px 8px;font-weight:800;font-size:.88rem;text-decoration:none;text-align:center;display:block;box-shadow:0 2px 10px rgba(52,211,153,.3)}
.hero-btn-prem{background:linear-gradient(135deg,#a78bfa,#7c3aed);color:#fff;border-radius:12px;padding:13px 8px;font-weight:800;font-size:.88rem;text-decoration:none;text-align:center;display:block;box-shadow:0 2px 10px rgba(167,139,250,.3)}
.hero-tg{display:flex;align-items:center;gap:10px;background:rgba(0,136,204,.12);border:1px solid #0088cc;border-radius:12px;padding:10px 12px;text-decoration:none;margin-bottom:4px}
.hero-tg-title{color:#eef1f8;font-weight:700;font-size:.85rem}
.hero-tg-sub{color:var(--tx2);font-size:.72rem;margin-top:1px}
.badges{display:flex;flex-wrap:wrap;gap:6px;justify-content:center;margin-top:12px}
.badge{display:inline-block;background:var(--panel2);border:1px solid var(--lin);color:var(--tx2);border-radius:999px;padding:2px 12px;font-size:.76rem}
.badge.on{border-color:var(--ac);color:var(--ac)}
h2{font-size:1.1rem;margin:32px 0 12px;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
h2 small{color:var(--tx2);font-weight:400;font-size:.82rem}
.ligas{display:flex;gap:6px;overflow-x:auto;padding:2px 2px 8px;scrollbar-width:none}
.ligas button{flex:0 0 auto;background:var(--panel);border:1px solid var(--lin);color:var(--tx2);border-radius:999px;padding:6px 14px;font-size:.82rem;font-weight:600;cursor:pointer;display:flex;align-items:center;gap:5px}
.ligas button.sel{background:var(--ac);border-color:var(--ac);color:#0d1220}
.dias{display:flex;gap:6px;overflow-x:auto;padding:2px 2px 10px;scrollbar-width:none}
.dias button{flex:0 0 auto;background:var(--panel);border:1px solid var(--lin);color:var(--tx2);border-radius:999px;padding:5px 13px;font-size:.82rem;font-weight:600;cursor:pointer}
.dias button.sel{background:var(--ac);border-color:var(--ac);color:#0d1220}
.dias button.eshoy:not(.sel){border-color:var(--ac);color:var(--ac)}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:14px}
.card{background:var(--panel);border:1px solid var(--lin);border-radius:14px;padding:16px}
.card.hoy{border-color:var(--ac)}
.enc{display:flex;justify-content:space-between;align-items:center;font-size:.76rem;color:var(--tx2);margin-bottom:8px;flex-wrap:wrap;gap:4px}
.liga-pill{display:inline-flex;align-items:center;gap:5px;font-size:.72rem;font-weight:700;border-radius:999px;padding:2px 9px}
.eqs{display:flex;justify-content:space-between;align-items:center;gap:8px;font-weight:600;font-size:.98rem;margin-top:2px}
.eqs span{min-width:0}
.eqs span:last-child{text-align:right}
.vs{color:var(--tx2);font-weight:400;font-size:.8rem;padding:0 6px}
.barra{display:flex;height:8px;border-radius:6px;overflow:hidden;margin:10px 0 3px;background:var(--panel2)}
.barra i{display:block;height:100%}
.leyenda{display:flex;justify-content:space-between;font-size:.76rem;margin-bottom:6px}
.vd{color:var(--v)}.em{color:var(--e)}.dr{color:var(--d)}
.mejor-apuesta{border-radius:10px;padding:10px 12px;margin:8px 0;display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap}
.mejor-apuesta.muy-alta{background:rgba(52,211,153,0.12);border:1px solid var(--v)}
.mejor-apuesta.alta{background:rgba(251,191,36,0.10);border:1px solid var(--e)}
.mejor-apuesta.media{background:rgba(251,146,60,0.10);border:1px solid var(--or)}
.mejor-apuesta .ma-label{font-size:.72rem;color:var(--tx2);margin-bottom:2px}
.mejor-apuesta .ma-mercado{font-size:.88rem;font-weight:700}
.mejor-apuesta .ma-right{text-align:right;flex-shrink:0}
.mejor-apuesta .ma-prob{font-size:1.1rem;font-weight:700}
.mejor-apuesta.muy-alta .ma-prob{color:var(--v)}
.mejor-apuesta.alta .ma-prob{color:var(--e)}
.mejor-apuesta.media .ma-prob{color:var(--or)}
.mejor-apuesta .ma-nivel{font-size:.72rem;color:var(--tx2)}
.xg-row{display:flex;justify-content:space-between;font-size:.76rem;color:var(--tx2);margin-top:8px}
.chips{display:flex;flex-wrap:wrap;gap:5px;margin-top:8px}
.chip{background:var(--panel2);border-radius:6px;padding:3px 8px;font-size:.72rem;color:var(--tx2)}
.chip b{color:var(--tx)}
.marcadores{display:flex;gap:6px;margin-top:8px;flex-wrap:wrap}
.marcadores span{background:var(--panel2);border-radius:6px;padding:3px 8px;font-size:.74rem;font-variant-numeric:tabular-nums}
.marcadores span b{color:var(--ac)}
.tg-banner{display:flex;align-items:center;gap:12px;background:linear-gradient(135deg,#0088cc,#005f8f);border-radius:14px;padding:14px 16px;margin:28px 0}
.tg-banner-txt{color:#fff;font-weight:700;font-size:.9rem}
.tg-banner-sub{color:rgba(255,255,255,.8);font-size:.76rem;margin-top:2px}
.tg-banner-btn{background:#fff;color:#0088cc;border-radius:8px;padding:8px 16px;font-weight:700;font-size:.82rem;text-decoration:none;white-space:nowrap}
.picks-aviso{display:flex;align-items:center;gap:12px;background:var(--panel);border:1px solid var(--lin);border-radius:14px;padding:14px 16px;margin:20px 0;flex-wrap:wrap}
.picks-aviso-ico{font-size:1.8rem}
.picks-aviso-txt{flex:1;min-width:200px}
.picks-aviso-title{font-weight:700;font-size:.9rem}
.picks-aviso-sub{color:var(--tx2);font-size:.78rem;margin-top:2px}
.picks-aviso-btns{display:flex;gap:8px}
.btn-picks-pub{background:var(--v);color:#0d1220;border-radius:8px;padding:8px 14px;font-weight:700;font-size:.8rem;text-decoration:none;white-space:nowrap}
.btn-picks-prem{background:var(--pu);color:#0d1220;border-radius:8px;padding:8px 14px;font-weight:700;font-size:.8rem;text-decoration:none;white-space:nowrap}
.resumen{background:var(--panel);border:1px solid var(--lin);border-radius:12px;padding:14px;margin-bottom:18px;display:grid;grid-template-columns:repeat(4,1fr);gap:8px;text-align:center}
.rs-v{font-size:1.25rem;font-weight:700;color:var(--ac)}
.rs-l{font-size:.7rem;color:var(--tx2)}
.seccion-titulo{display:flex;align-items:center;gap:8px;margin:20px 0 10px;font-size:.82rem;font-weight:700;letter-spacing:.07em;text-transform:uppercase;color:var(--tx2)}
.seccion-titulo::after{content:'';flex:1;height:1px;background:var(--lin)}
.badge-gratis{background:#1a3320;color:var(--v);border:1px solid var(--v);border-radius:6px;padding:2px 10px;font-size:.72rem;font-weight:700}
.badge-prem{background:#2a1a3d;color:var(--pu);border:1px solid var(--pu);border-radius:6px;padding:2px 10px;font-size:.72rem;font-weight:700}
.pick{background:var(--panel);border:1px solid var(--lin);border-radius:14px;padding:18px;margin-bottom:12px;position:relative}
.pick.value{border-color:var(--go)}.pick.combo{border-color:var(--pu)}
.pick-n{position:absolute;top:10px;right:12px;font-size:.72rem;color:var(--tx2);font-weight:600;background:var(--panel2);border-radius:5px;padding:1px 7px}
.ph{display:flex;align-items:flex-start;gap:10px;margin-bottom:10px}
.ph-em{font-size:1.7rem;flex-shrink:0;line-height:1}
.ph-info .sub{font-size:.75rem;color:var(--tx2);margin-bottom:2px}
.ph-info .merc{font-size:.95rem;font-weight:700;line-height:1.3}
.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin:10px 0}
.sb{background:var(--panel2);border-radius:9px;padding:9px;text-align:center}
.sb .v{font-size:1.2rem;font-weight:700}
.sb .l{font-size:.69rem;color:var(--tx2);margin-top:2px}
.desc{font-size:.79rem;color:var(--tx2);margin-top:8px;padding:7px 10px;background:var(--panel2);border-radius:7px;border-left:3px solid var(--go)}
.combo-patas{margin-top:10px;border-top:1px solid var(--lin);padding-top:8px}
.combo-pata{display:flex;justify-content:space-between;align-items:center;padding:4px 0;font-size:.78rem;color:var(--tx2)}
.combo-pata span{color:var(--go);margin-left:5px}
.combo-x{text-align:center;font-size:.7rem;color:var(--tx2);margin:2px 0}
.ev-pos{color:var(--v)}.ev-neg{color:var(--d)}
.pick-prem-bloq{background:var(--panel);border:2px solid var(--pu);border-radius:14px;padding:18px;margin-bottom:12px;position:relative;overflow:hidden}
.pick-prem-bloq::before{content:'';position:absolute;inset:0;background:rgba(13,18,32,.75);z-index:2;border-radius:12px}
.prem-overlay{position:absolute;inset:0;z-index:3;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px;padding:20px;text-align:center}
.prem-badge{background:var(--pu);color:#0d1220;border-radius:8px;padding:5px 16px;font-size:.85rem;font-weight:700;letter-spacing:.03em}
.prem-titulo{font-size:1rem;font-weight:700;color:var(--tx)}
.prem-sub{font-size:.78rem;color:var(--tx2)}
.prem-precio{font-size:1.4rem;font-weight:700;color:var(--go)}
.prem-btn{display:block;background:linear-gradient(90deg,#a78bfa,#818cf8);color:#fff;border-radius:10px;padding:10px 28px;font-weight:700;font-size:.9rem;text-decoration:none}
.prem-yape{font-size:.75rem;color:var(--tx2)}
.vacio{background:var(--panel);border:1px dashed var(--lin);border-radius:12px;padding:22px;text-align:center;color:var(--tx2);grid-column:1/-1}
.aviso{background:var(--panel);border-left:4px solid var(--e);border-radius:0 12px 12px 0;padding:14px 16px;font-size:.81rem;color:var(--tx2);margin-top:32px}
footer{text-align:center;color:var(--tx2);font-size:.76rem;margin-top:28px}
footer a{color:var(--ac);text-decoration:none}
@keyframes tgSlide{from{transform:translateY(80px);opacity:0}to{transform:translateY(0);opacity:1}}
#tg-float{position:fixed;bottom:16px;right:12px;left:12px;z-index:9999;background:linear-gradient(135deg,#0088cc,#005f8f);border-radius:14px;padding:12px 16px;box-shadow:0 4px 20px rgba(0,136,204,.5);display:flex;align-items:center;gap:12px;animation:tgSlide .6s ease;cursor:pointer;border:1px solid rgba(255,255,255,.15);max-width:460px;margin:0 auto}
@media(max-width:560px){.resumen{grid-template-columns:repeat(2,1fr)}}
"""


def render_card(p):
    fecha_h = p.get('fecha', '')
    hora = p.get('hora', '')
    liga_pill = (f'<span class="liga-pill" style="background:{p["liga_color"]}22;color:{p["liga_color"]};'
                 f'border:1px solid {p["liga_color"]}">{p["liga_emoji"]} {p.get("liga_nombre","")}</span>')
    ma = p['mejor_apuesta']
    mejor_html = f'''
    <div class="mejor-apuesta {ma['nivel']}">
      <div>
        <div class="ma-label">🏆 Mejor apuesta · {ma['categoria']}</div>
        <div class="ma-mercado">{ma['emoji']} {ma['mercado']}</div>
      </div>
      <div class="ma-right">
        <div class="ma-prob">{ma['prob']}%</div>
        <div class="ma-nivel">{ma['texto']}</div>
      </div>
    </div>'''

    marcadores = p.get('marcador_prob') or []
    marc_html = ''
    if marcadores:
        items = ''.join(f'<span>{m["marcador"]} <b>{m["prob"]}%</b></span>' for m in marcadores)
        marc_html = f'<div class="marcadores">{items}</div>'

    chips = (f'<div class="chips">'
             f'<span class="chip">+1.5 <b>{p.get("over_1.5",0)}%</b></span>'
             f'<span class="chip">+2.5 <b>{p.get("over_2.5",0)}%</b></span>'
             f'<span class="chip">+3.5 <b>{p.get("over_3.5",0)}%</b></span>'
             f'<span class="chip">BTTS Sí <b>{p.get("btts_si",0)}%</b></span>'
             f'</div>')

    xg = (f'<div class="xg-row">'
          f'<span>xG {p.get("local","")}: <b style="color:var(--tx)">{p.get("xg_l",0)}</b></span>'
          f'<span>xG {p.get("visitante","")}: <b style="color:var(--tx)">{p.get("xg_v",0)}</b></span>'
          f'</div>')

    return f'''<div class="card" data-liga="{p.get('liga','')}" data-fecha="{fecha_h}">
    <div class="enc">
      {liga_pill}
      <span>{fecha_h} · {hora}</span>
    </div>
    <div class="eqs">
      <span>{p.get('local','')}</span><span class="vs">vs</span><span>{p.get('visitante','')}</span>
    </div>
    <div class="barra">
      <i style="width:{p.get('p1',0)}%;background:var(--v)"></i>
      <i style="width:{p.get('px',0)}%;background:var(--e)"></i>
      <i style="width:{p.get('p2',0)}%;background:var(--d)"></i>
    </div>
    <div class="leyenda">
      <span class="vd">1·{p.get('p1',0)}%</span><span class="em">X·{p.get('px',0)}%</span><span class="dr">2·{p.get('p2',0)}%</span>
    </div>
    {mejor_html}
    {xg}
    {chips}
    {marc_html}
  </div>'''


def render_pick(pk, i):
    es_combo = pk.get('tipo') == 'premium' and pk.get('picks_combo')
    es_value = pk.get('ev', 0) and pk['ev'] > 0.10
    cls = 'combo' if es_combo else ('value' if es_value else '')
    cuota_d = pk.get('cuota_display', pk.get('cuota', 0))
    ev = pk.get('ev')
    ev_html = f'<span class="{"ev-pos" if ev and ev > 0 else "ev-neg"}">{"+" if ev and ev > 0 else ""}{round(ev*100,1) if ev is not None else 0}%</span>' if ev is not None else '—'
    liga_emoji = LIGA_EMOJI.get(pk.get('liga'), '⚽')

    combo_html = ''
    if es_combo:
        patas = pk['picks_combo']
        piezas = []
        for j, s in enumerate(patas):
            piezas.append(f'<div class="combo-pata"><span>{s.get("mercado","")}</span>'
                           f'<span>@{s.get("cuota","")}</span></div>')
            if j < len(patas) - 1:
                piezas.append('<div class="combo-x">✖️</div>')
        combo_html = f'<div class="combo-patas">{"".join(piezas)}</div>'

    sub = '🔗 COMBINADA' if es_combo else f'{liga_emoji} {pk.get("partido","")}'
    return f'''<div class="pick {cls}">
    <div class="pick-n">Pick #{i}</div>
    <div class="ph">
      <div class="ph-em">{pk.get('emoji','⚽')}</div>
      <div class="ph-info">
        <div class="sub">{sub} · {pk.get('categoria','')}</div>
        <div class="merc">{pk.get('mercado','')}</div>
      </div>
    </div>
    <div class="stats">
      <div class="sb"><div class="v" style="color:var(--v)">{pk.get('prob',0)}%</div><div class="l">Probabilidad</div></div>
      <div class="sb"><div class="v" style="color:var(--go)">@{cuota_d}</div><div class="l">Cuota</div></div>
      <div class="sb"><div class="v">{ev_html}</div><div class="l">EV</div></div>
    </div>
    {combo_html}
    {f'<div class="desc">💡 {pk["descripcion"]}</div>' if pk.get('descripcion') else ''}
  </div>'''


def main():
    partidos = preparar_partidos(cargar_json('Predicciones/predicciones_hoy.json', []))
    picks_data = cargar_json('Data/picks_hoy.json', {})
    publicos = picks_data.get('publicos', [])
    premium = picks_data.get('premium', [])
    premium_teaser = premium[0] if premium else None

    hoy = datetime.now(PERU_TZ).strftime('%Y-%m-%d')
    generado_str = datetime.now(PERU_TZ).strftime('%d-%m-%Y %H:%M')
    fechas = sorted({p.get('fecha', '') for p in partidos if p.get('fecha')})
    ligas_presentes = list(dict.fromkeys(p.get('liga', '') for p in partidos if p.get('liga')))

    ligas_btns = '<button type="button" class="sel" data-liga="TODAS">⚽ Todas</button>' + ''.join(
        f'<button type="button" data-liga="{lg}">{LIGA_EMOJI.get(lg,"")} {LIGA_CODIGO.get(lg,lg)}</button>' for lg in ligas_presentes
    )

    def fmt_dia(f):
        try:
            y, m, d = f.split('-')
            meses = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']
            return f'{int(d)} {meses[int(m)-1]}'
        except Exception:
            return f

    dias_btns = ''.join(
        f'<button type="button" data-f="{f}" class="{"eshoy" if f==hoy else ""}">'
        f'{"HOY · " if f==hoy else ""}{fmt_dia(f)}</button>' for f in fechas
    )

    cards_html = ''.join(render_card(p) for p in partidos) or '<div class="vacio">No hay partidos programados por ahora.</div>'

    res = resumen_picks(publicos)
    picks_html = ''.join(render_pick(pk, i + 1) for i, pk in enumerate(publicos)) or \
        '<div class="vacio">Sin picks públicos por ahora — vuelve más tarde.</div>'

    if premium_teaser:
        premium_html = f'''<div class="pick-prem-bloq">
      <div class="ph">
        <div class="ph-em">🎯</div>
        <div class="ph-info">
          <div class="sub" style="filter:blur(5px);user-select:none">██████ · {premium_teaser.get('categoria','Premium')}</div>
          <div class="merc" style="filter:blur(5px);user-select:none">████████████████</div>
        </div>
      </div>
      <div class="stats">
        <div class="sb"><div class="v" style="color:var(--v);filter:blur(4px)">{premium_teaser.get('prob',0)}%</div><div class="l">Probabilidad</div></div>
        <div class="sb"><div class="v" style="color:var(--go);filter:blur(4px)">@{premium_teaser.get('cuota_display', premium_teaser.get('cuota',0))}</div><div class="l">Cuota</div></div>
        <div class="sb"><div class="v" style="color:var(--pu)">🔒</div><div class="l">Bloqueado</div></div>
      </div>
      <div class="prem-overlay">
        <span class="prem-badge">💎 PICK PREMIUM</span>
        <div class="prem-titulo">🔒 Pick Seguro del Día</div>
        <div class="prem-sub">Mercado y partido revelados al pagar · Análisis del modelo</div>
        <div class="prem-precio">S/10 · Pick Seguro 🔥</div>
        <a class="prem-btn" href="https://wa.me/51982730164?text=Hola%2C%20quiero%20el%20pick%20seguro%20premium%20de%20hoy" target="_blank">📱 Activar por Yape/Plin</a>
        <div class="prem-yape">Yape/Plin: 982 730 164 · Telegram: t.me/sportpickoficial</div>
      </div>
    </div>'''
    else:
        premium_html = '<div class="vacio">Sin pick premium disponible por ahora.</div>'

    ligas_badges = ''.join(
        f'<span class="badge on" style="border-color:{LIGA_COLOR.get(k,"#60a5fa")};color:{LIGA_COLOR.get(k,"#60a5fa")}">{v["emoji"]} {v["nombre"]}</span>'
        for k, v in LIGAS.items() if v.get('activa')
    )

    html = f'''<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SportPicks Ligas · Predicciones Multi-Liga con IA</title>
<meta name="description" content="Predicciones deportivas con IA para 15 ligas: Champions League, Conference League, Libertadores, Sudamericana, Brasileirao, MLS, Liga 1 Perú y más.">
<style>{CSS}</style>
</head>
<body>
<nav><div class="wrap">
  <a href="#partidos">📅 Partidos</a>
  <a href="#picks-gratis">✅ Picks gratis</a>
  <a href="#picks-premium">💎 Premium</a>
  <a class="tg-nav" href="https://t.me/sportpickoficial" target="_blank">📣 Telegram</a>
</div></nav>

<div class="hero-wrap">
  <div class="wrap">
    <div class="hero-titulo">🏆 SportPicks — Multi-Liga</div>
    <div class="hero-sub">Predicciones con IA · XGBoost + Dixon-Coles + Monte Carlo 10K simulaciones</div>

    <div class="hero-btns">
      <a href="#picks-gratis" class="hero-btn-pub">✅ Ver picks GRATIS</a>
      <a href="#picks-premium" class="hero-btn-prem">💎 Pick Seguro S/10</a>
    </div>

    <a href="https://t.me/sportpickoficial" target="_blank" class="hero-tg">
      <span style="font-size:1.3rem">📣</span>
      <div>
        <div class="hero-tg-title">Únete al canal GRATIS</div>
        <div class="hero-tg-sub">Picks diarios · SportPicks Oficial · t.me/sportpickoficial</div>
      </div>
      <span style="color:#fff;font-size:1.1rem">→</span>
    </a>

    <div class="badges">
      <span class="badge">📅 {generado_str} (Perú)</span>
      {ligas_badges}
    </div>
  </div>
</div>

<main class="wrap">
  <h2 id="partidos">📅 Partidos <small id="sub-dia"></small></h2>
  <div class="ligas" id="ligas">{ligas_btns}</div>
  <div class="dias" id="dias">{dias_btns}</div>
  <div id="cards-wrap" class="cards">{cards_html}</div>

  <div class="tg-banner" onclick="window.open('https://t.me/sportpickoficial','_blank')" style="cursor:pointer">
    <div style="font-size:1.8rem">📣</div>
    <div style="flex:1">
      <div class="tg-banner-txt">Canal GRATIS de SportPicks — Únete ahora</div>
      <div class="tg-banner-sub">✅ Picks públicos diarios · 💎 Análisis del modelo · ⚽ 15 ligas</div>
    </div>
    <a class="tg-banner-btn" href="https://t.me/sportpickoficial" target="_blank" onclick="event.stopPropagation()">Unirme →</a>
  </div>

  <div class="picks-aviso">
    <div class="picks-aviso-ico">🎯</div>
    <div class="picks-aviso-txt">
      <div class="picks-aviso-title">Pronósticos del día disponibles</div>
      <div class="picks-aviso-sub">Análisis con IA · Cuotas reales · Picks públicos gratis y premium</div>
    </div>
    <div class="picks-aviso-btns">
      <a href="#picks-gratis" class="btn-picks-pub">✅ Ver picks gratis</a>
      <a href="#picks-premium" class="btn-picks-prem">💎 Ver premium</a>
    </div>
  </div>

  <h2 id="picks-gratis"><span class="badge-gratis">✅ GRATIS</span> Picks públicos del día</h2>
  <div class="resumen">
    <div><div class="rs-v">{res['n']}</div><div class="rs-l">Picks</div></div>
    <div><div class="rs-v" style="color:var(--v)">{res['prob']}%</div><div class="rs-l">Prob. prom.</div></div>
    <div><div class="rs-v" style="color:var(--go)">{res['cuota']}</div><div class="rs-l">Cuota prom.</div></div>
    <div><div class="rs-v" style="color:var(--pu)">{res['ev']}</div><div class="rs-l">Con EV+</div></div>
  </div>
  <div id="picks">{picks_html}</div>

  <h2 id="picks-premium"><span class="badge-prem">💎 PREMIUM</span> Pick exclusivo</h2>
  {premium_html}

  <div class="aviso">
    <b>⚠️ Mercados calculados automáticamente por el modelo.</b>
    Probabilidades vía XGBoost + Dixon-Coles + simulación Monte Carlo sobre datos de TheStatsAPI.
    El modelo elige el mercado con mayor valor esperado (EV) en cada partido.
  </div>
  <footer>
    Modelo: <a href="https://github.com/Sportpicks/SportPicks-Ligas">SportPicks-Ligas</a>
    · XGBoost + Dixon-Coles + Monte Carlo ·
    <a href="https://t.me/sportpickoficial" target="_blank">📣 Telegram</a> ·
    <a href="https://wa.me/51982730164" target="_blank">💬 WhatsApp</a>
  </footer>
</main>

<div id="tg-float">
  <div style="font-size:2rem;flex-shrink:0">📣</div>
  <div style="flex:1">
    <div style="color:#fff;font-weight:700;font-size:.88rem;line-height:1.3">Canal GRATIS de SportPicks</div>
    <div style="color:rgba(255,255,255,.8);font-size:.74rem;margin-top:3px">Picks diarios · 15 ligas internacionales</div>
  </div>
  <button id="tg-close" style="background:rgba(255,255,255,.15);border:none;color:#fff;border-radius:50%;width:24px;height:24px;cursor:pointer;font-size:.8rem;display:flex;align-items:center;justify-content:center;flex-shrink:0">✕</button>
</div>

<script>
const HOY = "{hoy}";
let ligaSel = 'TODAS';
let fechaSel = null;

function aplicarFiltros(){{
  const cards = document.querySelectorAll('#cards-wrap .card');
  let visibles = 0;
  cards.forEach(c => {{
    const okLiga = ligaSel==='TODAS' || c.dataset.liga===ligaSel;
    const okFecha = !fechaSel || c.dataset.fecha===fechaSel;
    const show = okLiga && okFecha;
    c.style.display = show ? '' : 'none';
    if(show) visibles++;
  }});
  const sub = document.getElementById('sub-dia');
  sub.textContent = fechaSel ? ('· '+fechaSel) : '';
}}

document.querySelectorAll('#ligas button').forEach(b=>{{
  b.onclick = () => {{
    ligaSel = b.dataset.liga;
    document.querySelectorAll('#ligas button').forEach(x=>x.classList.toggle('sel', x===b));
    aplicarFiltros();
  }};
}});

document.querySelectorAll('#dias button').forEach(b=>{{
  b.onclick = () => {{
    fechaSel = (fechaSel===b.dataset.f) ? null : b.dataset.f;
    document.querySelectorAll('#dias button').forEach(x=>x.classList.toggle('sel', x.dataset.f===fechaSel));
    aplicarFiltros();
  }};
}});

(function(){{
  const b=document.getElementById('tg-float');
  const c=document.getElementById('tg-close');
  if(sessionStorage.getItem('tg_cerrado')){{ b.style.display='none'; return; }}
  b.addEventListener('click', e => {{
    if(e.target!==c && !c.contains(e.target)) window.open('https://t.me/sportpickoficial','_blank');
  }});
  c.addEventListener('click', e => {{
    e.stopPropagation();
    b.style.display='none';
    sessionStorage.setItem('tg_cerrado','1');
  }});
}})();
</script>
</body>
</html>'''

    os.makedirs('docs', exist_ok=True)
    with open('docs/index.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'✅ docs/index.html generado — {len(partidos)} partidos, {len(publicos)} picks públicos, premium: {"sí" if premium_teaser else "no"}')


if __name__ == '__main__':
    main()
