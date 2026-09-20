/* ================= KAMELEON PDF — logika interfejsu ================= */
"use strict";

const $ = (id) => document.getElementById(id);
const state = {
  sid: null, name: "", pages: 0, page: 0,
  items: [],               // wykryte elementy (JSON z API)
  changed: {},             // id -> nowa wartość
  previewSrc: {},          // page -> dataURL (cache źródła)
  previewRes: {},          // page -> dataURL (cache wyniku)
  typeFilter: new Set(),
  hasResult: false,
};

const TYPE_GROUP = (t) => {
  if (t === "data") return "data";
  if (["imię i nazwisko","nazwisko","nazwa"].includes(t)) return "osoby";
  if (t.startsWith("kwota")) return "kwota";
  if (["PESEL","NIP","REGON","nr konta","kod pocztowy"].includes(t)) return "id";
  if (["telefon","telefon?"].includes(t)) return "id";
  return "numer";
};
const BADGE_CLASS = (t) => {
  const g = TYPE_GROUP(t);
  if (g === "osoby") return "t-osoba";
  if (g === "kwota") return "t-kwota";
  if (g === "id") return "t-id";
  if (g === "numer") return "t-numer";
  if (g === "data") return "t-data";
  return "t-inne";
};
const SCALE = 940; // szerokość podglądu w px logicznych PDF

/* ---------------- toasty ---------------- */
function toast(msg, kind = "") {
  const d = document.createElement("div");
  d.className = "toast " + kind;
  d.innerHTML = msg;
  $("toasts").appendChild(d);
  setTimeout(() => { d.style.opacity = "0"; d.style.transition = ".4s"; setTimeout(() => d.remove(), 420); }, 4600);
}

/* ---------------- upload / analiza ---------------- */
$("dropzone").onclick = () => $("file-input").click();
$("file-input").onchange = (e) => { if (e.target.files[0]) uploadFile(e.target.files[0]); };
const dz = $("dropzone");
["dragover","dragenter"].forEach(ev => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add("drag"); }));
["dragleave","drop"].forEach(ev => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.remove("drag"); }));
dz.addEventListener("drop", (e) => { const f = e.dataTransfer.files[0]; if (f) uploadFile(f); });

async function uploadFile(file) {
  if (!file.name.toLowerCase().endsWith(".pdf")) { toast("Wybierz plik PDF.", "err"); return; }
  const fd = new FormData(); fd.append("file", file);
  $("progress-wrap").classList.remove("hidden");
  $("progress-bar").style.width = "35%";
  try {
    const r = await fetch("/api/upload", { method: "POST", body: fd });
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || "Błąd wgrywania");
    Object.assign(state, {
      sid: j.session.sid, name: j.session.name, pages: j.session.pages, page: 0,
      items: j.items, changed: {}, previewSrc: {}, previewRes: {}, typeFilter: new Set(), hasResult: false,
    });
    $("file-info").classList.remove("hidden");
    $("fi-name").textContent = "📄 " + file.name;
    $("fi-meta").textContent = `${j.items.length} wykrytych elementów · ${j.session.pages} stron` +
      (j.session.empty_pages.length ? ` · ${j.session.empty_pages.length} stron do OCR` : "");
    $("viewer-empty").classList.add("hidden");
    $("viewer-stage").classList.remove("hidden");
    $("btn-apply").disabled = false;
    $("btn-download").classList.add("hidden");
    buildTypeChips();
    renderItems();
    await showPage(0);
    toast(`Przeanalizowano: <b>${j.items.length}</b> elementów.`, "ok");
    loadDatesInfo();
  } catch (err) {
    toast(err.message, "err");
  } finally {
    $("progress-bar").style.width = "100%";
    setTimeout(() => $("progress-wrap").classList.add("hidden"), 500);
  }
}

