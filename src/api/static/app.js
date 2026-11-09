"use strict";
const K = { draft: "seance.draft.v2", pending: "seance.pending.v1", cfg: "seance.cfg.v1", cat: "seance.catalog.v1" };
const TYPES = ["N", "W", "D", "F"];
const MIN_MS = 60000; // un EMOM dure toujours une minute par série

const load = (k, d) => { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : d; } catch { return d; } };
const save = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* stockage indisponible */ } };
const $ = (id) => document.getElementById(id);
const el = (tag, props = {}, ...kids) => {
  const e = Object.assign(document.createElement(tag), props);
  kids.forEach((c) => e.append(c));
  return e;
};
const nowMs = () => Date.now();
const nowIso = () => {
  const d = new Date(nowMs()), p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
};
const uuid = () => (crypto.randomUUID ? crypto.randomUUID() : String(nowMs()) + Math.random().toString(16).slice(2));
const mmss = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
const norm = (t) => t.trim().toLowerCase();

let cfg = { url: "", token: "", bodyweight_kg: null, height_cm: null, keyboard: false, ...load(K.cfg, {}) };
let catalog = { exercises: [], previous: {}, templates: [], ...load(K.cat, {}) };
const DRAFT_MAX_AGE_H = 12; // au-delà, un brouillon n'est plus supposé en cours
const MAX_WORK_MIN = 600; // identique au garde-fou de l'API (WorkoutIn)

// Brouillon rechargé au démarrage : un brouillon sans activité depuis plus de 12 h est proposé à la suppression,
// sinon son `worked_from` (posé à la première action, jamais remis à zéro) fausserait la durée de la séance.
function loadDraft() {
  const d = load(K.draft, null);
  if (!d) return newDraft();
  const last = new Date(d.worked_to || d.worked_from || d.started_at).getTime();
  if (!(nowMs() - last > DRAFT_MAX_AGE_H * 3600000)) return d;
  const done = (d.exercises || []).reduce((a, e) => a + e.sets.filter((s) => s.completed).length, 0);
  if (!done) { localStorage.removeItem(K.draft); return newDraft(); }
  const quand = new Date(last).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" });
  return confirm(`Un brouillon de séance (${done} série(s) validée(s)) n'a pas bougé depuis le ${quand}.\n`
    + "OK = le jeter et repartir à zéro. Annuler = le garder.")
    ? (localStorage.removeItem(K.draft), newDraft()) : d;
}
let draft = loadDraft();
let status = null; // {kind: ok|err|wait, text}

function newDraft() {
  const d = new Date();
  return {
    client_uuid: uuid(), name: "Séance du " + d.toLocaleDateString("fr-FR"), started_at: nowIso(),
    worked_from: null, worked_to: null, exercises: [], blocks: {},
  };
}
const persist = () => save(K.draft, draft);
const base = () => (cfg.url || "").replace(/\/+$/, "");
const api = (path, opts = {}) => fetch(base() + path, {
  ...opts,
  headers: { "Content-Type": "application/json", Authorization: "Bearer " + cfg.token, ...(opts.headers || {}) },
});

// Première à dernière action = durée d'entraînement enregistrée dans le journal.
function touch(end = true) {
  const t = nowIso();
  if (!draft.worked_from) draft.worked_from = t;
  if (end) draft.worked_to = t;
}

// ───────── Catalogue ─────────
const libOf = (name) => catalog.exercises.find((e) => norm(e.name) === norm(name));
const formulaOf = (ex) => ex.load_formula || libOf(ex.name)?.load_formula || "weight";
const unitOf = (ex) => ex.unit || libOf(ex.name)?.unit || "reps";
const bodyweight = () => cfg.bodyweight_kg || catalog.last_bodyweight_kg || null;

function prevOf(name, idx, side = null) {
  const p = catalog.previous[name];
  if (!p) return null;
  if (!side) return p[idx] || null;
  return p.filter((x) => x.side === side)[idx] || null;
}
// rang du set parmi les sets du même côté (uniquement utile pour un exercice unilatéral)
const rangDuCote = (ex, j) => ex.sets.slice(0, j).filter((x) => x.side === ex.sets[j].side).length;
function prevText(name, idx, unit, side = null) {
  const p = prevOf(name, idx, side);
  if (!p) return "--";
  const v = unit === "sec" ? `${p.weight_kg}x${p.reps}s` : `${p.weight_kg}x${p.reps}`;
  return p.duration_s ? `${v} ${mmss(p.duration_s)}` : v;
}
const estUnilateral = (name) => (catalog.previous[name] || []).some((p) => p.side);
function blankSet(name, idx = 0) {
  const p = name ? prevOf(name, idx) || (catalog.previous[name] || []).slice(-1)[0] : null;
  return { set_type: "N", weight_kg: p ? p.weight_kg : 0, reps: p ? p.reps : 0, rpe: null, completed: false };
}

// ───────── Statut ─────────
function setStatus(kind, text) { status = { kind, text }; renderStatus(); }
function renderStatus() {
  const box = $("status");
  box.replaceChildren();
  const pending = load(K.pending, []);
  if (status) box.append(el("div", { className: "msg " + status.kind, textContent: status.text }));
  if (pending.length) {
    box.append(el("div", { className: "msg wait" },
      `${pending.length} séance(s) en attente de synchronisation`,
      el("button", { textContent: "Réessayer", onclick: flush })));
  }
}

