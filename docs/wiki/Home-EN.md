🇬🇷 [Ελληνικά](Home) · 🇬🇧 **English**

# Karta wiki

**Karta** is a self-hosted digital work card (*ψηφιακή κάρτα εργασίας*) for small Greek
businesses. Staff clock in and out on a shop screen with a PIN or a QR code, and Karta
sends every arrival and departure to **Ergani II**. The owner manages everything from a
web admin page, and the accountant gets monthly and yearly Excel reports.

The app's screens are in Greek, and so is the main version of this wiki. These English
pages quote every button or label exactly as it appears on screen, e.g. «Αποχώρηση…».

## Start here

| If you want to… | Read |
|---|---|
| Install Karta on a server | [Installation](Installation-EN) |
| Look up a setting in `.env` | [Configuration](Configuration-EN) |
| Move from testing to real Ergani submissions | [Going live](Going-Live-EN) |
| Set up the shop laptop or tablet | [Shop screen (kiosk)](Kiosk-EN) |
| Give staff a QR card on their phone | [QR cards and the phone card](QR-Cards-EN) |

## The admin page, tab by tab

| Tab | What it's for |
|---|---|
| «Σήμερα» | [Today](Admin-Today-EN): who's in, who's coming, forgotten punch-outs, alerts |
| «Προσωπικό» | [Staff](Admin-Staff-EN): employee cards and the «Ενέργειες ▾» menu (leave, overtime, PIN, QR…) |
| «Ωράρια & αργίες» | [Schedules and holidays](Admin-Schedules-and-Holidays-EN) |
| «Αναφορές» | [Reports](Admin-Reports-EN): monthly and yearly Excel files for the accountant |
| «Ρυθμίσεις» | [Settings](Admin-Settings-EN): Ergani check, limits, business details, devices, movements |

## How it works

- [How punches reach Ergani](Ergani-Submissions-EN): the sending queue, statuses, late declarations, and what happens when Ergani doesn't answer
- [Alerts and reminders](Alerts-and-Reminders-EN): shop-screen reminders and phone notifications (ntfy)
- [Security and privacy](Security-and-Privacy-EN)
- [FAQ and troubleshooting](FAQ-EN)

## A typical day

1. **Morning:** an employee taps their name on the shop screen and enters their PIN, or
   shows their QR card to the camera. Karta records the arrival and sends it to Ergani
   within seconds.
2. **During the day:** the owner's phone gets an alert if someone hasn't punched in a few
   minutes after their declared start time. The shop screen also shows a reminder card and
   plays a doorbell sound.
3. **End of shift:** the shop screen counts down the last two minutes, then reminds the
   person to punch out. Staying on without declared overtime triggers a phone alert.
4. **End of month:** the owner downloads the monthly report from «Αναφορές» and sends it
   to the accountant. It covers hours, extra hours, leave, forgotten punches and the
   retrospective declarations (*απολογιστικές δηλώσεις*) to file.