/* ---------------- podgląd ---------------- */
async function showPage(p) {
  state.page = Math.max(0, Math.min(state.pages - 1, p));
  const which = ($("show-result").checked && state.hasResult) ? "wynik" : "zrodlo";
  const cache = which === "wynik" ? state.previewRes : state.previewSrc;
  $("pg-label").textContent = `strona ${state.page + 1} / ${state.pages}`;
  try {
    if (!cache[state.page]) {
      const r = await fetch(`/api/preview/${state.sid}/${state.page}?co=${which}`);
      const j = await r.json();
      if (j.error) throw new Error(j.error);
      cache[state.page] = j.img;
    }
    $("page-img").src = cache[state.page];
    drawBoxes();
  } catch (e) { toast(e.message, "err"); }
}
$("pg-prev").onclick = () => showPage(state.page - 1);
$("pg-next").onclick = () => showPage(state.page + 1);
$("show-result").onchange = () => { state.page = 0; showPage(0); };
$("show-boxes").onchange = () => drawBoxes();

function drawBoxes() {
  const img = $("page-img"), stage = $("boxes");
  stage.innerHTML = "";
  if (!$("show-boxes").checked || !img.naturalWidth) return;
  const sw = img.clientWidth / SCALE;
  for (const it of state.items) {
    if (it.page !== state.page) continue;
    if (state.typeFilter.size && !state.typeFilter.has(TYPE_GROUP(it.type))) continue;
    const [x0, y0, x1, y1] = it.rect;
    const b = document.createElement("div");
    b.className = "box" + (state.changed[it.id] ? " changed" : "");
    const col = { data: "var(--gold)", osoby: "var(--blue)", kwota: "var(--green)", id: "var(--red)", numer: "var(--purple)" }[TYPE_GROUP(it.type)];
    b.style.cssText = `left:${x0*sw}px; top:${y0*sw}px; width:${(x1-x0)*sw}px; height:${(y1-y0)*sw}px; border-color:${col}`;
    b.title = `${it.type}: ${it.value}${it.label ? "  •  " + it.label : ""}`;
    b.onclick = () => { document.querySelector(`[data-item="${it.id}"]`)?.scrollIntoView({ behavior: "smooth", block: "center" }); };
    stage.appendChild(b);
  }
}
window.addEventListener("resize", drawBoxes);

/* ---------------- lista elementów ---------------- */
function buildTypeChips() {
  const groups = new Set(state.items.map(i => TYPE_GROUP(i.type)));
  const names = { data: "daty", osoby: "osoby", kwota: "kwoty", id: "PESEL/NIP/konta/telefony", numer: "numery" };
  const el = $("type-chips"); el.innerHTML = "";
  for (const g of ["data","osoby","kwota","id","numer"]) {
    if (!groups.has(g)) continue;
    const c = document.createElement("span");
    c.className = "chip on"; c.textContent = names[g]; c.dataset.g = g;
    c.onclick = () => {
      if (state.typeFilter.has(g)) state.typeFilter.delete(g); else state.typeFilter.add(g);
      c.classList.toggle("on");
      drawBoxes(); renderItems();
    };
    el.appendChild(c);
  }
}

function renderItems() {
  const wrap = $("items"); wrap.innerHTML = "";
  const q = $("filter").value.trim().toLowerCase();
  const pageItems = state.items.filter(it => it.page === state.page);
  const list = pageItems.filter(it => {
    if (state.typeFilter.size && !state.typeFilter.has(TYPE_GROUP(it.type))) return false;
    if (q && !(`${it.value} ${it.type} ${it.label}`.toLowerCase().includes(q))) return false;
    return true;
  });
  if (!list.length) {
    wrap.innerHTML = `<div class="empty-list">${state.items.length ? "Brak elementów na tej stronie / dla filtra." : "Brak danych — wgraj dokument."}</div>`;
    return;
  }
  for (const it of list) {
    const nv = state.changed[it.id] || "";
    const d = document.createElement("div");
    d.className = "it"; d.dataset.item = it.id;
    d.innerHTML = `
      <div class="it-head">
        <span class="badge ${BADGE_CLASS(it.type)}">${it.type}</span>
        <span class="it-label" title="${esc(it.label)}">${esc(it.label) || "—"}</span>
        <span class="score-b" title="pewność wykrycia">${pct(it.score)}</span>
      </div>
      <div class="it-vals">
        <span class="old" title="wartość oryginalna">${esc(it.value)}</span>
        <span style="color:var(--txt3)">→</span>
        <input type="text" placeholder="nowa wartość…" value="${esc(nv)}" data-id="${it.id}">
      </div>
      <div class="it-meta"><span>${esc(it.font)}${it.source === "ocr" ? " • <b style='color:var(--orange)'>OCR</b>" : ""}</span><span>str. ${it.page + 1}</span></div>`;
    d.querySelector("input").addEventListener("input", (e) => {
      const v = e.target.value;
      if (v && v !== it.value) state.changed[it.id] = v; else delete state.changed[it.id];
      e.target.classList.toggle("has-new", !!(v && v !== it.value));
      updateStats(); drawBoxes();
    });
    wrap.appendChild(d);
  }
}
$("filter").addEventListener("input", renderItems);

