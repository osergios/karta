[Ελληνικά](Home) · **English**

# Karta wiki

**Karta** is a self-hosted digital work card (*ψηφιακή κάρτα εργασίας*) for small Greek
businesses. Staff clock in and out on a shop screen with a PIN or a QR code, and Karta
sends every arrival and departure to **Ergani II**. The owner manages everything from a
web admin page, and the accountant gets monthly and yearly Excel reports.

> **Disclaimer.** Karta is provided "as is", without any warranty, and is not official
> Ministry software. The employer alone is responsible for Ergani declarations, fines,
> backups and personal data. See the full [disclaimer](Disclaimer-EN).

The app's screens are in Greek, and so is the main version of this wiki. These English
pages quote every button or label exactly as it appears on screen, e.g. «Αποχώρηση…».

## Start here

| If you want to… | Read |
|---|---|
| Install Karta without being a programmer (Raspberry Pi, old PC or free cloud server) | [Easy installation, step by step](Easy-Installation-EN) |
| Install Karta on a server (short version) | [Installation](Installation-EN) |
| Look up a setting in `.env` | [Configuration](Configuration-EN) |
| Move from testing to real Ergani submissions | [Going live](Going-Live-EN) |
| Keep punches safe for years (USB, cloud, restore) | [Backups and restore](Backups-EN) |
| Set Karta up again if the machine is lost (VPS or local) | [Disaster recovery](Disaster-Recovery-EN) |
| Set up the shop laptop or tablet | [Shop screen (kiosk)](Kiosk-EN) |
| Give staff a QR card on their phone | [QR cards and the phone card](QR-Cards-EN) |

## The admin page, tab by tab

| Tab | What it's for |
|---|---|
| «Σήμερα» | [Today](Admin-Today-EN): every employee (who's in, who's coming, who's off) with the «Ενέργειες ▾» menu (leave, overtime, PIN, QR…), forgotten punch-outs, alerts |
| «Ωράρια & αργίες» | [Schedules and holidays](Admin-Schedules-and-Holidays-EN) |
| «Αναφορές» | [Reports](Admin-Reports-EN): monthly and yearly Excel files for the accountant |
| «Ρυθμίσεις» | [Settings](Admin-Settings-EN): business and Ergani connection (mode, ΑΦΜ, Ergani user), Ergani check, limits and alerts, phone notifications, backups, version and update, business details, devices, movements |

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
