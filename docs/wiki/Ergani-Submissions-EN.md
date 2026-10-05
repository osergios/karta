[Ελληνικά](Ergani-Submissions) · **English**

# How punches reach Ergani

Every punch is first **saved in Karta's database**, then sent to Ergani by a background
queue. The shop screen never waits for Ergani: if Ergani is slow or down, the punch is
safe and is sent as soon as possible.

## Movement statuses

You'll see these in «Ρυθμίσεις» → «Κινήσεις» and in the reports.

| Status | Meaning |
|---|---|
| «Υποβλήθηκε» | Accepted by Ergani; the protocol number is stored. |
| «Σε αναμονή» | Waiting to be sent, or waiting to retry after an error. |
| «Απέτυχε» | Still not accepted after 30 attempts. Check the error and retry by hand. |
| «Προς έλεγχο στο ΕΡΓΑΝΗ» | **Uncertain**: the request may have reached Ergani, but no clear answer came back. See below. |
| «Δοκιμή (δεν στάλθηκε)» | Made in `dry_run`; never sent. |
| «Μόνο στην κάρτα (δεν στάλθηκε)» | Entered by the admin in Karta only (forgotten punch / forgotten shift). Never sent. |
| «Προσαρμογή (δεν στάλθηκε)» | Made during the onboarding period. Never sent. |

## Retries

If sending fails, Karta tries again with a growing pause: 1 minute, then 2, then 3, up to
15 minutes between attempts. It stops after 30 attempts («Απέτυχε»). Errors raise an
alert:

- **Login rejected:** usually a wrong or expired Ergani password in `.env`.
- **Ergani rejected the punch:** the alert shows Ergani's own message. Ergani rejections
  stay on the admin page until you mark them done.
- **Ergani down** (HTTP 5xx) or **no connection:** retried automatically.

## Late declarations

If a punch reaches Ergani more than `LATE_THRESHOLD_SECONDS` (default 120) after it
happened, it's sent as a **late declaration** with a justification code:

| Code | Reason | When Karta uses it |
|---|---|---|
| 001 | Power outage («Διακοπή ρεύματος») | Only when you choose it with «Τεχνικό πρόβλημα». |
| 002 | Employer's systems unavailable | Automatically when the Ergani login failed, or by your choice with «Τεχνικό πρόβλημα». |
| 003 | Ergani's systems unavailable | Automatically when Ergani was down, rejected the request, or couldn't be reached. |

The code is chosen from the **first** failure and kept for the later retries. If you
know the real cause was different (e.g. a power cut in the shop), record the punch with
«Τεχνικό πρόβλημα» and pick the right code.

**A forgotten punch is never declared late.** It isn't a technical fault, so no code
applies. Close it with «Ξέχασε να χτυπήσει» instead (Karta only, never sent).

## Uncertain submissions («Προς έλεγχο»)

Sometimes the request may have reached Ergani but the answer was lost: the reply timed
out, the connection dropped mid‑answer, a gateway gave HTTP 504, or the reply couldn't be
read. Sending again could **declare the same punch twice**, so Karta does **not** retry
these. Instead:

1. It raises an urgent alert.
2. You check in Ergani whether the punch is there.
3. In «Κινήσεις», you choose:
   - **«Υπάρχει στο ΕΡΓΑΝΗ»:** it's there. Optionally type the protocol number.
   - **«Δεν υπάρχει — νέα αποστολή»:** it's not there; send it again.

Failures that certainly happened **before** anything was sent (DNS failure, connection
refused, login rejected) are always retried automatically.

## The modes are separate worlds

Each punch remembers the mode it was made in (`dry_run`, `trial`, `production`). The
in/out state, alerts and reports only consider the current mode. See
[Going live](Going-Live-EN).