// ───────── Ajout d'exercices / templates / EMOM ─────────
function addExercise(info) {
  if (!draft.exercises.some((e) => !e.block && norm(e.name) === norm(info.name))) {
    const ex = { ...info, sets: [blankSet(info.name)] };
    if (estUnilateral(info.name)) { ex.unilateral = true; ex.sets[0].side = "D"; }
    draft.exercises.push(ex);
    persist();
  }
  render();
}

function newBlockId() { return "b" + nowMs().toString(36) + Math.random().toString(36).slice(2, 5); }

// Bloc EMOM : N exercices se relaient, un par minute ; minutes = multiple de N.
function makeBlock(infos, minutes) {
  const id = newBlockId(), n = infos.length, rounds = minutes / n;
  draft.blocks[id] = { t0: null, el: 0 };
  infos.forEach((info, k) => {
    const sets = [];
    for (let r = 0; r < rounds; r++) sets.push({ ...blankSet(info.name, r), minute: r * n + k + 1, duration_s: null });
    draft.exercises.push({ ...info, block: id, sets });
  });
  persist();
  render();
}

function startFromTemplate(t) {
  draft.name = `${t.name} — ${new Date().toLocaleDateString("fr-FR")}`;
  draft.template_id = t.id;
  draft.exercises = []; draft.blocks = {};
  t.exercises.forEach((e) => {
    const sets = (e.sets.length ? e.sets : [blankSet(e.name)]).map((s) => ({ ...s, rpe: null, completed: false }));
    const ex = { name: e.name, unit: e.unit || undefined, sets };
    if (!e.emom_interval_sec && estUnilateral(e.name)) { ex.unilateral = true; ex.sets.forEach((s, i) => { s.side = i % 2 ? "G" : "D"; }); }
    if (e.emom_interval_sec) { // un exercice EMOM de template = un bloc d'un exercice, une série par minute
      const id = newBlockId();
      draft.blocks[id] = { t0: null, el: 0 };
      ex.block = id;
      ex.sets.forEach((s, i) => { s.minute = i + 1; s.duration_s = null; });
    }
    draft.exercises.push(ex);
  });
  persist();
  render();
}

function optionsFor(select) {
  const groups = {};
  catalog.exercises.forEach((e) => { (groups[e.category || "Autres"] ||= []).push(e); });
  Object.keys(groups).sort().forEach((cat) => {
    const g = el("optgroup", { label: cat });
    groups[cat].forEach((e) => g.append(el("option", { value: e.name, textContent: e.name })));
    select.append(g);
  });
  select.append(el("option", { value: "__new__", textContent: "+ Nouvel exercice..." }));
}

// Formulaire de création d'un exercice : nom + type (charge / poids du corps + lest / statique en secondes)
function newExerciseForm(onDone) {
  let kind = "charge";
  const name = el("input", { placeholder: "Nom de l'exercice", autocomplete: "off" });
  const seg = el("div", { className: "seg" });
  const kinds = [["charge", "Charge"], ["corps", "Corps + lest"], ["statique", "Statique (sec)"]];
  const paint = () => seg.replaceChildren(...kinds.map(([k, t]) => el("button", { textContent: t, className: k === kind ? "on" : "", onclick: () => { kind = k; paint(); } })));
  paint();
  const msg = el("div", { className: "small" });
  const go = el("button", { className: "add", textContent: "Créer l'exercice", onclick: () => {
    const n = name.value.trim();
    if (!n) { msg.textContent = "Nom requis."; return; }
    if (libOf(n)) { msg.textContent = "Existe déjà : sélectionne-le dans la liste."; return; }
    onDone({
      name: n, create: true,
      load_formula: kind === "charge" ? "weight" : "bw_plus_weight",
      unit: kind === "statique" ? "sec" : "reps",
    });
  } });
  return el("div", { className: "panel" }, el("div", { className: "lbl", textContent: "Nouvel exercice" }), name, seg, go, msg);
}

let addOpen = false, builder = { items: [], minutes: 10, open: false };

function addPanel() {
  const d = el("details", { className: "panel", open: addOpen, ontoggle: (e) => { addOpen = e.target.open; } });
  d.append(el("summary", { textContent: "Ajouter un exercice" }));
  const sel = el("select");
  optionsFor(sel);
  const slot = el("div");
  const add = el("button", { textContent: "Ajouter", onclick: () => { if (sel.value !== "__new__") { addOpen = false; addExercise({ name: sel.value }); } } });
  sel.onchange = () => {
    slot.replaceChildren();
    if (sel.value === "__new__") slot.append(newExerciseForm((info) => { addOpen = false; addExercise(info); }));
  };
  d.append(el("div", { className: "line" }, sel, add), slot);
  return d;
}