const esc = (s) => (s ?? "").toString().replace(/[&<>"]/g, c => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;" }[c]));
const pct = (s) => { const p = Math.round(s * 100); return p >= 85 ? "★★★" : p >= 60 ? "★★" : "★"; };

function updateStats() {
  $("stat-changed").innerHTML = `Zmienione: <b>${Object.keys(state.changed).length}</b>`;
}

/* ---------------- zastosowanie zmian ---------------- */
$("btn-apply").onclick = async () => {
  if (!state.sid) return;
  if (!Object.keys(state.changed).length) { toast("Najpierw wpisz nowe wartości w prawym panelu.", "err"); return; }
  $("btn-apply").disabled = true;
  $("apply-info").innerHTML = '<span class="spin"></span> Przetwarzanie…';
  const fd = new FormData();
  fd.append("sid", state.sid);
  fd.append("values", JSON.stringify(state.changed));
  fd.append("expand", $("opt-expand").checked ? "1" : "0");
  fd.append("embedded", $("opt-embedded").checked ? "1" : "0");
  fd.append("center", $("opt-center").checked ? "1" : "0");
  fd.append("fill", $("opt-fill").value);
  fd.append("min_size", $("opt-minsize").value);
  try {
    const r = await fetch("/api/apply", { method: "POST", body: fd });
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || "Błąd");
    state.hasResult = true; state.previewRes = {};
    const okCount = (j.reports || []).filter(x => x.status.startsWith("ok")).length;
    const shrunk = (j.reports || []).filter(x => x.shrunk).length;
    $("apply-info").innerHTML = `✅ Podmieniono <b>${okCount}</b> elementów` + (shrunk ? ` (w ${shrunk} zmniejszono czcionkę, by uniknąć nakładania)` : "");
    const dl = $("btn-download");
    dl.href = `/api/download/${state.sid}`;
    dl.classList.remove("hidden");
    if (j.warning) toast(j.warning, "err");
    toast("Zmiany zastosowane. Przełącz „podgląd wyniku”, aby zobaczyć efekt.", "ok");
    $("show-result").checked = true;
    showPage(0);
    loadDatesInfo();
  } catch (e) {
    $("apply-info").textContent = "";
    toast(e.message, "err");
  } finally {
    $("btn-apply").disabled = false;
  }
};

$("btn-bulk").onclick = () => { state.changed = {}; renderItems(); updateStats(); drawBoxes(); };

/* ---------------- OCR ---------------- */
$("btn-ocr").onclick = async () => {
  if (!state.sid) { toast("Najpierw wgraj dokument.", "err"); return; }
  if (!state.pages || !state.items) return;
  toast("OCR w toku — strony zeskanowane mogą chwilę zająć…");
  const fd = new FormData(); fd.append("sid", state.sid);
  try {
    const r = await fetch("/api/ocr", { method: "POST", body: fd });
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || "Błąd OCR");
    state.items = j.items;
    renderItems(); drawBoxes(); updateStats();
    toast(`OCR: dodano <b>${j.added}</b> elementów ze skanów (mniejsza pewność).`, "ok");
  } catch (e) { toast(e.message, "err"); }
};

