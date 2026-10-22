/*! © 2026 Award Insights · awardinsights.org · All rights reserved. */
/* Shared by every page: keeps the chosen institution (and Federal/NSF peers) on the tab links, lets each
   tool's search find institutions held by the other tools, and says plainly when a tool doesn't cover one.
   State lives only in the URL (#u=…); nothing is stored. Built pages load this with defer. */
(() => {
"use strict";
const TOOLS = [
  { id: "federal", bit: 1, name: "Federal Award Insights", short: "Federal" },
  { id: "nsf", bit: 2, name: "NSF Award Insights", short: "NSF" },
  { id: "designations", bit: 4, name: "Research Activity Designations", short: "Designations" },
  { id: "portfolio", bit: 8, name: "Research Portfolio Trends", short: "Portfolio" },
];
const PEERS = ["hold", "up", "x"];            // Federal and NSF share these peer settings
const SHARE_PEERS = new Set(["federal", "nsf"]);
const INST = (document.currentScript && document.currentScript.dataset.inst) || "/shared/inst.json";
const bar = document.querySelector(".sitebar"); if (!bar) return;
const here = bar.dataset.tool, T = TOOLS.find(t => t.id === here);
const $ = id => document.getElementById(id);
const strip = s => String(s == null ? "" : s).replace(/[<>&"]/g, "");
let IDX = null, byU = new Map(), pkRev = {}, pkFwd = {}, same = {};   // combined Portfolio unit -> main campus, campus -> unit, a tool's own id -> index id
let cur = "", peers = new URLSearchParams();

function readUrl(url) {
  const p = new URLSearchParams(new URL(url, location.href).hash.slice(1)), u = p.get("u");
  if (!u) return;
  cur = pkRev[u] || same[u] || u; peers = new URLSearchParams();
  PEERS.forEach(k => { if (p.has(k)) peers.set(k, p.get(k)); });
  links();
}
// the tools write their own state with history.replaceState; follow along so the tabs stay current
const rs = history.replaceState.bind(history), ps = history.pushState.bind(history);
history.replaceState = function (s, t, url) { const r = rs(s, t, url); if (url != null) try { readUrl(url); } catch (e) {} return r; };
history.pushState = function (s, t, url) { const r = ps(s, t, url); if (url != null) try { readUrl(url); } catch (e) {} return r; };

const idIn = (r, tool) => (r && r[4] && r[4][tool]) || (r ? r[0] : cur);   // the id that tool uses
function hashFor(id) {
  if (!cur) return "";
  const p = new URLSearchParams({ u: idIn(byU.get(cur), id) });
  if (SHARE_PEERS.has(id) && SHARE_PEERS.has(here)) peers.forEach((v, k) => p.set(k, v));
  return "#" + p.toString();
}
function links() {
  document.querySelectorAll(".sitebar nav a[data-t], .ai-src a[data-t]").forEach(a => { a.href = "/" + a.dataset.t + "/" + hashFor(a.dataset.t); });
}

function toolsFor(r) { return TOOLS.filter(t => r[3] & t.bit); }
function note(r) {
  const box = $("empty"); if (!box || !T) return;
  box.querySelectorAll(".ai-note").forEach(n => n.remove());
  const d = document.createElement("div"); d.className = "ai-note"; d.setAttribute("role", "status");
  const b = document.createElement("b"); b.textContent = strip(r[1]);
  d.append(b, ` isn't in ${T.name}`);
  const why = document.createElement("span"); why.className = "why"; why.textContent = `, which ${IDX.t[here].why}.`;
  d.append(why);
  const others = toolsFor(r);
  if (others.length) {
    const go = document.createElement("div"); go.className = "go";
    others.forEach(t => { const a = document.createElement("a"); a.href = "/" + t.id + "/#u=" + encodeURIComponent(idIn(r, t.id)); a.textContent = "See it in " + t.name; go.append(a); });
    d.append(go);
  }
  box.prepend(d); box.hidden = false;
}

function matches(s, rows) {
  return rows.filter(r => r[1].toLowerCase().includes(s))
    .sort((a, b) => (b[1].toLowerCase().startsWith(s) - a[1].toLowerCase().startsWith(s)) || a[1].localeCompare(b[1]));
}
function hitButton(r, cls) {
  const b = document.createElement("button"); b.type = "button"; if (cls) b.className = cls; b.dataset.ai = r[0];
  const n = document.createElement("span"); n.className = "rn"; n.textContent = strip(r[1]);
  const s = document.createElement("span"); s.className = "rs";
  s.textContent = [r[2], toolsFor(r).map(t => t.short).join(" · ") || "no tool"].filter(Boolean).join(" · ");
  b.append(n, s); return b;
}

/* a tool page: extend its own search, carry the selection, explain gaps */
function tool() {
  const q = $("q"), res = $("results");
  if (q && res) q.addEventListener("input", () => setTimeout(() => {   // after the tool has drawn its own hits
    const s = q.value.trim().toLowerCase(); if (!s || res.hidden) return;
    const extra = matches(s, IDX.i.filter(r => !(r[3] & T.bit))).slice(0, 6); if (!extra.length) return;
    if (!res.querySelector("button[data-u]")) res.innerHTML = "";        // drop "No institution found"
    const sep = document.createElement("div"); sep.className = "ai-sep"; sep.textContent = "Not in " + T.short;
    res.append(sep);
    extra.forEach(r => { const b = hitButton(r, "ai-other"); b.addEventListener("click", () => {
      res.hidden = true; q.value = ""; rs(null, "", "#u=" + encodeURIComponent(idIn(r, here))); location.reload();
    }); res.append(b); });
  }, 0));

  // Portfolio and Designations don't write the URL themselves: do it for them when an institution is chosen
  if (typeof window.select === "function") {
    const orig = window.select;
    window.select = function (u, ...rest) {
      const out = orig.call(this, u, ...rest);
      if (here === "portfolio" || here === "designations") history.replaceState(null, "", "#u=" + encodeURIComponent(pkRev[u] || u));
      else readUrl(location.href);
      document.querySelectorAll(".ai-note").forEach(n => n.remove());
      return out;
    };
  }

  const r = byU.get(cur);
  if (!cur || !r) return;
  if (!(r[3] & T.bit)) { note(r); return; }
  if (here === "portfolio" || here === "designations") {
    const key = here === "portfolio" ? (pkFwd[cur] || cur) : cur;
    if (typeof window.select === "function") window.select(key);
  }
}

/* the home page: one search across every tool; a choice opens the first tool that covers it */
function home() {
  const q = $("q"), res = $("results"); if (!q || !res) return;
  q.addEventListener("input", () => {
    const s = q.value.trim().toLowerCase(); res.innerHTML = "";
    if (!s) { res.hidden = true; return; }
    const hits = matches(s, IDX.i.filter(r => r[3])).slice(0, 12);
    if (!hits.length) { const b = document.createElement("button"); b.disabled = true; b.textContent = "No institution found"; res.append(b); }
    hits.forEach(r => { const b = hitButton(r); b.addEventListener("click", () => {
      const t = toolsFor(r)[0].id; location.href = "/" + t + "/#u=" + encodeURIComponent(idIn(r, t));
    }); res.append(b); });
    res.hidden = false;
  });
  document.addEventListener("click", e => { if (!e.target.closest(".search")) res.hidden = true; });
}

/* light/dark: follows the system until someone switches; a choice that matches the system is forgotten */
const dark = matchMedia("(prefers-color-scheme: dark)"), root = document.documentElement;
const mode = () => root.dataset.theme || (dark.matches ? "dark" : "light");
function label() { const b = bar.querySelector(".theme"); if (b) { const t = mode() === "dark" ? "Switch to light mode" : "Switch to dark mode"; b.setAttribute("aria-label", t); b.title = t; } }
const sw = bar.querySelector(".theme");
if (sw) sw.addEventListener("click", () => {
  const next = mode() === "dark" ? "light" : "dark", sys = dark.matches ? "dark" : "light";
  if (next === sys) delete root.dataset.theme; else root.dataset.theme = next;
  try { next === sys ? localStorage.removeItem("ai.theme") : localStorage.setItem("ai.theme", next); } catch (e) {}
  label();
});
dark.addEventListener("change", label); label();

/* NSF and Portfolio: card subtitles move into a popover behind a small "i" after the card title, as on Federal
   (Federal does this in its own script) */
if (here === "nsf" || here === "portfolio") {
  const closePops = except => document.querySelectorAll(".infopop").forEach(p => { if (p !== except && !p.hidden) { p.hidden = true; const b = p.parentElement.querySelector(".infobtn"); if (b) b.setAttribute("aria-expanded", "false"); } });
  const infoize = card => {
    const items = [...card.querySelectorAll(":scope > .csub")]; if (!items.length) return;
    const h3 = card.querySelector(":scope > .chd > h3, :scope > h3"); if (!h3) return;
    let btn = card.querySelector(".infobtn"), pop = card.querySelector(":scope > .infopop");
    if (!btn) { btn = document.createElement("button"); btn.type = "button"; btn.className = "infobtn"; btn.textContent = "i"; btn.setAttribute("aria-label", "About this section"); btn.setAttribute("aria-expanded", "false"); h3.after(btn); }
    if (!pop) { pop = document.createElement("div"); pop.className = "infopop"; pop.hidden = true; card.append(pop); }
    items.forEach(x => pop.append(x));
    btn.onclick = e => { e.stopPropagation(); const open = pop.hidden; closePops(pop); pop.hidden = !open; btn.setAttribute("aria-expanded", String(open)); if (open) pop.style.top = (btn.offsetTop + btn.offsetHeight + 6) + "px"; };
    pop.onclick = e => e.stopPropagation();
  };
  document.querySelectorAll(".card").forEach(infoize);
  new MutationObserver(ms => { for (const m of ms) { const c = m.target.closest && m.target.closest(".card"); if (c) infoize(c); } }).observe(document.body, { childList: true, subtree: true });
  document.addEventListener("click", () => closePops()); document.addEventListener("keydown", e => { if (e.key === "Escape") closePops(); });
}

/* the long methods paragraph at the bottom of each tool is tucked into a closed "Methods and notes" line
   (the element is moved, not copied, so a tool that fills it later still can) */
document.querySelectorAll(".foot").forEach(f => {
  if (f.closest(".ai-methods")) return;
  const d = document.createElement("details"); d.className = "ai-methods";
  const s = document.createElement("summary"); s.textContent = "Methods and notes";
  f.before(d); d.append(s, f);
});

try { readUrl(location.href); } catch (e) {}
links();
fetch(INST).then(r => r.json()).then(d => {
  IDX = d; IDX.i.forEach(r => { byU.set(r[0], r); if (r[4]) Object.values(r[4]).forEach(id => { same[id] = r[0]; }); });
  Object.entries(IDX.pk).forEach(([k, units]) => { pkRev[k] = units[0]; units.forEach(u => { pkFwd[u] = k; }); });
  if (cur && (pkRev[cur] || same[cur])) { cur = pkRev[cur] || same[cur]; links(); }
  if (here === "home") home(); else if (T) tool();
}).catch(() => {});
})();