function emomBuilder() {
  const d = el("details", { className: "panel", open: builder.open, ontoggle: (e) => { builder.open = e.target.open; } });
  d.append(el("summary", { textContent: "Nouvel EMOM (exercices à tour de rôle)" }));
  const body = el("div");
  d.append(body);
  const redraw = () => {
    body.replaceChildren();
    const n = builder.items.length;
    builder.items.forEach((it, i) => body.append(el("div", { className: "line", style: "margin:4px 0;align-items:center" },
      el("span", { className: "emin", textContent: `Min ${i + 1}` }),
      el("strong", { style: "flex:1;text-transform:uppercase", textContent: it.name + (it.unit === "sec" ? " (statique)" : "") }),
      el("button", { className: "x", textContent: "X", onclick: () => { builder.items.splice(i, 1); redraw(); } }))));
    const sel = el("select");
    optionsFor(sel);
    const slot = el("div");
    const add = (info) => {
      if (builder.items.some((x) => norm(x.name) === norm(info.name))) return;
      builder.items.push(info); redraw();
    };
    sel.onchange = () => {
      slot.replaceChildren();
      if (sel.value === "__new__") slot.append(newExerciseForm(add));
    };
    body.append(el("div", { className: "line" }, sel,
      el("button", { textContent: "Ajouter", onclick: () => { if (sel.value !== "__new__") add({ name: sel.value }); } })), slot);

    const valid = n > 0 && builder.minutes >= n && builder.minutes % n === 0;
    const set = (v) => { builder.minutes = Math.max(1, Math.min(120, v)); redraw(); };
    body.append(el("div", { className: "lbl", style: "margin-top:8px", textContent: "Durée totale (minutes)" }),
      el("div", { className: "stepbtns" },
        el("button", { textContent: "-1", onclick: () => set(builder.minutes - 1) }),
        el("button", { textContent: String(builder.minutes), style: "flex:2;font-size:1.1rem", disabled: true }),
        el("button", { textContent: "+1", onclick: () => set(builder.minutes + 1) })));
    if (n > 0 && !valid) {
      const lo = Math.max(n, Math.floor(builder.minutes / n) * n), hi = lo + n;
      body.append(el("div", { className: "msg err", style: "margin:6px 0" },
        `${n} exercice(s) : la durée doit être un multiple de ${n}. `,
        el("button", { textContent: String(lo), onclick: () => set(lo) }),
        el("button", { textContent: String(hi), onclick: () => set(hi) })));
    } else if (valid) {
      body.append(el("div", { className: "small", textContent: `${builder.minutes / n} tour(s) de ${n} exercice(s) = ${builder.minutes} min` }));
    }
    body.append(el("button", { className: "add", textContent: "Créer l'EMOM", disabled: !valid, onclick: () => {
      const items = builder.items, minutes = builder.minutes;
      builder = { items: [], minutes: 10, open: false };
      makeBlock(items, minutes);
    } }));
  };
  redraw();
  return d;
}

function startPanel() {
  const p = el("div", { className: "panel" }, el("div", { className: "lbl", textContent: "Démarrer depuis un template" }));
  const sel = el("select");
  sel.append(el("option", { value: "", textContent: catalog.templates.length ? "Choisir un template..." : "Aucun template (connexion requise)" }));
  catalog.templates.forEach((t) => sel.append(el("option", { value: t.id, textContent: `${t.name}  (${t.exercises.length})` })));
  p.append(el("div", { className: "line" }, sel, el("button", { textContent: "Charger", onclick: () => {
    const t = catalog.templates.find((x) => String(x.id) === sel.value);
    if (t) startFromTemplate(t);
  } })));
  const ign = catalog.templates.reduce((a, t) => a + (t.ignored || 0), 0);
  if (ign) p.append(el("div", { className: "small", textContent: `${ign} exercice(s) de template introuvable(s), ignoré(s).` }));
  return p;
}

// ───────── Rendu ─────────
function numInput(s, field, mode, label, unit) {
  return el("input", { value: s[field] ?? "", inputMode: cfg.keyboard ? mode : "none",
    oninput: (e) => { const v = e.target.value.replace(",", "."); s[field] = v === "" ? null : Number(v); persist(); },
    onfocus: (e) => { e.target.select(); showStepper(s, field, e.target, label, unit); },
    onblur: () => hideStepperSoon() });
}

function toggleDone(ex, s) {
  if (s.completed) { s.completed = false; s.duration_s = null; persist(); render(); return; }
  s.completed = true;
  if (ex.block && draft.blocks[ex.block].t0) {
    const info = blockInfo(ex.block);
    // série validée pendant sa propre minute : temps mis pour faire les reps prévues
    if (!info.done && info.minute === s.minute) s.duration_s = Math.round(info.inMin / 100) / 10;
  }
  touch(); persist(); render();
}

// Retire les séries non validées (surdimensionnées) ; un exercice sans série disparaît, un bloc sans exercice aussi.
function dropUnvalidated(match) {
  draft.exercises.forEach((e) => { if (match(e)) e.sets = e.sets.filter((s) => s.completed); });
  draft.exercises = draft.exercises.filter((e) => e.sets.length);
  Object.keys(draft.blocks).forEach((id) => { if (!draft.exercises.some((e) => e.block === id)) delete draft.blocks[id]; });
  persist(); render();
}
const unvalidatedCount = (match = () => true) => draft.exercises.reduce((a, e) => a + (match(e) ? e.sets.filter((s) => !s.completed).length : 0), 0);

