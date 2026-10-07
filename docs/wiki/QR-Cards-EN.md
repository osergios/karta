[Ελληνικά](QR-Cards) · **English**

# QR cards and the phone card

Every employee can have a **personal QR card**: an image they keep on their phone (or
printed) and show to the shop screen's camera to punch without typing a PIN.

## Issuing a card

On the admin page, «Σήμερα» → the employee's «Ενέργειες ▾» → **«Έκδοση QR»** (issue
QR). Karta creates a new random code and shows the card image. If they already have a card,
the same item is called **«Κάρτα QR»** and shows that card, with no new code (without
`PIN_KEY` it can't be shown again, so it asks whether you want a new one).

In the card window:

| Button | What it does |
|---|---|
| **«Λήψη εικόνας»** | Download the card as a PNG image. |
| **«Αποστολή»** | On a phone or tablet: send the image with any app. |
| **«Εκτύπωση»** | Print the card. |
| **«Νέα κάρτα»** | New code; the old card and its link stop at once. |
| **«Ακύρωση κάρτας»** | Cancel the card with no replacement; they punch by PIN only. |
| **«Κλείσιμο»** | Close the window. |
| **«Σύνδεσμος για το κινητό»** | Create a personal link for the employee's phone (see below). |

Send the link with the **Viber**, **WhatsApp**, **SMS** or **«Αποστολή…»** buttons, or
with **«Αντιγραφή μηνύματος»** (copy message), which copies a ready-made message («Γεια σου
…! Η κάρτα εργασίας σου για το …») to paste anywhere. The employee opens it, taps
**«Αποθήκευση εικόνας»** and keeps the card in their phone's photos. The page uses your
business name («η προσωπική σου κάρτα εργασίας για το …»).

When you open the card again, it shows the link's status: «Ενεργός σύνδεσμος έως … ·
άνοιξε (N×)» (opened N times) or «δεν έχει ανοίξει ακόμα» (not opened yet), with **«Νέος
σύνδεσμος»** (new link) and **«Ακύρωση συνδέσμου»** (cancel link). (An old link's address
isn't stored; to send it again, make a new one.)

Rules for the link:

- It's valid for **24 hours** and can be opened **10 times** at most.
- It stops working at once if you cancel it or issue a new card.
- It needs `PIN_KEY` in `.env` (see [Configuration](Configuration-EN)). Without it, a card
  can only be shown once, when it's created.

## Replacing or cancelling a card

- Issuing a new card makes the old one stop working immediately (lost phone, card shared
  with someone else…).
- In the card window («Ενέργειες ▾» → «Κάρτα QR»), «Ακύρωση κάρτας» or «Ακύρωση
  συνδέσμου» stops it with no replacement.

## The card on the phone (`/c/…`)

The link opens a page that greets the employee by name and shows their card image, with
short instructions:

1. Tap «Αποθήκευση εικόνας» to save the card to the phone's photos.
2. At the shop, tap «Κάρτα QR» on the shop screen and show the image to the camera, with
   the phone's brightness turned up.
3. Changed phone or lost the image? Ask for a new card.

The card is just a saved image, so it works without mobile data. The page never shows
the PIN or any other personal data. After the link expires, the page only says the link
is no longer valid.

## Card or Ergani QR?

| | Shop QR card | Ergani / myErgani QR |
|---|---|---|
| Who issues it | You, from Karta | Ergani |
| Contains a secret | Yes (random code, stored hashed) | No: a copy works like the original |
| Can be cancelled | Yes, instantly | No |
| Works at the shop screen | Yes | Yes (matched on ΑΦΜ + surname) |

Both work side by side. The shop card is the safer choice.
