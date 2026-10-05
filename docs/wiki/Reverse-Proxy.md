**Ελληνικά** · [English](Reverse-Proxy-EN)

# Πίσω από δικό σας reverse proxy

Ο οδηγός ρύθμισης (`./setup.sh`) βάζει την Karta πίσω από **Cloudflare Tunnel**. Αν έχετε
ήδη δικό σας reverse proxy (Caddy, nginx, Traefik) στον server, η Karta δουλεύει εξίσου
καλά πίσω από αυτόν. Αυτή η σελίδα είναι για όσους ξέρουν να ρυθμίζουν proxy.

## 1. Η Karta χωρίς το tunnel

Στο `.env` **μην** βάλετε `COMPOSE_PROFILES=tunnel` (ούτε `TUNNEL_TOKEN`). Τότε το
`docker compose up -d` ξεκινά μόνο την Karta, χωρίς το `cloudflared`.

Ο proxy πρέπει να φτάνει την Karta με έναν από δύο τρόπους:

- **Μόνο στο ίδιο το μηχάνημα:** δίπλα στο `docker-compose.yml` φτιάξτε ένα
  `docker-compose.override.yml` (το Docker Compose το διαβάζει αυτόματα):

  ```yaml
  services:
    karta:
      ports:
        - "127.0.0.1:8000:8000"     # μόνο από το ίδιο μηχάνημα, ποτέ από το internet
  ```

  Ο proxy στέλνει στο `127.0.0.1:8000`.
- **Στο ίδιο δίκτυο Docker:** αν ο proxy τρέχει κι αυτός σε container, βάλτε τον στο
  ίδιο δίκτυο με την Karta. Ο proxy στέλνει στο `karta:8000`.

Η Karta **δεν πρέπει** να είναι προσβάσιμη απευθείας από το internet, μόνο μέσω του proxy.

## 2. Caddy

```
karta.tokatastimamou.gr {
    reverse_proxy 127.0.0.1:8000 {
        header_up X-Real-IP {remote_host}
    }
}
```

Ο Caddy βγάζει μόνος του πιστοποιητικό HTTPS.

## 3. nginx

```nginx
server {
    listen 443 ssl;
    server_name karta.tokatastimamou.gr;
    # ssl_certificate / ssl_certificate_key: τα πιστοποιητικά σας (π.χ. από certbot)

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## 4. Η σελίδα διαχείρισης θέλει πάντα Cloudflare Access

Η Karta δέχεται το `/admin` **μόνο** με το token που προσθέτει το Cloudflare Access
(κεφαλίδα `Cf-Access-Jwt-Assertion`), και το ελέγχει με τα `CF_ACCESS_TEAM_DOMAIN` και
`CF_ACCESS_AUD`. Χωρίς αυτό η σελίδα διαχείρισης δεν ανοίγει, και αυτό γίνεται σκόπιμα.

Άρα και με δικό σας proxy:

1. το domain περνά από το Cloudflare (DNS με το πορτοκαλί σύννεφο, «Proxied»)·
2. στο Cloudflare Zero Trust υπάρχει εφαρμογή Access για το `/admin` (δείτε
   [Εγκατάσταση → Προστατέψτε το `/admin`](Installation)).

Ο proxy σας πρέπει να αφήνει την κεφαλίδα `Cf-Access-Jwt-Assertion` να περνά όπως είναι.
Το Caddy και το nginx το κάνουν χωρίς καμία ρύθμιση.

## 5. Η IP κάθε χτυπήματος: `X-Real-IP`

Η Karta καταγράφει με κάθε χτύπημα τη διεύθυνση IP της συσκευής, από την κεφαλίδα
**`X-Real-IP`**. Αν αυτή λείπει, καταγράφει τη διεύθυνση του proxy.

- Ο proxy πρέπει να **γράφει** την κεφαλίδα ο ίδιος, με τη διεύθυνση που βλέπει, και να
  μην κρατά μια `X-Real-IP` που έστειλε ο browser. Τα παραδείγματα παραπάνω το κάνουν.
- Επειδή η Karta εμπιστεύεται αυτή την κεφαλίδα, πρέπει να τη φτάνει **μόνο** ο proxy
  (βήμα 1).
- Αφού το domain περνά από το Cloudflare (βήμα 4), η διεύθυνση που βλέπει ο proxy είναι
  του Cloudflare. Για την πραγματική διεύθυνση της συσκευής, πάρτε την από την κεφαλίδα
  `CF-Connecting-IP`, αλλά μόνο για αιτήματα που έρχονται από τις
  [διευθύνσεις του Cloudflare](https://www.cloudflare.com/ips/):
  - **Caddy:** στις γενικές ρυθμίσεις `servers { trusted_proxies static <διευθύνσεις Cloudflare>
    ; client_ip_headers CF-Connecting-IP }`, και `header_up X-Real-IP {client_ip}`·
  - **nginx:** `set_real_ip_from <κάθε διεύθυνση Cloudflare>;` και
    `real_ip_header CF-Connecting-IP;`. Τότε το `$remote_addr` είναι η πραγματική
    διεύθυνση.