// Les séries validées sont stockées mais masquées ; « Voir » permet de relire ou de corriger.
function doneSummary(text, shown, toggle) {
  return el("div", { className: "sumline" }, el("span", { textContent: text }),
    el("button", { textContent: shown ? "Masquer" : "Voir", onclick: toggle }));
}
function cleanButton(n, onclick) {
  return n ? el("button", { className: "add", textContent: `Retirer les séries non validées (${n})`, onclick }) : null;
}

function exerciseCard(ex, i) {
  const bwf = formulaOf(ex) === "bw_plus_weight", unit = unitOf(ex);
  const done = ex.sets.filter((s) => s.completed).length, todo = ex.sets.length - done;
  const card = el("div", { className: "card" });
  card.append(el("div", { className: "ctitle" }, el("strong", { textContent: ex.name }),
    el("button", { className: "t" + (ex.unilateral ? " on" : ""), textContent: ex.unilateral ? "Côtés D/G" : "Côtés", title: "Exercice unilatéral : une série par bras",
      onclick: () => {
        ex.unilateral = !ex.unilateral;
        ex.sets.forEach((s, k) => { s.side = ex.unilateral ? (k % 2 ? "G" : "D") : null; });
        persist(); render();
      } }),
    el("button", { className: "x", textContent: "Suppr", onclick: () => { if (confirm("Retirer " + ex.name + " ?")) { draft.exercises.splice(i, 1); persist(); render(); } } })));
  const uni = !!ex.unilateral;
  if (bwf) {
    const w = bodyweight();
    const fr = libOf(ex.name)?.bw_fraction ?? 1;
    const part = fr < 1 ? `${Math.round(fr * 100)} % du poids du corps` : "poids du corps";
    card.append(el("div", { className: "small", textContent: w ? `Lest en plus de ${part} (${w} kg)` : `Lest en plus de ${part} (renseigne ton poids dans Réglages)` }));
  }
  if (done) card.append(doneSummary(`Validées ${done}/${ex.sets.length}`, ex.showDone, () => { ex.showDone = !ex.showDone; persist(); render(); }));
  if (todo || ex.showDone) card.append(el("div", { className: "row head" + (uni ? " side" : "") }, ...["Set", ...(uni ? ["Côté"] : []), "Préc.", bwf ? "Lest" : "Kg", unit === "sec" ? "Sec" : "Reps", "RPE", "OK"].map((t) => el("span", { textContent: t }))));
  let n = 0;
  ex.sets.forEach((s, j) => {
    if (s.set_type === "N") n++;
    if (s.completed && !ex.showDone) return; // stockée, non affichée
    const label = s.set_type === "N" ? String(n) : s.set_type;
    const rang = uni ? rangDuCote(ex, j) : j, cote = uni ? s.side : null;
    const prev = prevOf(ex.name, rang, cote);
    card.append(el("div", { className: "row" + (uni ? " side" : "") },
      el("button", { className: "t", textContent: label, title: "Changer le type (N, W, D, F)",
        onclick: () => { s.set_type = TYPES[(TYPES.indexOf(s.set_type) + 1) % TYPES.length]; persist(); render(); } }),
      ...(uni ? [el("button", { className: "t", textContent: s.side || "D", title: "Changer de côté (D / G)",
        onclick: () => { s.side = s.side === "D" ? "G" : "D"; persist(); render(); } })] : []),
      el("button", { className: "prev", textContent: prevText(ex.name, rang, unit, cote), disabled: !prev, title: "Copier les valeurs de la dernière séance",
        onclick: () => { s.weight_kg = prev.weight_kg; s.reps = prev.reps; persist(); render(); } }),
      numInput(s, "weight_kg", "decimal", `${ex.name} série ${label}`, unit),
      numInput(s, "reps", unit === "sec" ? "decimal" : "numeric", `${ex.name} série ${label}`, unit),
      numInput(s, "rpe", "decimal", `${ex.name} série ${label}`, unit),
      el("button", { className: "ok" + (s.completed ? " on" : ""), textContent: "OK", "aria-label": "Valider la série", onclick: () => toggleDone(ex, s) })));
  });
  card.append(el("button", { className: "add", textContent: "+ Ajouter une série", onclick: () => {
    const last = ex.sets[ex.sets.length - 1];
    const nouvelle = { set_type: "N", weight_kg: last ? last.weight_kg : 0, reps: last ? last.reps : 0, rpe: null, completed: false };
    if (uni) nouvelle.side = last && last.side === "D" ? "G" : "D"; // l'autre bras
    ex.sets.push(nouvelle);
    persist(); render();
  } }));
  const clean = cleanButton(todo, () => { if (confirm(`Retirer ${todo} série(s) non validée(s) de ${ex.name} ?`)) dropUnvalidated((e) => e === ex); });
  if (clean) card.append(clean);
  return card;
}

