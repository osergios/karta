"use strict";
(() => {
  const screen = document.getElementById("screen");
  const LABEL = { ARRIVAL: "Προσέλευση", DEPARTURE: "Αποχώρηση" };
  const IDLE_MS = 30000;
  let idleTimer = null;
  let employees = [];
  let atHome = false;
  const loadedAt = Date.now();

  // ---------- clock ----------
  const fmtTime = new Intl.DateTimeFormat("el-GR", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false, timeZone: "Europe/Athens" });
  const fmtDate = new Intl.DateTimeFormat("el-GR", { weekday: "long", day: "numeric", month: "long", timeZone: "Europe/Athens" });
  function tick() {
    const now = new Date();
    const [hh, mm, ss] = fmtTime.format(now).split(":");
    const sec = document.createElement("span"); sec.className = "sec"; sec.textContent = ss;
    document.getElementById("clock").replaceChildren(`${hh}:${mm}`, sec);
    document.getElementById("date").textContent = fmtDate.format(now);
  }
  tick(); setInterval(tick, 1000);
  const logo = document.getElementById("logo");
  const brandName = document.getElementById("brandName");
  const noLogo = () => { logo.hidden = true; if (brandName && brandName.textContent.trim()) brandName.hidden = false; };
  if (logo) { logo.addEventListener("error", noLogo); if (logo.complete && !logo.naturalWidth) noLogo(); }   // may fail before this script runs
  const PREVIEW = new URLSearchParams(location.search).get("preview");   // admin «Προεπισκόπηση» of a closed day
  const festive = theme => { if (window.Festive) window.Festive.apply(theme || null); };

  // ---------- helpers ----------
  function el(tag, attrs = {}, ...children) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "class") n.className = v;
      else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, v);
    }
    for (const c of children) n.append(c);
    return n;
  }
  let cleanup = null;           // e.g. stops the camera when leaving the QR screen
  let resultTimer = null;        // auto-return from the result screen
  function show(...nodes) {
    clearTimeout(resultTimer);   // leaving the result screen early must not send the next person back home later
    if (cleanup) { const f = cleanup; cleanup = null; try { f(); } catch { /* ignore */ } }
    onKey = null; atHome = false; wedgeOn = false; screen.replaceChildren(...nodes);
  }
  // Physical keyboard support (laptop kiosk): each screen may set onKey.
  let onKey = null;
  // A USB QR scanner "types" the code and Enter. Read it by physical key (ev.code) so it
  // works whatever the keyboard layout (Greek layout would turn C into Ψ).
  let wedgeOn = false, wedgeBuf = "", wedgeAt = 0;
  const CODE_CHAR = c => /^Key[A-Z]$/.test(c) ? c.slice(3) : /^Digit[0-9]$/.test(c) ? c.slice(5) : /^Numpad[0-9]$/.test(c) ? c.slice(6) : c === "Semicolon" ? ":" : null;
  document.addEventListener("keydown", ev => {
    if (wedgeOn && !ev.ctrlKey && !ev.altKey && !ev.metaKey) {
      const now = performance.now();
      if (now - wedgeAt > 120) wedgeBuf = "";
      wedgeAt = now;
      if (ev.key === "Enter" && /^CK1:[A-Z2-7]{26}$/.test(wedgeBuf)) { const c = wedgeBuf; wedgeBuf = ""; ev.preventDefault(); qrFound(c); return; }
      const ch = CODE_CHAR(ev.code);
      if (ch) wedgeBuf = (wedgeBuf + ch).slice(-40);
      if (wedgeBuf.length > 1) { ev.preventDefault(); return; }   // mid-scan: don't let the keys drive the screen
    }
    if (ev.ctrlKey || ev.altKey || ev.metaKey || !onKey) return;
    if (onKey(ev.key, ev) === true) ev.preventDefault();
  });

  // ---------- greetings ----------
  const hourFmt = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", hour12: false, timeZone: "Europe/Athens" });
  const nowHour = () => Number(hourFmt.format(new Date())) % 24;
  // Greek vocative for the common name endings (Νίκος -> Νίκο, Δημήτρης -> Δημήτρη, Κώστας -> Κώστα).
  function vocative(name) {
    const [first, ...rest] = name.trim().split(/\s+/);
    const rules = [["ους", "ου"], ["ος", "ο"], ["ός", "ό"], ["ης", "η"], ["ής", "ή"], ["ας", "α"], ["άς", "ά"]];
    for (const [end, repl] of rules) {
      if (first.length > end.length + 1 && first.endsWith(end)) return [first.slice(0, -end.length) + repl, ...rest].join(" ");
    }
    return name.trim();
  }
  const hello = h => (h >= 4 && h < 12 ? "Καλημέρα" : "Καλησπέρα");
  function farewell(h, weekday) {
    if (weekday === 6) return "Καλό Σαββατοκύριακο";   // the salon is closed Sunday and Monday
    if (h < 13) return "Καλή συνέχεια";
    if (h < 18) return "Καλό απόγευμα";
    if (h < 21) return "Καλό βράδυ";
    return "Καλή ξεκούραση";
  }
  function backspaceIcon() {
    const NS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", "0 0 24 24"); svg.setAttribute("fill", "none");
    svg.setAttribute("stroke", "currentColor"); svg.setAttribute("stroke-width", "1.6");
    svg.setAttribute("stroke-linecap", "round"); svg.setAttribute("stroke-linejoin", "round"); svg.setAttribute("aria-hidden", "true");
    for (const d of ["M9 5h11v14H9l-6-7z", "M12.5 9.5l5 5", "M17.5 9.5l-5 5"]) {
      const path = document.createElementNS(NS, "path"); path.setAttribute("d", d); svg.append(path);
    }
    return svg;
  }
  function armIdle() { clearTimeout(idleTimer); idleTimer = setTimeout(home, IDLE_MS); }
  function disarmIdle() { clearTimeout(idleTimer); }
  async function api(path, body) {
    const opt = body === undefined
      ? { credentials: "same-origin" }
      : { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
    let res;
    try { res = await fetch(path, opt); }
    catch { return { status: 0, data: { detail: "Δεν υπάρχει σύνδεση. Χρησιμοποίησε την εφαρμογή ΕΡΓΑΝΗ στο κινητό σου." } }; }
    let data = {};
    try { data = await res.json(); } catch { /* ignore */ }
    return { status: res.status, data };
  }

  // ---------- screens ----------
  async function home() {
    disarmIdle();
    const { status, data } = await api("/api/kiosk/employees");
    if (status === 401) return notEnrolled();
    if (status !== 200) {
      show(el("h1", {}, "Η κάρτα δεν είναι διαθέσιμη"),
           el("p", { class: "hint" }, data.detail || "Χρησιμοποίησε την εφαρμογή ΕΡΓΑΝΗ στο κινητό σου."),
           el("button", { class: "plain", onclick: home }, "Δοκιμή ξανά"));
      setTimeout(home, 15000);
      return;
    }
    const mode = document.getElementById("mode");
    if (data.mode !== "production") { mode.hidden = false; mode.textContent = data.mode === "dry_run" ? "Δοκιμαστική λειτουργία" : "Περιβάλλον δοκιμών ΕΡΓΑΝΗ"; }
    else mode.hidden = true;
    employees = data.employees;
    festive(data.festive);
    closedKey = data.closed && !data.closed.works && !trainingOn ? data.closed.key : null;
    if (closedKey) return closedDay(data.closed, data.festive);
    if (!employees.length) {
      show(el("h1", {}, "Δεν υπάρχουν εργαζόμενοι"), el("p", { class: "hint" }, "Προσθέστε εργαζόμενους από τη διαχείριση."));
      return;
    }
    if (!hasCamera) return names(true);
    show(el("h1", {}, "Χτύπημα κάρτας"),
         el("p", { class: "hint" }, "Με την κάρτα QR σου (του καταστήματος ή του ΕΡΓΑΝΗ) ή με το PIN σου."),
         el("div", { class: "choices" },
           el("button", { class: "choice qr", onclick: scan }, icon("qr"),
             el("span", { class: "c-title" }, "Κάρτα QR"), el("span", { class: "c-sub" }, "Δείξε το QR στην κάμερα")),
           el("button", { class: "choice", onclick: () => names() }, icon("pin"),
             el("span", { class: "c-title" }, "Με PIN"), el("span", { class: "c-sub" }, "Διάλεξε όνομα και γράψε το PIN"))));
    atHome = true; wedgeOn = true;
    onKey = (k, ev) => {
      if (ev.code === "KeyQ" || k === "Enter" || k === " ") { scan(); return true; }
      if (ev.code === "KeyP" || /^[0-9]$/.test(k)) { names(); return true; }
    };
  }

  // ---------- closed day (holiday / shop closed): a greeting instead of the punch choices ----------
  let closedKey = null, trainingOn = false;
  const fmtReopen = new Intl.DateTimeFormat("el-GR", { weekday: "long", day: "numeric", month: "long", timeZone: "Europe/Athens" });
  function closedDay(c, theme) {
    disarmIdle();
    const art = theme && window.Festive ? window.Festive.hero(c.key) : null;   // pictures only with the decorations on
    const reopen = c.reopen ? fmtReopen.format(new Date(c.reopen + "T12:00:00Z")) : null;
    show(el("div", { class: "closed-day" },
      art ? el("div", { class: "cd-art", "aria-hidden": "true" }, art) : "",
      el("h1", {}, c.title),
      c.sub ? el("p", { class: "cd-sub" }, c.sub) : "",
      el("p", { class: "cd-note" }, c.kind === "holiday" ? "Σήμερα το κατάστημα είναι κλειστό. Δεν γίνονται χτυπήματα κάρτας."
                                                         : "Το κατάστημα είναι κλειστό. Δεν γίνονται χτυπήματα κάρτας."),
      reopen ? el("p", { class: "cd-reopen" }, `Σας περιμένουμε ξανά ${reopen.startsWith("Σάββατο") ? "το" : "την"} ${reopen}`) : ""));
    atHome = true;
  }

  function names(isHome = false) {
    if (!isHome) armIdle();
    show(el("h1", {}, "Ποιος χτυπάει κάρτα;"),
         el("div", { class: "names" }, ...employees.map(e => el("button", { class: "name", onclick: () => pin(e) },
           el("span", { class: "initial", "aria-hidden": "true" }, (e.name.trim()[0] || "?").toUpperCase()), e.name))),
         isHome ? "" : el("div", { class: "row" }, el("button", { class: "plain", onclick: home }, "Πίσω")));
    if (isHome) { atHome = true; wedgeOn = true; }
    else onKey = k => { if (k === "Escape") { home(); return true; } };
  }

  // ---------- QR card via the laptop camera ----------
  const hasCamera = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
  let jsQRReady = null;
  function loadJsQR() {
    if (!jsQRReady) jsQRReady = new Promise((ok, fail) => {
      if (window.jsQR) return ok();
      const sc = document.createElement("script");
      sc.src = "/static/vendor/jsQR.min.js"; sc.onload = () => ok(); sc.onerror = () => { jsQRReady = null; fail(); };
      document.head.append(sc);
    });
    return jsQRReady;
  }
  const SCAN_MS = 30000;
  async function scan() {
    disarmIdle();
    const video = el("video", { class: "cam", autoplay: "", muted: "", playsinline: "" });
    video.muted = true;
    const status = el("p", { class: "scan-status", role: "status" }, "Άνοιγμα κάμερας…");
    const err = el("p", { class: "msg-error", role: "alert" });
    const frame = el("div", { class: "camwrap" }, video, el("div", { class: "camframe", "aria-hidden": "true" }));
    let stream = null, raf = 0, stopped = false, lastTry = 0;
    const timer = setTimeout(home, SCAN_MS);
    const shutterHint = setTimeout(() => { if (!stopped) status.textContent = "Κράτα το QR ίσια, 15-25 εκ. από την κάμερα. Αν η εικόνα είναι μαύρη, άνοιξε το καπάκι της κάμερας."; }, 9000);
    const stop = () => {
      stopped = true; clearTimeout(timer); clearTimeout(shutterHint); cancelAnimationFrame(raf);
      if (stream) stream.getTracks().forEach(t => t.stop());
      video.srcObject = null;
    };
    show(el("h1", {}, "Δείξε την κάρτα QR"), frame, status, err,
         el("div", { class: "row" },
           el("button", { class: "plain", onclick: home }, "Άκυρο"),
           el("button", { class: "plain", onclick: () => names() }, "Με PIN")));
    cleanup = stop;
    wedgeOn = true;   // a USB scanner works here too
    onKey = (k, ev) => { if (k === "Escape") { home(); return true; } if (ev.code === "KeyP") { names(); return true; } };
    try {
      [stream] = await Promise.all([
        navigator.mediaDevices.getUserMedia({ audio: false, video: { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 720 } } }),
        loadJsQR()]);
    } catch (e) {
      stop();
      status.textContent = "";
      err.textContent = !e ? "Δεν φορτώθηκε ο αναγνώστης QR. Χρησιμοποίησε το PIN."
        : e.name === "NotAllowedError" ? "Η κάμερα δεν επιτρέπεται. Πάτα το εικονίδιο της κάμερας δίπλα στη διεύθυνση και επίλεξε «Να επιτρέπεται», ή χρησιμοποίησε το PIN."
        : e.name === "NotReadableError" ? "Η κάμερα χρησιμοποιείται από άλλη εφαρμογή. Κλείσ' την ή χρησιμοποίησε το PIN."
        : "Δεν βρέθηκε κάμερα. Χρησιμοποίησε το PIN.";
      return;
    }
    if (stopped) { stream.getTracks().forEach(t => t.stop()); return; }
    video.srcObject = stream;
    try { await video.play(); } catch { /* autoplay of a muted stream is allowed */ }
    status.textContent = "Κράτα το QR μπροστά στην κάμερα.";
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    const loop = t => {
      if (stopped) return;
      raf = requestAnimationFrame(loop);
      if (t - lastTry < 140 || video.readyState < 2) return;
      lastTry = t;
      const scale = Math.min(1, 640 / (video.videoWidth || 640));
      const w = Math.round((video.videoWidth || 640) * scale), h = Math.round((video.videoHeight || 480) * scale);
      if (canvas.width !== w) { canvas.width = w; canvas.height = h; }
      ctx.drawImage(video, 0, 0, w, h);
      const hit = window.jsQR(ctx.getImageData(0, 0, w, h).data, w, h, { inversionAttempts: "attemptBoth" });
      if (!hit || !hit.data) return;
      const raw = hit.data.replace(/^\uFEFF/, "").trim(), code = raw.toUpperCase();
      if (/^CK1:[A-Z2-7]{26}$/.test(code)) { stop(); qrFound(code); }
      else if (/^erg\|/i.test(raw) && /afm:\s*\d{9}/i.test(raw) && raw.length <= 256) { stop(); qrFound(raw); }   // Ergani's own employee QR
      else status.textContent = "Αυτό δεν είναι κάρτα του καταστήματος ούτε QR του ΕΡΓΑΝΗ. Δείξε την κάρτα QR σου.";
    };
    raf = requestAnimationFrame(loop);
  }

  async function qrFound(code) {
    chime("scan");
    show(el("h1", {}, "Έλεγχος κάρτας…"));
    const { status, data } = await api("/api/kiosk/qr/state", { code });
    if (status === 200) return confirm({ id: data.employee_id, name: data.label, short: data.name }, { qr: code }, data);
    if (status === 401 && data.detail === "device_not_enrolled") return notEnrolled();
    armIdle();
    show(el("h1", {}, "Η κάρτα δεν αναγνωρίστηκε"),
         el("p", { class: "hint" }, data.detail || "Κάτι πήγε στραβά."),
         el("div", { class: "row" },
           el("button", { class: "plain", onclick: scan }, "Ξανά"),
           el("button", { class: "plain", onclick: () => names() }, "Με PIN"),
           el("button", { class: "plain", onclick: home }, "Άκυρο")));
    onKey = k => { if (k === "Escape") { home(); return true; } };
  }

  function icon(kind) {
    const NS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", "0 0 24 24"); svg.setAttribute("fill", "none"); svg.setAttribute("stroke", "currentColor");
    svg.setAttribute("stroke-width", "1.5"); svg.setAttribute("stroke-linecap", "round"); svg.setAttribute("stroke-linejoin", "round");
    svg.setAttribute("aria-hidden", "true"); svg.setAttribute("class", "c-icon");
    const paths = kind === "qr"
      ? ["M4 4h6v6H4z", "M14 4h6v6h-6z", "M4 14h6v6H4z", "M14 14h2v2h-2z", "M18 14h2", "M14 18h2", "M18 18h2v2", "M17 17v0", "M6.5 6.5h1v1h-1z", "M16.5 6.5h1v1h-1z", "M6.5 16.5h1v1h-1z"]
      : ["M5 4h14a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1z", "M8 9h.01", "M12 9h.01", "M16 9h.01", "M8 13h.01", "M12 13h.01", "M16 13h.01", "M9 17h6"];
    for (const d of paths) { const p = document.createElementNS(NS, "path"); p.setAttribute("d", d); svg.append(p); }
    return svg;
  }

  function notEnrolled() {
    show(el("h1", {}, "Η συσκευή δεν είναι εγγεγραμμένη"),
         el("p", { class: "hint" }, "Ζητήστε κωδικό εγγραφής από τη διαχείριση."),
         el("button", { class: "plain", onclick: () => { location.href = "/enroll"; } }, "Εγγραφή συσκευής"));
  }

  function pin(emp, message = "") {
    armIdle();
    let digits = "";
    const dots = el("div", { class: "pinbox", "aria-label": "PIN" });
    const err = el("p", { class: "msg-error", role: "alert" }, message);
    const render = () => dots.replaceChildren(...Array.from({ length: 6 }, (_, i) => el("span", { class: "dot" + (i < digits.length ? " on" : "") })));
    const press = d => { armIdle(); if (digits.length < 6) { digits += d; render(); if (digits.length === 6) go(); } };
    const back = () => { armIdle(); digits = digits.slice(0, -1); render(); };
    const go = async () => {
      if (digits.length < 6) { err.textContent = "Το PIN έχει 6 ψηφία."; return; }
      const entered = digits; digits = ""; render();
      const { status, data } = await api("/api/kiosk/state", { employee_id: emp.id, pin: entered });
      if (status === 200) return confirm(emp, { pin: entered }, data);
      if (status === 401 && data.detail === "device_not_enrolled") return notEnrolled();
      err.textContent = data.detail || "Κάτι πήγε στραβά.";
    };
    const keys = ["1","2","3","4","5","6","7","8","9"].map(d => el("button", { class: "key", onclick: () => press(d) }, d));
    keys.push(el("button", { class: "key text", onclick: back, "aria-label": "Διαγραφή" }, backspaceIcon()));
    keys.push(el("button", { class: "key", onclick: () => press("0") }, "0"));
    keys.push(el("button", { class: "key ok", onclick: go }, "OK"));
    render();
    show(el("h1", {}, emp.name), el("p", { class: "hint" }, "Πληκτρολόγησε το PIN σου."),
         dots, el("div", { class: "pad" }, ...keys), err,
         el("div", { class: "row" }, el("button", { class: "plain", onclick: home }, "Άκυρο")));
    onKey = k => {
      if (/^[0-9]$/.test(k)) { press(k); return true; }
      if (k === "Backspace") { back(); return true; }
      if (k === "Enter") { go(); return true; }
      if (k === "Escape") { home(); return true; }
    };
  }

  // Not punched in for the part of today's schedule that is ending / over: ask before offering «Προσέλευση»,
  // so someone going home doesn't record an arrival at the time they leave.
  function leavingGuard(emp, cred, state) {
    armIdle();
    const p = state.leaving_unpunched;
    const err = el("p", { class: "msg-error", role: "alert" });
    const leave = el("button", { class: "action DEPARTURE" }, "Φεύγω, ενημέρωσε τη διαχείριση");
    leave.addEventListener("click", async () => {
      leave.disabled = true; disarmIdle();
      const { status, data } = await api("/api/kiosk/leaving-unpunched", cred.qr ? { code: cred.qr } : { employee_id: emp.id, pin: cred.pin });
      if (status === 401 && data.detail === "device_not_enrolled") return notEnrolled();
      if (status !== 200) { err.textContent = data.detail || "Κάτι πήγε στραβά."; leave.disabled = false; armIdle(); return; }
      cred = {};
      const now = new Date();
      show(el("p", { class: "result flash warn" }, `${farewell(now.getHours(), now.getDay())}, ${vocative(emp.short || data.name)}!`),
           el("p", { class: "hint" }, "Ενημερώθηκε η διαχείριση."),
           el("p", { class: "small" }, "Δεν καταγράφηκε κίνηση και δεν στάλθηκε τίποτα στο ΕΡΓΑΝΗ."));
      setTimeout(home, 6000);
      if (typeof pollReminders === "function") setTimeout(pollReminders, 500);
    });
    const come = el("button", { class: "plain" }, "Έρχομαι τώρα (προσέλευση)");
    come.addEventListener("click", () => confirm(emp, { ...cred, goOn: true }, state));
    show(el("h1", {}, `${vocative(emp.short || state.name)}, δεν έχεις χτυπήσει προσέλευση σήμερα`),
         el("p", { class: "hint" }, `Ωράριο ${p.start}-${p.end}. Αν φεύγεις τώρα, μην πατήσεις προσέλευση.`),
         leave, err,
         el("div", { class: "row" }, come, el("button", { class: "plain", onclick: home }, "Άκυρο")));
    onKey = k => { if (k === "Escape") { home(); return true; } };
  }

  // Before the declared start: the arrival is refused (the server refuses it too) and the management is told.
  function tooEarly(emp, state) {
    armIdle();
    chime("scan");
    show(el("h1", {}, `Είναι νωρίς, ${vocative(emp.short || state.name)}`),
         el("p", { class: "hint" }, `Το ωράριό σου ξεκινά στις ${state.early.start}. Χτύπα κάρτα τότε, η οθόνη θα σου το θυμίσει.`),
         el("p", { class: "small" }, "Η διαχείριση ενημερώθηκε. Αν πρέπει να ξεκινήσεις νωρίτερα, πρώτα πρέπει να δηλωθεί στο ΕΡΓΑΝΗ."),
         el("div", { class: "row" }, el("button", { class: "plain", onclick: home }, "Εντάξει")));
    onKey = k => { if (k === "Escape" || k === "Enter") { home(); return true; } };
  }

  // Holiday / shop closed and no declared hours for today: the arrival is refused (the server refuses it too).
  function shopClosed(emp, state) {
    armIdle();
    chime("scan");
    show(el("h1", {}, `Σήμερα είμαστε κλειστά, ${vocative(emp.short || state.name)}`),
         el("p", { class: "hint" }, state.closed.label),
         el("p", { class: "small" }, "Δεν υπάρχει δηλωμένο ωράριο για σήμερα, οπότε η προσέλευση δεν καταγράφεται. Η διαχείριση ενημερώθηκε· αν πρέπει να δουλέψεις, πρώτα δηλώνεται στο ΕΡΓΑΝΗ και μετά μπορείς να χτυπήσεις."),
         el("div", { class: "row" }, el("button", { class: "plain", onclick: home }, "Εντάξει")));
    onKey = k => { if (k === "Escape" || k === "Enter") { home(); return true; } };
  }

  function confirm(emp, cred, state) {
    if (state.closed && state.next_action === "ARRIVAL" && !state.training) return shopClosed(emp, state);
    if (state.early && state.next_action === "ARRIVAL" && !state.training) return tooEarly(emp, state);
    if (state.leaving_unpunched && state.next_action === "ARRIVAL" && !state.training && !cred.goOn) return leavingGuard(emp, cred, state);
    armIdle();
    const err = el("p", { class: "msg-error", role: "alert" });
    const btn = el("button", { class: "action " + state.next_action }, LABEL[state.next_action]);
    btn.addEventListener("click", async () => {
      btn.disabled = true; btn.textContent = "Καταχώρηση…"; disarmIdle();
      const { status, data } = cred.qr
        ? await api("/api/kiosk/qr/punch", { code: cred.qr, action: state.next_action })
        : await api("/api/kiosk/punch", { employee_id: emp.id, pin: cred.pin, action: state.next_action });
      if (status === 200) cred = {};
      if (status === 200) return result(data);
      if (status === 401 && data.detail === "device_not_enrolled") return notEnrolled();
      err.textContent = data.detail || "Κάτι πήγε στραβά."; btn.textContent = LABEL[state.next_action]; btn.disabled = false; armIdle();
    });
    const nodes = [el("h1", {}, `${hello(nowHour())}, ${vocative(emp.short || state.name)}`)];
    if (state.open_previous_day) nodes.push(el("p", { class: "hint" }, "Δεν καταγράφηκε αποχώρηση την προηγούμενη φορά. Ενημέρωσε τη διαχείριση."));
    if (state.training) { setTraining(true); nodes.push(el("p", { class: "msg-error" }, "ΕΚΠΑΙΔΕΥΣΗ: αυτή η κίνηση δεν θα καταγραφεί.")); }
    nodes.push(el("p", { class: "hint" }, (state.inside ? "Είσαι σε βάρδια." : "Δεν είσαι σε βάρδια.") + (cred.qr ? " · Κάρτα QR" : "")),
               btn, err, el("div", { class: "row" }, el("button", { class: "plain", onclick: home }, "Άκυρο")));
    show(...nodes);
    onKey = k => {
      if (k === "Enter" && !btn.disabled) { btn.click(); return true; }
      if (k === "Escape") { home(); return true; }
    };
  }

  const RESULT_MS = 6000;
  function result(data) {
    const m = data.movement;
    const time = m.movement_at.slice(11, 16);
    const h = Number(m.movement_at.slice(11, 13));
    const weekday = new Date(m.movement_at.slice(0, 10) + "T12:00:00Z").getUTCDay();
    const who = vocative(data.name);
    const big = m.type === "ARRIVAL" ? `${hello(h)}, ${who}!` : `${farewell(h, weekday)}, ${who}!`;
    const wish = m.type === "ARRIVAL" ? "Καλή βάρδια!" : "Ευχαριστούμε για σήμερα.";
    let detail, cls = "ok";
    if (m.status === "submitted" && m.mode === "trial") detail = `Δοκιμαστικό ΕΡΓΑΝΗ (ΑΚΥΡΟ, χωρίς ισχύ). Πρωτόκολλο ${m.protocol || "-"}.`;
    else if (m.status === "submitted") detail = `Καταχωρήθηκε στο ΕΡΓΑΝΗ. Πρωτόκολλο ${m.protocol || "-"}.`;
    else if (m.status === "dry_run") detail = "Δοκιμαστική λειτουργία: δεν στάλθηκε στο ΕΡΓΑΝΗ.";
    else if (m.status === "onboarding") { detail = ""; punchLog(m); }   // onboarding: nothing that says "not for real"
    else if (m.status === "training") { cls = "warn"; detail = "ΕΚΠΑΙΔΕΥΣΗ: δεν καταγράφηκε και δεν στάλθηκε στο ΕΡΓΑΝΗ."; }
    else if (m.status === "uncertain") { cls = "warn"; detail = "Καταγράφηκε. Η διαχείριση θα επιβεβαιώσει την αποστολή στο ΕΡΓΑΝΗ."; }
    else { cls = "warn"; detail = "Καταγράφηκε. Θα σταλεί στο ΕΡΓΑΝΗ μόλις αποκατασταθεί η σύνδεση."; }
    // «Επόμενο χτύπημα»: the next person doesn't have to wait; the bar inside shows the automatic return
    const next = el("button", { class: "plain next", onclick: home }, "Επόμενο χτύπημα", el("span", { class: "next-bar", "aria-hidden": "true" }));
    next.style.setProperty("--wait", `${RESULT_MS}ms`);
    show(el("p", { class: "result flash " + cls }, big),
         el("p", { class: "movement" }, `${LABEL[m.type]} ${time}`),
         el("p", { class: "hint" }, wish),
         detail ? el("p", { class: "small" }, detail) : "",
         el("div", { class: "row" }, next));
    resultTimer = setTimeout(home, RESULT_MS);
    wedgeOn = true;                                   // the next person can scan their QR card right away
    onKey = k => { if (k === "Enter" || k === "Escape" || k === " ") { home(); return true; } };
    pollAlerts();
    if (typeof pollReminders === "function") setTimeout(pollReminders, 500);
  }

  // ---------- live alerts (banner + Windows notification + chime) ----------
  const alertsBox = document.getElementById("alerts");
  const notifBtn = document.getElementById("notif");
  const SEEN_KEY = "wc_seen_alerts";
  let seen = new Set();
  try { seen = new Set(JSON.parse(localStorage.getItem(SEEN_KEY) || "[]")); } catch { /* ignore */ }
  // Sound: installed apps (Edge/Chrome) may play audio right away; otherwise the
  // browser unlocks it on the first touch/key. Created at load so a self-reload
  // does not leave the kiosk silent.
  let audioCtx = null;
  try { audioCtx = new (window.AudioContext || window.webkitAudioContext)(); } catch { /* no audio */ }
  const unlock = () => { if (audioCtx && audioCtx.state === "suspended") audioCtx.resume().catch(() => {}); };
  document.addEventListener("pointerdown", unlock);
  document.addEventListener("keydown", unlock);
  // Every alert and reminder: a doorbell «ding-dong». The QR scan keeps its short beep (feedback, not an alert).
  function bell(freq, t, dur) {
    // bell-like tone: a sine with two soft overtones and a long exponential decay
    [[1, 0.6], [2, 0.18], [3, 0.08]].forEach(([mult, amp]) => {
      const o = audioCtx.createOscillator(), g = audioCtx.createGain();
      o.type = "sine"; o.frequency.value = freq * mult;
      g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(amp, t + 0.01);
      g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
      o.connect(g).connect(audioCtx.destination); o.start(t); o.stop(t + dur + 0.05);
    });
  }
  function chime(level) {
    if (!audioCtx) return;
    if (audioCtx.state === "suspended") audioCtx.resume().catch(() => {});
    const t0 = audioCtx.currentTime + 0.05;
    if (level === "scan") { bell(1319, t0, 0.25); return; }
    bell(659.25, t0, 1.1);          // ding (E5)
    bell(523.25, t0 + 0.55, 1.6);   // dong (C5)
  }
  // Urgent alerts keep sounding every 2 minutes until they are resolved (someone punches out).
  let lastUrgentChime = 0;
  function updateNotifBtn() {
    notifBtn.hidden = !("Notification" in window) || Notification.permission !== "default";
  }
  notifBtn.addEventListener("click", async () => { try { await Notification.requestPermission(); } catch { /* ignore */ } updateNotifBtn(); });
  async function desktopNotify(a) {
    if (!("Notification" in window) || Notification.permission !== "granted") return;
    const opts = { body: a.text, tag: a.key, icon: "/static/brand/icons/icon-192.png", requireInteraction: a.level === "urgent" };
    try {
      const reg = navigator.serviceWorker ? await navigator.serviceWorker.getRegistration() : null;
      if (reg) await reg.showNotification("Κάρτα εργασίας", opts); else new Notification("Κάρτα εργασίας", opts);
    } catch { /* ignore */ }
  }
  async function pollAlerts() {
    let res;
    try { res = await fetch("/api/kiosk/alerts", { credentials: "same-origin" }); } catch { return; }
    if (!res.ok) return;
    const { alerts } = await res.json();
    alertsBox.replaceChildren(...alerts.slice(0, 3).map(a => el("div", { class: "alert " + a.level, role: "status" }, a.text)));
    if (alerts.length > 3) alertsBox.append(el("div", { class: "alert-more" }, `+${alerts.length - 3} ακόμα`));
    const fresh = alerts.filter(a => !seen.has(a.key));
    const urgentActive = alerts.some(a => a.level === "urgent");
    if (fresh.length) {
      fresh.forEach(a => { seen.add(a.key); desktopNotify(a); });
      chime(fresh.some(a => a.level === "urgent") ? "urgent" : "info");
      if (urgentActive) lastUrgentChime = Date.now();
      try { localStorage.setItem(SEEN_KEY, JSON.stringify([...seen].slice(-200))); } catch { /* ignore */ }
    } else if (urgentActive && Date.now() - lastUrgentChime >= 2 * 60 * 1000) {
      chime("urgent");
      lastUrgentChime = Date.now();
    }
  }
  updateNotifBtn();
  if (!PREVIEW) { pollAlerts(); setInterval(pollAlerts, 30000); }

  // ---------- punch reminders: who should punch in/out now (sound + voice every 30″ until they do) ----------
  const remBox = document.getElementById("reminders");
  const soundBtn = document.getElementById("soundBtn");
  const REM_MS = 30000;
  let lastRemSound = 0, remTimer = null, shownRem = null;   // (pollReminders reschedules itself)
  function syncSoundBtn() { soundBtn.hidden = !audioCtx || audioCtx.state !== "suspended"; }
  soundBtn.addEventListener("click", () => { unlock(); setTimeout(syncSoundBtn, 200); });
  if (audioCtx) audioCtx.addEventListener("statechange", syncSoundBtn);
  const remText = r => r.kind === "in" ? `${r.name}: ώρα για προσέλευση (${r.at})`
    : r.kind === "out_soon" ? `${r.name}: αποχώρηση σε ${Math.max(1, Math.ceil(r.in_s / 60))}′ (${r.at})`
    : `${r.name}: ώρα για αποχώρηση (${r.at})`;
  const remTitle = r => r.kind === "in" ? "Προσέλευση" : r.kind === "out_soon" ? "Σε λίγο αποχώρηση" : "Αποχώρηση";
  function openFor(r) {
    const emp = employees.find(e => e.id === r.employee_id);
    if (emp) pin(emp);
  }
  // ---------- onboarding period: no notice on the shop screen (it must feel like the real thing);
  // only a faint log line bottom right after a punch ----------
  const logLine = document.getElementById("punchLog");
  function punchLog(m) {
    logLine.textContent = `✓ καταγράφηκε · ${m.movement_at.slice(11, 19)}`;
    logLine.hidden = false;
    clearTimeout(punchLog.t); punchLog.t = setTimeout(() => { logLine.hidden = true; }, 8000);
  }
  const trainingBox = document.getElementById("training");
  function setTraining(on) { trainingBox.hidden = !on; document.body.classList.toggle("training", on); }
  async function notifyAll(list) {
    if (!("Notification" in window) || Notification.permission !== "granted") return;
    for (const r of list) {
      const opts = { body: remText(r), tag: `rem-${r.employee_id}-${r.kind}`, renotify: true, requireInteraction: r.kind !== "out_soon",
                     icon: "/static/brand/icons/icon-192.png" };
      try {
        const reg = navigator.serviceWorker ? await navigator.serviceWorker.getRegistration() : null;
        if (reg) await reg.showNotification("Κάρτα εργασίας", opts); else new Notification("Κάρτα εργασίας", opts);
      } catch { /* ignore */ }
    }
  }
  // Timing: the server says when the next reminder moment is (a start, 2′ and 1′ before an end, the end), so the
  // screen wakes up exactly then. A due reminder (in / out) rings at once and then every 30″ until they punch;
  // the countdown before a punch-out rings once at 2′ and once at 1′.
  let seenDue = new Set(), seenSoon = new Set();
  let seenReload, reloadWanted = null, loadedFor = null;
  async function forceReload(stamp) {
    try { sessionStorage.setItem("karta-reload", stamp); } catch { /* ignore */ }
    try { const reg = navigator.serviceWorker && await navigator.serviceWorker.getRegistration(); if (reg) await reg.update(); } catch { /* ignore */ }
    location.reload();
  }
  async function pollReminders() {
    clearTimeout(remTimer);
    let wait = REM_MS;
    try {
      const res = await fetch(`/api/kiosk/reminders${loadedFor ? `?rv=${encodeURIComponent(loadedFor)}` : ""}`, { credentials: "same-origin", cache: "no-store" });
      if (!res.ok) return;
      const { reminders, training, next_in, closed_today, closed, festive: theme, reload_at } = await res.json();
      // admin «Ανανέωση οθόνης καταστήματος»: reload with the latest version (not in the middle of a punch)
      if (reload_at !== undefined) {
        if (seenReload === undefined) {
          seenReload = reload_at;
          try { if (sessionStorage.getItem("karta-reload") === reload_at) loadedFor = reload_at; } catch { /* ignore */ }
        } else if (reload_at && reload_at !== seenReload) reloadWanted = reload_at;
      }
      if (reloadWanted && atHome) return forceReload(reloadWanted);
      setTraining(!!training);
      trainingOn = !!training;
      festive(theme);
      const nowClosed = closed && !closed.works && !trainingOn ? closed.key : null;
      if (atHome && nowClosed !== closedKey) home();      // midnight / closure added or removed / training switched
      const cn = document.getElementById("closedNote");
      if (cn) { cn.textContent = closed_today ? `Σήμερα κλειστά · ${closed_today.replace(/^Αργία: |^Κατάστημα κλειστό: /, "")}` : ""; cn.hidden = !closed_today; }
      // redraw the cards only when they change: a redraw at the moment of a tap would swallow the tap
      const remKey = reminders.map(r => `${r.employee_id}:${r.kind}:${remText(r)}`).join("|");
      if (remKey !== shownRem) {
        shownRem = remKey;
        remBox.replaceChildren(...reminders.map(r => el("button", { class: "reminder " + r.kind, onclick: () => openFor(r) },
          el("strong", {}, remTitle(r)), " ", remText(r))));
      }
      syncSoundBtn();
      const due = reminders.filter(r => r.kind !== "out_soon"), soon = reminders.filter(r => r.kind === "out_soon");
      const dueKeys = new Set(due.map(r => `${r.employee_id}:${r.kind}:${r.at}`));
      const fresh = [...dueKeys].some(k => !seenDue.has(k));
      seenDue = dueKeys;
      const now = Date.now();
      let rang = false;
      if (due.length && (fresh || now - lastRemSound >= REM_MS - 1500)) {
        lastRemSound = now; rang = true;
        chime("reminder"); notifyAll(due);
      }
      if (!due.length) lastRemSound = 0;
      else wait = Math.min(wait, Math.max(1000, REM_MS - (Date.now() - lastRemSound)));
      const soonKeys = new Set(soon.map(r => `${r.employee_id}:${r.at}:${Math.max(1, Math.ceil(r.in_s / 60))}`));
      if ([...soonKeys].some(k => !seenSoon.has(k))) {
        if (!rang) chime("reminder");
        notifyAll(soon.filter(r => !seenSoon.has(`${r.employee_id}:${r.at}:${Math.max(1, Math.ceil(r.in_s / 60))}`)));
      }
      seenSoon = soonKeys;
      if (typeof next_in === "number") wait = Math.min(wait, Math.max(300, next_in * 1000 + 300));
    } catch { /* offline: try again later */ }
    finally { remTimer = setTimeout(pollReminders, wait); }
  }
  if (!PREVIEW) pollReminders();

  // An installed app / kiosk window stays open for days: pick up new versions by
  // reloading itself when it has been open 6h+ and is idle on the home screen.
  setInterval(() => { if (atHome && Date.now() - loadedAt > 6 * 3600 * 1000) location.reload(); }, 5 * 60 * 1000);
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});

  if (PREVIEW) {
    fetch(`/api/kiosk/preview?key=${encodeURIComponent(PREVIEW)}`, { cache: "no-store" }).then(r => r.json()).then(d => {
      festive(d.festive);
      document.body.append(el("span", { class: "preview-badge" }, "Προεπισκόπηση: τίποτα δεν καταγράφεται"));
      if (d.closed) closedDay(d.closed, d.festive);
    }).catch(() => {});
  } else home();
})();
