"""Minuteur EMOM de l'onglet « Log Workouts »."""

from __future__ import annotations

import streamlit.components.v1 as _st_components

# ─────────────────────────────────────────────────────────────────────────────
# TAB — LOG WORKOUTS
# ─────────────────────────────────────────────────────────────────────────────

_EMOM_TIMER_HTML = """<!DOCTYPE html>
<html>
<head>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: transparent; font-family: Satoshi, sans-serif; padding: 6px 0; }}
  #label {{ font-size: .6rem; letter-spacing: .12em; text-transform: uppercase;
             opacity: .55; margin-bottom: 4px; }}
  #wrap {{ display: flex; align-items: center; gap: 10px; }}
  #ring {{ position: relative; width: 64px; height: 64px; flex-shrink: 0; }}
  #ring svg {{ position: absolute; top: 0; left: 0; transform: rotate(-90deg); }}
  #ring-bg {{ fill: none; stroke: #ffffff22; stroke-width: 4; }}
  #ring-fg {{ fill: none; stroke: #ffb703; stroke-width: 4;
               stroke-linecap: round;
               stroke-dasharray: {circ};
               stroke-dashoffset: 0;
               transition: stroke-dashoffset .9s linear, stroke .3s; }}
  #ring-fg.urgent {{ stroke: #e63946; }}
  #digits {{ position: absolute; inset: 0; display: flex; align-items: center;
              justify-content: center;
              font-size: 1.05rem; font-weight: 200; color: #ffb703; }}
  #digits.urgent {{ color: #e63946; }}
  .btn {{ padding: 5px 14px; border: 1px solid #ffffff44; border-radius: 20px;
           background: transparent; color: #eee; cursor: pointer;
           font-size: .72rem; letter-spacing: .06em;
           transition: background .15s, border-color .15s; }}
  .btn:hover {{ background: #ffffff18; border-color: #ffffff88; }}
  #startBtn {{ min-width: 68px; text-align: center; }}
</style>
</head>
<body>
<div id="label">EMOM — {interval} s / série</div>
<div id="wrap">
  <div id="ring">
    <svg width="64" height="64" viewBox="0 0 64 64">
      <circle id="ring-bg" cx="32" cy="32" r="{r}"/>
      <circle id="ring-fg" cx="32" cy="32" r="{r}"/>
    </svg>
    <div id="digits">1:00</div>
  </div>
  <button class="btn" id="startBtn" onclick="toggle()">▶ Start</button>
  <button class="btn" onclick="reset()">↺ Reset</button>
</div>
<script>
const INTERVAL = {interval};
const CIRC = {circ};
let remaining = INTERVAL;
let running = false;
let tick = null;
let ctx = null;

function beep() {{
  ctx = ctx || new (window.AudioContext || window.webkitAudioContext)();
  const osc = ctx.createOscillator();
  const g   = ctx.createGain();
  osc.connect(g); g.connect(ctx.destination);
  osc.frequency.value = 880; osc.type = 'sine';
  g.gain.setValueAtTime(0.45, ctx.currentTime);
  g.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.45);
  osc.start(ctx.currentTime); osc.stop(ctx.currentTime + 0.45);
}}

function draw() {{
  const pct = remaining / INTERVAL;
  const offset = CIRC * (1 - pct);
  const fg = document.getElementById('ring-fg');
  const dg = document.getElementById('digits');
  fg.style.strokeDashoffset = offset;
  const urgent = remaining <= 5;
  fg.className = urgent ? 'urgent' : '';
  dg.className = urgent ? 'urgent' : '';
  const m = Math.floor(remaining / 60);
  const s = remaining % 60;
  dg.textContent = m + ':' + String(s).padStart(2,'0');
}}

function toggle() {{
  if (running) {{
    clearInterval(tick); running = false;
    document.getElementById('startBtn').textContent = '▶ Start';
  }} else {{
    running = true;
    document.getElementById('startBtn').textContent = '⏸ Pause';
    tick = setInterval(() => {{
      remaining--;
      draw();
      if (remaining <= 0) {{
        beep();
        remaining = INTERVAL;
        draw();
      }}
    }}, 1000);
  }}
}}

function reset() {{
  clearInterval(tick); running = false; remaining = INTERVAL;
  document.getElementById('startBtn').textContent = '▶ Start';
  draw();
}}

draw();
</script>
</body>
</html>"""


def _render_emom_timer(interval_sec: int) -> None:
    import math

    r = 28
    circ = round(2 * math.pi * r, 2)
    html = _EMOM_TIMER_HTML.format(interval=interval_sec, r=r, circ=circ)
    _st_components.html(html, height=90)