function blockCard(id) {
  const rows = [];
  draft.exercises.forEach((ex, i) => { if (ex.block === id) ex.sets.forEach((s, j) => rows.push({ ex, i, s, j })); });
  rows.sort((a, b) => a.s.minute - b.s.minute);
  const names = [...new Set(rows.map((r) => r.ex.name))];
  const b = draft.blocks[id], running = !!b.t0;
  const done = rows.filter((r) => r.s.completed), todo = rows.length - done.length;
  const times = done.filter((r) => r.s.duration_s != null).map((r) => r.s.duration_s);
  const card = el("div", { className: "card emom" });
  card.dataset.block = id;
  const head = el("div", { className: "ehead" },
    el("div", { className: "meta" },
      el("span", { className: "etag", textContent: "EMOM  " + names.join(" / ") }),
      el("span", { className: "etime" })),
    el("div", { className: "meta" }, el("span", { className: "emin ehmin" })),
    el("div", { className: "gbar" }, el("div", { className: "gfill" })),
    el("div", { className: "ctrls" },
      el("button", { textContent: running ? "Pause" : "Start", onclick: () => (running ? blockPause(id) : blockStart(id)) }),
      el("button", { textContent: "Reset", onclick: () => blockReset(id) }),
      el("button", { className: "x", textContent: "Suppr", onclick: () => { if (confirm("Supprimer cet EMOM ?")) { draft.exercises = draft.exercises.filter((e) => e.block !== id); delete draft.blocks[id]; persist(); render(); } } })));
  card.append(head);
  if (!("wakeLock" in navigator)) card.append(el("div", { className: "small", textContent: "Écran non maintenu allumé (HTTPS requis) : règle la mise en veille Android au maximum." }));
  if (done.length) {
    const avg = times.length ? times.reduce((a, c) => a + c, 0) / times.length : null;
    const txt = `Validées ${done.length}/${rows.length}` + (times.length ? ` · dernière ${mmss(times[times.length - 1])} · moy. ${mmss(avg)}` : "");
    card.append(doneSummary(txt, b.showDone, () => { b.showDone = !b.showDone; persist(); render(); }));
  }
  rows.forEach(({ ex, s, j }) => {
    if (s.completed && !b.showDone) return; // stockée, non affichée
    const bwf = formulaOf(ex) === "bw_plus_weight", unit = unitOf(ex);
    const prev = prevOf(ex.name, j);
    const r = el("div", { className: "erow" });
    r.dataset.block = id; r.dataset.ex = draft.exercises.indexOf(ex); r.dataset.set = j; r.dataset.minute = s.minute;
    const fld = (lab, input) => el("div", { className: "fld" }, el("label", { textContent: lab }), input);
    r.append(
      el("div", { className: "etop" },
        el("span", { className: "mn", textContent: "M" + s.minute }),
        el("span", { className: "nm", textContent: ex.name }),
        el("button", { className: "prev", textContent: "Préc. " + prevText(ex.name, j, unit), disabled: !prev,
          onclick: () => { s.weight_kg = prev.weight_kg; s.reps = prev.reps; persist(); render(); } }),
        el("span", { className: "tm" })),
      el("div", { className: "ebar" }, el("div", { className: "efill" })),
      el("div", { className: "efields" },
        fld(bwf ? "Lest" : "Kg", numInput(s, "weight_kg", "decimal", `${ex.name} M${s.minute}`, unit)),
        fld(unit === "sec" ? "Sec" : "Reps", numInput(s, "reps", unit === "sec" ? "decimal" : "numeric", `${ex.name} M${s.minute}`, unit)),
        fld("RPE", numInput(s, "rpe", "decimal", `${ex.name} M${s.minute}`, unit)),
        el("button", { className: "ok" + (s.completed ? " on" : ""), textContent: "OK", style: "min-height:44px", onclick: () => toggleDone(ex, s) })));
    card.append(r);
  });
  const clean = cleanButton(todo, () => { if (confirm(`Retirer ${todo} série(s) non validée(s) de cet EMOM ?`)) dropUnvalidated((e) => e.block === id); });
  if (clean) card.append(clean);
  return card;
}

function render() {
  $("date").textContent = new Date().toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long" });
  const app = $("app");
  app.replaceChildren();
  app.append(el("input", { value: draft.name, "aria-label": "Nom de la séance", oninput: (e) => { draft.name = e.target.value; persist(); } }));
  if (!draft.exercises.length) app.append(startPanel());
  const seen = new Set();
  draft.exercises.forEach((ex, i) => {
    if (ex.block) {
      if (!seen.has(ex.block)) { seen.add(ex.block); app.append(blockCard(ex.block)); }
    } else app.append(exerciseCard(ex, i));
  });
  app.append(addPanel(), emomBuilder());
  renderStatus();
  tick();
}

// ───────── Barre − / + (saisie sans clavier) ─────────
const STEPS = { weight_kg: [-5, -2.5, 2.5, 5], reps: [-5, -1, 1, 5], repsSec: [-5, -1, 1, 5], rpe: [-1, -0.5, 0.5, 1] };
const FIELD_LABEL = { weight_kg: "Kg / lest", reps: "Reps", rpe: "RPE" };
let stepTarget = null, hideTimer = null;
const stepper = el("div", { id: "stepper", hidden: true });
document.body.append(stepper);

