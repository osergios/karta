"use strict";
(() => {
  const LABEL = { ARRIVAL: "Προσέλευση", DEPARTURE: "Αποχώρηση" };
  const STATUS = { submitted: "Υποβλήθηκε", dry_run: "Δοκιμή (δεν στάλθηκε)", pending: "Σε αναμονή", failed: "Απέτυχε", uncertain: "Προς έλεγχο στο ΕΡΓΑΝΗ",
                   local: "Μόνο στην κάρτα (δεν στάλθηκε)", onboarding: "Προσαρμογή (δεν στάλθηκε)" };
  const MODE = { dry_run: "Δοκιμαστική", trial: "Δοκιμαστικό ΕΡΓΑΝΗ", production: "Κανονική λειτουργία" };   // same names as «Ρυθμίσεις» → «Λειτουργία»

  function el(tag, attrs = {}, ...children) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "class") n.className = v;
      else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, v);
    }
    for (const c of children) if (c !== null && c !== undefined) n.append(c);
    return n;
  }
  function toast(text, isErr = false) {
    const t = document.getElementById("toast");
    t.textContent = text; t.className = "toast" + (isErr ? " err" : ""); t.hidden = false;
    clearTimeout(toast.h); toast.h = setTimeout(() => { t.hidden = true; }, 4000);
  }
  // panels (dialogs) and the date in Athens
  const hide = box => { box.hidden = true; box.replaceChildren(); };
  const closePanels = (except = null) => document.querySelectorAll(".qr-panel:not([hidden])").forEach(p => { if (p !== except) hide(p); });
  const athensDay = new Intl.DateTimeFormat("sv-SE", { timeZone: "Europe/Athens" });
  const todayAthens = () => athensDay.format(new Date());

  // The 30″ refresh must never redraw a part of the page the user is working in: a focused or edited field
  // (typing on a phone takes time, a date picker stays open) or an open menu / «Τι θα στελνόταν».
  const TYPING = "input:not([type=checkbox]):not([type=radio]):not([type=file]), select, textarea";   // a tick saves at once
  for (const type of ["input", "change"]) {
    document.addEventListener(type, ev => { if (ev.target.matches?.(TYPING)) ev.target.dataset.dirty = "1"; });
  }
  const editing = box => !!box && ((box.contains(document.activeElement) && document.activeElement.matches(TYPING))
    || !!box.querySelector("[data-dirty], details[open]:not(.help)"));

  // errors that come from Cloudflare (not from Karta), in words the admin can act on
  function httpError(status) {
    if (status === 524) return "Η Karta άργησε να απαντήσει και το Cloudflare σταμάτησε την αναμονή (σφάλμα 524). Δοκίμασε ξανά σε λίγο.";
    if (status === 502 || status === 503 || status === 530)
      return `Το Cloudflare δεν βρίσκει την Karta (σφάλμα ${status}): ο server ή το tunnel δεν τρέχει, ή δεν έχει internet.`;
    if (status === 522 || status === 523) return `Το Cloudflare δεν φτάνει στην Karta (σφάλμα ${status}). Δοκίμασε ξανά σε λίγο.`;
    return `Σφάλμα ${status}`;
  }
  async function api(path, body) {
    const opt = body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
    const res = await fetch(path, { credentials: "same-origin", ...opt });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const msg = Array.isArray(data.detail) ? "Μη έγκυρα στοιχεία" : (data.detail || httpError(res.status));
      throw new Error(msg);
    }
    return data;
  }
  function showPin(r, viewing = false) {
    const box = document.getElementById("pin");
    box.hidden = false;
    box.replaceChildren(el("strong", {}, r.pin.replace(/(\d{3})(\d{3})/, "$1 $2")),
      viewing ? `Τρέχον PIN για ${r.name}. Κρύβεται σε 20 δευτερόλεπτα.`
              : `PIN για ${r.name}. Δώσ' το στον/στην εργαζόμενο/η — μπορείς να το ξαναδείς με «Εμφάνιση PIN».`);
    clearTimeout(showPin.h); showPin.h = setTimeout(() => hide(box), viewing ? 20000 : 120000);
  }
  // ---------- personal QR card (phone image / printable) ----------
  const drawCard = (name, svg) => window.KartaCard.draw(name, svg);
  async function showQrCard(r, employee) {
    const box = document.getElementById("qrcard");
    const canvas = await drawCard(employee.display_name, r.svg);
    const url = canvas.toDataURL("image/png");
    const blob = await new Promise(ok => canvas.toBlob(ok, "image/png"));
    const fname = `karta-qr-${employee.display_name}.png`;
    const file = new File([blob], fname, { type: "image/png" });
    const dl = el("a", { class: "btn", href: URL.createObjectURL(blob), download: fname }, "Λήψη εικόνας");
    const canShare = navigator.canShare && navigator.canShare({ files: [file] });
    const close = () => hide(box);
    const linkBox = el("div", { class: "qr-link" });
    const expiresFmt = iso => fmtUtc(iso.slice(0, 19));
    function renderLink(L, fresh) {
      if (!L) {
        linkBox.replaceChildren(
          el("button", { class: "btn", onclick: act(async () => { renderLink(await api(`/admin/api/employees/${employee.id}/qr/link`, {}), true); }) }, "Σύνδεσμος για το κινητό"),
          el("span", { class: "small" }, " Στέλνεις έναν σύνδεσμο (Viber/WhatsApp/SMS) που ισχύει 24 ώρες· ανοίγει την κάρτα στο κινητό του/της για αποθήκευση."));
        return;
      }
      if (!fresh) {   // a link exists from before: its address is not stored, only its status
        linkBox.replaceChildren(
          el("span", { class: "small" }, `Ενεργός σύνδεσμος έως ${expiresFmt(L.expires_at)} · ${L.first_opened_at ? `άνοιξε (${L.opens}×)` : "δεν έχει ανοίξει ακόμα"}. `),
          el("button", { class: "link", onclick: act(async () => { renderLink(await api(`/admin/api/employees/${employee.id}/qr/link`, {}), true); }) }, "Νέος σύνδεσμος"),
          el("button", { class: "link danger", onclick: act(async () => { await api(`/admin/api/employees/${employee.id}/qr/link/revoke`, {}); renderLink(null); toast("Ο σύνδεσμος ακυρώθηκε"); }) }, "Ακύρωση συνδέσμου"));
        return;
      }
      const first = employee.display_name.trim().split(/\s+/)[0];
      const brandShort = (document.querySelector('meta[name="brand"]') || {}).content || "";
      const msg = `Γεια σου ${first}! Η κάρτα εργασίας σου${brandShort ? ` για το ${brandShort}` : ""}: ${L.url}\nΆνοιξέ τη και αποθήκευσε την εικόνα. Ο σύνδεσμος ισχύει έως ${expiresFmt(L.expires_at)}.`;
      const enc = encodeURIComponent(msg);
      linkBox.replaceChildren(
        el("div", { class: "small" }, `Σύνδεσμος για ${employee.display_name} (ισχύει έως ${expiresFmt(L.expires_at)}, έως ${L.max_opens} ανοίγματα):`),
        el("input", { class: "qr-url", readonly: "", value: L.url, "aria-label": "Σύνδεσμος", onfocus: ev => ev.target.select() }),
        el("div", { class: "qr-actions" },
          el("a", { class: "btn", href: `viber://forward?text=${enc}` }, "Viber"),
          el("a", { class: "btn ghost", href: `https://wa.me/?text=${enc}`, target: "_blank", rel: "noopener noreferrer" }, "WhatsApp"),
          el("a", { class: "btn ghost", href: `sms:?&body=${enc}` }, "SMS"),
          navigator.share ? el("button", { class: "btn ghost", onclick: async () => { try { await navigator.share({ text: msg }); } catch { /* cancelled */ } } }, "Αποστολή…") : null,
          el("button", { class: "link", onclick: async () => {
            try { await navigator.clipboard.writeText(msg); toast("Αντιγράφηκε το μήνυμα με τον σύνδεσμο"); } catch { toast("Αντέγραψε τον σύνδεσμο από το πεδίο", true); }
          } }, "Αντιγραφή μηνύματος"),
          el("button", { class: "link danger", onclick: act(async () => { await api(`/admin/api/employees/${employee.id}/qr/link/revoke`, {}); renderLink(null); toast("Ο σύνδεσμος ακυρώθηκε"); }) }, "Ακύρωση συνδέσμου")));
    }
    renderLink(r.viewable === false ? undefined : (employee.link || null));
    if (r.viewable === false) linkBox.replaceChildren(el("span", { class: "small" }, "Ο σύνδεσμος για το κινητό χρειάζεται PIN_KEY στο .env."));
    box.replaceChildren(
      el("img", { class: "qr-preview", src: url, alt: `Κάρτα QR ${employee.display_name}` }),
      el("div", { class: "qr-side" },
        el("strong", {}, `Κάρτα QR · ${employee.display_name}`),
        el("p", { class: "small" }, "Στείλε την εικόνα στο κινητό του/της (π.χ. Viber) ή εκτύπωσέ την. Στην οθόνη του καταστήματος: «Κάρτα QR» και δείχνει την εικόνα στην κάμερα — χωρίς PIN."),
        el("p", { class: "small warn-text" }, "Όποιος έχει την εικόνα μπορεί να χτυπήσει κάρτα για λογαριασμό του/της. Αν χαθεί ή δοθεί σε άλλον, πάτα «Νέα κάρτα»: η παλιά σταματά αμέσως."),
        r.viewable === false ? el("p", { class: "small warn-text" }, "Χωρίς PIN_KEY η κάρτα δεν ξαναεμφανίζεται: κατέβασέ την τώρα.") : null,
        el("div", { class: "qr-actions" },
          dl,
          canShare ? el("button", { class: "btn ghost", onclick: async () => { try { await navigator.share({ files: [file], title: fname }); } catch { /* cancelled */ } } }, "Αποστολή") : null,
          el("button", { class: "btn ghost", onclick: () => printCard(url) }, "Εκτύπωση"),
          el("button", { class: "link", onclick: act(async () => {
            if (!confirm(`Νέα κάρτα QR για ${employee.display_name}; Η τωρινή θα σταματήσει να ισχύει.`)) return;
            await showQrCard(await api(`/admin/api/employees/${employee.id}/qr`, {}), { ...employee, link: null }); toast("Νέα κάρτα QR — η παλιά (και ο σύνδεσμός της) δεν ισχύει πια");
          }) }, "Νέα κάρτα"),
          el("button", { class: "link danger", onclick: act(async () => {
            if (!confirm(`Ακύρωση της κάρτας QR του/της ${employee.display_name}; Θα χτυπά μόνο με PIN.`)) return;
            await api(`/admin/api/employees/${employee.id}/qr/revoke`, {}); close(); toast("Η κάρτα QR ακυρώθηκε");
          }) }, "Ακύρωση κάρτας"),
          el("button", { class: "link", onclick: close }, "Κλείσιμο")),
        linkBox));
    openPanel(box);
  }
  function printCard(url) {
    const area = document.getElementById("printArea");
    area.replaceChildren(el("img", { src: url, alt: "" }));
    document.body.classList.add("printing");
    const done = () => { document.body.classList.remove("printing"); area.replaceChildren(); window.removeEventListener("afterprint", done); };
    window.addEventListener("afterprint", done);
    setTimeout(() => window.print(), 50);
  }

  // ---------- admin correction: punch someone out ----------
  const LATE_CODES = [
    ["EMPLOYER_SYSTEMS_UNAVAILABLE", "002 · Πρόβλημα στα συστήματα του εργοδότη (π.χ. η συσκευή του καταστήματος δεν λειτουργούσε)"],
    ["ERGANI_SYSTEMS_UNAVAILABLE", "003 · Πρόβλημα επικοινωνίας με το ΕΡΓΑΝΗ"],
    ["POWER_OUTAGE", "001 · Διακοπή ρεύματος"],
  ];
  // e = employee; old = {id, movement_at, until} to close a forgotten shift, or null for the current one
  function showDepart(e, old = null) {
    const box = document.getElementById("departBox");
    const hhmm = d => `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
    const arrived = old ? old.movement_at : (e.last_movement_at || "");
    const onb = (old ? old.status : e.last_status) === "onboarding";   // punched in during the onboarding period: nothing goes to Ergani
    const todayIso = todayAthens();
    const pastDay = !!arrived && arrived.slice(0, 10) !== todayIso;   // "now" would make a shift across midnight
    const dayTxt = arrived ? `${arrived.slice(8, 10)}/${arrived.slice(5, 7)}` : "";
    const radio = v => el("input", { type: "radio", name: "dep-how", value: v });
    const nowR = radio("now"), forgotR = radio("forgot"), techR = radio("tech");
    (pastDay ? forgotR : nowR).checked = true;
    const time = el("input", { type: "time", value: pastDay ? "" : hhmm(new Date()), step: "60", "aria-label": "Ώρα αποχώρησης" });
    const code = el("select", { "aria-label": "Αιτιολογία" }, el("option", { value: "" }, "— διάλεξε αιτιολογία —"),
      ...LATE_CODES.map(([v, t]) => el("option", { value: v }, t)));
    const note = el("input", { type: "text", maxlength: "200", placeholder: "Σημείωση για το αρχείο", "aria-label": "Σημείωση" });
    const timeRow = el("label", {}, pastDay ? `Ώρα που έφυγε στις ${dayTxt} ` : "Ώρα που έφυγε ", time);
    const codeRow = el("label", {}, "Αιτιολογία ΕΡΓΑΝΗ ", code);
    const until = old && old.until ? el("p", { class: "small" }, `Πρέπει να είναι πριν από την επόμενη προσέλευση (${fmt(old.until)}).`) : null;
    const help = el("p", { class: "small" });
    const sync = () => {
      const how = nowR.checked ? "now" : forgotR.checked ? "forgot" : "tech";
      const vis = (n, on) => { if (n) n.style.display = on ? "" : "none"; };   // (labels are display:flex: `hidden` alone won't hide them)
      vis(timeRow.parentNode, how !== "now"); vis(codeRow, how === "tech"); vis(until, how !== "now");
      if (onb) vis(techR.parentNode, false);
      note.placeholder = how === "forgot" ? "Υποχρεωτικό: π.χ. ξέχασε να χτυπήσει αποχώρηση" : "Σημείωση για το αρχείο (προαιρετικό)";
      help.className = how === "now" ? "small" : "small warn-text";
      help.textContent = onb && how === "now" ? "Περίοδος προσαρμογής: καταγράφεται στην κάρτα, ΔΕΝ στέλνεται στο ΕΡΓΑΝΗ (όπως και η προσέλευσή του/της)."
        : how === "now" ? "Στέλνεται στο ΕΡΓΑΝΗ τώρα, σε πραγματικό χρόνο. Μόνο αν φεύγει αυτή τη στιγμή."
        : how === "forgot" ? "ΔΕΝ στέλνεται στο ΕΡΓΑΝΗ. Η βάρδια κλείνει μόνο στην κάρτα (αναφορά, υπενθυμίσεις). Στο ΕΡΓΑΝΗ μένει ως παράλειψη χτυπήματος — η ξεχασμένη κάρτα δεν είναι τεχνικό πρόβλημα και δεν δηλώνεται εκπρόθεσμα."
        : "Στέλνεται στο ΕΡΓΑΝΗ ως εκπρόθεσμη. ΜΟΝΟ αν υπήρξε πραγματικό τεχνικό πρόβλημα (ρεύμα, ίντερνετ, laptop/server, ΕΡΓΑΝΗ) — κράτα αποδεικτικά. Για απλή παράλειψη διάλεξε «Ξέχασε να χτυπήσει».";
    };
    [nowR, forgotR, techR].forEach(r => r.addEventListener("change", sync));
    const go = el("button", { class: "btn", onclick: act(async () => {
      const how = nowR.checked ? "now" : forgotR.checked ? "forgot" : "tech";
      const body = { note: note.value.trim() };
      if (old) body.arrival_id = old.id;
      if (how !== "now") {
        if (!time.value) { toast("Γράψε την ώρα που έφυγε", true); return; }
        body.at = time.value;
      }
      if (how === "forgot") {
        if (!body.note) { toast("Γράψε μια σημείωση (π.χ. ξέχασε να χτυπήσει αποχώρηση)", true); return; }
        body.local = true;
      }
      if (how === "tech") {
        if (!code.value) { toast("Διάλεξε αιτιολογία ΕΡΓΑΝΗ", true); return; }
        body.justification = code.value;
      }
      const label = how === "now" ? "τώρα" : `στις ${pastDay ? dayTxt + " " : ""}${time.value}`;
      const what = how === "forgot" ? "Κλείνει ΜΟΝΟ στην κάρτα — δεν στέλνεται στο ΕΡΓΑΝΗ."
        : how === "tech" ? "Στέλνεται στο ΕΡΓΑΝΗ ως εκπρόθεσμη και δεν αναιρείται."
        : onb ? "Περίοδος προσαρμογής: καταγράφεται στην κάρτα, δεν στέλνεται στο ΕΡΓΑΝΗ." : "Στέλνεται στο ΕΡΓΑΝΗ τώρα και δεν αναιρείται.";
      if (!confirm(`Αποχώρηση για ${e.display_name} ${label};\n\n${what}`)) return;
      const r = await api(`/admin/api/employees/${e.id}/depart`, body);
      hide(box);
      toast(`Αποχώρηση ${r.name} ${r.movement.movement_at.slice(11, 16)}: ${STATUS[r.movement.status] || r.movement.status}`);
    }) }, "Καταχώρηση αποχώρησης");
    box.replaceChildren(
      el("div", { class: "qr-side" },
        el("strong", {}, old ? `Ξεχασμένη αποχώρηση · ${e.display_name} · ${dayTxt}` : `Αποχώρηση για ${e.display_name}`),
        el("p", { class: "small" }, arrived ? `Προσέλευση: ${fmt(arrived)}${onb ? " (περίοδος προσαρμογής — δεν στάλθηκε στο ΕΡΓΑΝΗ)" : ""}.` : ""),
        pastDay ? null : el("label", { class: "dep-opt" }, nowR, " Φεύγει τώρα"),
        el("label", { class: "dep-opt" }, forgotR, " Ξέχασε να χτυπήσει — κλείσιμο μόνο στην κάρτα"),
        el("label", { class: "dep-opt" }, techR, " Τεχνικό πρόβλημα — εκπρόθεσμη δήλωση στο ΕΡΓΑΝΗ"),
        el("div", { class: "dep-past" }, timeRow, codeRow, until), help, note,
        el("div", { class: "qr-actions" }, go, el("button", { class: "link", onclick: () => hide(box) }, "Άκυρο"))));
    sync();
    openPanel(box);
  }

  // «Ξεχασμένη βάρδια»: someone worked but punched nothing (e.g. pressed «Φεύγω» at the shop). Karta only.
  function showLocalShift(e, sched) {
    const box = document.getElementById("departBox");
    const hhmmOf = x => `${String(Math.floor(x / 60)).padStart(2, "0")}:${String(x % 60).padStart(2, "0")}`;
    const today = todayAthens();
    const day = el("input", { type: "date", value: today, max: today, "aria-label": "Ημερομηνία" });
    const from = el("input", { type: "time", step: "60", "aria-label": "Από" });
    const to = el("input", { type: "time", step: "60", "aria-label": "Έως" });
    const note = el("input", { type: "text", maxlength: "200", placeholder: "Υποχρεωτικό: π.χ. δεν χτύπησε καθόλου κάρτα", "aria-label": "Σημείωση" });
    const fill = () => {   // start/end from that weekday's schedule
      const wd = (new Date(day.value + "T12:00:00Z").getUTCDay() + 6) % 7;
      const sp = parseSpan((sched || {})[String(wd)] || "");
      if (sp && !sp.error) { from.value = hhmmOf(sp.s); to.value = hhmmOf(sp.e); }
    };
    day.addEventListener("change", fill); fill();
    const close = () => hide(box);
    box.replaceChildren(el("div", { class: "qr-side" },
      el("strong", {}, `Ξεχασμένη βάρδια · ${e.display_name}`),
      el("p", { class: "small warn-text" }, "Για βάρδια που δούλεψε χωρίς να χτυπήσει καθόλου κάρτα. Καταχωρείται ΜΟΝΟ στην κάρτα (αναφορά, ώρες) — ΔΕΝ στέλνεται στο ΕΡΓΑΝΗ, όπου μένει ως παράλειψη."),
      el("div", { class: "dep-past" }, el("label", {}, "Ημέρα ", day), el("label", {}, "Από ", from), el("label", {}, "Έως ", to)),
      note,
      el("div", { class: "qr-actions" },
        el("button", { class: "btn", onclick: act(async () => {
          if (!from.value || !to.value) { toast("Γράψε από–έως", true); return; }
          if (!note.value.trim()) { toast("Γράψε μια σημείωση", true); return; }
          if (!confirm(`Βάρδια ${e.display_name} ${day.value.slice(8, 10)}/${day.value.slice(5, 7)} ${from.value}–${to.value} μόνο στην κάρτα;\n\nΔεν στέλνεται στο ΕΡΓΑΝΗ.`)) return;
          await api(`/admin/api/employees/${e.id}/local-shift`, { day: day.value, start: from.value, end: to.value, note: note.value.trim() });
          close(); toast("Η βάρδια καταχωρήθηκε μόνο στην κάρτα");
        }) }, "Καταχώρηση"),
        el("button", { class: "link", onclick: close }, "Άκυρο"))));
    openPanel(box);
  }

  const dmy = iso => `${iso.slice(8, 10)}/${iso.slice(5, 7)}`;
  // ---------- leave: no reminders / alerts, «Άδεια» in the monthly report ----------
  function showLeave(e) {
    const box = document.getElementById("leaveBox");
    const today = todayAthens();
    const from = el("input", { type: "date", value: today, "aria-label": "Από" });
    const to = el("input", { type: "date", value: today, "aria-label": "Έως" });
    const kind = el("select", { "aria-label": "Είδος άδειας" },
      ...Object.entries(LEAVE_KINDS).map(([k, v]) => el("option", { value: k }, v)));
    const note = el("input", { type: "text", maxlength: "120", placeholder: "Σημείωση (προαιρετικά)", "aria-label": "Σημείωση" });
    const close = () => hide(box);
    const list = (e.leaves || []).map(l => el("div", { class: "leave-row" },
      `${dmy(l.start_date)} – ${dmy(l.end_date)} · ${l.label || LEAVE_KINDS[l.kind] || "Άδεια"} `,
      el("button", { class: "link danger", onclick: act(async () => {
        if (!confirm(`Ακύρωση της άδειας ${dmy(l.start_date)}–${dmy(l.end_date)} για ${e.display_name};`)) return;
        await api(`/admin/api/leaves/${l.id}/delete`, {}); close(); toast("Η άδεια ακυρώθηκε");
      }) }, "Ακύρωση")));
    box.replaceChildren(el("div", { class: "qr-side" },
      el("strong", {}, `Άδεια · ${e.display_name}`),
      el("p", { class: "small" }, "Όσο διαρκεί η άδεια δεν γίνονται υπενθυμίσεις στο κατάστημα ούτε ειδοποιήσεις «δεν χτύπησε». Η μηνιαία και η ετήσια αναφορά μετρούν τις εργάσιμες ημέρες χωριστά ανά είδος (κανονική, ασθενείας, ειδικού σκοπού)· αργία ή κλειστό κατάστημα μέσα στην άδεια δεν μετρά ως ημέρα άδειας. Η άδεια δηλώνεται και στο ΕΡΓΑΝΗ από τον λογιστή — εδώ δεν στέλνεται τίποτα."),
      ...(list.length ? [el("div", { class: "small" }, "Τρέχουσες / επόμενες άδειες:"), ...list] : []),
      el("div", { class: "leave-form" },
        el("label", {}, "Είδος ", kind), el("label", {}, "Από ", from), el("label", {}, "Έως (τελευταία ημέρα άδειας) ", to), note),
      el("div", { class: "qr-actions" },
        el("button", { class: "btn", onclick: act(async () => {
          if (!from.value || !to.value) { toast("Συμπλήρωσε ημερομηνίες", true); return; }
          await api(`/admin/api/employees/${e.id}/leaves`, { start: from.value, end: to.value, note: note.value.trim(), kind: kind.value });
          close(); toast(`${LEAVE_KINDS[kind.value]} ${e.display_name}: ${dmy(from.value)}–${dmy(to.value)}`);
        }) }, "Καταχώρηση άδειας"),
        el("button", { class: "link", onclick: close }, "Κλείσιμο"))));
    openPanel(box);
  }

  // ---------- «Έφυγε νωρίτερα»: why someone left before the end (the report lists the hours to declare afterwards) ----------
  const EARLY_REASONS = { sick: "Ασθένεια", personal: "Προσωπικός λόγος", other: "Άλλος λόγος" };
  function showEarlyLeave(e) {
    const box = document.getElementById("earlyBox");
    const today = todayAthens();
    const lo = new Date(Date.parse(today + "T12:00:00Z") - 62 * 864e5).toISOString().slice(0, 10);
    const tomorrow = new Date(Date.parse(today + "T12:00:00Z") + 864e5).toISOString().slice(0, 10);
    const day = el("input", { type: "date", value: today, min: lo, max: today, "aria-label": "Ημέρα" });
    const reason = el("select", { "aria-label": "Λόγος" }, ...Object.entries(EARLY_REASONS).map(([k, v]) => el("option", { value: k }, v)));
    const note = el("input", { type: "text", maxlength: "200", placeholder: "Σημείωση (προαιρετικά), π.χ. πυρετός", "aria-label": "Σημείωση" });
    const sickOn = el("input", { type: "checkbox" });
    const sickTo = el("input", { type: "date", value: tomorrow, min: tomorrow, "aria-label": "Άδεια ασθενείας έως" });
    const sickRow = el("div", { class: "leave-form" }, el("label", {}, sickOn, " Άδεια ασθενείας από την επόμενη ημέρα, έως "), sickTo);
    const syncSick = () => { sickRow.hidden = reason.value !== "sick"; };
    reason.addEventListener("change", syncSick); syncSick();
    const t = e.today && e.today.left;
    const close = () => hide(box);
    const list = (e.early_leaves || []).map(m => el("div", { class: "leave-row" },
      `${dmy(m.day)} · ${EARLY_REASONS[m.reason] || m.reason}${m.note ? " · " + m.note : ""} `,
      el("button", { class: "link danger", onclick: act(async () => {
        if (!confirm(`Διαγραφή της σημείωσης ${dmy(m.day)} για ${e.display_name};`)) return;
        await api(`/admin/api/employees/${e.id}/early-leave/${m.day}/delete`, {}); close(); toast("Η σημείωση διαγράφηκε");
      }) }, "Διαγραφή")));
    box.replaceChildren(el("div", { class: "qr-side" },
      el("strong", {}, `Έφυγε νωρίτερα · ${e.display_name}`),
      t ? el("div", { class: "an-line warn" }, `Σήμερα αποχώρησε ${t.at}, ${Math.floor(t.minutes / 60)}:${String(t.minutes % 60).padStart(2, "0")} πριν τη λήξη (${t.end}).`) : null,
      el("p", { class: "small" }, "Η αποχώρηση έχει ήδη σταλεί στο ΕΡΓΑΝΗ με την πραγματική ώρα — εδώ σημειώνεις μόνο τον λόγο. Η μηνιαία αναφορά δείχνει στο φύλλο «Απολογιστικές δηλώσεις» τις ώρες που δηλώνονται εκ των υστέρων στο ΕΡΓΑΝΗ (έως το τέλος του επόμενου μήνα). Την πληρωμή της ημέρας την κρίνει ο λογιστής."),
      ...(list.length ? [el("div", { class: "small" }, "Σημειώσεις:"), ...list] : []),
      el("div", { class: "leave-form" }, el("label", {}, "Ημέρα ", day), el("label", {}, "Λόγος ", reason), note),
      sickRow,
      el("div", { class: "qr-actions" },
        el("button", { class: "btn", onclick: act(async () => {
          if (!day.value) { toast("Διάλεξε ημέρα", true); return; }
          const sick = reason.value === "sick" && sickOn.checked;
          const from = new Date(Date.parse(day.value + "T12:00:00Z") + 864e5).toISOString().slice(0, 10);
          if (sick && (!sickTo.value || sickTo.value < from)) { toast("Η άδεια πρέπει να τελειώνει μετά την ημέρα της αποχώρησης", true); return; }
          await api(`/admin/api/employees/${e.id}/early-leave`, { day: day.value, reason: reason.value, note: note.value.trim() });
          let msg = `${e.display_name} ${dmy(day.value)}: ${EARLY_REASONS[reason.value].toLowerCase()}`;
          if (sick) {
            await api(`/admin/api/employees/${e.id}/leaves`, { start: from, end: sickTo.value, kind: "sick", note: note.value.trim() });
            msg += ` · άδεια ασθενείας ${dmy(from)}–${dmy(sickTo.value)}`;
          }
          close(); toast(msg);
        }) }, "Καταχώρηση"),
        el("button", { class: "link", onclick: close }, "Κλείσιμο"))));
    openPanel(box);
  }

  // ---------- one-day change: declared overtime, other hours, or no work (AFTER declaring it in Ergani) ----------
  const CHANGE_KINDS = { overtime: "Υπερωρία (αργότερη αποχώρηση)", change: "Άλλο ωράριο αυτή την ημέρα", off: "Δεν δουλεύει (ρεπό)" };
  function showDayChange(e, d) {
    const box = document.getElementById("dayBox");
    const today = todayAthens();
    const day = el("input", { type: "date", value: today, min: today, "aria-label": "Ημέρα" });
    const kind = el("select", { "aria-label": "Είδος" }, ...Object.entries(CHANGE_KINDS).map(([k, v]) => el("option", { value: k }, v)));
    const text = el("input", { type: "text", maxlength: "60", placeholder: "π.χ. 10:00-17:30/+30", "aria-label": "Ωράριο ημέρας" });
    const note = el("input", { type: "text", maxlength: "120", placeholder: "Σημείωση (προαιρετικά), π.χ. νυφικό", "aria-label": "Σημείωση" });
    const info = el("div", {});
    const regularOf = iso => {
      const wd = (new Date(iso + "T12:00:00Z").getUTCDay() + 6) % 7;
      return ((d.schedules || {})[String(e.id)] || {})[String(wd)] || "";
    };
    const hh = x => `${String(Math.floor(x / 60)).padStart(2, "0")}:${String(x % 60).padStart(2, "0")}`;
    const refresh = () => {
      text.disabled = kind.value === "off";
      const reg = parseSpan(regularOf(day.value));
      const kids = [el("div", { class: "small" }, `Κανονικό ωράριο αυτής της ημέρας: ${reg && !reg.error ? regularOf(day.value) : "ρεπό"}`)];
      const sp = kind.value === "off" ? null : parseSpan(text.value);
      if (kind.value !== "off") {
        if (!sp || sp.error) kids.push(el("div", { class: "an-line bad" }, "Γράψε το ωράριο της ημέρας όπως θα είναι δηλωμένο στο ΕΡΓΑΝΗ, π.χ. 10:00-17:30/+30."));
        else {
          const leave = sp.e + (sp.bo ? sp.b : 0);
          kids.push(el("div", { class: "an-line" }, `Πληρωμένες ώρες ${H(netMin(sp))} · αποχώρηση ${sp.bo ? `από ${hh(sp.e)} έως ${hh(leave)}` : `στις ${hh(sp.e)}`}` +
            (reg && !reg.error ? ` · ${netMin(sp) - netMin(reg) >= 0 ? "+" : "−"}${H(Math.abs(netMin(sp) - netMin(reg)))} σε σχέση με το κανονικό` : "")));
        }
      }
      const t = e.today;
      if (day.value === today && t && kind.value !== "off" && !t.ot_by) {
        kids.push(el("div", { class: "an-line" }, "Απολογιστικό σύστημα: πέρασέ την εδώ· στο ΕΡΓΑΝΗ δηλώνεται έως το τέλος του επόμενου μήνα (φύλλο «Απολογιστικές δηλώσεις» της μηνιαίας αναφοράς)."));
      } else if (day.value === today && t && kind.value !== "off") {
        kids.push(el("div", { class: `an-line ${t.ot_passed ? "bad" : "warn"}` }, t.ot_passed
          ? `Η προθεσμία για σήμερα ήταν ${t.ot_by} (${d.settings.ot_deadline_minutes}′ πριν τη λήξη ${t.end}). Αν η υπερωρία δεν δηλώθηκε εγκαίρως στο ΕΡΓΑΝΗ, ΜΗΝ την περάσεις: ${e.display_name} φεύγει έως ${t.end}.`
          : `Δήλωσε πρώτα την υπερωρία στο ΕΡΓΑΝΗ — προθεσμία σήμερα έως ${t.ot_by} (${d.settings.ot_deadline_minutes}′ πριν τη λήξη ${t.end}). Μετά πέρασέ την εδώ.`));
      }
      info.replaceChildren(...kids);
    };
    const prefill = () => { text.value = kind.value === "off" ? "" : regularOf(day.value); refresh(); };
    day.addEventListener("change", prefill); kind.addEventListener("change", prefill); text.addEventListener("input", refresh);
    prefill();
    const close = () => hide(box);
    const list = (e.day_changes || []).map(c => el("div", { class: "leave-row" },
      `${dmy(c.day)} · ${CHANGE_KINDS[c.kind]}${c.text ? " · " + c.text : ""}${c.note ? " · " + c.note : ""} `,
      el("button", { class: "link danger", onclick: act(async () => {
        if (!confirm(`Ακύρωση της αλλαγής ${dmy(c.day)} για ${e.display_name}; Ισχύει ξανά το κανονικό ωράριο.`)) return;
        await api(`/admin/api/employees/${e.id}/day-change/${c.day}/delete`, {}); close(); toast("Η αλλαγή ακυρώθηκε");
      }) }, "Ακύρωση")));
    box.replaceChildren(el("div", { class: "qr-side" },
      el("strong", {}, `Υπερωρία / αλλαγή ημέρας · ${e.display_name}`),
      el("p", { class: "small" }, "Για μία ημέρα: υπερωρία, άλλο ωράριο, ή ρεπό (και για εργασία σε αργία ή όταν το κατάστημα είναι κλειστό). ΠΡΩΤΑ τη δηλώνεις στο ΕΡΓΑΝΗ, ΜΕΤΑ την περνάς εδώ: οι υπενθυμίσεις, οι ειδοποιήσεις και η αναφορά ακολουθούν το νέο ωράριο, και η αναφορά δείχνει τις δηλωμένες επιπλέον ώρες χωριστά. Εδώ δεν στέλνεται τίποτα στο ΕΡΓΑΝΗ."),
      ...(list.length ? [el("div", { class: "small" }, "Επόμενες αλλαγές:"), ...list] : []),
      el("div", { class: "leave-form" }, el("label", {}, "Ημέρα ", day), el("label", {}, "Είδος ", kind),
        el("label", {}, "Ωράριο ημέρας ", text), note),
      info,
      el("div", { class: "qr-actions" },
        el("button", { class: "btn", onclick: act(async () => {
          if (kind.value !== "off") { const sp = parseSpan(text.value); if (!sp || sp.error) { toast("Γράψε σωστά το ωράριο της ημέρας", true); return; } }
          const t = e.today;
          if (day.value === today && t && t.ot_passed && kind.value !== "off" &&
              !confirm(`Η προθεσμία ήταν ${t.ot_by}.\n\nΠέρασέ την ΜΟΝΟ αν η αλλαγή δηλώθηκε στο ΕΡΓΑΝΗ πριν τις ${t.ot_by}. Αλλιώς ${e.display_name} πρέπει να φύγει έως ${t.end}.\n\nΣυνέχεια;`)) return;
          const r = await api(`/admin/api/employees/${e.id}/day-change`, { day: day.value, kind: kind.value, text: text.value.trim(), note: note.value.trim() });
          close(); toast(`${e.display_name} ${dmy(day.value)}: ${kind.value === "off" ? "ρεπό" : r.text}` + (r.late_after ? ` — καταχωρήθηκε μετά την προθεσμία ${r.late_after}` : ""), !!r.late_after);
        }) }, "Καταχώρηση"),
        el("button", { class: "link", onclick: close }, "Κλείσιμο"))));
    openPanel(box);
  }

  // ---------- public holidays, local holidays and shop closures ----------
  function renderOffDays(d) {
    if (editing(document.getElementById("offdays"))) return;      // a closure / local holiday is being typed
    const today = todayAthens();
    const closures = d.closures.filter(c => c.end_date >= today);
    const cFrom = el("input", { type: "date", value: today, "aria-label": "Από" });
    const cTo = el("input", { type: "date", value: today, "aria-label": "Έως" });
    const cWhy = el("input", { type: "text", maxlength: "80", placeholder: "Αιτία, π.χ. ανακαίνιση", "aria-label": "Αιτία" });
    const closureBox = el("div", { class: "off-block" },
      el("h3", {}, "Κλείσιμο καταστήματος (ανακαίνιση, έκτακτο κλείσιμο…)"),
      ...(closures.length ? closures.map(c => el("div", { class: "leave-row" },
        `${dmy(c.start_date)}${c.end_date !== c.start_date ? "–" + dmy(c.end_date) : ""} · ${c.reason} `,
        el("button", { class: "link danger", onclick: act(async () => {
          if (!confirm(`Ακύρωση του κλεισίματος ${dmy(c.start_date)}–${dmy(c.end_date)} (${c.reason});`)) return;
          await api(`/admin/api/closures/${c.id}/delete`, {}); toast("Το κλείσιμο ακυρώθηκε");
        }) }, "Ακύρωση"))) : [el("p", { class: "small" }, "Κανένα προγραμματισμένο κλείσιμο.")]),
      el("div", { class: "leave-form" }, el("label", {}, "Από ", cFrom), el("label", {}, "Έως (τελευταία κλειστή ημέρα) ", cTo), cWhy,
        el("button", { class: "btn", onclick: act(async () => {
          if (!cWhy.value.trim()) { toast("Γράψε την αιτία", true); return; }
          await api("/admin/api/closures", { start: cFrom.value, end: cTo.value, reason: cWhy.value.trim() });
          toast(`Κλειστό ${dmy(cFrom.value)}–${dmy(cTo.value)}`);
        }) }, "Προσθήκη")));

    const until = new Date(Date.now() + 365 * 864e5).toISOString().slice(0, 10);
    const upcoming = d.holidays.filter(h => h.date >= today && h.date <= until);
    const wdName = iso => DAYS[(new Date(iso + "T12:00:00Z").getUTCDay() + 6) % 7];
    const holBox = el("div", { class: "off-block" },
      el("h3", {}, "Αργίες (επόμενοι 12 μήνες)"),
      el("p", { class: "small" }, "Υπολογίζονται μόνες τους κάθε χρόνο (και οι κινητές του Πάσχα). Τσεκαρισμένο = το κατάστημα είναι κλειστό. Η Μεγάλη Παρασκευή είναι από προεπιλογή ανοιχτή — τσέκαρέ την αν κλείνετε. Αν μια αργία μετατεθεί με απόφαση (συμβαίνει με την Πρωτομαγιά όταν πέφτει κοντά στο Πάσχα), ξετσέκαρε την αρχική ημερομηνία και βάλε τη νέα στο «Κλείσιμο καταστήματος»."),
      el("table", { class: "hol-table" }, ...upcoming.map(h => {
        const cb = el("input", { type: "checkbox", "aria-label": `Κλειστά ${h.name}` });
        cb.checked = h.closed;
        cb.addEventListener("change", act(async () => {
          await api("/admin/api/holidays", { day: h.date, closed: cb.checked });
          toast(`${h.name} ${dmy(h.date)}: ${cb.checked ? "κλειστά" : "ανοιχτά"}`);
        }));
        return el("tr", { class: h.closed ? "" : "hol-open" },
          el("td", {}, `${wdName(h.date)} ${dmy(h.date)}/${h.date.slice(2, 4)}`),
          el("td", {}, h.name + (h.kind === "local" ? " (τοπική)" : "")),
          el("td", {}, el("label", { class: "hol-cb" }, cb, h.closed ? "κλειστά" : "ανοιχτά")));
      })));

    const lMd = el("input", { type: "text", maxlength: "5", placeholder: "ΗΗ/ΜΜ", "aria-label": "Ημέρα/μήνας", class: "md" });
    const lName = el("input", { type: "text", maxlength: "60", placeholder: "Όνομα, π.χ. Πολιούχος", "aria-label": "Όνομα" });
    const saveLocal = items => api("/admin/api/local-holidays", { items });
    const localBox = el("div", { class: "off-block" },
      el("h3", {}, "Τοπικές αργίες (κάθε χρόνο την ίδια ημερομηνία)"),
      d.local_holidays.length ? null : el("p", { class: "small" }, "Καμία ακόμα. Πρόσθεσε π.χ. τη γιορτή του πολιούχου της πόλης σου, αν κλείνετε τότε."),
      ...d.local_holidays.map((x, i) => el("div", { class: "leave-row" }, `${x.md.slice(3, 5)}/${x.md.slice(0, 2)} · ${x.name} `,
        el("button", { class: "link danger", onclick: act(async () => {
          if (!confirm(`Αφαίρεση της τοπικής αργίας «${x.name}»;`)) return;
          await saveLocal(d.local_holidays.filter((_, j) => j !== i)); toast("Η τοπική αργία αφαιρέθηκε");
        }) }, "Αφαίρεση"))),
      el("div", { class: "leave-form" }, lMd, lName,
        el("button", { class: "btn ghost", onclick: act(async () => {
          const m = /^(\d{1,2})\/(\d{1,2})$/.exec(lMd.value.trim());
          if (!m || !lName.value.trim()) { toast("Γράψε ημέρα/μήνα (π.χ. 15/05) και όνομα", true); return; }
          const md = `${m[2].padStart(2, "0")}-${m[1].padStart(2, "0")}`;
          await saveLocal([...d.local_holidays, { md, name: lName.value.trim() }]); toast("Η τοπική αργία προστέθηκε");
        }) }, "Προσθήκη")));
    const fOn = !!d.settings.festive;
    const SEASON = { christmas: "Χριστουγεννιάτικη", easter: "Πασχαλινή", flag: "Εθνική επέτειος", kites: "Καθαρά Δευτέρα", may: "Πρωτομαγιά" };
    const PREVIEWS = [["christmas", "Χριστούγεννα"], ["newyear", "Πρωτοχρονιά"], ["clean_monday", "Καθαρά Δευτέρα"], ["mar25", "25η Μαρτίου"],
                      ["easter", "Πάσχα"], ["may1", "Πρωτομαγιά"], ["oct28", "28η Οκτωβρίου"], ["aug15", "Δεκαπενταύγουστος"], ["closure", "Κλείσιμο (π.χ. ανακαίνιση)"]];
    const festBox = el("div", { class: "off-block" },
      el("h3", {}, "Εορταστική διακόσμηση στην οθόνη του καταστήματος"),
      el("div", { class: `an-line ${fOn ? "ok" : "muted"} send-row` },
        el("span", {}, fOn
          ? `Ενεργή — μπαίνει μόνη της: Χριστούγεννα (1/12–6/1: χιόνι, δέντρα, Άγιος Βασίλης), Πάσχα (από των Βαΐων: αυγά, λαμπάδα, λουλούδια), 25η Μαρτίου και 28η Οκτωβρίου (σημαίες), Καθαρά Δευτέρα (χαρταετοί), Πρωτομαγιά (στεφάνι).${d.festive_today ? ` Σήμερα: ${SEASON[d.festive_today]}.` : ""}`
          : "Ανενεργή — η οθόνη μένει πάντα με την κανονική της εμφάνιση (οι ευχές τις κλειστές ημέρες εμφανίζονται κανονικά)."),
        el("button", { class: fOn ? "btn ghost" : "btn", onclick: act(async () => {
          await api("/admin/api/settings", { values: { festive: fOn ? 0 : 1 } });
          toast(fOn ? "Η εορταστική διακόσμηση απενεργοποιήθηκε" : "Η εορταστική διακόσμηση ενεργοποιήθηκε");
        }) }, fOn ? "Απενεργοποίηση" : "Ενεργοποίηση")),
      el("p", { class: "small" }, "Τις κλειστές ημέρες η οθόνη δεν δείχνει QR / PIN αλλά ευχή, την αιτία και πότε ξανανοίγετε. Προεπισκόπηση (ανοίγει σε νέα καρτέλα, δεν καταγράφει τίποτα):"),
      el("div", { class: "preview-links" }, ...PREVIEWS.map(([k, t]) => el("a", { class: "btn ghost", href: `/?preview=${k}`, target: "_blank", rel: "noopener" }, t))));
    document.getElementById("offdays").replaceChildren(closureBox, holBox, localBox, festBox);
  }

  // ---------- business details: name, short name, colour, logo ----------
  function renderBrand(d) {
    const box = document.getElementById("brandBox");
    if (editing(box)) return;          // don't redraw under the cursor
    const b = d.brand;
    const name = el("input", { type: "text", maxlength: "80", value: b.name, placeholder: "π.χ. Κομμωτήριο Άλφα" });
    const short = el("input", { type: "text", maxlength: "30", value: b.short === b.name ? "" : b.short, placeholder: "προαιρετικά, π.χ. Άλφα" });
    // colours: helpers (same formulas as brand.py)
    const rgb = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16));
    const blend = (x, y, t) => "#" + rgb(x).map((v, i) => Math.round(v + (rgb(y)[i] - v) * t).toString(16).padStart(2, "0")).join("");
    const lum = h => { const c = rgb(h).map(v => v / 255).map(v => v <= .03928 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4); return .2126 * c[0] + .7152 * c[1] + .0722 * c[2]; };
    const contrast = (x, y) => { const [p, q] = [lum(x), lum(y)].sort((m, n) => n - m); return (p + .05) / (q + .05); };
    const onColor = h => contrast(h, "#0c1a17") >= contrast(h, "#ffffff") ? "#0c1a17" : "#ffffff";
    const D = b.defaults;
    const autoIn = c => blend(c, "#ffffff", .3);
    const picker = v => el("input", { type: "color", value: v });
    const main = picker(b.color);
    const pk = { bg: picker(b.bg || D.bg), side: picker(b.side || D.side), ink: picker(b.ink || D.ink),
                 in: picker(b.in || autoIn(b.color)), out: picker(b.out || D.out) };
    const darkK = el("input", { type: "checkbox" }); darkK.checked = b.dark_kiosk;
    const darkA = el("input", { type: "checkbox" }); darkA.checked = b.dark_admin;
    const theme = el("select", {}, ...Object.entries(b.themes).map(([k, t]) => el("option", { value: k }, t.label)),
      el("option", { value: "" }, "Δικά μου χρώματα"));
    theme.value = b.theme && b.themes[b.theme] ? b.theme : (b.theme === "" && b.color === "#16897b" && !b.bg ? "karta" : "");
    let inAuto = !b.in;
    theme.addEventListener("change", () => {
      const t = b.themes[theme.value]; if (!t) return;
      main.value = t.color; for (const k of ["bg", "side", "ink", "out"]) pk[k].value = t[k] || D[k];
      pk.in.value = autoIn(t.color); inAuto = true;
      darkK.checked = t.dark_kiosk === "1"; darkA.checked = t.dark_admin === "1";
      update();
    });
    // a small shop screen with the chosen colours (CSSOM: allowed by the CSP)
    const prev = el("div", { class: "theme-preview", "aria-hidden": "true" },
      el("div", { class: "tp-side" }, el("div", { class: "tp-clock" }, "09:41"), el("div", { class: "tp-date" }, "Τρίτη 6 Οκτωβρίου")),
      el("div", { class: "tp-main" }, el("div", { class: "tp-title" }, "Καλημέρα!"),
        el("div", { class: "tp-keys" }, ...["1", "2", "3"].map(k => el("span", { class: "tp-key" }, k))),
        el("div", { class: "tp-btns" }, el("span", { class: "tp-in" }, "Προσέλευση"), el("span", { class: "tp-out" }, "Αποχώρηση"))));
    const warn = el("span", { class: "small" });
    function update(ev) {
      if (ev && ev.target === main && inAuto) pk.in.value = autoIn(main.value);
      if (ev && (ev.target === main || Object.values(pk).includes(ev.target))) theme.value = "";   // changed by hand: «Δικά μου χρώματα»
      const dark = darkK.checked;
      for (const k of ["bg", "side", "ink"]) pk[k].disabled = dark;      // the dark theme has its own background and text
      const v = dark
        ? { bg: "#14191a", side: "#1c2224", panel: "#232a2c", ink: "#eef1f0", ink2: "#a9b4b2", acc: blend(main.value, "#ffffff", .45) }
        : { bg: pk.bg.value, side: pk.side.value, panel: "#ffffff", ink: pk.ink.value, ink2: blend(pk.ink.value, pk.bg.value, .38), acc: main.value };
      const out = dark && pk.out.value === D.out ? "#4a5559" : pk.out.value;
      const set = (k, x) => prev.style.setProperty(k, x);
      set("--p-bg", v.bg); set("--p-side", v.side); set("--p-panel", v.panel); set("--p-ink", v.ink); set("--p-ink2", v.ink2);
      set("--p-acc", v.acc); set("--p-in", pk.in.value); set("--p-on-in", onColor(pk.in.value)); set("--p-out", out); set("--p-on-out", onColor(out));
      const msgs = [];
      if (!dark && contrast(pk.ink.value, pk.bg.value) < 4.5) msgs.push("Το κείμενο δεν διαβάζεται καλά πάνω στο φόντο: διαλέξτε πιο σκούρο κείμενο ή πιο ανοιχτό φόντο.");
      if (contrast(main.value, "#ffffff") < 3 && !dark) msgs.push("Πολύ ανοιχτό κύριο χρώμα: τα κουμπιά και οι τίτλοι δεν θα διαβάζονται καλά.");
      warn.className = msgs.length ? "small warn-text" : "small";
      warn.textContent = msgs.join(" ") || "Τα κείμενα στα κουμπιά παίρνουν μόνα τους μαύρο ή λευκό χρώμα, όποιο διαβάζεται καλύτερα.";
    }
    pk.in.addEventListener("input", () => { inAuto = false; });
    for (const x of [main, ...Object.values(pk), darkK, darkA]) x.addEventListener("input", update);
    update();
    const logoImg = el("img", { class: "brand-logo", alt: "Λογότυπο", src: `/brand/logo?v=${Date.now()}` });
    logoImg.addEventListener("error", () => { logoImg.hidden = true; });
    const file = el("input", { type: "file", accept: "image/png,image/jpeg,image/webp" });
    file.addEventListener("change", act(async () => {
      const f = file.files[0]; if (!f) return;
      if (f.size > 1000000) { toast("Το λογότυπο πρέπει να είναι έως 1 MB", true); return; }
      const data = await new Promise((ok, fail) => { const r = new FileReader(); r.onload = () => ok(r.result); r.onerror = fail; r.readAsDataURL(f); });
      await api("/admin/api/brand/logo", { data }); toast("Το λογότυπο αποθηκεύτηκε");
    }));
    const save = act(async () => {
      const or = (x, dflt) => x.value.toLowerCase() === dflt.toLowerCase() ? "" : x.value;      // the default = "" (follows the theme)
      await api("/admin/api/brand", { name: name.value.trim(), short: short.value.trim(), color: main.value, theme: theme.value,
        bg: or(pk.bg, D.bg), side: or(pk.side, D.side), ink: or(pk.ink, D.ink), in_color: or(pk.in, autoIn(main.value)),
        out_color: or(pk.out, D.out), dark_kiosk: darkK.checked, dark_admin: darkA.checked });
      const link = document.querySelector('link[href^="/brand.css"]');
      if (link) link.href = `/brand.css?v=${Date.now()}`;                                 // the admin page takes the new colours now
      toast("Τα στοιχεία αποθηκεύτηκαν — η οθόνη του καταστήματος τα παίρνει στο επόμενο άνοιγμα ή με «Ανανέωση οθόνης»");
    });
    const col = (label, input) => el("label", { class: "brand-color" }, label, input);
    box.replaceChildren(el("div", { class: "brand-form" },
      el("label", {}, "Επωνυμία (όπως τη βλέπουν οι πελάτες) ", name),
      el("label", {}, "Σύντομο όνομα (στους τίτλους και στα μηνύματα) ", short)),
      el("h3", { class: "brand-sub" }, "Χρώματα"),
      el("div", { class: "brand-colors" },
        el("div", { class: "brand-form" },
          el("label", {}, "Έτοιμο θέμα ", theme),
          col("Κύριο χρώμα", main), col("Φόντο", pk.bg), col("Πλαϊνό πάνελ", pk.side), col("Κείμενο", pk.ink),
          col("Κουμπί «Προσέλευση»", pk.in), col("Κουμπί «Αποχώρηση»", pk.out),
          el("label", { class: "check" }, darkK, " Σκούρο θέμα στην οθόνη του καταστήματος"),
          el("label", { class: "check" }, darkA, " Σκούρο θέμα στη σελίδα διαχείρισης"),
          warn),
        prev),
      el("div", { class: "backup-row" },
        el("button", { class: "btn", type: "button", onclick: save }, "Αποθήκευση στοιχείων"),
        el("button", { class: "link", type: "button", onclick: () => { theme.value = "karta"; theme.dispatchEvent(new Event("change")); } }, "Αρχικά χρώματα")),
      el("div", { class: "brand-logo-row" }, logoImg,
        el("div", {}, el("div", { class: "small" }, b.has_logo ? "Λογότυπο (PNG, JPG ή WebP, έως 1 MB· καλύτερα τετράγωνο με διάφανο φόντο):" : "Χωρίς λογότυπο: η οθόνη δείχνει την επωνυμία. Ανέβασε PNG, JPG ή WebP έως 1 MB (καλύτερα τετράγωνο με διάφανο φόντο):"),
          file,
          b.has_logo ? el("button", { class: "link danger", onclick: act(async () => {
            if (!confirm("Αφαίρεση του λογότυπου;")) return;
            await api("/admin/api/brand/logo/delete", {}); toast("Το λογότυπο αφαιρέθηκε");
          }) }, "Αφαίρεση λογότυπου") : "")));
  }

  // ---------- business, Ergani users and mode («Επιχείρηση και σύνδεση με το ΕΡΓΑΝΗ») ----------
  const SRC = { gui: "", env: " (από το .env)", "": "" };
  const MODE_TEXT = {
    dry_run: "Δοκιμαστική λειτουργία: τα χτυπήματα καταγράφονται μόνο στην Karta, τίποτα δεν στέλνεται στο ΕΡΓΑΝΗ.",
    trial: "Δοκιμαστικό ΕΡΓΑΝΗ: τα χτυπήματα στέλνονται στο περιβάλλον δοκιμών του ΕΡΓΑΝΗ, χωρίς νομική ισχύ.",
    production: "Κανονική λειτουργία: κάθε χτύπημα δηλώνεται στο πραγματικό ΕΡΓΑΝΗ.",
  };
  function field(label, input, src, help) {
    return el("label", {}, label, input, src ? el("span", { class: "cfg-src" }, SRC[src] ? SRC[src].trim() : "") : null,
      help ? el("span", { class: "cfg-src" }, help) : null);
  }
  const input = (value, attrs = {}) => el("input", { type: "text", value: value || "", ...attrs });
  const secretInput = (info, ph) => el("input", { type: "password", autocomplete: "new-password",
    placeholder: info.set ? "•••••• (αποθηκευμένος· άφησέ το κενό για να μείνει)" : ph });
  function userTypeSelect(value, fallback) {
    const s = el("select", {},
      el("option", { value: "01" }, "01: χρήστης API (web services)"),
      el("option", { value: "02" }, "02: χρήστης ΕΡΓΑΝΗ παραρτήματος"));
    s.value = value || fallback;
    return s;
  }
  function erganiUser(C, group, target, names, typeFallback) {
    const [U, P, T] = names;
    const user = input(C[group][U].value, { maxlength: "100", autocomplete: "off" });
    const pass = secretInput(C[group][P], "κωδικός");
    const type = userTypeSelect(C[group][T].value, typeFallback);
    const result = el("span", { class: "small" });
    return {
      fields: [field("Όνομα χρήστη", user, C[group][U].source), field("Κωδικός", pass, C[group][P].source),
               field("Τύπος χρήστη", type, C[group][T].source)],
      values: () => ({ [U]: user.value.trim(), [P]: pass.value ? pass.value : null, [T]: type.value }),
      saved: () => { pass.value = ""; },
      result,
      test: el("button", { class: "btn ghost", type: "button", onclick: act(async () => {
        result.textContent = "Δοκιμή…";
        const r = await api("/admin/api/config/login-test", { target, username: user.value.trim(),
          password: pass.value ? pass.value : null, user_type: type.value });
        result.className = r.ok ? "small" : "small warn-text";
        result.textContent = r.ok ? "✓ Η σύνδεση πέτυχε (δεν υποβλήθηκε τίποτα)." : `✗ ${r.message}`;
      }) }, "Δοκιμή σύνδεσης"),
    };
  }
  function erganiUserForm(C, group, target, names, typeFallback) {
    const u = erganiUser(C, group, target, names, typeFallback);
    return el("div", { class: "brand-form" }, ...u.fields, u.test,
      el("button", { class: "btn", type: "button", onclick: act(async () => {
        await api("/admin/api/config", { group, values: u.values() }); u.saved();
        toast("Τα στοιχεία σύνδεσης αποθηκεύτηκαν");
      }) }, "Αποθήκευση"),
      u.result);
  }
  function renderConfig(d) {
    const box = document.getElementById("cfgBox");
    if (editing(box)) return;
    const C = d.config;
    const B = C.business;
    const afm = input(B.EMPLOYER_AFM.value, { maxlength: "9", inputmode: "numeric", autocomplete: "off" });
    const branch = input(B.BRANCH_NUMBER.value || "0", { maxlength: "4", inputmode: "numeric" });
    const empId = input(B.ERGANI_EMPLOYER_ID.value, { maxlength: "40", placeholder: "προαιρετικά" });
    const decl = el("select", {},
      el("option", { value: "advance" }, "Προαναγγελία: αλλαγές και υπερωρίες δηλώνονται πριν"),
      el("option", { value: "retro" }, "Απολογιστικό: δηλώνονται μετά, έως το τέλος του επόμενου μήνα"));
    decl.value = B.TIME_DECLARATION.value || "advance";
    const ergUser = erganiUser(C, "ergani", "production", ["ERGANI_USERNAME", "ERGANI_PASSWORD", "ERGANI_USER_TYPE"], "01");
    const mode = C.mode.value;
    const onboard = d.onboarding && d.onboarding.active ? d.onboarding : null;   // nothing is sent until its end
    // «Λειτουργία»: Δοκιμαστική · Περίοδος προσαρμογής (production with a date) · Κανονική λειτουργία; trial for the advanced
    const cur = mode === "production" ? (onboard ? "onboarding" : "production") : mode;
    const today = todayAthens();
    const until = el("input", { type: "date", min: isoPlus(today, 1), max: isoPlus(today, 366), value: onboard ? onboard.until : "",
                                "aria-label": "Υποχρεωτική χρήση από" });
    const askAfm = text => { const t = prompt(`${text}\n\nΓια επιβεβαίωση γράψε το ΑΦΜ της επιχείρησης:`); return t === null ? null : t.trim(); };
    const setMode = async (m, afm, onboarding_until, done) => { await api("/admin/api/mode", { mode: m, afm, onboarding_until }); toast(done); };
    const choose = {
      dry_run: async () => {
        if (!confirm("Δοκιμαστική λειτουργία; Τα νέα χτυπήματα καταγράφονται μόνο στην Karta και δεν στέλνονται στο ΕΡΓΑΝΗ." +
            (onboard ? "\n\nΗ περίοδος προσαρμογής τελειώνει." : ""))) return;
        await setMode("dry_run", "", null, "Δοκιμαστική λειτουργία");
      },
      onboarding: async () => {
        if (!until.value) { toast("Διάλεξε την ημερομηνία που η κάρτα γίνεται υποχρεωτική", true); return; }
        if (onboard) {          // only a new date
          if (until.value === onboard.until) { toast("Διάλεξε νέα ημερομηνία", true); return; }
          await api("/admin/api/onboarding", { until: until.value }); toast(`Η κάρτα γίνεται υποχρεωτική ${fmtDayLong(until.value)}`);
          return;
        }
        const text = `Περίοδος προσαρμογής έως και ${fmtDayLong(isoPlus(until.value, -1))};\n\nΤα χτυπήματα καταγράφονται κανονικά αλλά ΔΕΝ στέλνονται ` +
          `στο ΕΡΓΑΝΗ. Από ${fmtDayLong(until.value)} στέλνονται μόνα τους, χωρίς να κάνεις τίποτα.\n\nΜόνο αν η κάρτα δεν είναι ακόμα υποχρεωτική για την επιχείρηση.`;
        let afm = "";
        if (mode === "production") { if (!confirm(text)) return; }
        else { afm = askAfm(`${text} Πρώτα γίνεται δοκιμή σύνδεσης στο ΕΡΓΑΝΗ.`); if (afm === null) return; }
        await setMode("production", afm, until.value, `Περίοδος προσαρμογής: υποχρεωτική ${fmtDayLong(until.value)}`);
      },
      production: async () => {
        let afm = "";
        if (mode === "production") {    // in the onboarding period: it ends now
          const inside = d.employees.filter(e => e.inside && e.last_status === "onboarding").map(e => e.display_name);
          if (!confirm("Τέλος της περιόδου προσαρμογής τώρα;\n\nΑπό αυτή τη στιγμή κάθε νέα προσέλευση στέλνεται στο ΕΡΓΑΝΗ." +
              (inside.length ? `\n\n${inside.join(", ")}: είναι ήδη μέσα — η αποχώρησή τους μένει μόνο στην κάρτα (όπως η προσέλευση), ώστε να μη σταλεί αποχώρηση χωρίς προσέλευση.` : ""))) return;
        } else {
          afm = askAfm("ΠΡΟΣΟΧΗ: από εδώ και πέρα κάθε χτύπημα δηλώνεται στο πραγματικό ΕΡΓΑΝΗ και έχει νομική ισχύ. Πρώτα γίνεται δοκιμή σύνδεσης.");
          if (afm === null) return;
        }
        await setMode("production", afm, null, "Κανονική λειτουργία: τα χτυπήματα στέλνονται στο ΕΡΓΑΝΗ");
      },
      trial: async () => {
        const afm = askAfm("Τα χτυπήματα θα στέλνονται στο περιβάλλον δοκιμών του ΕΡΓΑΝΗ (χωρίς νομική ισχύ). Πρώτα γίνεται δοκιμή σύνδεσης.");
        if (afm === null) return;
        await setMode("trial", afm, null, "Δοκιμαστικό ΕΡΓΑΝΗ");
      },
    };
    const days = n => n === 1 ? "αύριο" : `σε ${n} ημέρες`;
    const MODES = [
      ["dry_run", "Δοκιμαστική", "Για δοκιμές και εκπαίδευση: τα χτυπήματα καταγράφονται μόνο στην Karta, τίποτα δεν στέλνεται στο ΕΡΓΑΝΗ."],
      ...(cur === "trial" ? [["trial", "Δοκιμαστικό ΕΡΓΑΝΗ", MODE_TEXT.trial]] : []),
      ["onboarding", "Περίοδος προσαρμογής", onboard
        ? `Από ${fmtDayLong(onboard.since)}: το προσωπικό χτυπά κανονικά (υπενθυμίσεις, ειδοποιήσεις, αναφορές), αλλά τίποτα δεν στέλνεται στο ΕΡΓΑΝΗ. ` +
          `Η κάρτα γίνεται υποχρεωτική ${fmtDayLong(onboard.until)} (${days(onboard.days_left)}) και τότε η αποστολή ξεκινά μόνη της.`
        : "Για όσο η κάρτα δεν είναι ακόμα υποχρεωτική: το προσωπικό τη χρησιμοποιεί κανονικά (υπενθυμίσεις, ειδοποιήσεις, αναφορές), αλλά τίποτα " +
          "δεν στέλνεται στο ΕΡΓΑΝΗ μέχρι την ημερομηνία που ορίζεις· από εκείνη τη μέρα η αποστολή ξεκινά μόνη της."],
      ["production", "Κανονική λειτουργία", "Κάθε χτύπημα δηλώνεται στο πραγματικό ΕΡΓΑΝΗ και έχει νομική ισχύ."],
    ];
    const buttons = k => k === "onboarding" && cur === "onboarding"
      ? [el("button", { class: "btn ghost", type: "button", onclick: act(choose.onboarding) }, "Αλλαγή ημερομηνίας"),
         el("button", { class: "btn danger", type: "button", onclick: act(choose.production) }, "Τέλος περιόδου τώρα")]
      : k === cur || (k === "production" && cur === "onboarding") ? []      // the period ends from its own row
      : [el("button", { class: k === "production" ? "btn" : "btn ghost", type: "button", onclick: act(choose[k]) },
            k === "onboarding" ? "Έναρξη" : "Επιλογή")];
    const modeRows = MODES.map(([k, title, text]) => el("div", { class: `mode-opt${k === cur ? " current" : ""}` },
      el("div", { class: "mode-text" },
        el("strong", {}, title), k === cur ? el("span", { class: "mode-now" }, " · τώρα") : null,
        k === cur && C.mode.source === "env" ? el("span", { class: "cfg-src" }, " (από το .env)") : null,
        el("div", { class: "small" }, text),
        k === "onboarding" ? el("label", { class: "mode-date" }, "Υποχρεωτική από ", until) : null),
      buttons(k).length ? el("div", { class: "mode-buttons" }, ...buttons(k)) : null));
    const advanced = el("details", { class: "help cfg-advanced" },
      el("summary", {}, "Για προχωρημένους: δοκιμαστικό ΕΡΓΑΝΗ"),
      el("p", { class: "small" }, "Στέλνει τα χτυπήματα στο περιβάλλον δοκιμών του ΕΡΓΑΝΗ (trialv2eservices.yeka.gr), χωρίς νομική ισχύ, " +
        "για να δοκιμάσετε τη σύνδεση πριν την κανονική λειτουργία. Δεν χρειάζεται για να ξεκινήσετε. Το περιβάλλον δοκιμών έχει δικούς " +
        "του χρήστες· αν αφήσετε τον χρήστη κενό, χρησιμοποιείται ο παραπάνω."),
      erganiUserForm(C, "trial", "trial", ["ERGANI_TRIAL_USERNAME", "ERGANI_TRIAL_PASSWORD", "ERGANI_TRIAL_USER_TYPE"], "02"),
      cur === "trial" ? null : el("div", { class: "mode-actions" },
        el("button", { class: "btn ghost", type: "button", onclick: act(choose.trial) }, "Πέρασμα σε δοκιμαστικό ΕΡΓΑΝΗ")));
    box.replaceChildren(
      ...(C.problems.length ? [el("div", { class: "an-line bad" }, el("strong", {}, "Χρειάζεται συμπλήρωση: "), C.problems.join(" · "),
        mode !== "dry_run" ? " — μέχρι τότε τα χτυπήματα περιμένουν και δεν στέλνονται." : "")] : []),
      el("div", { class: "cfg-group" },
        el("h3", {}, "Λειτουργία"), ...modeRows),
      el("div", { class: "cfg-group" },
        el("h3", {}, "Επιχείρηση"),
        el("div", { class: "brand-form" },
          field("ΑΦΜ εργοδότη", afm, B.EMPLOYER_AFM.source),
          field("Αριθμός παραρτήματος", branch, B.BRANCH_NUMBER.source, "Συνήθως 0 (η έδρα)."),
          field("Κωδικός εργοδότη στο ΕΡΓΑΝΗ", empId, B.ERGANI_EMPLOYER_ID.source, "Προαιρετικά: το «id:» στο QR του ΕΡΓΑΝΗ."),
          field("Δήλωση αλλαγών ωραρίου και υπερωριών", decl, B.TIME_DECLARATION.source,
            "Ό,τι έχει επιλέξει η επιχείρηση στο ΕΡΓΑΝΗ (ρωτήστε τον λογιστή). Το απολογιστικό σύστημα υπάρχει για " +
            "επιχειρήσεις με ψηφιακή κάρτα: οι αλλαγές και οι υπερωρίες δηλώνονται από τα χτυπήματα, έως το τέλος του " +
            "επόμενου μήνα. Τα όρια ωρών και ανάπαυσης ισχύουν και στα δύο. Αλλάζει τις ειδοποιήσεις της Karta.")),
        el("h4", { class: "cfg-sub" }, "Χρήστης web services του ΕΡΓΑΝΗ"),
        el("p", { class: "small" }, "Τον φτιάχνει ο λογιστής σας ή εσείς στο ΕΡΓΑΝΗ. Με αυτόν η Karta διαβάζει το προσωπικό και, σε κανονική λειτουργία, στέλνει τα χτυπήματα. Ο κωδικός φυλάσσεται κρυπτογραφημένος."),
        C.can_store_secrets ? null : el("p", { class: "small warn-text" }, "Λείπει το PIN_KEY από το .env: ο κωδικός μπορεί να αλλάξει μόνο στο .env."),
        el("div", { class: "brand-form" }, ...ergUser.fields, ergUser.test,
          el("button", { class: "btn", type: "button", onclick: act(async () => {
            await api("/admin/api/config", { group: "company", values: {
              EMPLOYER_AFM: afm.value.trim(), BRANCH_NUMBER: branch.value.trim(), ERGANI_EMPLOYER_ID: empId.value.trim(),
              TIME_DECLARATION: decl.value, ...ergUser.values() } });
            ergUser.saved();
            toast("Τα στοιχεία της επιχείρησης αποθηκεύτηκαν");
          }) }, "Αποθήκευση"),
          ergUser.result)),
      advanced);
  }

  // ---------- phone alerts (ntfy) ----------
  function renderNtfy(d) {
    const box = document.getElementById("cfgNtfy");
    if (editing(box)) return;
    const N = d.config.ntfy;
    // one suggestion per page load: the 30″ refresh must not change a topic someone is copying into the phone app
    renderNtfy.topic ||= "karta-" + Array.from(crypto.getRandomValues(new Uint8Array(6)), b => b.toString(16).padStart(2, "0")).join("");
    const url = input(N.NTFY_URL.value || "https://ntfy.sh", { maxlength: "200" });
    const topic = input(N.NTFY_TOPIC.value || renderNtfy.topic, { maxlength: "64", autocomplete: "off" });
    const token = secretInput(N.NTFY_TOKEN, "μόνο αν ο server θέλει token");
    const on = !!(N.NTFY_URL.value && N.NTFY_TOPIC.value);
    box.replaceChildren(
      el("p", { class: "small" }, "Οι ειδοποιήσεις (δεν χτύπησε κάποιος, σφάλμα ΕΡΓΑΝΗ…) έρχονται στο κινητό σας με τη δωρεάν εφαρμογή ",
        el("strong", {}, "ntfy"), " (Android / iPhone). Στην εφαρμογή πατήστε «+» και γράψτε το θέμα (topic) παρακάτω. Κρατήστε το θέμα μυστικό: όποιος το ξέρει βλέπει τις ειδοποιήσεις."),
      el("div", { class: "brand-form" },
        field("Server", url, N.NTFY_URL.source),
        field("Θέμα (topic)", topic, N.NTFY_TOPIC.source),
        field("Token (προαιρετικά)", token, N.NTFY_TOKEN.source),
        el("button", { class: "btn", type: "button", onclick: act(async () => {
          await api("/admin/api/config", { group: "ntfy", values: { NTFY_URL: url.value.trim(), NTFY_TOPIC: topic.value.trim(),
            NTFY_TOKEN: token.value ? token.value : null } });
          toast("Οι ειδοποιήσεις κινητού αποθηκεύτηκαν");
        }) }, "Αποθήκευση"),
        on ? el("button", { class: "btn ghost", type: "button", onclick: act(async () => {
          await api("/admin/api/ntfy/test", {}); toast("Στάλθηκε δοκιμαστική ειδοποίηση στο κινητό");
        }) }, "Δοκιμαστική ειδοποίηση") : null,
        on ? el("button", { class: "link danger", type: "button", onclick: act(async () => {
          if (!confirm("Απενεργοποίηση των ειδοποιήσεων στο κινητό;")) return;
          await api("/admin/api/config", { group: "ntfy", values: { NTFY_URL: "", NTFY_TOPIC: "", NTFY_TOKEN: "" } });
        }) }, "Απενεργοποίηση") : null));
  }

  // ---------- backups: nightly copy (machine/USB), encrypted cloud upload, downloads, restore ----------
  const dmyhm = iso => `${iso.slice(8, 10)}/${iso.slice(5, 7)} ${iso.slice(11, 16)}`;
  // Greek capitals that look exactly like Latin ones, for comparing what someone typed on a Greek keyboard
  const LOOKALIKE = { "Α": "A", "Β": "B", "Ε": "E", "Ζ": "Z", "Η": "H", "Ι": "I", "Κ": "K", "Μ": "M", "Ν": "N", "Ο": "O",
                      "Ρ": "P", "Τ": "T", "Υ": "Y", "Χ": "X" };
  const latin = t => t.trim().toUpperCase().replace(/\s+/g, "").replace(/[ΑΒΕΖΗΙΚΜΝΟΡΤΥΧ]/g, c => LOOKALIKE[c]);
  const sameChars = (typed, want) => latin(typed) === latin(want);

  // The only way into the cloud backups if this machine is lost: it can't be recovered by anyone, so the panel stays
  // until the admin types its last 4 characters back.
  function showCloudPassword(pw, again = false) {
    const box = document.getElementById("cloudPass");
    const tail = pw.slice(-4);
    const check = el("input", { type: "text", maxlength: "8", autocomplete: "off", autocapitalize: "off", autocorrect: "off",
                                spellcheck: "false", lang: "en", class: "pass-check", "aria-label": "Οι 4 τελευταίοι χαρακτήρες του κωδικού" });
    const note = el("span", { class: "small", role: "status" });
    // It only proves the password was looked at: capitals and Greek look-alike letters (a Greek keyboard, a phone that
    // capitalises the first letter) must not make a correct answer fail without a word.
    const same = () => sameChars(check.value, tail);
    const done = el("button", { class: "btn", type: "button", onclick: () => {
      if (same()) { hide(box); return; }
      note.className = "small warn-text";
      note.textContent = check.value.trim()
        ? `Δεν ταιριάζει: γράψτε τους 4 τελευταίους χαρακτήρες όπως φαίνονται παραπάνω (${tail.length} λατινικοί χαρακτήρες).`
        : "Γράψτε πρώτα τους 4 τελευταίους χαρακτήρες του κωδικού.";
      check.focus();
    } }, "Τον σημείωσα");
    check.addEventListener("input", () => {
      const ok = same();
      note.className = ok ? "small ok-text" : "small";
      note.textContent = ok ? "✓ Σωστά" : "";
    });
    box.hidden = false;
    box.replaceChildren(
      el("h3", {}, "Κωδικός κρυπτογράφησης των αντιγράφων"),
      el("p", { class: "pass" }, pw),
      el("div", { class: "pass-warn" },
        el("strong", {}, "Χωρίς αυτόν τον κωδικό τα αντίγραφα στο cloud δεν ανοίγουν ποτέ."),
        " Δεν υπάρχει «ξέχασα τον κωδικό»: δεν μπορεί να τον ανακτήσει ούτε η Karta, ούτε η Google / Dropbox / Backblaze, " +
        "ούτε κανείς άλλος. Αν χαλάσει ή χαθεί αυτό το μηχάνημα, είναι ο μόνος τρόπος να πάρετε πίσω το αρχείο χτυπημάτων, " +
        "που πρέπει να φυλάσσεται για χρόνια."),
      el("p", {}, el("strong", {}, "Γράψτε τον τώρα σε χαρτί (φυλάξτε το εκτός καταστήματος) ή σε διαχειριστή κωδικών."),
        " Είναι λατινικοί χαρακτήρες, και τα κεφαλαία και τα πεζά μετράνε: γράψτε τον ακριβώς όπως φαίνεται.",
        again ? " Από εδώ φαίνεται μόνο όσο δουλεύει αυτό το μηχάνημα· όταν χαλάσει, μένει μόνο ό,τι έχετε γράψει."
              : " Εμφανίζεται μόνο αυτή τη φορά (μετά, μόνο όσο δουλεύει αυτό το μηχάνημα: «Εμφάνιση κωδικού κρυπτογράφησης»)."),
      el("div", { class: "backup-row" },
        el("button", { class: "btn ghost", type: "button", onclick: async () => {
          try { await navigator.clipboard.writeText(pw); toast("Ο κωδικός αντιγράφηκε"); } catch { toast("Επιλέξτε τον κωδικό και αντιγράψτε τον", true); }
        } }, "Αντιγραφή")),
      el("label", { class: "pass-confirm" }, "Για επιβεβαίωση, γράψτε τους 4 τελευταίους χαρακτήρες:", check, note),
      done);
    box.scrollIntoView({ behavior: "smooth", block: "center" });
  }
  function showRestore(info) {
    const box = document.getElementById("restorePanel");
    box.hidden = false;
    const warn = info.pin_key_ok === false
      ? el("p", { class: "warn-text" }, "Προσοχή: το αντίγραφο φτιάχτηκε με άλλο PIN_KEY. Μετά την επαναφορά ο κωδικός ΕΡΓΑΝΗ και τα PIN δεν θα εμφανίζονται: βάλτε στο .env το PIN_KEY της παλιάς εγκατάστασης (υπάρχει στο karta.env των αντιγράφων) ή ξαναγράψτε τον κωδικό ΕΡΓΑΝΗ και δώστε νέα PIN.")
      : null;
    box.replaceChildren(
      el("h3", {}, "Επαναφορά από αντίγραφο"),
      el("p", {}, `${info.business || "(χωρίς όνομα επιχείρησης)"} · ${info.employees} ενεργοί εργαζόμενοι · ${info.punches} πραγματικά χτυπήματα` +
        (info.test_punches ? ` (και ${info.test_punches} δοκιμαστικά)` : "") +
        (info.last_punch ? ` · τελευταίο χτύπημα ${info.last_punch.slice(8, 10)}/${info.last_punch.slice(5, 7)}/${info.last_punch.slice(0, 4)} ${info.last_punch.slice(11, 16)}` : "")),
      ...(warn ? [warn] : []),
      el("p", { class: "small" }, "Η τωρινή βάση θα αντικατασταθεί από αυτό το αντίγραφο. Πριν από αυτό κρατιέται αντίγραφό της (before-restore-…db, δίπλα στη βάση)."),
      el("div", { class: "backup-row" },
        el("button", { class: "btn danger", type: "button", onclick: act(async () => {
          if (!confirm("Επαναφορά τώρα; Ό,τι έγινε μετά από αυτό το αντίγραφο δεν θα φαίνεται πια.")) return;
          const r = await api("/admin/api/restore/apply", { confirm: true });
          hide(box); toast(`Η επαναφορά έγινε (η προηγούμενη βάση κρατήθηκε ως ${r.kept}).`);
          editorsFor = null;
        }) }, "Επαναφορά τώρα"),
        el("button", { class: "btn ghost", type: "button", onclick: act(async () => {
          await api("/admin/api/restore/discard", {}); hide(box);
        }) }, "Ακύρωση")));
    box.scrollIntoView({ behavior: "smooth", block: "center" });
  }
  function cloudForm(B) {
    const provider = el("select", {},
      el("option", { value: "drive" }, "Google Drive"), el("option", { value: "dropbox" }, "Dropbox"),
      el("option", { value: "b2" }, "Backblaze B2"));
    const token = el("textarea", { rows: "3", placeholder: '{"access_token":"…","token_type":"Bearer",…}', autocomplete: "off" });
    const account = el("input", { type: "text", placeholder: "keyID", autocomplete: "off" });
    const key = el("input", { type: "password", placeholder: "applicationKey", autocomplete: "new-password" });
    const bucket = el("input", { type: "text", placeholder: "όνομα bucket" });
    const password = el("input", { type: "password", placeholder: "ο κωδικός κρυπτογράφησης των αντιγράφων", autocomplete: "new-password" });
    const kind = () => provider.value === "b2" ? "b2" : "oauth";
    const oauthHelp = el("ol", { class: "small" },
      el("li", {}, "Σε έναν υπολογιστή κατεβάστε το rclone από ", el("a", { href: "https://rclone.org/downloads/", target: "_blank", rel: "noopener" }, "rclone.org/downloads"), " και αποσυμπιέστε το zip."),
      el("li", {}, "Ανοίξτε τερματικό σε εκείνο τον φάκελο (Windows: δεξί κλικ μέσα στον φάκελο → «Άνοιγμα στο τερματικό») και τρέξτε:",
        el("br", {}), "Windows: ", el("code", { class: "cmd-win" }, ""), el("br", {}), "Mac / Linux: ", el("code", { class: "cmd-mac" }, "")),
      el("li", {}, "Συνδεθείτε στον browser που ανοίγει και πατήστε «Allow»."),
      el("li", {}, "Αντιγράψτε το κείμενο που τυπώνει (ξεκινά με {\"access_token\") και επικολλήστε το εδώ:"));
    const b2Help = el("p", { class: "small" }, "Στο Backblaze: B2 Cloud Storage → Buckets → Create a Bucket (Private), και Application Keys → Add a New Key. Τα πρώτα 10 GB είναι δωρεάν.");
    const oauthBox = el("div", {}, oauthHelp, token);
    const b2Box = el("div", { class: "brand-form" }, b2Help, account, key, bucket);
    const sync = () => {
      oauthBox.hidden = kind() !== "oauth"; b2Box.hidden = kind() !== "b2";
      oauthHelp.querySelector(".cmd-win").textContent = `.\\rclone.exe authorize "${provider.value}"`;
      oauthHelp.querySelector(".cmd-mac").textContent = `./rclone authorize "${provider.value}"`;
    };
    provider.addEventListener("change", sync); sync();
    const send = existing => act(async () => {
      const r = await api("/admin/api/cloud/connect", { provider: provider.value, token: token.value.trim(), account: account.value.trim(),
        key: key.value.trim(), bucket: bucket.value.trim(), password: existing ? password.value : null });
      if (r.password) showCloudPassword(r.password);
      if (r.empty) toast(existing ? "Συνδέθηκε με τα υπάρχοντα αντίγραφα· τώρα: «Επαναφορά» → «Από το cloud…»."
                                  : "Το cloud ρυθμίστηκε· το πρώτο αντίγραφο ανεβαίνει μόλις προστεθούν εργαζόμενοι.");
      else if (r.first_backup !== "ok") toast(`Το cloud ρυθμίστηκε, αλλά το πρώτο αντίγραφο απέτυχε: ${r.error || "άγνωστο σφάλμα"}`, true);
      else toast(existing ? "Συνδέθηκε με τα υπάρχοντα αντίγραφα· τώρα μπορείτε να κάνετε επαναφορά από το cloud."
                          : "Το cloud ρυθμίστηκε και το πρώτο αντίγραφο ανέβηκε ✓");
    });
    const existingBox = el("details", { class: "help" },
      el("summary", {}, "Έχω ήδη αντίγραφα στο cloud (νέο μηχάνημα / επαναφορά)"),
      el("div", { class: "backup-row" }, password,
        el("button", { class: "btn ghost", type: "button", onclick: send(true) }, "Σύνδεση στα υπάρχοντα αντίγραφα")));
    return el("div", { class: "cloud-form" },
      el("label", {}, "Πού ", provider), oauthBox, b2Box,
      el("p", { class: "small warn-text" }, "Θα σας δοθεί ένας κωδικός κρυπτογράφησης, μία φορά. Κρατήστε τον οπωσδήποτε: χωρίς αυτόν " +
        "τα αντίγραφα στο cloud δεν ανοίγουν και δεν υπάρχει τρόπος ανάκτησης."),
      el("div", { class: "backup-row" }, el("button", { class: "btn", type: "button", onclick: send(false) }, "Σύνδεση και πρώτο ανέβασμα")),
      existingBox);
  }
  async function restoreFromFile(file) {
    if (!file) return;
    const res = await fetch("/admin/api/restore/upload", { method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/octet-stream" }, body: file });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || httpError(res.status));
    showRestore(data);
  }
  async function restoreFromCloudList() {
    const box = document.getElementById("restorePanel");      // outside #backupBox: the refresh doesn't redraw it
    const { backups } = await api("/admin/api/cloud/backups");
    if (!backups.length) { toast("Δεν βρέθηκαν αντίγραφα στο cloud", true); return; }
    const sel = el("select", {}, ...backups.map(b => el("option", { value: b.id },
      `${b.time.slice(8, 10)}/${b.time.slice(5, 7)}/${b.time.slice(0, 4)} ${b.time.slice(11, 16)}`)));
    box.hidden = false;
    box.replaceChildren(el("h3", {}, "Επαναφορά από το cloud"),
      el("div", { class: "backup-row" }, sel,
        el("button", { class: "btn ghost", type: "button", onclick: act(async () => {
          showRestore(await api("/admin/api/restore/cloud", { id: sel.value }));
        }) }, "Έλεγχος αντιγράφου"),
        el("button", { class: "link", type: "button", onclick: () => hide(box) }, "Ακύρωση")));
  }
  function renderBackup(d) {
    const box = document.getElementById("backupBox");
    if (editing(box)) return;
    const H = d.backup.host, C = d.backup.cloud;
    const mark = v => v === "ok" ? "✓" : v === "fail" ? "✗ απέτυχε" : "δεν έχει ρυθμιστεί";
    const hostLine = !H
      ? el("div", { class: "an-line muted" }, "Στο μηχάνημα: δεν έχει καταγραφεί νυχτερινό αντίγραφο (το ρυθμίζει το ./setup.sh). USB: ", el("code", {}, "./setup.sh usb"), " στο μηχάνημα.")
      : el("div", { class: `an-line ${H.old || H.local === "fail" || H.usb === "fail" ? "bad" : ""}` },
          `Στο μηχάνημα: ${dmyhm(H.when)} ${mark(H.local)} · USB ${mark(H.usb)}`,
          H.usb === "-" ? el("span", { class: "small" }, " (για USB: ", el("code", {}, "./setup.sh usb"), " στο μηχάνημα)") : null,
          H.old ? el("div", { class: "small" }, "Είναι παλιό: ελέγξτε ότι το μηχάνημα είναι ανοιχτό και ότι τρέχει το backup.sh κάθε βράδυ.") : null);
    const cloudPart = !d.backup.cloud_available
      ? el("div", { class: "an-line muted" }, "Cloud: χρειάζεται νεότερο image της Karta (docker compose pull).")
      : C
        ? el("div", {},
            el("div", { class: `an-line ${C.state === "fail" || C.old ? "bad" : C.state === "ok" ? "" : "muted"}` },
              `Cloud (${C.provider}, κρυπτογραφημένο): ` + (C.when ? `${dmyhm(C.when)} ${C.state === "ok" ? "✓" : "✗ απέτυχε"}` : "αναμονή για το πρώτο ανέβασμα…"),
              C.state === "fail" && C.error ? el("div", { class: "small" }, C.error) : null),
            el("div", { class: "backup-row" },
              el("button", { class: "btn ghost", type: "button", onclick: act(async () => {
                await api("/admin/api/cloud/run", {}); toast("Το ανέβασμα ξεκίνησε· το αποτέλεσμα φαίνεται εδώ σε λίγο.");
                setTimeout(load, 15000); setTimeout(load, 45000);
              }) }, "Ανέβασμα τώρα"),
              el("button", { class: "link", type: "button", onclick: act(async () => {
                showCloudPassword((await api("/admin/api/cloud/password", {})).password, true);
              }) }, "Εμφάνιση κωδικού κρυπτογράφησης"),
              el("button", { class: "link danger", type: "button", onclick: act(async () => {
                if (!confirm("Να σταματήσουν τα ανεβάσματα στο cloud; Όσα έχουν ήδη ανέβει μένουν εκεί.")) return;
                await api("/admin/api/cloud/disconnect", {});
              }) }, "Αποσύνδεση cloud")))
        : el("div", {},
            el("div", { class: "an-line warn" }, "Cloud: δεν έχει ρυθμιστεί. Κάθε βράδυ η Karta ανεβάζει ένα κρυπτογραφημένο αντίγραφο σε Google Drive, Dropbox ή Backblaze B2 (σε VPS είναι ο μόνος τρόπος για αντίγραφο εκτός μηχανήματος)."),
            cloudForm(d.backup));
    const thisYear = Number(todayAthens().slice(0, 4));
    const year = el("input", { type: "number", min: "2020", max: String(thisYear), step: "1", value: String(thisYear), "aria-label": "Έτος" });
    const archive = el("a", { class: "btn ghost", href: `/admin/api/punches.xlsx?year=${thisYear}` }, "Αρχείο χτυπημάτων (Excel)");
    year.addEventListener("input", () => { archive.href = `/admin/api/punches.xlsx?year=${year.value}`; });
    const file = el("input", { type: "file", accept: ".db,application/vnd.sqlite3,application/octet-stream", class: "visually-hidden", id: "restoreFile" });
    file.addEventListener("change", act(async () => { await restoreFromFile(file.files[0]); file.value = ""; }));
    box.replaceChildren(
      el("p", { class: "small" }, "Τα χτυπήματα της κάρτας εργασίας πρέπει να φυλάσσονται για τουλάχιστον 5 χρόνια (ρωτήστε τον λογιστή σας). " +
        "Η Karta δεν σβήνει ποτέ πραγματικό χτύπημα, και κάθε αντίγραφο έχει όλο το ιστορικό. Ο κίνδυνος είναι να χαλάσει το μηχάνημα: γι' αυτό χρειάζεται αντίγραφο και εκτός του (cloud ή USB)."),
      hostLine, cloudPart,
      el("h3", {}, "Λήψη"),
      el("div", { class: "backup-row" },
        el("a", { class: "btn ghost", href: "/admin/api/backup.db" }, "Λήψη αντιγράφου τώρα"),
        el("span", { class: "small" }, "Όλη η βάση σε ένα αρχείο, για να το φυλάξετε όπου θέλετε (περιέχει στοιχεία του προσωπικού).")),
      el("div", { class: "backup-row" },
        el("label", {}, "Έτος ", year), archive,
        el("span", { class: "small" }, "Όλα τα χτυπήματα του έτους, με ώρα και αριθμό πρωτοκόλλου ΕΡΓΑΝΗ. Ανοίγει χωρίς την Karta (π.χ. για έλεγχο).")),
      el("h3", {}, "Επαναφορά"),
      el("div", { class: "backup-row" },
        el("label", { class: "btn ghost", for: "restoreFile" }, "Από αρχείο…"), file,
        C ? el("button", { class: "btn ghost", type: "button", onclick: act(async () => { await restoreFromCloudList(); }) }, "Από το cloud…") : null,
        el("span", { class: "small" }, "Πρώτα βλέπετε τι έχει το αντίγραφο· τίποτα δεν αλλάζει πριν πατήσετε «Επαναφορά τώρα».")),
      el("a", { class: "link", href: "https://github.com/osergios/karta/wiki/Backups", target: "_blank", rel: "noopener" }, "Οδηγίες για αντίγραφα και επαναφορά"));
    const panel = document.getElementById("restorePanel");
    if (d.backup.restore_pending && panel.hidden) api("/admin/api/restore/pending").then(showRestore).catch(() => {});
  }

  // ---------- version and «Ενημέρωση τώρα» (update.sh on the host does the update) ----------
  function renderUpdate(d) {
    const U = d.update, box = document.getElementById("updateBox");
    const busy = U.requested || U.running;
    if (busy && !renderUpdate.timer) {                 // follow it: the page reloads once the new version answers
      const from = U.version;
      renderUpdate.timer = setInterval(async () => {
        try {
          const r = await fetch("/admin/api/overview", { credentials: "same-origin" });
          if (!r.ok) return;                             // restarting
          const u = (await r.json()).update;
          if (u.version !== from || (!u.requested && !u.running)) { clearInterval(renderUpdate.timer); location.reload(); }
        } catch { /* restarting */ }
      }, 5000);
    }
    const res = U.result;
    const resLine = res && res.at
      ? el("div", { class: `an-line ${res.state === "ok" ? "" : "bad"}` },
          `Τελευταία ενημέρωση: ${dmyhm(new Date(res.at + "Z").toLocaleString("sv-SE", { timeZone: "Europe/Athens" }))} ` +
          (res.state === "ok" ? `✓ ενημερώθηκε σε ${(res.version || "").replace(/^v/, "") || "νέα έκδοση"}`
            : `✗ απέτυχε — επέστρεψε στην ${(res.version || "").replace(/^v/, "") || "προηγούμενη έκδοση"} (δείτε το backups/update.log στο μηχάνημα).`))
      : null;
    const notes = U.latest_url ? el("a", { class: "link", href: U.latest_url, target: "_blank", rel: "noopener" }, "Τι αλλάζει") : null;
    let main;
    if (busy) main = el("div", { class: "an-line warn" }, "Η ενημέρωση γίνεται τώρα (πρώτα αντίγραφο ασφαλείας, μετά η νέα έκδοση). Η Karta θα είναι εκτός για περίπου ένα λεπτό· η σελίδα θα ξαναφορτώσει μόνη της.");
    else if (U.available) main = el("div", { class: "an-line warn" },
      `Υπάρχει νέα έκδοση: ${U.latest}. `, notes,
      U.updater
        ? el("div", { class: "backup-row" }, el("button", { class: "btn", type: "button", onclick: act(async () => {
            if (!confirm(`Ενημέρωση στην έκδοση ${U.latest}; Η Karta θα είναι εκτός για περίπου ένα λεπτό (οι οθόνες του καταστήματος περιμένουν και συνεχίζουν). Πρώτα γίνεται αντίγραφο ασφαλείας.`)) return;
            await api("/admin/api/update", {}); toast("Η ενημέρωση θα ξεκινήσει μέσα σε δύο λεπτά");
          }) }, "Ενημέρωση τώρα"))
        : el("div", { class: "small" }, "Ενημερώστε μία φορά από το μηχάνημα με ", el("code", {}, "cd ~/karta && ./setup.sh update"),
            ": από εκεί και πέρα, εδώ θα εμφανίζεται κουμπί «Ενημέρωση τώρα»."));
    else main = el("div", { class: "an-line muted" }, U.latest ? "Έχετε την τελευταία έκδοση ✓ " : "Ο έλεγχος για νέα έκδοση γίνεται κάθε λίγες ώρες. ",
      el("button", { class: "link", type: "button", onclick: act(async () => {
        const u = await api("/admin/api/update/check", {});
        toast(u.available ? `Υπάρχει νέα έκδοση: ${u.latest}` : u.latest ? "Έχετε την τελευταία έκδοση" : "Το GitHub δεν απάντησε· δοκιμάστε σε λίγο", !u.latest);
      }) }, "Έλεγχος τώρα"));
    box.replaceChildren(el("p", {}, `Έκδοση: ${U.version}`), main, ...(resLine ? [resLine] : []));
  }

  // ---------- reload the shop screen from here (it usually runs unattended, as an installed app) ----------
  function renderKioskReload(d) {
    const R = d.kiosk_reload || {};
    const when = R.at ? `${R.at.slice(8, 10)}/${R.at.slice(5, 7)} ${R.at.slice(11, 16)}` : null;
    document.getElementById("kioskReload").replaceChildren(el("div", { class: "an-line send-row" },
      el("span", {}, "Ανανέωση οθόνης καταστήματος: ξαναφορτώνει την οθόνη στη συσκευή του καταστήματος με την τελευταία έκδοση, χωρίς να την κλείσει κανείς. Γίνεται μέσα σε 30″· αν εκείνη τη στιγμή κάποιος χτυπά κάρτα, περιμένει να τελειώσει.",
        when ? el("div", { class: "small" }, R.done ? `Τελευταία: ${when} — ✓ η οθόνη ανανεώθηκε.` : `Ζητήθηκε ${when} — αναμονή για την οθόνη…`) : ""),
      el("button", { class: "btn", onclick: act(async () => {
        await api("/admin/api/kiosk/reload", {}); toast("Η οθόνη του καταστήματος θα ανανεωθεί μέσα σε 30″");
        setTimeout(load, 40000); setTimeout(load, 70000);
      }) }, "Ανανέωση οθόνης")));
  }

  function renderRemState(d) {
    const on = !!d.settings.kiosk_reminders;
    document.getElementById("remState").replaceChildren(el("div", { class: `an-line ${on ? "ok" : "muted"} send-row` },
      el("span", {}, on
        ? `Υπενθυμίσεις στο κατάστημα: ενεργές — όποιος δεν έχει χτυπήσει προσέλευση/αποχώρηση στην ώρα του βλέπει και ακούει υπενθύμιση κάθε 30″. Μετά από ${d.settings.grace_minutes}′ ειδοποίηση στο κινητό σου${d.retro ? " (στη λήξη της ημέρας μετά από 10′, απολογιστικό σύστημα)" : ""}.`
        : "Υπενθυμίσεις στο κατάστημα: απενεργοποιημένες (οι ειδοποιήσεις στο κινητό σου συνεχίζουν)."),
      el("button", { class: on ? "btn ghost" : "btn", onclick: act(async () => {
        await api("/admin/api/settings", { values: { kiosk_reminders: on ? 0 : 1 } });
        toast(on ? "Οι υπενθυμίσεις στο κατάστημα απενεργοποιήθηκαν" : "Οι υπενθυμίσεις στο κατάστημα ενεργοποιήθηκαν");
      }) }, on ? "Απενεργοποίηση" : "Ενεργοποίηση")),
      d.closed_today ? el("div", { class: "an-line muted" }, `Σήμερα: ${d.closed_today} — καμία υπενθύμιση ή ειδοποίηση, και η οθόνη δεν δέχεται προσέλευση (εκτός αν πέρασες ωράριο με «Υπερωρία / αλλαγή ημέρας…»).`) : "");
  }

  // ---------- onboarding period («Περίοδος προσαρμογής»): real use of the card, nothing sent until a date ----------
  const dayLong = new Intl.DateTimeFormat("el-GR", { weekday: "long", day: "numeric", month: "long", year: "numeric", timeZone: "Europe/Athens" });
  const fmtDayLong = iso => { const t = dayLong.format(new Date(iso + "T12:00:00Z")); return (t.startsWith("Σάββατο") ? "το " : "την ") + t; };
  const isoPlus = (iso, n) => { const x = new Date(iso + "T12:00:00Z"); x.setUTCDate(x.getUTCDate() + n); return x.toISOString().slice(0, 10); };
  function renderOnboarding(d) {
    const box = document.getElementById("onboardState");
    if (!box || editing(box)) return;
    const ob = d.onboarding && d.onboarding.active ? d.onboarding : null;
    const kids = [];
    const P = d.onboarding_progress;
    if (P && P.length) {
      const pct = (a, b) => b ? `${Math.round(100 * a / b)}%` : "—";
      kids.push(el("h3", { class: "onb-h" }, ob ? "Πώς τα πάνε" : "Πώς τα πήγαν στην περίοδο προσαρμογής"),
        el("p", { class: "small" }, "Από την αρχή της περιόδου έως χθες. «Σωστές ημέρες»: προσέλευση και αποχώρηση χτυπήθηκαν από τον/την ίδιο/α, " +
          "χωρίς διόρθωση από εσένα. Οι διορθώσεις (ξεχασμένα χτυπήματα) και οι ημέρες χωρίς κινήσεις είναι αυτά που θα μετρούσαν στο ΕΡΓΑΝΗ."),
        el("div", { class: "scroll" }, el("table", { class: "cardify onb-table" },
          head("Εργαζόμενος", "Χτυπήματα", "Σωστές ημέρες", "Διορθώσεις από εσένα", "Ημέρες χωρίς κινήσεις"),
          ...P.map(p => el("tr", { class: p.fixed || p.missing_days ? "onb-warn" : "" },
            el("td", { "data-label": "Εργαζόμενος" }, p.name),
            el("td", { "data-label": "Χτυπήματα" }, `${p.punches}${p.punches ? ` (QR ${pct(p.qr, p.punches)})` : ""}`),
            el("td", { "data-label": "Σωστές ημέρες" }, p.days ? `${p.good_days} / ${p.days} (${pct(p.good_days, p.days)})` : "—"),
            el("td", { "data-label": "Διορθώσεις" }, String(p.fixed)),
            el("td", { "data-label": "Χωρίς κινήσεις" }, String(p.missing_days)))))));
    }
    box.replaceChildren(...kids);
  }

  // One line on «Σήμερα»: the mode chosen in «Ρυθμίσεις» (same names) and what it means for Ergani.
  function renderSendState(d) {
    const box = document.getElementById("sendState");
    const ob = d.onboarding && d.onboarding.active ? d.onboarding : null;
    const where = d.mode === "trial" ? "στο δοκιμαστικό ΕΡΓΑΝΗ" : "στο ΕΡΓΑΝΗ";
    const [name, text] = d.mode === "dry_run" ? ["Δοκιμαστική", "τίποτα δεν στέλνεται στο ΕΡΓΑΝΗ"]
      : ob ? ["Περίοδος προσαρμογής", `τίποτα δεν στέλνεται ${where}· η αποστολή ξεκινά ${fmtDayLong(ob.until)}`]
      : d.mode === "trial" ? ["Δοκιμαστικό ΕΡΓΑΝΗ", "οι κινήσεις στέλνονται στο δοκιμαστικό ΕΡΓΑΝΗ, χωρίς ισχύ"]
      : ["Κανονική λειτουργία", "οι κινήσεις στέλνονται στο ΕΡΓΑΝΗ"];
    const extra = (d.held ? ` · σε αναμονή/επανάληψη: ${d.held}` : "") + (d.uncertain ? ` · προς έλεγχο: ${d.uncertain} (δες «Κινήσεις»)` : "");
    const cls = d.uncertain || d.mode === "dry_run" || d.mode === "trial" ? "warn" : "ok";
    box.replaceChildren(el("div", { class: `an-line ${cls} send-row` },
      el("span", {}, "Λειτουργία: ", el("strong", {}, name), ` · ${text}${extra}.`)));
  }

  // Runs an action, then refreshes. One tap = one action: while it runs, further taps are ignored and the button is
  // disabled (a double/triple tap on a touch screen used to send the request two or three times).
  const act = fn => {
    let running = false;
    return async (ev, ...rest) => {
      if (running) return;
      running = true;
      const src = ev && ev.target;
      const btn = !ev ? null : ev.currentTarget instanceof HTMLButtonElement ? ev.currentTarget
        : ev.type === "submit" ? ev.currentTarget.querySelector("button:not([type=button])") : null;
      if (btn) btn.disabled = true;
      try {
        await fn(ev, ...rest);
        // what was typed in this section is saved now: the refresh may redraw it
        src?.closest?.("section")?.querySelectorAll("[data-dirty]").forEach(x => { delete x.dataset.dirty; });
        await load();
      } catch (e) { toast(e.message, true); }
      // a short cool-down: the 2nd/3rd tap of a burst lands after a fast request has already finished
      finally { setTimeout(() => { running = false; if (btn) btn.disabled = false; }, 600); }
    };
  };
  const head = (...cols) => el("tr", {}, ...cols.map(c => el("th", {}, c)));
  const fmt = iso => iso ? iso.replace("T", " ").slice(0, 16) : "-";
  const athens = new Intl.DateTimeFormat("el-GR", { dateStyle: "short", timeStyle: "short", timeZone: "Europe/Athens" });
  const fmtUtc = iso => iso ? athens.format(new Date(iso + "Z")) : "-";

  const DAYS = ["Δευ", "Τρι", "Τετ", "Πεμ", "Παρ", "Σαβ", "Κυρ"];
  const LEAVE_KINDS = { regular: "Κανονική άδεια", sick: "Άδεια ασθενείας", special: "Άδεια ειδικού σκοπού" };
  const LEVEL = { info: "Ενημέρωση", warning: "Προσοχή", urgent: "Επείγον" };
  const LIMITS = [
    ["grace_minutes", "Ευελιξία προσέλευσης / αποχώρησης (λεπτά)"],
    ["early_minutes", "Προσέλευση πριν το ωράριο (λεπτά)"],
    ["ot_deadline_minutes", "Προθεσμία δήλωσης υπερωρίας πριν τη λήξη (λεπτά)"],
    ["ot_notice_minutes", "Υπενθύμιση προθεσμίας υπερωρίας (λεπτά πριν)"],
    ["escalate_minutes", "Επείγον μετά από (λεπτά)"],
    ["daily_max_hours", "Όριο ημέρας, μετά υπερωρία (ώρες)"],
    ["weekly_max_hours", "Συμβατική εβδομάδα, μετά υπερεργασία (ώρες)"],
    ["weekly_legal_hours", "Νόμιμη εβδομάδα, μετά υπερωρία (ώρες)"],
    ["min_rest_hours", "Ελάχιστη ανάπαυση (ώρες)"],
  ];
  let editorsFor = null;   // active employee ids the editors were drawn for (and the declaration system)
  const editorsKey = d => d.employees.filter(e => e.active).map(e => e.id).join(",") + (d.retro ? "|retro" : "");
  let RETRO = false;       // the business declares changes and overtime afterwards (απολογιστικό σύστημα)
  const OT_LIMITS = ["ot_deadline_minutes", "ot_notice_minutes"];   // only with προαναγγελία (the retrospective system has no deadline)

  // ---------- schedule analysis (mirrors the server rules; explains what the numbers mean) ----------
  const DAY_FULL = ["Δευτέρα", "Τρίτη", "Τετάρτη", "Πέμπτη", "Παρασκευή", "Σάββατο", "Κυριακή"];
  // "10:00-18:00", "10:00-18:30/30", split shift "10:00-14:00+17:00-21:00/20"
  const SEG_RE = /^\s*(\d{1,2}):(\d{2})\s*[-–]\s*(\d{1,2}):(\d{2})\s*$/;
  const BRK_RE = /\/\s*(\+?)\s*(\d{1,3})\s*[′']?\s*$/;   // "/30" inside the hours, "/+30" «εκτός ωραρίου»
  function parseSpan(t) {
    if (!t || !t.trim()) return null;
    let body = t.trim(), b = 0, bo = false;
    const bm = BRK_RE.exec(body);
    if (bm) { bo = bm[1] === "+"; b = +bm[2]; body = body.slice(0, bm.index); }
    const parts = body.trim().split(/\s*[+,]\s*/);
    if (!parts.length || parts.length > 3) return { error: true };
    const segs = []; let prev = -1, g = 0;
    for (const p of parts) {
      const m = SEG_RE.exec(p);
      if (!m) return { error: true };
      const [h1, m1, h2, m2] = [+m[1], +m[2], +m[3], +m[4]];
      const s0 = h1 * 60 + m1, e0 = h2 * 60 + m2;
      if (h1 > 23 || h2 > 23 || m1 > 59 || m2 > 59 || e0 <= s0 || s0 <= prev) return { error: true };
      segs.push([s0, e0]); prev = e0; g += e0 - s0;
    }
    if (b > 120 || (b >= g && !bo)) return { error: true };
    const hhmm = x => `${String(Math.floor(x / 60)).padStart(2, "0")}:${String(x % 60).padStart(2, "0")}`;
    return { s: segs[0][0], e: segs[segs.length - 1][1], g, b, bo: bo && b > 0, segs,
             body: segs.map(([a, z]) => `${hhmm(a)}-${hhmm(z)}`).join("+") };
  }
  // break «εκτός ωραρίου» (/+30): outside the declared hours, so they are all paid; inside (/30): deducted after 4h
  const netMin = sp => { const g = sp.g; return sp.bo ? g : g - Math.min(sp.b, Math.max(0, g - 240)); };
  const H = m => { m = Math.round(m); const h = Math.floor(m / 60), r = m % 60; return r ? `${h}ω ${String(r).padStart(2, "0")}λ` : `${h}ω`; };

  function currentLimits(fallback) {
    const out = { ...fallback };
    document.querySelectorAll("#limits input").forEach(i => { if (i.value !== "") out[i.name] = Number(i.value); });
    return out;
  }

  // Returns {days:[{i, cls, text}], lines:[{cls, text}]} for one weekly schedule.
  function analyse(values, L, F) {
    const spans = values.map(parseSpan);
    const work = spans.map((sp, i) => ({ sp, i })).filter(x => x.sp && !x.sp.error);
    const sixDay = work.length >= 6;
    const normalDay = sixDay ? 400 : 480;                  // 6h40 on a 6-day week, 8h on a 5-day week
    const legalDay = L.daily_max_hours * 60;
    const days = [], lines = [];
    let total = 0, gross = 0, weekOT = 0;
    spans.forEach((sp, i) => {
      if (!sp) return;
      if (sp.error) { days.push({ i, cls: "bad", text: `${DAYS[i]}: δεν καταλαβαίνω «${values[i]}». Γράψε 10:00-18:00, 10:00-18:30/30 ή σπαστό 10:00-14:00+17:00-21:00.` }); return; }
      const n = netMin(sp), g = sp.g; total += n; gross += g;
      const parts = [], notes = [];
      let cls = "ok";
      if (n <= normalDay) parts.push(`${H(n)} καθαρά — κανονική ημέρα`);
      else {
        parts.push(`${H(n)} καθαρά`);
        const over8 = Math.min(n, legalDay) - normalDay;
        if (over8 > 0) { parts.push(`${H(over8)} πάνω από το ${sixDay ? "6ω40" : "8ωρο"}`); cls = "warn"; }
        const ot = Math.max(0, n - legalDay);
        if (ot > 0) { parts.push(`${H(ot)} υπερωρία (${RETRO ? "απολογιστική δήλωση στο ΕΡΓΑΝΗ" : "δήλωση στο ΕΡΓΑΝΗ πριν ξεκινήσει"}, +40%)`); cls = "bad"; weekOT += ot; }
      }
      if (sp.b && F && F.break_within === false && !sp.bo) { notes.push(`στο ΕΡΓΑΝΗ το διάλειμμα είναι ΕΚΤΟΣ ωραρίου: γράψε /+${sp.b} (όχι /${sp.b})`); cls = "bad"; }
      else if (sp.bo && F && F.break_within === true) { notes.push(`στο ΕΡΓΑΝΗ το διάλειμμα είναι ΕΝΤΟΣ ωραρίου: γράψε /${sp.b} (όχι /+${sp.b})`); cls = "bad"; }
      if (g > 240 && sp.b < 15 && F && F.break_within === true && F.break_minutes >= 15) notes.push(`διάλειμμα ${F.break_minutes}′ εντός ωραρίου κατά το ΕΡΓΑΝΗ — μετρά ως εργασία`);
      else if (g > 240 && sp.b < 15) { notes.push("χρειάζεται διάλειμμα 15–30′: γράψε π.χ. /30 στο τέλος"); cls = "bad"; }
      else if (sp.b > 30) { notes.push("διάλειμμα πάνω από 30′: αυτό είναι διακεκομμένο ωράριο, όχι απλό διάλειμμα"); if (cls === "ok") cls = "warn"; }
      if (sp.segs.length > 1) {
        const gaps = sp.segs.slice(1).map((x, k) => x[0] - sp.segs[k][1]);
        notes.push(`σπαστό ωράριο, κενό ${gaps.map(H).join(" και ")}`);
      }
      else if (sp.b && sp.bo) { const lb = sp.e + sp.b; notes.push(`διάλειμμα ${sp.b}′ εκτός ωραρίου: αποχώρηση από ${String(Math.floor(sp.e / 60)).padStart(2, "0")}:${String(sp.e % 60).padStart(2, "0")} έως ${String(Math.floor(lb / 60)).padStart(2, "0")}:${String(lb % 60).padStart(2, "0")}`); }
      else if (sp.b) notes.push(`διάλειμμα ${sp.b}′ όποτε βολεύει (εντός ωραρίου)`);
      const j = (i + 1) % 7, nx = spans[j];
      if (nx && !nx.error) {
        const rest = (24 * 60 - sp.e) + nx.s;
        if (rest < L.min_rest_hours * 60) { notes.push(`μόνο ${H(rest)} ανάπαυση μέχρι ${DAY_FULL[j]} (ελάχιστο ${L.min_rest_hours}ω)`); cls = "bad"; }
      }
      days.push({ i, cls, text: `${DAYS[i]}: ${parts.join(" · ")}${notes.length ? " — " + notes.join("; ") : ""}` });
    });
    if (!work.length) return { days, lines: [{ cls: "muted", text: "Χωρίς ωράριο: κάθε προσέλευση θα θεωρείται αδήλωτη εργασία." }] };
    const wk = `${H(total)} καθαρά σε ${work.length} ${work.length === 1 ? "ημέρα" : "ημέρες"}`;
    if (total <= L.weekly_max_hours * 60) lines.push({ cls: "ok", text: `Εβδομάδα: ${wk} — εντός ${L.weekly_max_hours}ώρου.` });
    else if (total <= L.weekly_legal_hours * 60) lines.push({ cls: "warn", text: `Εβδομάδα: ${wk} — ${H(total - L.weekly_max_hours * 60)} υπερεργασία (+20%) πάνω από τις ${L.weekly_max_hours} ώρες.` });
    else lines.push({ cls: "bad", text: `Εβδομάδα: ${wk} — πάνω από το νόμιμο όριο των ${L.weekly_legal_hours} ωρών: ${H(total - L.weekly_legal_hours * 60)} υπερωρία κάθε εβδομάδα.` });
    if (work.length === 7) lines.push({ cls: "bad", text: "Καμία ημέρα ρεπό: χρειάζεται εβδομαδιαία ανάπαυση." });
    if (F) {
      if (F.weekly_hours != null) {
        // break "εκτός ωραρίου": Ergani's weekly hours are the declared time ranges, the break is not deducted from them
        const outside = F.break_within === false && total !== gross;
        const cmp = outside ? gross : total;
        const diff = cmp / 60 - F.weekly_hours;
        const how = outside ? ` (${H(gross)} ωραρίου χωρίς να αφαιρεθεί το διάλειμμα, όπως μετρά το ΕΡΓΑΝΗ)` : "";
        lines.push(Math.abs(diff) <= 0.25
          ? { cls: "ok", text: `Ταιριάζει με τις ${F.weekly_hours} ώρες/εβδομάδα που είναι δηλωμένες στο ΕΡΓΑΝΗ${how} ✓` }
          : { cls: "warn", text: `Στο ΕΡΓΑΝΗ είναι δηλωμένες ${F.weekly_hours} ώρες/εβδομάδα, εδώ ${H(cmp)}${how} (${diff > 0 ? "+" : "−"}${H(Math.abs(diff) * 60)}). Πρέπει να ταιριάζουν.` });
      }
      if (F.week_days && F.week_days !== work.length)
        lines.push({ cls: "warn", text: `Στο ΕΡΓΑΝΗ είναι ${F.week_days}ήμερη απασχόληση, εδώ ${work.length} ημέρες.` });
      if (F.full_time === false)
        lines.push({ cls: "warn", text: "Μερική απασχόληση κατά το ΕΡΓΑΝΗ: κάθε ώρα πάνω από τις συμφωνημένες είναι πρόσθετη εργασία με προσαύξηση — ρώτα τον λογιστή." });
      if (F.arrangement === true)
        lines.push({ cls: "ok", text: "Στο ΕΡΓΑΝΗ υπάρχει διευθέτηση χρόνου εργασίας: έως 10 ώρες/ημέρα χωρίς υπερωρία, αν τη συμψηφίζετε. Μπορείς να ορίσεις «Όριο ημέρας» 10 στα Όρια." });
      else if (F.arrangement === false && weekOT > 0)
        lines.push({ cls: "warn", text: "Στο ΕΡΓΑΝΗ δεν υπάρχει δηλωμένη διευθέτηση χρόνου εργασίας, άρα οι ώρες πάνω από το όριο ημέρας είναι υπερωρία." });
    }
    if (sixDay && (L.daily_max_hours > 8 || L.weekly_legal_hours > 48))
      lines.push({ cls: "warn", text: "Εξαήμερο: τα νόμιμα όρια είναι 8ω/ημέρα και 48ω/εβδομάδα — προσάρμοσε τα Όρια παρακάτω." });
    if (weekOT > 0) {
      const year = weekOT * 46 / 60;
      lines.push({ cls: year > 150 ? "bad" : "warn",
        text: `Υπερωρία ${H(weekOT)}/εβδομάδα ≈ ${Math.round(year)} ώρες τον χρόνο (όριο 150). ` +
              (year > 150 ? "Ξεπερνά το ετήσιο όριο — χρειάζεται αλλαγή ωραρίου ή διευθέτηση χρόνου εργασίας (ρώτα τον λογιστή)."
                          : RETRO ? "Δηλώνεται απολογιστικά στο ΕΡΓΑΝΗ, έως το τέλος του επόμενου μήνα."
                                  : "Κάθε φορά πρέπει να δηλώνεται στο ΕΡΓΑΝΗ πριν γίνει.") });
    }
    return { days, lines };
  }

  function renderAnalysis(box, values, L, F) {
    const { days, lines } = analyse(values, L, F);
    box.replaceChildren(
      ...lines.map(l => el("div", { class: "an-line " + l.cls }, l.text)),
      ...(days.length ? [el("ul", { class: "an-days" }, ...days.map(x => el("li", { class: x.cls }, x.text)))] : []));
  }

  function salonInsight(box, values, L) {
    const spans = values.map(parseSpan);
    const open = spans.map((sp, i) => ({ sp, i })).filter(x => x.sp && !x.sp.error);
    if (!open.length) { box.replaceChildren(el("div", { class: "an-line muted" }, "Συμπλήρωσε τις ώρες λειτουργίας για να δεις τι σημαίνουν για το προσωπικό.")); return; }
    const total = open.reduce((a, x) => a + x.sp.g, 0);
    const oneFull = analyse(values.map(v => { const sp = parseSpan(v); return sp && !sp.error && sp.g > 240 ? `${v.trim()}/30` : v; }), L);
    const longDays = open.filter(x => netMin({ ...x.sp, b: 30 }) > L.daily_max_hours * 60).map(x => DAY_FULL[x.i]);
    const kids = [el("div", { class: "an-line muted" },
      `Το κατάστημα είναι ανοιχτό ${H(total)} την εβδομάδα σε ${open.length} ημέρες. ` +
      `Ένας εργαζόμενος πλήρους απασχόλησης καλύπτει έως ${L.weekly_max_hours} ώρες.`)];
    oneFull.lines.forEach((l, k) => kids.push(el("div", { class: "an-line " + l.cls },
      k === 0 ? `Αν ένα άτομο δούλευε όλο το ωράριο καταστήματος (με διάλειμμα 30′): ${l.text.replace(/^Εβδομάδα: /, "")}` : l.text)));
    if (longDays.length) kids.push(el("div", { class: "an-line warn" },
      `${longDays.join(", ")}: η ημέρα είναι μεγαλύτερη από το όριο των ${L.daily_max_hours} ωρών — ` +
      "χρειάζεται βάρδια μέχρι το όριο και άλλο άτομο για το υπόλοιπο, αλλιώς υπερωρία."));
    box.replaceChildren(...kids);
  }

  const LIMIT_HELP = {
    grace_minutes: v => `Αν κάποιος δεν έχει χτυπήσει προσέλευση ${v}′ μετά την έναρξη του ωραρίου του, ή είναι ακόμα μέσα ${RETRO ? "10′ (απολογιστικό σύστημα)" : `${v}′`} μετά τη λήξη, σου έρχεται ειδοποίηση στο κινητό. Στο κατάστημα η υπενθύμιση ξεκινά από την ακριβή ώρα.`,
    early_minutes: v => +v === 0
      ? "Κανείς δεν μπορεί να χτυπήσει προσέλευση πριν την ώρα έναρξης του ωραρίου του. Αν προσπαθήσει, η οθόνη το αρνείται και σου έρχεται ειδοποίηση."
      : `Επιτρέπεται προσέλευση έως ${v}′ πριν την έναρξη του ωραρίου. Νωρίτερα η οθόνη το αρνείται και σου έρχεται ειδοποίηση. (Το ΕΡΓΑΝΗ δεν δίνει ανοχή: για να είσαι 100% καλυμμένος άφησέ το 0.)`,
    ot_deadline_minutes: v => `Υπερωρία ή αργότερη αποχώρηση δηλώνεται στο ΕΡΓΑΝΗ τουλάχιστον ${v}′ πριν τη λήξη του ωραρίου. Η λίστα εργαζομένων δείχνει κάθε μέρα την προθεσμία («υπερωρία δηλώνεται έως …»), και η «Υπερωρία / αλλαγή ημέρας…» σε προειδοποιεί αν πέρασε. Μετά τη λήξη χωρίς δηλωμένη υπερωρία: αποχώρηση αμέσως, με την πραγματική ώρα.`,
    ot_notice_minutes: v => +v === 0
      ? "Καμία υπενθύμιση στο κινητό για την προθεσμία της υπερωρίας (η λίστα εργαζομένων τη δείχνει πάντα)."
      : `Ειδοποίηση στο κινητό ${v}′ πριν την προθεσμία, με όσους είναι μέσα και λήγουν εκείνη την ώρα: «αν χρειαστεί να μείνει κάποιος, δήλωσε υπερωρία έως …». Μία φορά ανά ώρα λήξης.`,
    escalate_minutes: v => `Αν συνεχίζει ${v}′ αργότερα: επείγον, με ήχο κάθε 2 λεπτά μέχρι να χτυπήσει αποχώρηση.`,
    daily_max_hours: v => `Μετά από ${v} ώρες καθαρής εργασίας την ημέρα, κάθε λεπτό είναι υπερωρία και ${RETRO ? "δηλώνεται απολογιστικά στο ΕΡΓΑΝΗ έως το τέλος του επόμενου μήνα" : "πρέπει να έχει δηλωθεί στο ΕΡΓΑΝΗ πριν ξεκινήσει"}. Πενθήμερο: 9 · εξαήμερο: 8.`,
    weekly_max_hours: v => `Έως ${v} ώρες την εβδομάδα είναι κανονική εργασία (συμβατικό 40ωρο). Πάνω από αυτό: υπερεργασία, +20%.`,
    weekly_legal_hours: v => `Πάνω από ${v} ώρες την εβδομάδα: υπερωρία, +40%, μόνο δηλωμένη. Πενθήμερο: 45 · εξαήμερο: 48. Μέσος όρος 4μήνου έως 48.`,
    min_rest_hours: v => `Τουλάχιστον ${v} συνεχόμενες ώρες από την αποχώρηση ως την επόμενη προσέλευση. Ελέγχεται στο ωράριο και σε κάθε προσέλευση.`,
  };

  function erganiFacts(F) {
    return [
      F.weekly_hours != null && `${F.weekly_hours} ώρες/εβδ.`,
      F.week_days && `${F.week_days}ήμερο`,
      F.full_time === true ? "πλήρης" : F.full_time === false ? "μερική" : null,
      F.break_minutes != null && `διάλειμμα ${F.break_minutes}′${F.break_within === true ? " εντός ωραρίου" : F.break_within === false ? " εκτός ωραρίου" : ""}`,
      F.arrangement === true ? "με διευθέτηση" : F.arrangement === false ? "χωρίς διευθέτηση" : null,
      F.flex != null ? `ευέλικτη προσέλευση ${F.flex}′` : F.flex_text ? `ευέλικτο ωράριο: ${F.flex_text}` : null,
    ].filter(Boolean).join(" · ") || "—";
  }

  function renderEditors(d) {
    // rendered once / when the staff list changes, so the 30s refresh never wipes what you are typing
    const refreshers = [];
    const L = () => currentLimits(d.settings);
    // break stepper: rewrites the "/NN" part of a day field in 15′ steps
    const BREAK_STEP = 15, BREAK_MAX = 120;
    function setBreak(inp, minutes) {
      const sp = parseSpan(inp.value);
      if (!sp || sp.error) return false;
      minutes = Math.max(0, Math.min(minutes, BREAK_MAX, sp.g - BREAK_STEP));
      inp.value = minutes ? `${sp.body}/${sp.bo ? "+" : ""}${minutes}` : sp.body;
      inp.dispatchEvent(new Event("input"));
      return true;
    }
    const breakOf = inp => { const sp = parseSpan(inp.value); return sp && !sp.error ? sp.b : null; };
    function breakStepper(inp) {
      const minus = el("button", { type: "button", "aria-label": "λιγότερο διάλειμμα" }, "−");
      const plus = el("button", { type: "button", "aria-label": "περισσότερο διάλειμμα" }, "+");
      const label = el("span", {});
      const sync = () => {
        const b = breakOf(inp);
        minus.disabled = b === null || b === 0; plus.disabled = b === null || b >= BREAK_MAX;
        label.textContent = b === null ? "—" : b ? `διάλ. ${b}′` : "χωρίς διάλ.";
      };
      minus.addEventListener("click", () => { const b = breakOf(inp); if (b !== null) setBreak(inp, b - BREAK_STEP); });
      plus.addEventListener("click", () => { const b = breakOf(inp); if (b !== null) setBreak(inp, b + BREAK_STEP); });
      inp.addEventListener("input", sync); sync();
      return el("div", { class: "brk" }, minus, label, plus);
    }
    // split shifts don't fit in the field: show the parts underneath
    function segCaption(inp) {
      const cap = el("div", { class: "seg-cap" });
      const sync = () => {
        const sp = parseSpan(inp.value);
        const split = sp && !sp.error && sp.segs.length > 1;
        cap.textContent = split ? sp.body.split("+").map(x => x.replace("-", "–")).join("\n") : "";
        cap.hidden = !split; inp.title = inp.value;
        inp.closest(".day")?.classList.toggle("split", !!split);
      };
      inp.addEventListener("input", sync); setTimeout(sync);
      return cap;
    }
    const dayFields = (inputs, withBreaks) => el("div", { class: "sched-days" },
      ...inputs.map((inp, i) => el("div", { class: "day" }, el("span", {}, DAYS[i]), inp, segCaption(inp), withBreaks ? breakStepper(inp) : null)));
    const card = (cls, title, actions, inputs, box, withBreaks) => el("div", { class: "sched-card " + cls },
      el("div", { class: "sched-head" }, title, el("span", { class: "sched-actions" }, ...actions)),
      dayFields(inputs, withBreaks), box);
    // What Ergani says for one employee, with the actions it allows.
    function erganiBox(F, inputs, refresh) {
      const kids = [el("strong", {}, "ΕΡΓΑΝΗ: "), erganiFacts(F), ` (ενημ. ${fmt(F.fetched_at)})`];
      const actions = [];
      const withBreak = (v) => {
        const sp = parseSpan(v);
        return sp && !sp.error && F.break_within === false && F.break_minutes && sp.g > 240 ? `${v}/+${F.break_minutes}` : v;
      };
      if (F.proposal) {
        actions.push(el("button", { class: "link", type: "button", onclick: () => {
          inputs.forEach((inp, i) => { inp.value = F.proposal[String(i)] ? withBreak(F.proposal[String(i)]) : ""; inp.dispatchEvent(new Event("input")); });
          refresh(); toast("Συμπληρώθηκαν οι ώρες από το ΕΡΓΑΝΗ — έλεγξέ τες και πάτα Αποθήκευση");
        } }, "Συμπλήρωση ωρών από ΕΡΓΑΝΗ"));
      } else if (F.digital) {
        kids.push(el("div", { class: "sub" }, "Οι ώρες ανά ημέρα είναι στο ψηφιακό ωράριο του ΕΡΓΑΝΗ και δεν επιστρέφονται σε αυτή την ανάγνωση — συμπλήρωσέ τες ίδιες με τη δήλωση."));
      } else if (F.schedule_text) {
        kids.push(el("div", { class: "sub" }, `Ωράριο ΕΡΓΑΝΗ (δεν διαβάστηκε αυτόματα): ${F.schedule_text}`));
      }
      if (!F.proposal && F.break_within === false && F.break_minutes) {
        actions.push(el("button", { class: "link", type: "button", onclick: () => {
          let n = 0; inputs.forEach(inp => { const sp = parseSpan(inp.value);
            if (sp && !sp.error && sp.g > 240) { inp.value = `${sp.body}/+${F.break_minutes}`; inp.dispatchEvent(new Event("input")); n++; } });
          toast(n ? `Διάλειμμα ${F.break_minutes}′ σε ${n} ημέρες — πάτα Αποθήκευση` : "Συμπλήρωσε πρώτα τις ώρες");
        } }, `Διάλειμμα ${F.break_minutes}′ εκτός ωραρίου (από ΕΡΓΑΝΗ)`));
      }
      if (actions.length) kids.push(el("div", { class: "er-card-actions" }, ...actions));
      return el("div", { class: "er-ref" }, ...kids);
    }


    const salonInputs = DAYS.map((_, i) => el("input", { value: (d.salon_hours || {})[String(i)] || "", placeholder: "κλειστά", "aria-label": `Κατάστημα ${DAYS[i]}` }));
    const salonBox = el("div", { class: "analysis" });
    const salonRefresh = () => salonInsight(salonBox, salonInputs.map(x => x.value), L());
    salonInputs.forEach(x => x.addEventListener("input", salonRefresh)); refreshers.push(salonRefresh);
    const salonSave = el("button", { class: "link", onclick: act(async () => {
      const days = {}; salonInputs.forEach((x, i) => { days[String(i)] = x.value.trim(); });
      await api("/admin/api/salon-hours", { days }); toast("Το ωράριο καταστήματος αποθηκεύτηκε");
    }) }, "Αποθήκευση");

    const cards = [card("salon", el("strong", {}, "Ωράριο καταστήματος"), [salonSave], salonInputs, salonBox)];
    d.employees.filter(e => e.active).forEach(e => {
      const cur = d.schedules[String(e.id)] || {};
      const inputs = DAYS.map((_, i) => el("input", { value: cur[String(i)] || "", placeholder: "ρεπό", "data-day": String(i), "aria-label": `${e.display_name} ${DAYS[i]}` }));
      const box = el("div", { class: "analysis" });
      const ei = (d.ergani_info || {})[String(e.id)];
      const refresh = () => renderAnalysis(box, inputs.map(x => x.value), L(), ei);
      inputs.forEach(x => x.addEventListener("input", refresh)); refreshers.push(refresh);
      const save = el("button", { class: "link", onclick: act(async () => {
        const days = {}; inputs.forEach(inp => { days[inp.dataset.day] = inp.value.trim(); });
        const vf = document.getElementById("schedFrom").value || todayAthens();
        const when = vf === todayAthens() ? "από σήμερα" : `από ${dmy(vf)}/${vf.slice(0, 4)}`;
        if (!confirm(`Αποθήκευση ωραρίου για ${e.display_name} — ισχύει ${when};\n\nΟι ημέρες πριν μετρούν με το ωράριο που ίσχυε τότε.`)) return;
        await api(`/admin/api/schedules/${e.id}`, { days, valid_from: vf }); editorsFor = null; toast(`Το ωράριο για ${e.display_name} αποθηκεύτηκε (ισχύει ${when})`);
      }) }, "Αποθήκευση");
      const copy = el("button", { class: "link", onclick: () => {
        salonInputs.forEach((s0, i) => { const v = s0.value.trim(), sp = parseSpan(v); inputs[i].value = v && sp && !sp.error && sp.g > 240 ? `${v}/30` : v; });
        refresh(); toast("Αντιγράφηκε το ωράριο καταστήματος — προσάρμοσέ το και πάτα Αποθήκευση");
      } }, "Από κατάστημα");
      const all30 = el("button", { class: "link", onclick: () => {
        let n = 0;
        inputs.forEach(inp => { const sp = parseSpan(inp.value); if (sp && !sp.error && sp.g > 240 && setBreak(inp, 30)) n++; });
        toast(n ? `Διάλειμμα 30′ σε ${n} ${n === 1 ? "ημέρα" : "ημέρες"} — πάτα Αποθήκευση` : "Καμία ημέρα πάνω από 4 ώρες");
      } }, "Διάλειμμα 30′ παντού");
      const ref = ei ? erganiBox(ei, inputs, refresh) : null;
      const meta = (d.schedule_meta || {})[String(e.id)];
      const vtxt = !meta ? "" : meta.latest_from > todayAthens()
        ? ` · νέο ωράριο από ${dmy(meta.latest_from)} (μέχρι τότε ισχύει το προηγούμενο)`
        : meta.latest_from > "2000-01-01" ? ` · ισχύει από ${dmy(meta.latest_from)}/${meta.latest_from.slice(0, 4)}` : "";
      const c0 = card("", el("span", {}, el("strong", {}, e.display_name), vtxt ? el("span", { class: "small" }, vtxt) : null),
                      [all30, copy, save], inputs, box, true);
      if (ref) c0.insertBefore(ref, c0.children[1]);
      cards.push(c0);
    });
    if (!d.employees.some(e => e.active)) cards.push(el("p", { class: "small" }, "Κάνε πρώτα εισαγωγή εργαζομένων από το ΕΡΓΑΝΗ."));
    document.getElementById("scheds").replaceChildren(...cards);

    // limits, each with a live explanation of what the value means
    const form = document.getElementById("limits");
    form.replaceChildren(...LIMITS.filter(([k]) => !(RETRO && OT_LIMITS.includes(k))).map(([k, label]) => {
      const help = el("span", { class: "help" }, LIMIT_HELP[k](d.settings[k]));
      const input = el("input", { name: k, type: "number", step: "0.5", min: "0", value: String(d.settings[k]) });
      input.addEventListener("input", () => { help.textContent = LIMIT_HELP[k](input.value || "–"); refreshers.forEach(f => f()); });
      return el("label", {}, label, input, help);
    }), el("button", { class: "btn" }, "Αποθήκευση ορίων"));
    refreshers.forEach(f => f());
    editorsFor = editorsKey(d);
  }


  // ---------- employees: one card each, actions in one menu (a sheet on the phone) ----------
  function actionsMenu(items) {
    const list = items.filter(Boolean);
    while (list.length && list[0].tagName === "HR") list.shift();          // no divider at the top (inactive: no first group)
    const menu = el("details", { class: "menu" }, el("summary", { class: "btn ghost small-btn" }, "Ενέργειες ▾"),
      el("div", { class: "menu-list" }, ...list));
    menu.addEventListener("toggle", () => {
      if (!menu.open) return;
      document.querySelectorAll("details.menu[open]").forEach(m => { if (m !== menu) m.open = false; });
      menu.classList.remove("up");
      const r = menu.querySelector(".menu-list").getBoundingClientRect();
      if (innerWidth > 760 && r.bottom > innerHeight - 8 && r.top - r.height > 60) menu.classList.add("up");
    });
    menu.querySelector(".menu-list").addEventListener("click", ev => { if (ev.target.closest("button")) menu.open = false; });
    return menu;
  }
  const sep = () => el("hr", { class: "menu-sep" });
  function empActions(e, d) {
    return [
      e.inside ? el("button", { class: "link strong", onclick: () => showDepart(e) }, "Αποχώρηση…") : null,
      ...(e.open_arrivals || []).map(o => el("button", { class: "link strong", onclick: () => showDepart(e, o) },
        `Κλείσιμο ${o.movement_at.slice(8, 10)}/${o.movement_at.slice(5, 7)}…`)),
      e.active ? el("button", { class: "link", onclick: () => showDayChange(e, d) }, "Υπερωρία / αλλαγή ημέρας…") : null,
      e.active ? el("button", { class: "link", onclick: () => showLeave(e) }, "Άδεια…") : null,
      e.active && !e.inside ? el("button", { class: e.today && e.today.left && !e.today.left.reason ? "link strong" : "link", onclick: () => showEarlyLeave(e) }, "Έφυγε νωρίτερα…") : null,
      e.active && !e.inside ? el("button", { class: "link", onclick: () => showLocalShift(e, d.schedules[String(e.id)]) }, "Ξεχασμένη βάρδια…") : null,
      e.active && !e.inside && !e.early_allowed_today ? el("button", { class: "link", onclick: act(async () => {
        if (!confirm(`Νωρίτερη προσέλευση σήμερα για ${e.display_name};\n\nΚάν' το ΜΟΝΟ αφού δηλώσεις στο ΕΡΓΑΝΗ την αλλαγή ωραρίου (νωρίτερη έναρξη). Ισχύει μόνο για σήμερα.`)) return;
        await api(`/admin/api/employees/${e.id}/allow-early`, {}); toast(`${e.display_name}: επιτρέπεται νωρίτερη προσέλευση σήμερα`);
      }) }, "Νωρίτερη προσέλευση σήμερα") : null,
      e.active && !e.inside && e.today && !e.today.over ? el("button", { class: "link", onclick: act(async () => {
        await api(`/admin/api/employees/${e.id}/quiet`, { on: !e.quiet_today });
        toast(e.quiet_today ? `${e.display_name}: οι υπενθυμίσεις προσέλευσης ξαναμπήκαν` : `${e.display_name}: χωρίς υπενθύμιση προσέλευσης σήμερα`);
      }) }, e.quiet_today ? "Άρση σίγασης προσέλευσης" : "Θα αργήσει σήμερα (σίγαση)") : null,
      e.active ? el("button", { class: "link", onclick: act(async () => {
        const v = prompt(`Ευέλικτη προσέλευση για ${e.display_name}, σε λεπτά (0 = καμία, έως 120).\n\n` +
          "Βάλε ό,τι γράφει το ΕΡΓΑΝΗ στην καρτέλα του εργαζομένου («Ψηφιακή Οργάνωση Χρόνου Εργασίας» → «Ευέλικτη Προσέλευση»). " +
          "Η προσέλευση μέσα σε αυτά τα λεπτά μετά την έναρξη δεν είναι καθυστέρηση και η λήξη μετακινείται ανάλογα. Πριν την έναρξη δεν επιτρέπεται ποτέ.",
          String(e.flex_arrival || 0));
        if (v === null) return;
        const n = Number(v.trim());
        if (!Number.isInteger(n) || n < 0 || n > 120) { toast("Γράψε λεπτά από 0 έως 120", true); return; }
        await api(`/admin/api/employees/${e.id}/flex`, { minutes: n });
        toast(n ? `${e.display_name}: ευέλικτη προσέλευση ${n}′` : `${e.display_name}: χωρίς ευέλικτη προσέλευση`);
      }) }, "Ευέλικτη προσέλευση…") : null,
      e.active ? el("button", { class: "link", onclick: act(async () => {
        if (e.qr && e.qr_viewable) return showQrCard(await api(`/admin/api/employees/${e.id}/qr`), e);
        if (e.qr && !confirm(`Η κάρτα QR του/της ${e.display_name} δεν μπορεί να ξαναεμφανιστεί. Έκδοση νέας; Η παλιά θα σταματήσει να ισχύει.`)) return;
        await showQrCard(await api(`/admin/api/employees/${e.id}/qr`, {}), e);
      }) }, e.qr ? "Κάρτα QR" : "Έκδοση QR") : null,
      sep(),
      el("button", { class: "link", onclick: act(async () => {
        if (!confirm(`Νέο PIN για ${e.display_name}; Το τωρινό PIN θα σταματήσει να ισχύει.`)) return;
        showPin(await api(`/admin/api/employees/${e.id}/pin`, {}));
      }) }, "Νέο PIN"),
      d.pin_view ? el("button", { class: "link", onclick: act(async () => {
        const r = await api(`/admin/api/employees/${e.id}/pin`);
        showPin({ name: r.name, pin: r.pin }, true);
      }) }, "Εμφάνιση PIN") : null,
      el("button", { class: "link", onclick: act(async () => {
        const pin = prompt(`Δικό σου PIN για ${e.display_name} (6 ψηφία):`);
        if (pin === null) return;
        await api(`/admin/api/employees/${e.id}/pin`, { pin: pin.replace(/\s/g, "") });
        toast(`Το PIN για ${e.display_name} ορίστηκε`);
      }) }, "Ορισμός PIN"),
      el("button", { class: "link", onclick: act(async () => {
        const name = prompt("Όνομα στο tablet (π.χ. με τόνους):", e.display_name);
        if (name === null || !name.trim() || name.trim() === e.display_name) return;
        await api(`/admin/api/employees/${e.id}/name`, { display_name: name.trim() }); editorsFor = null; toast("Το όνομα άλλαξε");
      }) }, "Μετονομασία"),
      el("button", { class: "link", onclick: act(async () => {
        await api(`/admin/api/employees/${e.id}/active`, { active: !e.active });
      }) }, e.active ? "Απενεργοποίηση" : "Ενεργοποίηση"),
      el("button", { class: "link danger", onclick: act(async () => {
        if (!confirm(`Οριστική διαγραφή του/της ${e.display_name};\n\nΓίνεται μόνο αν δεν υπάρχουν πραγματικές κινήσεις κάρτας (οι δοκιμαστικές διαγράφονται μαζί). Αλλιώς χρησιμοποίησε «Απενεργοποίηση».`)) return;
        const r = await api(`/admin/api/employees/${e.id}/delete`, {}); editorsFor = null;
        toast(`Διαγράφηκε: ${e.display_name}${r.test_movements ? ` (και ${r.test_movements} δοκιμαστικές κινήσεις)` : ""}`);
      }) }, "Διαγραφή"),
    ];
  }
  // flexible arrival today: the window while waiting, how far the day moved once they came in
  const flexNote = (t, inside) => !t || !t.flex ? "" : t.moved > 0 ? ` · ευέλικτη +${t.moved}′ (κανονικά έως ${t.declared_end})`
    : inside ? "" : ` · ευέλικτη προσέλευση έως ${t.arrive_by}`;
  function empFacts(e) {
    return [
      e.active && e.off_today ? el("div", { class: "small" }, `Σήμερα: ${e.off_today}`) : null,
      e.active && e.today ? el("div", { class: "small" }, `Σήμερα: ${e.today.label}` + (e.today.change === "overtime" ? " (δηλωμένη υπερωρία)" : e.today.change ? " (αλλαγή ημέρας)" : "") +
        flexNote(e.today, e.inside) + ` · φεύγει έως ${e.today.end}` + (e.today.over || !e.today.ot_by ? "" : e.today.ot_passed ? " · προθεσμία υπερωρίας πέρασε" : ` · υπερωρία δηλώνεται έως ${e.today.ot_by}`)) : null,
      (e.leaves || []).length ? el("div", { class: "small" }, e.leaves.map(l => `${l.label || "Άδεια"}: ${dmy(l.start_date)}–${dmy(l.end_date)}`).join(" · ")) : null,
      (e.day_changes || []).filter(c => c.day > todayAthens()).length ? el("div", { class: "small" },
        "Αλλαγές: " + e.day_changes.filter(c => c.day > todayAthens()).map(c => `${dmy(c.day)} ${c.text || "ρεπό"}`).join(", ")) : null,
      e.locked ? el("div", { class: "warn-text" }, "Κλειδωμένο PIN") : null,
      (e.open_arrivals || []).length ? el("div", { class: "warn-text" },
        `Χωρίς αποχώρηση: ${e.open_arrivals.map(o => `${dmy(o.movement_at)} ${o.movement_at.slice(11, 16)}`).join(", ")}`) : null,
      e.early_allowed_today ? el("div", { class: "small" }, "Επιτρέπεται νωρίτερη προσέλευση σήμερα") : null,
      e.active && e.quiet_today && !e.inside ? el("div", { class: "small" }, "Θα αργήσει: χωρίς υπενθύμιση προσέλευσης σήμερα") : null,
      e.active && e.flex_arrival ? el("div", { class: "small muted" }, `Ευέλικτη προσέλευση ${e.flex_arrival}′`) : null,
      e.omissions_month ? el("div", { class: e.omissions_month >= 3 ? "warn-text" : "small" },
        `Ξεχασμένα χτυπήματα μήνα: ${e.omissions_month}` + (e.omissions_month >= 3 ? " — πολλά: πάνω από 3 τον μήνα μπορεί να τραβήξουν έλεγχο" : "")) : null,
    ];
  }
  const stateOf = e => !e.active ? ["off", "Ανενεργός"] : e.inside ? ["in", "Σε βάρδια"] : e.on_leave ? ["leave", "Σε άδεια"]
    : e.off_today ? ["leave", "Κλειστά"] : ["out", "Εκτός"];
  function renderPeople(d) {
    const box = document.getElementById("emps");
    if (editing(box)) return;      // don't redraw under an open menu
    box.replaceChildren(...(d.employees.length ? d.employees.map(e => {
      const [cls, txt] = stateOf(e);
      return el("div", { class: `emp-card ${e.active ? "" : "inactive"}` },
        el("div", { class: "emp-head" }, el("strong", {}, e.display_name), el("span", { class: `pill ${cls}` }, txt)),
        el("div", { class: "small muted" }, `${e.last_name} ${e.first_name} · ΑΦΜ ${e.afm}`),
        ...empFacts(e),
        el("div", { class: "emp-actions" },
          e.inside ? el("button", { class: "btn small-btn", onclick: () => showDepart(e) }, "Αποχώρηση…") : null,
          actionsMenu(empActions(e, d))));
    }) : [el("p", { class: "small" }, "Δεν υπάρχουν εργαζόμενοι ακόμα. «Ρυθμίσεις» → ΕΡΓΑΝΗ → «Έλεγχος ΕΡΓΑΝΗ» για εισαγωγή.")]));
  }

  // ---------- «Σήμερα»: who is in, who is expected, who is off ----------
  function renderToday(d) {
    const box = document.getElementById("todayBox");
    if (editing(box)) return;
    const act_ = d.employees.filter(e => e.active);
    const inside = act_.filter(e => e.inside);
    const left = act_.filter(e => !e.inside && e.today && e.today.left);
    const expected = act_.filter(e => !e.inside && e.today && !e.today.over && !e.today.left);
    const done = act_.filter(e => !e.inside && e.today && e.today.over && !e.today.left);
    const off = act_.filter(e => !e.inside && !e.today);
    const open = act_.filter(e => (e.open_arrivals || []).some(o => o.movement_at.slice(0, 10) < todayAthens()));
    const row = (e, lines, buttons) => el("div", { class: "today-row" },
      el("div", { class: "tr-main" }, el("strong", {}, e.display_name), ...lines.filter(Boolean).map(t => el("div", { class: "small" }, t))),
      el("div", { class: "tr-actions" }, ...buttons.filter(Boolean), actionsMenu(empActions(e, d))));
    const deadline = t => !t || t.over || !t.ot_by ? "" : t.ot_passed ? `προθεσμία υπερωρίας πέρασε (${t.ot_by})` : `υπερωρία δηλώνεται έως ${t.ot_by}`;
    const kids = [];
    if (d.closed_today) kids.push(el("div", { class: "an-line muted" }, `Σήμερα: ${d.closed_today}`));
    if (open.length) kids.push(el("h3", {}, "Ξέχασαν αποχώρηση"), ...open.map(e => row(e,
      [`Χωρίς αποχώρηση: ${e.open_arrivals.map(o => `${dmy(o.movement_at)} ${o.movement_at.slice(11, 16)}`).join(", ")}`],
      e.open_arrivals.map(o => el("button", { class: "btn small-btn", onclick: () => showDepart(e, o) }, `Κλείσιμο ${o.movement_at.slice(8, 10)}/${o.movement_at.slice(5, 7)}…`)))));
    kids.push(el("h3", {}, `Μέσα τώρα (${inside.length})`));
    kids.push(...(inside.length ? inside.map(e => row(e,
      [e.today ? `${e.today.label}${e.today.change === "overtime" ? " · δηλωμένη υπερωρία" : ""}${flexNote(e.today, true)} · φεύγει έως ${e.today.end}` : "χωρίς ωράριο σήμερα", deadline(e.today)],
      [el("button", { class: "btn small-btn", onclick: () => showDepart(e) }, "Αποχώρηση…")]))
      : [el("p", { class: "small muted" }, "Κανείς αυτή τη στιγμή.")]));
    const leftLine = t => `αποχώρησε ${t.left.at} αντί ${t.left.end}` + (t.left.reason ? ` · ${EARLY_REASONS[t.left.reason].toLowerCase()}${t.left.note ? ": " + t.left.note : ""}` : "");
    if (left.length) kids.push(el("h3", {}, `Έφυγαν νωρίτερα (${left.length})`), ...left.map(e => row(e, [leftLine(e.today)],
      [e.today.left.reason ? null : el("button", { class: "btn small-btn", onclick: () => showEarlyLeave(e) }, "Λόγος…")])));
    if (expected.length) kids.push(el("h3", {}, `Έρχονται σήμερα (${expected.length})`), ...expected.map(e => row(e, [e.today.label + flexNote(e.today) + (e.quiet_today ? " · θα αργήσει (σίγαση)" : ""), deadline(e.today)], [])));
    if (done.length) kids.push(el("h3", {}, "Τελείωσαν"), el("p", { class: "small muted" }, done.map(e => `${e.display_name} (${e.today.label})`).join(" · ")));
    if (off.length) kids.push(el("h3", {}, "Εκτός σήμερα"), el("p", { class: "small muted" }, off.map(e => `${e.display_name}${e.off_today ? ` — ${e.off_today}` : e.on_leave ? " — άδεια" : " — ρεπό"}`).join(" · ")));
    box.replaceChildren(...kids);
  }

  // ---------- long section explanations fold into «Οδηγίες» ----------
  document.querySelectorAll(".tab section > p.small, .sched-from > p.small").forEach(p => {
    if (p.textContent.length < 140) return;
    const d = el("details", { class: "help" }, el("summary", {}, "Οδηγίες"));
    p.replaceWith(d); d.append(p);
  });

  // ---------- tables as cards on the phone ----------
  function cardify(table) {
    const heads = [...table.querySelectorAll("tr:first-child th")].map(th => th.textContent);
    table.querySelectorAll("tr").forEach(tr => [...tr.children].forEach((td, i) => { if (td.tagName === "TD" && heads[i]) td.dataset.label = heads[i]; }));
  }

  // ---------- panels: a dialog on the PC, full screen on the phone ----------
  function openPanel(box) {
    if (!box.querySelector(":scope > .sheet-x")) {
      box.prepend(el("button", { type: "button", class: "sheet-x", "aria-label": "Κλείσιμο", onclick: () => hide(box) }, "✕"));
    }
    closePanels(box);
    box.hidden = false;
    box.scrollTop = 0;
  }
  document.addEventListener("keydown", ev => {
    if (ev.key !== "Escape") return;
    closePanels();
    document.querySelectorAll("details.menu[open]").forEach(m => { m.open = false; });
  });
  document.querySelector(".sheet-backdrop").addEventListener("click", () => closePanels());
  // a touch / click outside an open «Ενέργειες» menu closes it (pointerdown: iOS sends no click for taps on plain areas)
  document.addEventListener("pointerdown", ev => {
    if (!ev.target.closest("details.menu")) document.querySelectorAll("details.menu[open]").forEach(m => { m.open = false; });
  });

  // ---------- tabs (top on the PC, bottom bar on the phone) ----------
  const TABS = ["today", "people", "sched", "reports", "settings"];
  function showTab(name, push = true) {
    if (!TABS.includes(name)) name = "today";
    document.querySelectorAll(".tab").forEach(t => { t.hidden = t.dataset.tab !== name; });
    document.querySelectorAll("#tabs button").forEach(b => b.setAttribute("aria-current", b.dataset.tab === name ? "page" : "false"));
    try { localStorage.setItem("karta-admin-tab", name); } catch { /* ignore */ }
    if (push && location.hash !== "#" + name) history.replaceState(null, "", "#" + name);
    window.scrollTo(0, 0);
  }
  document.querySelectorAll("#tabs button").forEach(b => b.addEventListener("click", () => showTab(b.dataset.tab)));
  window.addEventListener("hashchange", () => showTab(location.hash.slice(1), false));
  {
    let start = location.hash.slice(1);
    if (!TABS.includes(start)) { try { start = localStorage.getItem("karta-admin-tab") || "today"; } catch { start = "today"; } }
    showTab(start);
  }
  document.getElementById("alertBadge").addEventListener("click", () => {
    showTab("today"); const a = document.getElementById("alerts"); if (a) a.scrollIntoView({ behavior: "smooth", block: "start" });
  });
  function renderBadge(d) {
    const n = d.alerts.filter(a => !a.resolved_at).length;
    const b = document.getElementById("alertBadge"), t = document.querySelector("#tabs .t-badge");
    b.hidden = !n; b.textContent = `⚠ ${n}`; b.title = `${n} ειδοποιήσεις`;
    t.hidden = !n; t.textContent = String(n);
  }


  // ---------- «Πρώτα βήματα»: checklist of a new installation (hidden once dismissed) ----------
  function goTo(tab, target) {
    showTab(tab);
    const node = document.getElementById(target);
    if (!node) return;
    setTimeout(() => {
      node.scrollIntoView({ behavior: "smooth", block: "center" });
      node.classList.remove("flash"); void node.offsetWidth; node.classList.add("flash");
    }, 60);
  }
  function renderFirstSteps(d) {
    const sec = document.getElementById("firstStepsSec"), box = document.getElementById("firstSteps");
    const steps = d.first_steps;
    sec.hidden = !steps;
    if (!steps) return;
    const done = steps.filter(s => s.done).length;
    const fill = el("i");
    fill.style.width = `${Math.round(100 * done / steps.length)}%`;      // CSSOM: allowed by the CSP (no inline style attribute)
    const mark = (step, on) => act(async () => { await api("/admin/api/first-steps", { step, done: on }); });
    const items = steps.map((s, i) => el("li", { class: s.done ? "done" : "" },
      el("span", { class: "mark", "aria-hidden": "true" }, s.done ? "✓" : String(i + 1)),
      el("span", { class: "step-title" }, s.title, el("span", { class: "visually-hidden" }, s.done ? " (έγινε)" : "")),
      el("span", { class: "step-text" }, s.text),
      el("span", { class: "step-actions" },
        s.tab ? el("button", { class: "link", onclick: () => goTo(s.tab, s.target) }, s.done ? "Άνοιγμα" : "Πάμε") : null,
        s.href ? el("a", { class: "link", href: s.href, target: "_blank", rel: "noopener" }, "Οδηγίες") : null,
        s.test ? el("button", { class: "link", onclick: act(async () => {
          await api("/admin/api/ntfy/test", {}); toast("Στάλθηκε δοκιμαστική ειδοποίηση στο κινητό");
        }) }, "Δοκιμαστική ειδοποίηση") : null,
        s.key === "notify" && !s.test ? el("a", { class: "link", href: "https://github.com/osergios/karta/wiki/Alerts-and-Reminders",
          target: "_blank", rel: "noopener" }, "Οδηγίες") : null,
        s.manual && !s.done ? el("button", { class: "link", onclick: mark(s.key, true) }, s.key === "holidays" ? "Δεν χρειάζεται" : "Έγινε / Παράλειψη") : null,
        s.manual && s.marked ? el("button", { class: "link", onclick: mark(s.key, false) }, "Αναίρεση") : null)));     // only what was ticked by hand
    box.replaceChildren(
      el("div", { class: "steps-head" },
        el("span", { class: "small" }, done === steps.length ? "Όλα έτοιμα! Η Karta είναι στημένη." : `${done} από ${steps.length} έτοιμα`),
        el("span", { class: "steps-bar", role: "progressbar", "aria-valuemin": "0", "aria-valuemax": String(steps.length),
          "aria-valuenow": String(done) }, fill)),
      el("ol", { class: "steps" }, ...items),
      el("button", { class: "link", onclick: act(async () => {
        if (done < steps.length && !confirm("Απόκρυψη των «Πρώτων βημάτων»; Όσα δεν έγιναν δεν θα εμφανίζονται πια εδώ.")) return;
        await api("/admin/api/first-steps", { hide: true });
      }) }, "Απόκρυψη"));
  }

  async function load() {
    let d;
    try { d = await api("/admin/api/overview"); } catch (e) { toast(e.message, true); return; }
    RETRO = !!d.retro;
    if (editorsFor !== editorsKey(d)) renderEditors(d);
    document.getElementById("erganiState").textContent = d.ergani_configured
      ? "Στοιχεία σύνδεσης ΕΡΓΑΝΗ: ρυθμισμένα." : "Στοιχεία σύνδεσης ΕΡΓΑΝΗ: συμπλήρωσέ τα παραπάνω, στο «Επιχείρηση και σύνδεση με το ΕΡΓΑΝΗ».";
    document.getElementById("erganiCheck").disabled = !d.ergani_configured;
    document.getElementById("ntfyState").textContent = d.ntfy
      ? "Οι ειδοποιήσεις έρχονται και στο κινητό σου (ntfy)."
      : "Ειδοποιήσεις κινητού ανενεργές: ρυθμίζονται στις «Ρυθμίσεις» → «Ειδοποιήσεις στο κινητό».";
    const alertRows = d.alerts.map(a => el("div", { class: `alert-row ${a.level}${a.resolved_at ? " done" : ""}` },
      el("span", { class: "when" }, fmt(a.created_at)),
      el("span", { class: "msg" }, el("strong", {}, LEVEL[a.level] + ": "), a.message),
      a.resolved_at ? null : el("button", { class: "link", onclick: act(async () => { await api(`/admin/api/alerts/${a.id}/resolve`, {}); }) }, "Εντάξει")));
    document.getElementById("alerts").replaceChildren(...(alertRows.length ? alertRows
      : [el("p", { class: "small" }, "Καμία ειδοποίηση.")]));
    document.getElementById("alertsClear").hidden = !d.alerts.length;
    document.getElementById("status").textContent = `${d.onboarding && d.onboarding.active ? "Περίοδος προσαρμογής" : MODE[d.mode]} · παράρτημα ${d.branch} · ${d.admin}`;
    document.body.classList.toggle("env-trial", d.mode === "trial");
    renderSendState(d);
    renderOnboarding(d);
    renderRemState(d);
    renderOffDays(d);
    renderBrand(d);
    renderConfig(d);
    renderNtfy(d);
    renderBackup(d);
    renderUpdate(d);
    renderKioskReload(d);
    renderBadge(d);
    const tm = document.getElementById("testMoves");
    const tmKids = [];
    if (d.mode === "trial") tmKids.push(el("p", { class: "an-line warn" },
      "Δοκιμαστικό ΕΡΓΑΝΗ: οι κινήσεις πάνε στο trialv2eservices.yeka.gr, σημειώνονται «ΑΚΥΡΟ» και δεν έχουν καμία νομική ισχύ. Δεν στέλνονται ποτέ στο πραγματικό ΕΡΓΑΝΗ."));
    if (d.stuck_other_mode) tmKids.push(el("p", { class: "an-line bad" },
      `${d.stuck_other_mode} κινήσεις σε αναμονή έγιναν σε άλλη λειτουργία και δεν θα σταλούν σε αυτή (π.χ. δοκιμαστικές όταν είσαι σε παραγωγή).`));
    if (d.test_movements) tmKids.push(el("div", { class: "er-actions" },
      el("span", { class: "small" }, `${d.test_movements} δοκιμαστικές κινήσεις (dry run / δοκιμαστικό ΕΡΓΑΝΗ). `),
      el("button", { class: "link danger", onclick: act(async () => {
        if (!confirm(`Διαγραφή ${d.test_movements} δοκιμαστικών κινήσεων;\n\nΟι πραγματικές κινήσεις (ΕΡΓΑΝΗ παραγωγής) δεν αγγίζονται ποτέ. Κάν' το πριν περάσεις σε παραγωγή, ώστε ωράρια, ειδοποιήσεις και αναφορά να ξεκινούν καθαρά.`)) return;
        const r = await api("/admin/api/movements/purge-tests", {}); toast(`Διαγράφηκαν ${r.deleted} δοκιμαστικές κινήσεις`);
      }) }, "Διαγραφή δοκιμαστικών κινήσεων")));
    tm.replaceChildren(...tmKids);

    renderPeople(d);
    renderToday(d);
    renderFirstSteps(d);

    document.getElementById("devs").replaceChildren(
      head("Συσκευή", "Εγγράφηκε", "Τελευταία χρήση", "Κατάσταση", ""),
      ...d.devices.map(v => el("tr", {},
        el("td", {}, v.name), el("td", {}, fmtUtc(v.created_at)), el("td", {}, fmtUtc(v.last_seen)),
        el("td", {}, v.revoked ? "Ανακλήθηκε" : "Ενεργή"),
        el("td", {}, v.revoked ? null : el("button", { class: "link", onclick: act(async () => {
          if (!confirm(`Ανάκληση της συσκευής «${v.name}»; Θα χρειαστεί νέα εγγραφή.`)) return;
          await api(`/admin/api/devices/${v.id}/revoke`, {}); toast("Η συσκευή ανακλήθηκε");
        }) }, "Ανάκληση"),
          el("button", { class: "link danger", onclick: act(async () => {
            if (!confirm(v.revoked ? `Διαγραφή της «${v.name}» από τη λίστα;`
                                   : `Διαγραφή της «${v.name}»; Ανακαλείται κιόλας — αν είναι ακόμα σε χρήση θα χρειαστεί νέα εγγραφή.`)) return;
            await api(`/admin/api/devices/${v.id}/delete`, {}); toast("Η συσκευή διαγράφηκε");
          }) }, "Διαγραφή")))));

    if (!editing(document.getElementById("movs"))) document.getElementById("movs").replaceChildren(
      head("Ώρα", "Εργαζόμενος", "Κίνηση", "Κατάσταση", "Πρωτόκολλο", "Λεπτομέρειες"),
      ...d.movements.map(m => el("tr", {},
        el("td", {}, fmt(m.movement_at)),
        el("td", {}, m.name),
        el("td", {}, LABEL[m.type], m.auth_method ? el("span", { class: "small" }, ({ qr: " · QR", qr_ergani: " · QR ΕΡΓΑΝΗ", pin: " · PIN", admin: " · από διαχείριση" })[m.auth_method] || "") : null),
        el("td", {}, el("span", { class: "tag " + m.status }, STATUS[m.status] || m.status),
          m.mode === "trial" ? el("span", { class: "tag trial" }, "Δοκιμαστικό ΕΡΓΑΝΗ · ΑΚΥΡΟ") : null,
          m.late_justification ? el("div", { class: "small" }, `Εκπρόθεσμη: ${m.late_justification}`) : null),
        el("td", {}, m.protocol || "-"),
        el("td", {},
          m.note ? el("div", { class: "small" }, `Σημείωση: ${m.note}`) : null,
          m.last_error ? el("div", { class: "small" }, `${m.attempts} προσπάθειες: ${m.last_error}`) : null,
          m.payload ? el("details", {}, el("summary", {}, "Τι θα στελνόταν"), el("pre", {}, m.payload)) : null,
          m.status === "failed" ? el("button", { class: "link", onclick: act(async () => {
            await api(`/admin/api/movements/${m.id}/retry`, {}); toast("Μπήκε ξανά στην ουρά");
          }) }, "Νέα αποστολή") : null,
          m.status === "uncertain" ? el("div", {},
            el("div", { class: "small warn-text" }, "Δεν ξέρουμε αν έφτασε στο ΕΡΓΑΝΗ. Έλεγξε τις κινήσεις κάρτας στο ΕΡΓΑΝΗ πριν διαλέξεις:"),
            el("button", { class: "link", onclick: act(async () => {
              const protocol = prompt("Υπάρχει στο ΕΡΓΑΝΗ. Αριθμός πρωτοκόλλου (προαιρετικό):", "");
              if (protocol === null) return;
              await api(`/admin/api/movements/${m.id}/uncertain`, { sent: true, protocol: protocol.trim() }); toast("Σημειώθηκε ως υποβληθείσα");
            }) }, "Υπάρχει στο ΕΡΓΑΝΗ"),
            el("button", { class: "link danger", onclick: act(async () => {
              if (!confirm("Η κίνηση ΔΕΝ υπάρχει στο ΕΡΓΑΝΗ; Θα σταλεί τώρα (ως εκπρόθεσμη αν πέρασε η ώρα).")) return;
              await api(`/admin/api/movements/${m.id}/uncertain`, { sent: false }); toast("Στέλνεται ξανά");
            }) }, "Δεν υπάρχει — νέα αποστολή")) : null))));
    cardify(document.getElementById("devs")); cardify(document.getElementById("movs"));
  }

  document.getElementById("addDev").addEventListener("submit", act(async ev => {
    ev.preventDefault();
    const f = new FormData(ev.target);
    const r = await api("/admin/api/enroll-codes", Object.fromEntries(f.entries()));
    const c = document.getElementById("code");
    c.hidden = false;
    c.replaceChildren(el("strong", {}, r.code),
      `Ισχύει ${r.expires_minutes} λεπτά. Στο tablet άνοιξε ${location.host}/enroll και πληκτρολόγησέ τον.`);
    ev.target.reset();
  }));

  // ---------- ΕΡΓΑΝΗ import ----------
  const STATUS_TXT = { new: "Νέος", match: "Υπάρχει ✓", name_differs: "Διαφορετική γραφή ονόματος" };
  async function erganiCheck() {
    const out = document.getElementById("erganiResult"), btn = document.getElementById("erganiCheck");
    btn.disabled = true; btn.textContent = "Έλεγχος…"; out.replaceChildren(el("p", { class: "small" }, "Επικοινωνία με το ΕΡΓΑΝΗ…"));
    let r;
    try { r = await api("/admin/api/ergani/review"); }
    catch (e) { out.replaceChildren(el("div", { class: "er-line bad" }, e.message)); btn.disabled = false; btn.textContent = "Έλεγχος ΕΡΓΑΝΗ"; return; }
    btn.disabled = false; btn.textContent = "Νέος έλεγχος";
    const lines = [];
    const em = r.employer;
    if (r.mode === "trial") lines.push(el("div", { class: "er-line warn" },
      "Αυτά είναι τα στοιχεία του ΔΟΚΙΜΑΣΤΙΚΟΥ ΕΡΓΑΝΗ (trialv2eservices), όχι του πραγματικού. Μην κάνεις εισαγωγή ή απενεργοποίηση με βάση αυτή τη λίστα."));
    lines.push(el("div", { class: "er-line " + (em.afm_matches ? "" : "bad") },
      `Εργοδότης: ${em.name || "—"} · ` + (em.afm_matches ? "ο ΑΦΜ ταιριάζει ✓" : "ο ΑΦΜ ΔΕΝ ταιριάζει με το ΑΦΜ στις «Ρυθμίσεις»")));
    lines.push(el("div", { class: "er-line " + (em.in_card_sector === true ? "" : "warn") },
      em.in_card_sector === true ? "Η επιχείρηση είναι ενταγμένη στην ψηφιακή κάρτα ✓"
        : em.in_card_sector === false ? "Το ΕΡΓΑΝΗ δεν δείχνει ακόμα ένταξη στην ψηφιακή κάρτα — ρώτα τον λογιστή."
        : "Δεν επιστράφηκε ένδειξη ένταξης στην κάρτα."));
    const found = r.branches.find(b => b.number === r.configured_branch);
    lines.push(el("div", { class: "er-line " + (found ? "" : "bad") },
      "Παραρτήματα: " + (r.branches.map(b => `#${b.number} ${b.address || ""}${b.status ? " (" + b.status + ")" : ""}`).join(" · ") || "—") +
      (found ? ` — η εφαρμογή χρησιμοποιεί το #${r.configured_branch} ✓` : ` — το παράρτημα #${r.configured_branch} των «Ρυθμίσεων» δεν υπάρχει στο ΕΡΓΑΝΗ`)));
    (r.mode === "trial" ? [] : r.not_in_ergani).forEach(x => {
      const off = el("button", { class: "link", onclick: act(async () => {
        await api(`/admin/api/employees/${x.employee_id}/active`, { active: false });
        line.replaceChildren(`${x.display_name}: απενεργοποιήθηκε ✓`); line.className = "er-line";
      }) }, "Απενεργοποίηση");
      const line = el("div", { class: "er-line warn" },
        x.is_employer ? `${x.display_name}: είναι ο ΑΦΜ του εργοδότη — ο εργοδότης δεν χτυπά κάρτα. `
                      : `${x.display_name} (ΑΦΜ …${x.afm_tail}): δεν υπάρχει στο τρέχον προσωπικό του ΕΡΓΑΝΗ. Αν δεν εργάζεται: `, off);
      lines.push(line);
    });

    const rows = [], picks = [];
    r.people.forEach(p => {
      const cb = el("input", { type: "checkbox" }); const name = el("input", { type: "text", value: p.suggested_name || p.display_name || "", maxlength: "40" });
      if (p.status === "new" && p.in_branch) cb.checked = true;
      if (p.status === "name_differs") cb.checked = true;
      if (p.status === "match") { cb.disabled = true; }
      if (p.status !== "new") name.disabled = true;
      picks.push({ p, cb, name });
      const info = erganiFacts(p.facts) + (p.facts.proposal ? " · ωράριο ανά ημέρα διαθέσιμο" : p.facts.digital ? " · ψηφιακό ωράριο" : "");
      rows.push(el("tr", {},
        el("td", {}, cb),
        el("td", {}, `${p.last_name} ${p.first_name}`, el("span", { class: "sub" }, `ΑΦΜ …${p.afm.slice(-3)} · παράρτημα #${p.branch ?? "—"}${p.in_branch ? "" : " (άλλο παράρτημα)"}`)),
        el("td", {}, STATUS_TXT[p.status], p.status === "name_differs" ? el("span", { class: "sub" }, `στην εφαρμογή: ${p.app_name} → θα γίνει όπως στο ΕΡΓΑΝΗ`) : null),
        el("td", {}, name, p.status === "new" ? el("span", { class: "sub" }, "όπως θα φαίνεται στο tablet — βάλε τόνους") : null),
        el("td", {}, el("span", { class: "sub" }, info || "—"))));
    });
    const table = rows.length
      ? el("div", { class: "scroll" }, el("table", { class: "er-table" }, el("tr", {}, el("th", {}, ""), el("th", {}, "Στο ΕΡΓΑΝΗ"), el("th", {}, "Κατάσταση"), el("th", {}, "Όνομα στο tablet"), el("th", {}, "Δηλωμένα")), ...rows))
      : el("p", { class: "small" }, "Το ΕΡΓΑΝΗ δεν επέστρεψε εργαζόμενους.");
    const go = el("button", { class: "btn" }, "Εισαγωγή / ενημέρωση επιλεγμένων");
    const pinsBox = el("div", {});
    go.addEventListener("click", act(async () => {
      const people = picks.filter(x => x.cb.checked && !x.cb.disabled).map(x => ({ afm: x.p.afm, display_name: x.name.value.trim() }));
      if (!people.length) { toast("Δεν επιλέχθηκε κανείς", true); return; }
      const res = await api("/admin/api/ergani/import", { people });
      if (res.created.length) {
        pinsBox.replaceChildren(el("div", { class: "pins" },
          el("p", { class: "small" }, "PIN των νέων εργαζομένων — δώσ' τα στον καθένα. Τα ξαναβλέπεις με «Εμφάνιση PIN» στους Εργαζόμενους, ή τα αλλάζεις με «Ορισμός PIN»."),
          ...res.created.map(c => el("div", {}, c.name, el("strong", {}, c.pin.replace(/(\d{3})(\d{3})/, "$1 $2"))))));
      }
      toast(`Έτοιμο: ${res.created.length} νέοι, ${people.length - res.created.length} ενημερώθηκαν`);
      editorsFor = null;
    }));
    out.replaceChildren(...[...lines, table, rows.length && r.mode !== "trial" ? el("div", { class: "er-actions" }, go) : null, pinsBox].filter(Boolean));
  }
  document.getElementById("erganiCheck").addEventListener("click", erganiCheck);
  document.getElementById("alertsClear").addEventListener("click", act(async () => {
    if (!confirm("Εκκαθάριση της λίστας ειδοποιήσεων;\n\nΟι ανοιχτές σημειώνονται «Εντάξει». Η μηνιαία αναφορά συνεχίζει να τις μετρά.")) return;
    const r = await api("/admin/api/alerts/clear", {}); toast(`Καθαρίστηκαν ${r.cleared} ειδοποιήσεις`);
  }));
  document.getElementById("erganiRefresh").addEventListener("click", act(async () => {
    const r = await api("/admin/api/ergani/refresh", {}); editorsFor = null;
    toast(`Ενημερώθηκαν τα στοιχεία ΕΡΓΑΝΗ για ${r.updated} εργαζόμενους`);
  }));
  document.getElementById("erganiServices").addEventListener("click", act(async () => {
    const box = document.getElementById("erganiExtra");
    box.replaceChildren(el("p", { class: "small" }, "Ανάγνωση λίστας υπηρεσιών…"));
    const r = await api("/admin/api/ergani/services");
    box.replaceChildren(el("details", { open: "" }, el("summary", {}, `Υπηρεσίες που δίνει το ΕΡΓΑΝΗ σε αυτόν τον λογαριασμό (${r.services.length})`),
      r.services.length ? el("table", { class: "er-table" }, el("tr", {}, el("th", {}, "Κωδικός"), el("th", {}, "Περιγραφή"), el("th", {}, "Παράμετροι")),
        ...r.services.map(x => el("tr", {}, el("td", {}, x.code), el("td", {}, x.description), el("td", {}, x.parameters.join(", ")))))
        : el("p", { class: "small" }, "Το ΕΡΓΑΝΗ δεν επέστρεψε υπηρεσίες.")));
  }));

  document.getElementById("limits").addEventListener("submit", act(async ev => {
    ev.preventDefault();
    const values = {};
    for (const [k, v] of new FormData(ev.target).entries()) values[k] = Number(v);
    await api("/admin/api/settings", { values }); toast("Τα όρια αποθηκεύτηκαν");
  }));
  const schedFrom = document.getElementById("schedFrom");
  if (schedFrom) schedFrom.value = todayAthens();
  const month = document.getElementById("month"), reportLink = document.getElementById("reportLink");
  month.value = new Date().toISOString().slice(0, 7);
  const setLink = () => { reportLink.href = `/admin/api/report.xlsx?month=${month.value}`; };
  month.addEventListener("change", setLink); setLink();
  const year = document.getElementById("year"), reportYearLink = document.getElementById("reportYearLink");
  year.value = String(new Date().getFullYear());
  const setYearLink = () => { reportYearLink.href = `/admin/api/report-year.xlsx?year=${year.value}`; };
  year.addEventListener("input", setYearLink); setYearLink();

  const logo = document.getElementById("logo");
  if (logo) { logo.addEventListener("error", () => { logo.hidden = true; }); if (logo.complete && !logo.naturalWidth) logo.hidden = true; }
  load();
  setInterval(() => { if (!document.hidden) load(); }, 30000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) load(); });   // back on the phone: fresh data at once
})();
