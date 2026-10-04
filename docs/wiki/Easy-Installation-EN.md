🇬🇷 [Ελληνικά](Easy-Installation) · 🇬🇧 **English**

# Easy installation, step by step

This guide is for people who are **not** programmers. At the end, Karta runs on a small
machine with a secure connection (HTTPS) on your own name, e.g.
`https://karta.yourshop.gr`, **without** touching your router's settings.

Plan on about **1–2 hours** the first time. If you get stuck, see the [FAQ](FAQ-EN) or ask
in [Discussions](https://github.com/osergios/karta/discussions/categories/q-a).

> If you're more experienced, the short version is [Installation](Installation-EN).

---

## Step 0: What you need

| | What | Cost |
|---|---|---|
| 1 | **A domain name**, e.g. `yourshop.gr` | about €10–20 a year |
| 2 | **A machine that stays on** (see below) | €0 (old PC or free cloud) or ~€60–100 for a Raspberry Pi |
| 3 | **A free Cloudflare account** | €0 |
| 4 | **An Ergani web‑services user** (your accountant can create it, or you can in Ergani) | €0 |

### "Can I do it without a domain?"

Unfortunately **not** for real use, for two reasons:

- The admin page is protected by **Cloudflare Access**, which only works on a domain you
  have on Cloudflare.
- The camera for QR cards and the shop screen's cookie only work over **HTTPS**, which
  Cloudflare provides for free on your domain.

The domain is the **only** certain cost. Everything else can be free.

### Which machine?

| Option | Pros | Cons |
|---|---|---|
| **A. Raspberry Pi 4 or 5** (2 GB RAM or more), at the shop or at home | Small, silent, ~5 W of power (a few euros a year). Your data stays with you. | Purchase cost. If power or internet fails there, Karta is unavailable. |
| **B. An old laptop or small PC** | Free if you already have one. A laptop's battery rides through power cuts. | Uses more power; same internet caveat. |
| **C. Free cloud: Oracle Cloud "Always Free"** | Always on, fast internet, €0. | Needs a card for verification. Sign‑up sometimes says "out of capacity". Oracle may reclaim machines that are almost completely idle; keep backups. |

**Personal data (GDPR):** Karta stores details about your staff. If you choose a cloud,
pick a **region inside the European Union** (e.g. Frankfurt, Amsterdam, Milan).

**Where should it live?** The shop screen talks to Karta over the shop's internet
connection. If the shop's internet goes down, the screen says so and staff punch through
the Ergani app instead. That's true wherever Karta runs.

---

## Step 1: Get a domain and put it on Cloudflare

1. Create a free account at [cloudflare.com](https://dash.cloudflare.com/sign-up).
2. Buy a domain:
   - **`.com` / `.eu` etc.:** straight from Cloudflare (**Domain Registration → Register
     Domains**), at cost price. It's on Cloudflare automatically: go to step 2.
   - **`.gr`:** from a Greek registrar. Then, in Cloudflare, click **Add a domain**, choose
     the **Free** plan, and Cloudflare gives you two **nameservers**. On the registrar's
     site, change the domain's nameservers to those two. The change takes from a few
     minutes up to 24 hours; Cloudflare emails you when it's ready.

If you already have a domain for your website, you can use a **subdomain** of it, e.g.
`karta.yourshop.gr`, without affecting the website.

---

## Step 2: Prepare the machine

Choose **one** of the three options.

### Option A: Raspberry Pi

1. You need: a Raspberry Pi 4 or 5, its power supply, a good‑quality 32 GB microSD card (or,
   better, a USB SSD), and a network cable (better than Wi‑Fi).
2. On a computer, download [Raspberry Pi Imager](https://www.raspberrypi.com/software/).
3. Choose: device → your model; operating system → **Raspberry Pi OS Lite (64‑bit)**;
   storage → your card.
4. In **Edit settings**, set: a hostname (e.g. `karta`), a **username and password**, and on
   the **Services** tab turn on **SSH** with password login.
5. Write the card, put it in the Pi, connect the network cable and power. Wait 2 minutes.

### Option B: Old PC or laptop

1. Download [Ubuntu Server LTS](https://ubuntu.com/download/server) and write it to a USB
   stick with [balenaEtcher](https://etcher.balena.io/).
2. Boot the PC from the USB stick and install (the defaults are fine). Set a username and
   password, and tick **Install OpenSSH server**.
3. On a laptop: set it **not to sleep when the lid is closed**. Ask if you need help; it's
   one setting.

### Option C: Oracle Cloud Always Free

1. Sign up at [oracle.com/cloud/free](https://www.oracle.com/cloud/free/). During sign‑up,
   choose a **Home Region** inside the EU (it can't be changed later).
2. **Compute → Instances → Create instance**:
   - Image: **Ubuntu** (22.04 or newer);
   - Shape: **Ampere (VM.Standard.A1.Flex)**, 1 OCPU and 6 GB memory (within the free limits);
   - download the **SSH key** it offers (you need it to connect).
3. Click **Create**. Note the machine's **Public IP**.

You don't need to open any port in Oracle's firewall: the tunnel from step 4 connects
outwards.

---

## Step 3: Connect to the machine and install Docker

On your computer, open a terminal (Windows: **PowerShell**; Mac: **Terminal**) and connect:

```bash
ssh USERNAME@karta.local          # Raspberry Pi on the same network
ssh USERNAME@192.168.1.50         # or with the machine's IP address
ssh -i key.key ubuntu@PUBLIC_IP   # Oracle Cloud
```

Then copy and run these commands one by one:

```bash
sudo apt update && sudo apt -y upgrade
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
exit
```

Connect again with `ssh` (so the last command takes effect) and check:

```bash
docker run --rm hello-world
```

If you see "Hello from Docker!", all is well.

---

## Step 4: Create the Cloudflare Tunnel

The tunnel is a secure "line" from your machine to Cloudflare. It makes Karta reachable at
`https://karta.yourshop.gr` with no open ports on your router.

1. In Cloudflare, open **Zero Trust** (left menu). The first time: choose a **team name**
   (e.g. `yourshop`) and the **Free** plan (up to 50 users). It may ask for a card, but the
   Free plan doesn't charge.
2. Go to **Networks → Tunnels → Create a tunnel → Cloudflared**. Give it a name (e.g.
   `karta`) and click **Save**.
3. The next page shows a command with a long **token** (after `--token`). **Copy only the
   token** and keep it; you don't need to run the command.
4. Click **Next**. Under **Public hostname**:
   - Subdomain: `karta` · Domain: your domain;
   - Service: **Type** `HTTP`, **URL** `karta:8000`.
5. Click **Save tunnel**.

> Cloudflare renames its menus from time to time. If you can't find something, search for
> "Tunnels" inside Zero Trust.

---

## Step 5: Protect the admin page (Cloudflare Access)

1. In Zero Trust: **Access → Applications → Add an application → Self‑hosted**.
2. Name: `Karta admin`. Under **Public hostname / Application domain**: subdomain `karta`,
   your domain, and in **Path** type `admin`.
3. Add a **policy**: Action **Allow**, rule **Emails** → your email address (and anyone else
   who should have access).
4. Save. The default login method, **One‑time PIN** (a code sent to your email), is enough.
5. Open the application you created and copy its **Application Audience (AUD) Tag**. You
   need it in the next step.

---

## Step 6: Download and configure Karta

On the machine (through `ssh`):

```bash
mkdir ~/karta && cd ~/karta
curl -fsSLO https://raw.githubusercontent.com/osergios/karta/main/docker-compose.yml
curl -fsSL  https://raw.githubusercontent.com/osergios/karta/main/.env.example -o .env
python3 -c "import os,base64;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
nano .env
```

The third command prints a random key: copy it for `PIN_KEY`. In `nano`, fill in (move with
the arrow keys):

| Line | What to put |
|---|---|
| `ERGANI_MODE=` | `dry_run` (**always** this at first) |
| `ERGANI_USERNAME=` / `ERGANI_PASSWORD=` | your Ergani web‑services user |
| `EMPLOYER_AFM=` | the business's ΑΦΜ |
| `BRANCH_NUMBER=` | the branch number (usually `0`) |
| `CF_ACCESS_TEAM_DOMAIN=` | `yourshop.cloudflareaccess.com` (your team name + `.cloudflareaccess.com`) |
| `CF_ACCESS_AUD=` | the AUD tag from step 5 |
| `ADMIN_EMAILS=` | your email (the same as in the policy) |
| `PUBLIC_ORIGIN=` | `https://karta.yourshop.gr` |
| `PIN_KEY=` | the key the command printed |
| `TUNNEL_TOKEN=` | the token from step 4 |

Save with **Ctrl+O**, **Enter**, and exit with **Ctrl+X**. `.env` contains passwords: never
send it anywhere.

You can fill in `NTFY_*` (phone alerts) later; see [Alerts](Alerts-and-Reminders-EN).

---

## Step 7: Start Karta

```bash
cd ~/karta
docker compose up -d
docker compose ps
```

Both lines (`karta` and `cloudflared`) should say **running** or **Up**. After a minute,
open in your browser:

- `https://karta.yourshop.gr/healthz` → you should see `{"ok":true,"mode":"dry_run"}`.
- `https://karta.yourshop.gr/admin` → Cloudflare asks for your email, sends you a code, and
  then you see the admin page.

Karta starts by itself whenever the machine boots.

**Something wrong?** See what it says:

```bash
docker compose logs --tail 50 karta
docker compose logs --tail 50 cloudflared
```

Common mistakes: a wrong or empty value in `.env` (Karta says which one is missing), a wrong
tunnel token, or a wrong `PUBLIC_ORIGIN` (it must be exactly the address, with `https://`
and no `/` at the end).

---

## Step 8: First setup and the shop screen

Continue from [Installation → First login and setup](Installation-EN#5-first-login-and-setup):
import your staff from Ergani, set the name and logo, check the schedules, and register the
shop laptop ([Shop screen](Kiosk-EN)).

When everything works, follow [Going live](Going-Live-EN) to move from `dry_run` to the
real Ergani.

---

## Step 9: Backups (important!)

All your data is in one file. These commands create a small script that keeps a dated copy
(and deletes anything older than the last 30), and run it once to test it:

```bash
cat > ~/karta/backup.sh <<'SH'
#!/bin/sh
# Karta: nightly copy of the database, keeping the last 30
set -e
cd "$(dirname "$0")"
mkdir -p backups
docker compose exec -T karta python -c "import sqlite3; s=sqlite3.connect('/data/workcard.db'); d=sqlite3.connect('/data/backup.db'); s.backup(d); d.close()"
docker compose cp karta:/data/backup.db "backups/karta-$(date +%F).db"
ls -1t backups/karta-*.db | tail -n +31 | xargs -r rm --
SH
chmod +x ~/karta/backup.sh
~/karta/backup.sh && ls ~/karta/backups
```

To run it **automatically every night** at 23:30, type `crontab -e` (the first time, choose
`nano`) and add this line at the end:

```text
30 23 * * * $HOME/karta/backup.sh
```

The copy must also leave **the machine**: regularly copy the `backups` folder to a USB stick
or another computer, and keep your `.env` safe. If the Raspberry Pi's card fails, without a
backup the data is lost.

---

## Updating to a new version

When a new version comes out ([Releases](https://github.com/osergios/karta/releases)):

```bash
cd ~/karta
docker compose pull
docker compose up -d
```

Then click **«Σήμερα» → «Οθόνη καταστήματος και αποστολή» → «Ανανέωση οθόνης»**.
