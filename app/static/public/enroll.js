"use strict";
(() => {
  const btn = document.getElementById("go");
  const err = document.getElementById("err");
  const input = document.getElementById("code");
  const logo = document.getElementById("logo");
  if (logo) logo.addEventListener("error", () => { logo.hidden = true; });
  async function go() {
    err.textContent = ""; btn.disabled = true;
    try {
      const res = await fetch("/api/enroll", {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code: input.value }),
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok) { btn.textContent = `Εγγράφηκε: ${data.device}`; setTimeout(() => { location.href = "/"; }, 1500); return; }
      err.textContent = data.detail || "Η εγγραφή απέτυχε.";
    } catch { err.textContent = "Δεν υπάρχει σύνδεση."; }
    btn.disabled = false;
  }
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
  btn.addEventListener("click", go);
  input.addEventListener("keydown", e => { if (e.key === "Enter") go(); });
})();
