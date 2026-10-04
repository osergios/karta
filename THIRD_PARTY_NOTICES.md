# Third-party notices

Karta is Copyright © 2026 osergios and licensed under the GNU Affero General Public
License v3.0 (see [`LICENSE`](LICENSE)). The components below are not covered by that
license.

Karta includes code and assets written by other people. Each one keeps its
original license, and the full license text ships next to it in this repository.
Many thanks to their authors.

| Component | Where in this repo | Upstream | License | Changes |
|---|---|---|---|---|
| Ergani Python SDK | `vendor/ergani/` | [withlogicco/ergani-python-sdk](https://github.com/withlogicco/ergani-python-sdk) @ `caa51f5` (2026-09-25) | MIT, © 2024 LOGIC | Modified (see below) |
| jsQR 1.4.0 | `app/static/public/vendor/jsQR.min.js` | [cozmo/jsQR](https://github.com/cozmo/jsQR) | Apache-2.0 | Unmodified minified build |
| Tabler Icons ("volume" icon) | inline SVG in `app/static/public/kiosk.html` | [tabler/tabler-icons](https://github.com/tabler/tabler-icons), © 2020-2024 Paweł Kuna | MIT | Single icon path copied inline |
| Inter typeface | `app/static/public/brand/fonts/` | [rsms/inter](https://github.com/rsms/inter), © 2016 The Inter Project Authors | SIL Open Font License 1.1 | Greek and Latin subsets, weights 300–600, as WOFF2 |

## Ergani Python SDK

- License text: [`vendor/ergani/LICENSE-ergani-sdk`](vendor/ergani/LICENSE-ergani-sdk)
- Source details: [`vendor/ergani/VENDORED_FROM.txt`](vendor/ergani/VENDORED_FROM.txt)
- Vendored from the GitHub `main` branch because it includes the read services that
  are not in the PyPI 1.0.1 release.
- **Local modification:** `vendor/ergani/auth.py` reads the login `UserType` from the
  `ERGANI_USER_TYPE` environment variable (default `"01"`, the SDK's own value) so
  that Ergani branch users (`"02"`) can log in.

## jsQR

- License text: [`app/static/public/vendor/LICENSE-jsQR.txt`](app/static/public/vendor/LICENSE-jsQR.txt)
- Copyright the jsQR authors ([Cosmo Wolfe](https://github.com/cozmo) and contributors).
  Used to scan QR codes with the kiosk camera.

## Tabler Icons

- License text: [`app/static/public/vendor/LICENSE-tabler-icons.txt`](app/static/public/vendor/LICENSE-tabler-icons.txt)
- The speaker icon on the kiosk's "enable sound" button.

## Inter

- License text: [`app/static/public/brand/fonts/LICENSE-Inter.txt`](app/static/public/brand/fonts/LICENSE-Inter.txt)
- The font files may be used, redistributed and modified under the OFL. They may
  not be sold on their own.

## Python dependencies

The packages listed in `requirements.txt` (FastAPI, Uvicorn, Requests, argon2-cffi,
PyJWT, tzdata, openpyxl, segno) are **not** included in this repository. `pip`
downloads them at install time, and each package is covered by its own license.
