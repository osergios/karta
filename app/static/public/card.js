"use strict";
(() => {
  const box = document.getElementById("cp");
  const token = decodeURIComponent(location.pathname.split("/").filter(Boolean)[1] || "");
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
  const fmt = new Intl.DateTimeFormat("el-GR", { weekday: "long", day: "numeric", month: "long", hour: "2-digit", minute: "2-digit", timeZone: "Europe/Athens" });
  const first = name => name.trim().split(/\s+/)[0];
  const meta = n => (document.querySelector(`meta[name="${n}"]`) || {}).content || "";
  const BRAND = meta("brand"), BRAND_NAME = meta("brand-name");

  function fail(text) {
    box.replaceChildren(el("img", { class: "cp-logo", src: "/brand/logo", alt: BRAND_NAME, onerror: ev => { ev.target.hidden = true; } }),
      el("h1", {}, "Ο σύνδεσμος δεν ισχύει"), el("p", { class: "hint" }, text));
  }

  async function main() {
    if (!token) return fail("Ζήτα νέο σύνδεσμο από το κατάστημα.");
    let res, data = {};
    try { res = await fetch(`/api/card/${encodeURIComponent(token)}`, { credentials: "omit", cache: "no-store" }); data = await res.json(); }
    catch { return fail("Δεν υπάρχει σύνδεση. Δοκίμασε ξανά σε λίγο."); }
    if (!res.ok) return fail(data.detail || "Ζήτα νέο σύνδεσμο από το κατάστημα.");

    const canvas = await window.KartaCard.draw(data.name, data.svg);
    const url = canvas.toDataURL("image/png");
    const blob = await new Promise(ok => canvas.toBlob(ok, "image/png"));
    const fname = `karta-${data.name}.png`;
    const file = new File([blob], fname, { type: "image/png" });
    const canShare = !!(navigator.canShare && navigator.canShare({ files: [file] }));
    const save = canShare
      ? el("button", { class: "cp-btn", onclick: async () => { try { await navigator.share({ files: [file] }); } catch { /* cancelled */ } } }, "Αποθήκευση εικόνας")
      : el("a", { class: "cp-btn", href: URL.createObjectURL(blob), download: fname }, "Αποθήκευση εικόνας");

    box.replaceChildren(
      el("h1", {}, `Γεια σου, ${first(data.name)}!`),
      el("p", { class: "hint" }, BRAND ? `Αυτή είναι η προσωπική σου κάρτα εργασίας για το ${BRAND}.` : "Αυτή είναι η προσωπική σου κάρτα εργασίας."),
      el("img", { class: "cp-card", src: url, alt: `Κάρτα QR · ${data.name}` }),
      save,
      el("ol", { class: "cp-steps" },
        el("li", {}, canShare ? "Πάτα «Αποθήκευση εικόνας» και διάλεξε «Αποθήκευση εικόνας» / «Αποθήκευση στις Φωτογραφίες»."
                              : "Πάτα «Αποθήκευση εικόνας» ή κράτα πατημένη την εικόνα και διάλεξε «Αποθήκευση»."),
        el("li", {}, "Στο κατάστημα πάτα «Κάρτα QR» στο laptop και δείξε την εικόνα στην κάμερα, με τη φωτεινότητα στο μέγιστο."),
        el("li", {}, "Αν αλλάξεις κινητό ή χαθεί η εικόνα, ζήτα νέα κάρτα.")),
      el("p", { class: "cp-note" }, `Η κάρτα είναι προσωπική: μην τη στέλνεις σε άλλους. Ο σύνδεσμος λήγει: ${fmt.format(new Date(data.expires_at + "Z"))}`));
  }
  main();
})();
