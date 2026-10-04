/* Festive decorations for the shop screen (admin toggle «Εορταστική διακόσμηση»).
   Themes follow the calendar (the server says which one is on): christmas, easter, flag (25/3, 28/10),
   kites (Καθαρά Δευτέρα), may (Πρωτομαγιά). All art is drawn here as plain SVG; motion is CSS only and
   stops with the Windows «reduce animations» setting. Nothing here takes clicks. */
"use strict";
window.Festive = (() => {
  const NS = "http://www.w3.org/2000/svg";
  const svg = (w, h, body, cls = "") => {
    const d = document.createElement("div");
    d.className = "fx " + cls;
    d.innerHTML = `<svg xmlns="${NS}" viewBox="0 0 ${w} ${h}" focusable="false">${body}</svg>`;
    return d;
  };
  const rnd = (a, b) => a + Math.random() * (b - a);

  // ---------- art ----------
  const tree = (k = 0) => svg(60, 100, `
    <rect x="26" y="84" width="8" height="14" rx="1.5" fill="#7a4b2a"/>
    <polygon points="30,10 50,40 10,40" fill="#237f4d"/>
    <polygon points="30,24 55,62 5,62" fill="#1f7446"/>
    <polygon points="30,42 58,88 2,88" fill="#1b6a40"/>
    <path d="M12 38 Q30 46 48 36 M8 60 Q30 70 52 58 M5 84 Q30 94 55 82" stroke="#f2c14e" stroke-width="1.4" fill="none" opacity=".8"/>
    <circle class="fx-bulb b1" cx="20" cy="40" r="2.6" fill="#e0453a"/><circle class="fx-bulb b2" cx="38" cy="38" r="2.6" fill="#3b7dd8"/>
    <circle class="fx-bulb b3" cx="14" cy="61" r="2.8" fill="#f2c14e"/><circle class="fx-bulb b1" cx="30" cy="66" r="2.8" fill="#e0453a"/>
    <circle class="fx-bulb b2" cx="46" cy="60" r="2.8" fill="#f2c14e"/><circle class="fx-bulb b3" cx="10" cy="86" r="3" fill="#3b7dd8"/>
    <circle class="fx-bulb b1" cx="24" cy="89" r="3" fill="#f2c14e"/><circle class="fx-bulb b2" cx="40" cy="88" r="3" fill="#e0453a"/>
    <circle class="fx-bulb b3" cx="52" cy="84" r="3" fill="#f2c14e"/>
    <polygon class="fx-star" points="30,1 32.6,7.4 39.4,7.6 34,11.8 36,18.4 30,14.6 24,18.4 26,11.8 20.6,7.6 27.4,7.4" fill="#f2c14e"/>`,
    "fx-tree t" + k);

  const santa = () => svg(130, 170, `
    <g class="fx-wave"><path d="M18 118 Q4 96 10 78" stroke="#c62828" stroke-width="14" stroke-linecap="round" fill="none"/>
      <circle cx="10" cy="74" r="9" fill="#f7f5f1"/></g>
    <rect x="22" y="104" width="86" height="70" rx="26" fill="#c62828"/>
    <rect x="22" y="136" width="86" height="11" fill="#2b2b2b"/><rect x="58" y="134" width="15" height="15" rx="2" fill="none" stroke="#f2c14e" stroke-width="3"/>
    <rect x="58" y="104" width="14" height="70" fill="#f7f5f1" opacity=".95"/>
    <path d="M28 44 Q60 -4 104 36 L112 60 L22 60 Z" fill="#c62828"/>
    <circle cx="112" cy="38" r="9" fill="#f7f5f1"/>
    <rect x="18" y="54" width="94" height="14" rx="7" fill="#f7f5f1"/>
    <circle cx="65" cy="84" r="23" fill="#f3c9a8"/>
    <path d="M40 84 Q42 126 65 132 Q88 126 90 84 Q80 104 65 102 Q50 104 40 84 Z" fill="#fbfbfb"/>
    <path d="M50 96 Q58 90 65 96 Q72 90 80 96 Q72 101 65 98 Q58 101 50 96 Z" fill="#ffffff" stroke="#e5e5e5" stroke-width=".8"/>
    <circle cx="57" cy="80" r="2.6" fill="#2b2b2b"/><circle cx="73" cy="80" r="2.6" fill="#2b2b2b"/>
    <circle cx="51" cy="88" r="4" fill="#f29c9c" opacity=".7"/><circle cx="79" cy="88" r="4" fill="#f29c9c" opacity=".7"/>
    <circle cx="65" cy="89" r="4.2" fill="#e8998a"/>
    <path d="M52 73 Q57 70 61 73 M69 73 Q73 70 78 73" stroke="#ffffff" stroke-width="3" stroke-linecap="round" fill="none"/>`,
    "fx-santa");

  const garland = n => {
    let dots = "";
    const cols = ["#e0453a", "#f2c14e", "#3b7dd8", "#3aa76d"];
    for (let i = 0; i < n; i++) {
      const x = 10 + i * (380 / (n - 1)), y = 10 + 12 * Math.sin((i / (n - 1)) * Math.PI);
      dots += `<line x1="${x}" y1="${y - 4}" x2="${x}" y2="${y}" stroke="#3a3a3a" stroke-width="1.2"/>` +
              `<ellipse class="fx-bulb b${1 + (i % 3)}" cx="${x}" cy="${y + 5}" rx="3.6" ry="5.4" fill="${cols[i % 4]}"/>`;
    }
    return svg(400, 36, `<path d="M0 6 Q200 34 400 6" stroke="#3a3a3a" stroke-width="1.4" fill="none"/>${dots}`, "fx-garland");
  };

  const egg = (c = "#c62828") => `<ellipse cx="0" cy="0" rx="13" ry="17" fill="${c}"/>
    <ellipse cx="-4" cy="-7" rx="4" ry="6" fill="#ffffff" opacity=".35"/>`;
  const eggs = () => svg(170, 70, `
    <path d="M4 64 Q85 44 166 64 L166 70 L4 70 Z" fill="#6aa84f"/>
    ${[18, 46, 74, 102, 130, 156].map((x, i) => `<path d="M${x - 8} 62 l4 -14 l3 14 M${x + 4} 62 l5 -12 l2 12" stroke="#58a043" stroke-width="2" fill="none"/>`).join("")}
    <g transform="translate(40 46) rotate(-12)">${egg()}</g><g transform="translate(70 42) rotate(6)">${egg("#b71c1c")}</g>
    <g transform="translate(100 46) rotate(-4)">${egg()}</g><g transform="translate(128 48) rotate(14)">${egg("#d32f2f")}</g>`, "fx-eggs");

  const candle = () => svg(40, 170, `
    <g class="fx-flame"><path d="M20 4 Q29 18 20 30 Q11 18 20 4 Z" fill="#f6b73c"/><path d="M20 13 Q24 21 20 27 Q16 21 20 13 Z" fill="#fff3c4"/></g>
    <line x1="20" y1="29" x2="20" y2="35" stroke="#3a3a3a" stroke-width="1.4"/>
    <rect x="12" y="34" width="16" height="132" rx="4" fill="#fbf7ee" stroke="#e7dcc6"/>
    <path d="M12 70 Q20 76 28 70 M12 80 Q20 86 28 80" stroke="#8fb8e0" stroke-width="2" fill="none"/>
    <path d="M20 90 Q4 82 6 98 Q12 104 20 94 Q28 104 34 98 Q36 82 20 90 Z" fill="#8fb8e0"/>
    <path d="M18 96 Q12 116 10 128 M22 96 Q28 116 30 128" stroke="#8fb8e0" stroke-width="3" fill="none" stroke-linecap="round"/>
    <circle cx="20" cy="93" r="3.5" fill="#6d9fcf"/>`, "fx-candle");

  const flower = (cx, cy, r, c) => {
    let p = "";
    for (let i = 0; i < 5; i++) {
      const a = i * 72 * Math.PI / 180;
      p += `<circle cx="${(cx + Math.cos(a) * r).toFixed(1)}" cy="${(cy + Math.sin(a) * r).toFixed(1)}" r="${r}" fill="${c}"/>`;
    }
    return p + `<circle cx="${cx}" cy="${cy}" r="${r * .8}" fill="#f2c14e"/>`;
  };
  const flowers = () => svg(160, 90, `
    <path d="M30 90 Q28 60 34 40 M80 90 Q80 56 78 30 M128 90 Q130 64 124 46" stroke="#4f8f3a" stroke-width="3" fill="none"/>
    <path d="M30 70 Q16 62 18 52 Q28 58 30 70 M80 64 Q94 56 96 46 Q84 50 80 64 M128 72 Q142 66 140 56 Q130 60 128 72" fill="#6aa84f"/>
    ${flower(34, 38, 6, "#f28cb1")}${flower(78, 28, 7, "#b39ddb")}${flower(124, 44, 6, "#ffb74d")}`, "fx-flowers");

  const butterfly = c => svg(40, 30, `<g class="fx-wings"><ellipse cx="12" cy="11" rx="10" ry="8" fill="${c}"/><ellipse cx="28" cy="11" rx="10" ry="8" fill="${c}"/>
    <ellipse cx="13" cy="22" rx="7" ry="6" fill="${c}" opacity=".85"/><ellipse cx="27" cy="22" rx="7" ry="6" fill="${c}" opacity=".85"/></g>
    <rect x="18.8" y="6" width="2.4" height="20" rx="1.2" fill="#3a3a3a"/>`, "fx-butterfly");

  const GR = `<rect width="27" height="18" fill="#0d5eaf"/>
    ${[2, 6, 10, 14].map(y => `<rect y="${y}" width="27" height="2" fill="#ffffff"/>`).join("")}
    <rect width="10" height="10" fill="#0d5eaf"/><rect y="4" width="10" height="2" fill="#ffffff"/><rect x="4" width="2" height="10" fill="#ffffff"/>`;
  const flag = () => svg(120, 150, `
    <rect x="6" y="4" width="4" height="146" rx="2" fill="#8a6a4a"/><circle cx="8" cy="4" r="4" fill="#d4a93b"/>
    <g class="fx-flagwave" transform="translate(10 10) scale(3.9)">${GR}</g>`, "fx-flag");
  const bunting = n => {
    let t = "";
    for (let i = 0; i < n; i++) {
      const x = 6 + i * (388 / n), y = 6 + 10 * Math.sin(((i + .5) / n) * Math.PI);
      t += `<polygon class="fx-pennant" points="${x},${y} ${x + 388 / n - 4},${y} ${x + (388 / n - 4) / 2},${y + 20}" fill="${i % 2 ? "#ffffff" : "#0d5eaf"}" stroke="#d9d9d9" stroke-width=".5"/>`;
    }
    return svg(400, 40, `<path d="M0 5 Q200 30 400 5" stroke="#6a6a6a" stroke-width="1.2" fill="none"/>${t}`, "fx-bunting");
  };

  const kite = (a, b, c) => svg(70, 160, `
    <path d="M35 76 Q20 100 38 120 Q54 140 34 158" stroke="#6a6a6a" stroke-width="1" fill="none"/>
    ${[96, 116, 136].map((y, i) => `<path d="M${i % 2 ? 44 : 26} ${y} l6 -5 l0 10 Z M${i % 2 ? 44 : 26} ${y} l-6 -5 l0 10 Z" fill="${[a, b, c][i]}"/>`).join("")}
    <polygon points="35,4 64,34 35,76 6,34" fill="${a}"/><polygon points="35,4 64,34 35,34" fill="${b}"/><polygon points="6,34 35,34 35,76" fill="${c}"/>
    <path d="M35 4 L35 76 M6 34 L64 34" stroke="#3a3a3a" stroke-width="1" opacity=".5"/>`, "fx-kite");

  const wreath = () => {
    let s = "";
    const cols = ["#f28cb1", "#ffb74d", "#b39ddb", "#ef5350", "#fff176"];
    for (let i = 0; i < 14; i++) {
      const a = i * (360 / 14) * Math.PI / 180, x = 70 + Math.cos(a) * 50, y = 70 + Math.sin(a) * 50;
      s += `<ellipse cx="${(70 + Math.cos(a + .2) * 52).toFixed(1)}" cy="${(70 + Math.sin(a + .2) * 52).toFixed(1)}" rx="9" ry="4.5" fill="#5f9e45" transform="rotate(${(i * 360 / 14 + 110).toFixed(0)} ${(70 + Math.cos(a + .2) * 52).toFixed(1)} ${(70 + Math.sin(a + .2) * 52).toFixed(1)})"/>`;
      s += flower(+x.toFixed(1), +y.toFixed(1), 4.2, cols[i % cols.length]);
    }
    return svg(140, 140, `<circle cx="70" cy="70" r="50" fill="none" stroke="#6aa84f" stroke-width="5"/>${s}`, "fx-wreath");
  };

  // ---------- falling / floating things over the whole screen ----------
  function sky(box, kind, n) {
    for (let i = 0; i < n; i++) {
      const f = document.createElement("i");
      f.className = "fx-fall " + kind;
      f.style.left = rnd(0, 100).toFixed(1) + "%";
      f.style.setProperty("--s", rnd(.5, 1.25).toFixed(2));
      f.style.setProperty("--dur", rnd(9, 18).toFixed(1) + "s");
      f.style.setProperty("--delay", (-rnd(0, 18)).toFixed(1) + "s");
      f.style.setProperty("--drift", rnd(-40, 40).toFixed(0) + "px");
      box.append(f);
    }
  }

  const THEMES = {
    christmas(side, skyBox) {
      side.append(garland(14), tree(1), tree(2), santa());
      sky(skyBox, "snow", 46);
    },
    easter(side, skyBox) {
      side.append(candle(), eggs(), flowers());
      const b1 = butterfly("#f2a1c4"), b2 = butterfly("#9fc5f8");
      b1.classList.add("bf1"); b2.classList.add("bf2");
      skyBox.append(b1, b2);
    },
    flag(side) { side.append(bunting(12), flag()); },
    kites(side, skyBox) {
      const k1 = kite("#e53935", "#fdd835", "#1e88e5"), k2 = kite("#43a047", "#ff7043", "#ab47bc"), k3 = kite("#1e88e5", "#ffffff", "#fdd835");
      k1.classList.add("k1"); k2.classList.add("k2"); k3.classList.add("k3");
      side.append(k1, k2); skyBox.append(k3);
    },
    may(side, skyBox) { side.append(wreath(), flowers()); sky(skyBox, "petal", 22); },
  };

  // Big picture on the closed-day screen, by holiday.
  const HERO = {
    christmas: () => { const g = document.createElement("div"); g.className = "fx-hero-row"; g.append(tree(1), santa(), tree(2)); return g; },
    newyear: () => { const g = document.createElement("div"); g.className = "fx-hero-row"; g.append(tree(1), tree(2)); return g; },
    theophany: () => tree(1),
    clean_monday: () => { const g = document.createElement("div"); g.className = "fx-hero-row"; g.append(kite("#e53935", "#fdd835", "#1e88e5"), kite("#43a047", "#ff7043", "#ab47bc")); return g; },
    mar25: flag, oct28: flag,
    good_friday: candle,
    easter: () => { const g = document.createElement("div"); g.className = "fx-hero-row"; g.append(candle(), eggs()); return g; },
    may1: wreath,
  };

  let current = null;
  function apply(theme) {
    const side = document.getElementById("festiveSide"), skyBox = document.getElementById("festiveSky");
    if (!side || !skyBox || theme === current) return;
    current = theme;
    side.replaceChildren(); skyBox.replaceChildren();
    document.body.dataset.festive = theme || "";
    if (theme && THEMES[theme]) THEMES[theme](side, skyBox);
  }
  function hero(key) { return HERO[key] ? HERO[key]() : null; }
  return { apply, hero, themes: Object.keys(THEMES) };
})();
