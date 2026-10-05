[Ελληνικά](Security-and-Privacy) · **English**

# Security and privacy

Karta handles legal working‑time records and staff personal data (names, ΑΦΜ, work
hours). Here's how it's protected, and what you're responsible for.

## Who can do what

| Area | Protected by |
|---|---|
| **Admin page** (`/admin`, `/admin/api/…`) | **Cloudflare Access**. Karta checks the signed token on every request (RS256 signature, audience, issuer, expiry) and that the email is in `ADMIN_EMAILS`. If anything is missing or wrong, access is refused. |
| **Shop screen punches** | Only **registered devices** can punch. Registration needs a one‑time code from the admin (valid 10 minutes), and the device then keeps an `HttpOnly`, `Secure`, `SameSite=Strict` cookie. You can revoke any device. |
| **Each punch** | The employee's **PIN** (6 digits, too‑easy PINs refused, locked for 5 minutes after 5 wrong tries) or their **QR card**. |
| **Phone‑card links** | A random token, valid for 24 hours and at most 10 opens, cancelled as soon as a new card is issued. |

Requests that change data must come from your own `PUBLIC_ORIGIN`. Requests from other
sites are refused.

## How secrets are stored

- **PINs:** hashed with **Argon2**, so they can't be read back. If `PIN_KEY` is set, a
  copy is also encrypted with **AES‑GCM** so the admin can view it; the key lives only in
  `.env`, never in the database.
- **QR card codes, device tokens, registration codes and link tokens:** stored as
  SHA‑256 hashes only. QR codes are also encrypted with `PIN_KEY`, so a card can be shown
  again.
- **Ergani password:** in `.env` or, if you set it in the admin page, in the database
  encrypted with **AES‑GCM** and `PIN_KEY` (as is the ntfy token). It is never sent back
  to the page.
- **Cloud backups:** encrypted on your machine before upload (restic, AES-256); the cloud
  provider can't read them. The encryption password and the cloud access are kept on the
  machine (`/data/cloud-password`, `/data/rclone.conf`, for Karta only); on Google Drive Karta can only see the
  files it creates itself.

## Data minimisation

- From Ergani's employee data (which includes ID documents, pay and family details),
  Karta keeps **only** ΑΦΜ, full name and the declared schedule. The rest is discarded at
  once and never logged.
- The audit log never stores a full ΑΦΜ (only the last 3 digits).
- The shop screen and phone card show only the display name.

## Web hardening

- A strict **Content‑Security‑Policy**: no inline scripts or styles, and no third‑party
  content. Pages can't be embedded in other sites.
- Only Karta's own pages may use the camera. Microphone, location, payment and USB are
  disabled.
- `Cache-Control: no-store` on every response.
- Hidden from search engines: `/robots.txt` disallows everything, and every response
  carries `X-Robots-Tag: noindex, nofollow, …`.
- The Docker image runs as an **unprivileged user**, without server or access‑log
  banners.

## Where the image comes from

Karta's image is built only by the project's GitHub Actions, with signed build provenance
and an SBOM. To check: `gh attestation verify oci://ghcr.io/osergios/karta:<version> --owner osergios`.

## Audit trail

Admin actions (new PIN, QR issued, schedule changes, leave, departures entered by hand,
device registration, deletions…) are written to an audit table with who did it and when.

## Your responsibilities

- Serve Karta **only over HTTPS**, and keep `/admin` behind Cloudflare Access.
- Keep `.env` private and backed up (especially `PIN_KEY`); never commit it.
- Back up the database regularly, including off the machine (see [Backups](Backups-EN)).
  Punches must be kept for at least 5 years.
- Real punches are **legal working‑time records**. Karta refuses to delete an employee
  who has real punches; deactivate them instead.
- You're responsible for the declarations made to Ergani from your installation. Test
  with `dry_run` and `trial` first (see [Going live](Going-Live-EN)).

## Reporting a security problem

Please don't open a public issue. Use GitHub's
[private vulnerability reporting](https://github.com/osergios/karta/security/advisories/new);
see the [security policy](https://github.com/osergios/karta/blob/main/SECURITY.md).
