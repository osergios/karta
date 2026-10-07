[Ελληνικά](Disaster-Recovery) · **English**

# Disaster recovery

Karta's machine is gone: the **VPS** was deleted (e.g. the Oracle Cloud account was closed) or
the **PC / Raspberry Pi** broke, was stolen or destroyed. This page brings you back on a new
machine, with all data up to the last backup. The steps are the same in both cases; where
they differ, it says so.

Time: about an hour.

The **encryption password** is all you need: the cloud backup holds the database **and** the
key that locks the Ergani password, the PINs and the QR cards inside it (`PIN_KEY`). Karta
takes it over by itself when restoring.

## What you need

| What | Why |
|---|---|
| **The encryption password** of the backups | The one you wrote on paper or in a password manager. Without it the cloud backups can't be opened. |
| **The cloud account** | The same Google Drive, Dropbox or Backblaze B2 account the backups went to. Don't touch the folder there (`data`, `index`, `keys`, `locks`, `snapshots`, `config`). |
| **The Cloudflare account** | Your domain is there. |
| **A new machine** | A VPS, or a PC / Raspberry Pi with Ubuntu, as in [Easy installation](Easy-Installation-EN#step-2-prepare-the-machine). |

> **A local machine with a USB backup that survived?** See [With USB](#with-usb-local-machine-only):
> it's simpler, and the USB has the `.env` too.

## Until Karta is back

- The shop screen doesn't work. Staff punch with the **Ergani app on their phone** (the
  screen says the same when it's offline). Those punches go straight to Ergani.
- If the old machine still exists somewhere (e.g. a VPS that was "deleted" but came back),
  **switch it off** before you start. Two Karta installations with the same data could
  send the same punches to Ergani twice.

## Step 1: A new machine

- **VPS:** create a new VPS and connect with SSH
  ([Option C: Oracle Cloud](Easy-Installation-EN#option-c-oracle-cloud-always-free)).
- **Local:** a PC, laptop or Raspberry Pi with Ubuntu
  ([Option A](Easy-Installation-EN#option-a-raspberry-pi) /
  [Option B](Easy-Installation-EN#option-b-old-pc-or-laptop)).

## Step 2: Install Karta with the setup assistant

Do [steps 3–5 of Easy installation](Easy-Installation-EN#step-3-connect-to-the-machine-and-start-the-setup-assistant),
with the same answers as the first time:

- **The same address** (e.g. `karta.tokatastimamou.gr`) and the same admin emails.
- **"1" for a local machine, "2" for a VPS.**
- A **new Cloudflare key** ([step 4](Easy-Installation-EN#step-4-create-a-cloudflare-key)).
  The assistant reuses the tunnel and the admin page protection, which live in Cloudflare
  and weren't lost.
- **"y"** to the nightly backup.

**Don't set anything up on the admin page** («Πρώτα βήματα», employees, Ergani): it all comes
from the backup.

## Step 3: Connect the cloud to the existing backups

Open the admin page (`https://…/admin`) → **«Ρυθμίσεις» → «Αντίγραφα ασφαλείας»**:

1. **«Πού»** (where): the same provider (e.g. Google Drive).
2. A new access code, as the page says (for Google Drive: `rclone authorize "drive"`),
   **with the same Google account**. Paste it.
3. Open **«Έχω ήδη αντίγραφα στο cloud»**, type the **encryption password** and press
   **«Σύνδεση στα υπάρχοντα αντίγραφα»**.

Don't press «Σύνδεση και πρώτο ανέβασμα»: that's for new backups (and it will tell you some
already exist).

## Step 4: Restore

1. On the same page: **«Επαναφορά» → «Από το cloud…»**.
2. Pick the **most recent** backup and press **«Έλεγχος αντιγράφου»** (check backup).
3. Check what it says: business name, number of employees and the **date of the last
   punch**. It should be the last day the old machine worked. It also says that the backup's
   own key (`PIN_KEY`) will be used automatically.
4. **«Επαναφορά τώρα»** (restore now).

Within seconds Karta has everything it had: employees (PINs and QR cards work as before),
schedules, leave, punches, settings, the mode (e.g. «Κανονική λειτουργία») and the registered
shop screens.

## Step 5: Check

- **«Ρυθμίσεις» → «Επιχείρηση και σύνδεση με το ΕΡΓΑΝΗ» → «Δοκιμή σύνδεσης».**
  If the backup is from a version before 1.7.5 (without the key), type the Ergani
  web-services user's password again and press «Αποθήκευση»; the same for the ntfy token,
  if you had one.
- **«Λειτουργία»** (mode): the same as before.
- **«Αντίγραφα ασφαλείας»:** press **«Ανέβασμα τώρα»**, for a first backup from the new machine.
- On the machine: `cd ~/karta && ./setup.sh check`.

## Step 6: The shop screen

- **VPS** (the shop device survived): open Karta's address as always. It works as before,
  because its registration is in the backup.
- **Local** (the screen was the same machine that was lost), or if it says «Η συσκευή δεν
  είναι εγγεγραμμένη»: register the device again: «Ρυθμίσεις» → «Συσκευές» → «Δημιουργία
  κωδικού εγγραφής» and `/enroll` on the device ([Shop screen](Kiosk-EN#registering-the-device)).
  You can delete the old one from the list.

## Step 7: Punches during the gap

Whatever happened after the last backup (the cloud copy goes up every night at 23:40) until
Karta came back isn't in Karta:

- **Ergani has it all:** what Karta sent that day and what staff punched with the Ergani app.
  The legal record is complete.
- **For Karta's reports to be right,** add those shifts with «Σήμερα» → the person's
  «Ενέργειες ▾» → **«Ξεχασμένη βάρδια…»** (forgotten shift). They go into Karta only and
  are never sent to Ergani again.

## With USB (local machine only)

If you had set up USB backups (`./setup.sh usb`) and the USB stick survived, it has the
nightly backup **and** the `.env` (with the `PIN_KEY`).

1. Do [steps 1 and 2](#step-1-a-new-machine).
2. Plug the USB into the new machine and run:

   ```bash
   cd ~/karta && ./setup.sh usb
   ./setup.sh restore
   ```

   Choose **"2) από USB"** (from USB) and the most recent backup. When asked about the
   backup's `PIN_KEY`, answer **"y"**.
3. Continue with [steps 5–7](#step-5-check).
4. Reconnect the cloud as in [step 3](#step-3-connect-the-cloud-to-the-existing-backups)
   (with «Έχω ήδη αντίγραφα στο cloud» and the encryption password), so the backups carry on
   in the same folder.

## Be ready, starting now

- Keep the **encryption password** on paper or in a password manager («Εμφάνιση κωδικού
  κρυπτογράφησης» shows it again). It's the only thing you need.
- Print this page and keep it with it.
