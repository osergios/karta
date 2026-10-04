🇬🇷 [Ελληνικά](Alerts-and-Reminders) · 🇬🇧 **English**

# Alerts and reminders

Karta checks who is working every 15 seconds and tells the right people:

| Where | Who sees it | What |
|---|---|---|
| **Shop screen** | Staff | Neutral reminders only: "time to punch in", "time to punch out". Each has a doorbell sound and a Windows notification. |
| **Admin page** | You | Every alert, with full detail («Σήμερα» → «Ειδοποιήσεις»). |
| **Your phone** (ntfy) | You | The same alerts as push notifications. Set `NTFY_URL` / `NTFY_TOPIC`; see [Configuration](Configuration-EN). |

Each alert is raised **once** per person, per day and per kind, so you won't get spammed.
Phone alerts are sent in the background and never slow down a punch.

## Shop‑screen reminders

See [Shop screen → Reminders](Kiosk-EN#reminders-on-the-shop-screen). They repeat every 30
seconds until the person punches. Turn them off with «Υπενθυμίσεις στο κατάστημα» on the
[Today](Admin-Today-EN) tab.

## Phone and admin alerts

| Alert | When |
|---|---|
| Didn't punch in | «Ευελιξία» minutes (default 5) after the start of a scheduled part, if not in. |
| Still in after the end | «Ευελιξία» minutes after the end (or after the end + break «εκτός ωραρίου»). It becomes **urgent** after «Επείγον μετά από» minutes (default 30). It says «μη δηλωμένη υπερωρία — να χτυπήσει αποχώρηση ΤΩΡΑ, με την πραγματική ώρα» when no overtime was declared. |
| Overtime deadline (optional) | «Υπενθύμιση προθεσμίας υπερωρίας» minutes before the deadline to declare overtime, naming who's in. Off by default. |
| Daily / weekly limits, rest | Close to or past the daily limit, past the contractual or legal week, or less than the minimum rest between days. |
| Left early | Punched out before the end of the day (an info note on the admin page, not a phone alert). Record why with «Λόγος…». |
| Work outside the schedule | Punching in on a day without declared hours. |
| Early arrival refused | Someone tried to punch in before their start (once a day per person). |
| Closed day | Someone tried to punch in on a holiday or closure. |
| Punch during leave | Someone on leave punched. |
| "Leaving, didn't punch in" | Someone chose «Φεύγω — ενημέρωσε τη διαχείριση» on the shop screen. |
| Sending problems | A punch was rejected, the Ergani login failed, or a submission is uncertain. See [How punches reach Ergani](Ergani-Submissions-EN). |
| Onboarding period | On its last day and on the first mandatory day. |

## Muting

- **«Θα αργήσει σήμερα (σίγαση)»** mutes one person's punch‑in reminder and "didn't punch
  in" alert for today.
- Leave, holidays and closures mute everything for that person or day.
- Punch‑out notices are never muted.

## Setting up ntfy

1. Install the **ntfy** app on your phone (Android / iOS).
2. Subscribe to a topic with a long, random name, e.g. `karta-7f3k9q2x`. On the public
   server anyone who knows the name can read it.
3. In `.env`: `NTFY_URL=https://ntfy.sh`, `NTFY_TOPIC=karta-7f3k9q2x`. Restart Karta.

You can also run your own ntfy server and use `NTFY_TOKEN` for access control.
Priorities: info = normal, warning = high, urgent = max.