/* ---------------- daty ---------------- */
async function loadDatesInfo() {
  if (!state.sid) return;
  try {
    const r = await fetch(`/api/filedates/${state.sid}`);
    const j = await r.json();
    const c = j.current;
    $("dates-current").innerHTML =
      `Utworzony: <b>${(c.created || "—").replace("T", " ")}</b><br>` +
      `Zmodyfikowany: <b>${(c.modified || "—").replace("T", " ")}</b><br>` +
      `PDF CreationDate: <b>${esc((c.pdf_creation || "—").replace("D:", ""))}</b>`;
  } catch (e) { /* ignoruj */ }
}
function openDates() {
  if (!state.sid) { toast("Najpierw wgraj dokument.", "err"); return; }
  $("dlg-dates").showModal();
}
$("btn-dates").onclick = openDates;
$("btn-dates-2").onclick = openDates;
$("dt-save").onclick = async () => {
  const fd = new FormData();
  fd.append("sid", state.sid);
  if ($("dt-created").value) fd.append("created", $("dt-created").value);
  if ($("dt-modified").value) fd.append("modified", $("dt-modified").value);
  fd.append("pdf_meta", $("dt-pdfmeta").checked ? "1" : "0");
  fd.append("target", state.hasResult ? "wynik" : "zrodlo");
  try {
    const r = await fetch("/api/filedates", { method: "POST", body: fd });
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || "Błąd");
    toast("Daty zapisane: " + JSON.stringify(j.current).slice(0, 120), "ok");
    $("dlg-dates").close();
    loadDatesInfo();
  } catch (e) { toast(e.message, "err"); }
};

/* ---------------- eksporty ---------------- */
function doExport(kind) {
  if (!state.sid) { toast("Najpierw wgraj dokument.", "err"); return; }
  const fd = new FormData(); fd.append("sid", state.sid); fd.append("kind", kind);
  fetch("/api/export", { method: "POST", body: fd })
    .then(r => { if (!r.ok) throw new Error("błąd"); return r.blob(); })
    .then(b => {
      const a = document.createElement("a");
      a.href = URL.createObjectURL(b); a.download = `kameleon_${kind}.${kind === "mapping" ? "json" : kind}`;
      a.click();
      toast("Wyeksportowano.", "ok");
    }).catch(e => toast(e.message, "err"));
}
$("btn-export-csv").onclick = () => doExport("csv");
$("btn-export-json").onclick = () => doExport("json");
$("btn-export-map").onclick = () => doExport("mapping");

/* ---------------- tryb wsadowy ---------------- */
let batchBid = null;
$("btn-batch").onclick = () => $("dlg-batch").showModal();
$("batch-run").onclick = async () => {
  const files = $("batch-files").files;
  const mapFile = $("batch-mapping").files[0];
  if (!files.length) { toast("Wybierz pliki PDF.", "err"); return; }
  if (!mapFile) { toast("Wybierz plik mapowania JSON (przycisk MAPA).", "err"); return; }
  $("batch-status").innerHTML = '<span class="spin"></span> Przetwarzanie wsadowe…';
  const fd = new FormData();
  for (const f of files) fd.append("files", f);
  try {
    const r1 = await fetch("/api/batch/upload", { method: "POST", body: fd });
    const j1 = await r1.json();
    if (!r1.ok) throw new Error(j1.error);
    batchBid = j1.bid;
    const mapping = JSON.parse((await mapFile.text()).replace(/^\uFEFF/, ''));
    const fd2 = new FormData();
    fd2.append("bid", batchBid); fd2.append("mapping", JSON.stringify(mapping));
    const r2 = await fetch("/api/batch/run", { method: "POST", body: fd2 });
    const j2 = await r2.json();
    if (!r2.ok) throw new Error(j2.error);
    let html = "<table><tr><th>Plik</th><th>Status</th><th>Podmiany</th></tr>";
    for (const r of j2.results) html += `<tr><td>${esc(r.plik)}</td><td>${esc(r.status)}</td><td>${r.podmieniono}</td></tr>`;
    html += "</table>";
    $("batch-status").innerHTML = html;
    const zip = $("batch-zip");
    zip.href = `/api/batch/download/${batchBid}`;
    zip.classList.remove("hidden");
    toast("Wsad zakończony.", "ok");
  } catch (e) { $("batch-status").textContent = "Błąd: " + e.message; }
};
