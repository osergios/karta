/* Personal QR card artwork: the same image in the admin page and on the employee's phone. */
"use strict";
window.CentroCard = (() => {
  const CARD_W = 1080, CARD_H = 1712;          // portrait, ID-card proportions (54 × 85.6 mm)
  const loadImg = src => new Promise((ok, fail) => { const i = new Image(); i.onload = () => ok(i); i.onerror = fail; i.src = src; });
  function roundRect(ctx, x, y, w, h, r) { ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r); ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath(); }
  async function drawCard(name, svg) {
    await Promise.all(["500 104px Inter", "400 40px Inter", "600 34px Inter"].map(f => document.fonts.load(f, name + "ΚάρταΔείξε QR").catch(() => {})));
    const [qr, logo] = await Promise.all([loadImg("data:image/svg+xml;base64," + btoa(svg)), loadImg("/brand/logo").catch(() => null)]);
    const c = document.createElement("canvas"); c.width = CARD_W; c.height = CARD_H;
    const x = c.getContext("2d");
    x.fillStyle = "#f7f5f1"; x.fillRect(0, 0, CARD_W, CARD_H);
    x.fillStyle = "#ece3d6"; x.fillRect(0, 0, CARD_W, 470);
    if (logo) x.drawImage(logo, (CARD_W - 300) / 2, 70, 300, 300);
    x.textAlign = "center"; x.textBaseline = "alphabetic";
    x.fillStyle = (getComputedStyle(document.documentElement).getPropertyValue("--brand") || "").trim() || "#16897b"; x.font = "600 34px Inter, sans-serif";
    x.fillText("ΚΑΡΤΑ ΕΡΓΑΣΙΑΣ", CARD_W / 2, 430);
    x.fillStyle = "#232323"; let size = 104;
    do { x.font = `500 ${size}px Inter, sans-serif`; size -= 4; } while (x.measureText(name).width > CARD_W - 140 && size > 40);
    x.fillText(name, CARD_W / 2, 610);
    const P = 780, px = (CARD_W - P) / 2, py = 680;
    x.save(); x.shadowColor = "rgba(35,35,35,.10)"; x.shadowBlur = 24; x.shadowOffsetY = 6;
    x.fillStyle = "#ffffff"; roundRect(x, px, py, P, P, 44); x.fill(); x.restore();
    x.imageSmoothingEnabled = false;
    x.drawImage(qr, px + 30, py + 30, P - 60, P - 60);
    x.fillStyle = "#5c5c5c"; x.font = "400 40px Inter, sans-serif";
    x.fillText("Δείξε το QR στην κάμερα του καταστήματος", CARD_W / 2, 1560);
    x.font = "400 32px Inter, sans-serif"; x.fillStyle = "#8a8a8a";
    x.fillText("Προσωπική κάρτα · μην τη μοιράζεσαι", CARD_W / 2, 1625);
    return c;
  }
  return { draw: drawCard, W: CARD_W, H: CARD_H };
})();