function showStepper(set, field, input, title, unit) {
  clearTimeout(hideTimer);
  stepTarget = { set, field, input };
  const steps = field === "reps" && unit === "sec" ? STEPS.repsSec : STEPS[field];
  const fl = field === "reps" && unit === "sec" ? "Secondes" : FIELD_LABEL[field];
  stepper.replaceChildren(
    el("div", { className: "small", textContent: `${title} · ${fl}` }),
    el("div", { className: "stepbtns" },
      ...steps.map((d) => el("button", { textContent: (d > 0 ? "+" : "-") + Math.abs(d),
        onpointerdown: (e) => e.preventDefault(), onclick: () => step(d) })),
      el("button", { textContent: "Clav.", title: "Clavier numérique", className: cfg.keyboard ? "on" : "",
        onpointerdown: (e) => e.preventDefault(),
        onclick: () => { cfg.keyboard = !cfg.keyboard; save(K.cfg, cfg); input.blur();
          input.inputMode = cfg.keyboard ? (field === "reps" ? "numeric" : "decimal") : "none"; input.focus(); } }),
      el("button", { textContent: "OK", onpointerdown: (e) => e.preventDefault(), onclick: () => document.activeElement.blur() })));
  stepper.hidden = false;
}
function hideStepperSoon() {
  hideTimer = setTimeout(() => {
    if (!document.activeElement || document.activeElement.tagName !== "INPUT") { stepper.hidden = true; stepTarget = null; }
  }, 150);
}
function step(d) {
  if (!stepTarget) return;
  const { set, field, input } = stepTarget;
  const base0 = field === "rpe" ? 7 : 0;
  let v = Math.round(((set[field] ?? base0) + d) * 100) / 100;
  v = field === "rpe" ? Math.min(10, Math.max(1, v)) : Math.max(0, v);
  set[field] = v; input.value = v; persist(); input.select();
}

// ───────── Son, vibration, écran ─────────
let audioCtx = null, wake = null;
function beep(ms, hz) {
  try {
    audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
    const o = audioCtx.createOscillator(), g = audioCtx.createGain();
    o.connect(g); g.connect(audioCtx.destination); o.frequency.value = hz;
    g.gain.setValueAtTime(0.4, audioCtx.currentTime);
    g.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + ms / 1000);
    o.start(); o.stop(audioCtx.currentTime + ms / 1000);
  } catch { /* son indisponible */ }
}
const TONE = { warn: [110, 880], minute: [550, 1320], end: [1000, 520] }; // [durée ms, fréquence Hz]
const tone = (k) => beep(...TONE[k]);
const buzz = (p) => { try { navigator.vibrate && navigator.vibrate(p); } catch { /* ignoré */ } };
const anyRunning = () => Object.values(draft.blocks).some((b) => b.t0);
async function wantWake(on) {
  try {
    if (on && navigator.wakeLock && !wake) { wake = await navigator.wakeLock.request("screen"); wake.onrelease = () => { wake = null; }; }
    else if (!on && wake) { await wake.release(); wake = null; }
  } catch { /* refusé */ }
}
document.addEventListener("visibilitychange", () => { if (!document.hidden && anyRunning()) wantWake(true); });

// ───────── Minuteur EMOM (heure réelle : exact même si l'onglet est ralenti) ─────────
const lastSec = {};
function blockTotal(id) {
  let m = 0;
  draft.exercises.forEach((e) => { if (e.block === id) e.sets.forEach((s) => { m = Math.max(m, s.minute); }); });
  return m;
}
function blockInfo(id) {
  const b = draft.blocks[id], total = blockTotal(id);
  const elapsed = b.t0 ? nowMs() - b.t0 : b.el || 0;
  const done = elapsed >= total * MIN_MS;
  const minute = Math.min(total, Math.floor(elapsed / MIN_MS) + 1);
  const inMin = done ? MIN_MS : elapsed % MIN_MS;
  return { total, elapsed, done, minute, inMin, remain: Math.ceil((MIN_MS - inMin) / 1000) };
}
function blockStart(id) {
  Object.entries(draft.blocks).forEach(([o, ob]) => { if (o !== id && ob.t0) { ob.el = nowMs() - ob.t0; ob.t0 = null; } });
  const b = draft.blocks[id];
  if (blockInfo(id).done) b.el = 0;
  b.t0 = nowMs() - (b.el || 0);
  lastSec[id] = Math.floor((nowMs() - b.t0) / 1000);
  tone("minute"); buzz(150); wantWake(true); touch(false); persist(); render();
}
function blockPause(id) {
  const b = draft.blocks[id];
  b.el = nowMs() - b.t0; b.t0 = null; touch(); persist(); render();
  if (!anyRunning()) wantWake(false);
}
function blockReset(id) {
  const b = draft.blocks[id]; b.t0 = null; b.el = 0; delete lastSec[id];
  persist(); render();
  if (!anyRunning()) wantWake(false);
}
function blockFinish(id) {
  const b = draft.blocks[id];
  b.el = blockTotal(id) * MIN_MS; b.t0 = null; delete lastSec[id];
  tone("end"); buzz([300, 100, 300]); touch(); persist();
  if (!anyRunning()) wantWake(false);
  render();
}

function updateBlockDom(id, info) {
  const card = document.querySelector(`.card[data-block="${id}"]`);
  if (!card) return;
  const b = draft.blocks[id], started = !!b.t0 || (b.el || 0) > 0;
  const head = card.querySelector(".ehead");
  card.querySelector(".etime").textContent = info.done ? "FIN" : mmss(info.remain);
  card.querySelector(".ehmin").textContent = info.done ? `Terminé · ${info.total} min` : `Minute ${info.minute}/${info.total}`;
  card.querySelector(".gfill").style.width = `${Math.min(100, (info.elapsed / (info.total * MIN_MS)) * 100)}%`;
  head.classList.toggle("urgent", !!b.t0 && !info.done && info.remain <= 4);
  card.querySelectorAll(".erow").forEach((r) => {
    const ex = draft.exercises[+r.dataset.ex], s = ex.sets[+r.dataset.set], m = +r.dataset.minute;
    const fill = r.querySelector(".efill"), tm = r.querySelector(".tm");
    const active = started && !info.done && m === info.minute;
    r.classList.toggle("cur", active);
    r.classList.toggle("urgent", active && !!b.t0 && info.remain <= 4);
    r.classList.toggle("done", s.completed && s.duration_s != null);
    r.classList.toggle("late", s.completed && s.duration_s == null);
    r.classList.toggle("miss", !s.completed && started && (info.done || m < info.minute));
    if (s.completed && s.duration_s != null) { fill.style.width = `${Math.min(100, (s.duration_s * 1000 / MIN_MS) * 100)}%`; tm.textContent = mmss(s.duration_s); }
    else if (s.completed) { fill.style.width = "100%"; tm.textContent = "--"; }
    else if (active) { fill.style.width = `${(info.inMin / MIN_MS) * 100}%`; tm.textContent = mmss(info.inMin / 1000); }
    else { fill.style.width = "0"; tm.textContent = started && (info.done || m < info.minute) ? "ratée" : ""; }
  });
}

function tick() {
  Object.keys(draft.blocks).forEach((id) => {
    const b = draft.blocks[id], info = blockInfo(id);
    if (b.t0 && info.done) { blockFinish(id); return; }
    if (b.t0) {
      const sec = Math.floor(info.elapsed / 1000);
      if (lastSec[id] !== sec) {
        const s = sec % 60;
        if (lastSec[id] !== undefined) {
          if (s === 0) { // 60 s : début de la minute suivante, bip différent
            tone("minute"); buzz(250);
            if (!document.activeElement || document.activeElement.tagName !== "INPUT") {
              document.querySelector(`.erow[data-block="${id}"][data-minute="${info.minute}"]`)?.scrollIntoView({ block: "center", behavior: "smooth" });
            }
          } else if (s >= 57) { tone("warn"); buzz(40); } // 57, 58, 59
        }
        lastSec[id] = sec;
      }
    }
    updateBlockDom(id, info);
  });
}
setInterval(tick, 250);

// ───────── Envoi ─────────
function payloadFromDraft() {
  const wf = draft.worked_from, wt = draft.worked_to || wf;
  return {
    client_uuid: draft.client_uuid, name: draft.name.trim() || "Séance", template_id: draft.template_id || null,
    bodyweight_kg: cfg.bodyweight_kg || catalog.last_bodyweight_kg || null,
    started_at: draft.started_at, finished_at: nowIso(),
    ...(wf ? { worked_from: wf, worked_to: wt } : {}),
    exercises: draft.exercises.map((e) => ({ e, sets: e.sets.filter((s) => s.completed) })).filter((x) => x.sets.length).map(({ e, sets }) => ({
      name: e.name, create: !!e.create,
      load_formula: e.create ? e.load_formula || "weight" : "weight", unit: e.create ? e.unit || "reps" : "reps",
      emom_interval_sec: e.block ? 60 : null,
      sets: [...sets].sort((a, b) => (a.minute || 0) - (b.minute || 0)).map((s) => ({
        set_type: s.set_type, weight_kg: s.weight_kg || 0, reps: s.reps || 0, rpe: s.rpe || null, completed: true,
        duration_s: s.duration_s ?? null, emom_minute: s.minute ?? null,
        side: e.unilateral ? s.side || null : null,
      })),
    })),
  };
}

async function flush() {
  const pending = load(K.pending, []);
  if (!pending.length) return;
  if (!cfg.token) { setStatus("err", "Jeton manquant : ouvre Réglages."); return; }
  let sent = 0, logged = 0;
  const results = [];
  for (const p of pending) {
    let r;
    try { r = await api("/api/workouts", { method: "POST", body: JSON.stringify(p) }); }
    catch { setStatus("wait", "Serveur injoignable : la séance reste en attente."); break; }
    if (r.ok) {
      sent++;
      const out = await r.json().catch(() => ({}));
      logged += out.duration_min || 0;
      results.push(out);
      save(K.pending, load(K.pending, []).filter((x) => x.client_uuid !== p.client_uuid));
    } else {
      const t = await r.text().catch(() => "");
      setStatus("err", `Refusée (${r.status}). ${t.slice(0, 200)}`);
      break;
    }
  }
  if (sent) {
    setStatus("ok", `Séance synchronisée (${sent}).` + (logged ? ` Durée enregistrée : ${Math.round(logged * 10) / 10} min.` : ""));
    showResults(results);
  }
  renderStatus();
  refreshCatalog();
}

async function refreshCatalog() {
  if (!cfg.token) return;
  try {
    const [rx, rt] = await Promise.all([api("/api/exercises"), api("/api/templates")]);
    if (!rx.ok || !rt.ok) return;
    catalog = { ...(await rx.json()), templates: await rt.json() };
    save(K.cat, catalog);
    bwHint();
    if (!stepTarget && !(document.activeElement && document.activeElement.tagName === "INPUT")) render();
  } catch { /* hors ligne : catalogue en cache */ }
}

// Durée > 600 min : le début est presque sûrement faux (vieux brouillon). Propose de saisir l'heure de début réelle
// (aujourd'hui) ; retourne false si la durée reste hors limites, pour ne pas envoyer une séance que l'API refuserait.
function corrigerDureeExcessive() {
  if (!draft.worked_from) return true;
  const mins = () => (new Date(draft.worked_to || draft.worked_from) - new Date(draft.worked_from)) / 60000;
  if (mins() >= 0 && mins() <= MAX_WORK_MIN) return true;
  const rep = prompt(`Durée calculée : ${Math.round(mins())} min (maximum ${MAX_WORK_MIN}). Le début est sans doute faux.\n`
    + "Heure de début réelle d'aujourd'hui (HH:MM) ? Annuler pour ne rien envoyer.");
  const m = rep && rep.trim().match(/^(\d{1,2})[:h](\d{2})$/);
  if (!m || +m[1] > 23 || +m[2] > 59) { setStatus("err", "Envoi annulé : début de séance à corriger."); return false; }
  const p = (n) => String(n).padStart(2, "0"), d = new Date(nowMs());
  draft.worked_from = `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(+m[1])}:${m[2]}:00`;
  if (new Date(draft.worked_to || draft.worked_from) < new Date(draft.worked_from)) draft.worked_to = nowIso();
  draft.started_at = draft.worked_from;
  persist();
  if (mins() < 0 || mins() > MAX_WORK_MIN) { setStatus("err", "Durée toujours hors limites : envoi annulé."); return false; }
  return true;
}

$("finish").onclick = () => {
  const done = draft.exercises.reduce((a, e) => a + e.sets.filter((s) => s.completed).length, 0);
  if (!done) { setStatus("err", "Aucune série validée à envoyer."); return; }
  const skipped = unvalidatedCount();
  let dur = "";
  if (!corrigerDureeExcessive()) return;
  if (draft.worked_from) {
    const m = (new Date(draft.worked_to || draft.worked_from) - new Date(draft.worked_from)) / 60000;
    dur = `, durée ${Math.round(m * 10) / 10} min`;
  }
  const ignore = skipped ? `\n${skipped} série(s) non validée(s) seront ignorée(s).` : "";
  if (!confirm(`Terminer la séance (${done} série(s) validée(s)${dur}) et l'envoyer ?${ignore}`)) return;
  Object.values(draft.blocks).forEach((b) => { if (b.t0) { b.el = nowMs() - b.t0; b.t0 = null; touch(); } });
  const pending = load(K.pending, []);
  pending.push(payloadFromDraft());
  save(K.pending, pending); // la séance est en file avant tout envoi : rien n'est perdu
  localStorage.removeItem(K.draft);
  draft = newDraft();
  persist();
  wantWake(false);
  render();
  flush();
};

// ───────── Fenêtre de fin de séance ─────────
const fmtKg = (v) => Math.round(v || 0).toLocaleString("fr-FR");
function showResults(results) {
  const box = $("mlines");
  box.replaceChildren();
  results.forEach((r) => box.append(
    el("div", { className: "mtitle", textContent: `Entraînement #${r.number}` }),
    el("div", { className: "mvol", textContent: `Volume ${fmtKg(r.volume_kg)} kg` }),
    r.duration_min ? el("div", { className: "small", textContent: `Durée ${Math.round(r.duration_min * 10) / 10} min` }) : el("span")));
  $("modal").hidden = false;
}
$("mok").onclick = () => { $("modal").hidden = true; };

// ───────── Réglages ─────────
const num = (id) => { const v = $(id).value.trim().replace(",", "."); return v === "" ? null : Number(v); };
function bwHint() {
  $("cfg-bw-hint").textContent = catalog.last_bodyweight_kg ? `(dernier enregistré : ${catalog.last_bodyweight_kg} kg)` : "";
}
$("cfg-url").value = cfg.url;
$("cfg-token").value = cfg.token;
$("cfg-bw").value = cfg.bodyweight_kg ?? "";
$("cfg-height").value = cfg.height_cm ?? "";
bwHint();
$("cfg-save").onclick = () => {
  const bw = num("cfg-bw"), h = num("cfg-height");
  if (bw !== null && !(bw >= 30 && bw <= 300)) { setStatus("err", "Poids invalide (30 à 300 kg)."); return; }
  if (h !== null && !(h >= 100 && h <= 250)) { setStatus("err", "Taille invalide (100 à 250 cm)."); return; }
  cfg = { ...cfg, url: $("cfg-url").value.trim(), token: $("cfg-token").value.trim(), bodyweight_kg: bw, height_cm: h };
  save(K.cfg, cfg);
  setStatus("ok", "Réglages enregistrés.");
  flush(); refreshCatalog();
};

window.addEventListener("online", flush);
if ("serviceWorker" in navigator && (location.protocol === "https:" || location.hostname === "localhost")) {
  navigator.serviceWorker.register("sw.js").catch(() => {});
}
render();
flush();
refreshCatalog();
