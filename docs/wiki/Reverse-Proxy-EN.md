[Ελληνικά](Reverse-Proxy) · **English**

# Behind your own reverse proxy

The setup assistant (`./setup.sh`) puts Karta behind a **Cloudflare Tunnel**. If you
already run your own reverse proxy (Caddy, nginx, Traefik) on the server, Karta works just
as well behind it. This page is for people who know how to configure a proxy.

## 1. Karta without the tunnel

In `.env`, **don't** set `COMPOSE_PROFILES=tunnel` (nor `TUNNEL_TOKEN`). Then
`docker compose up -d` starts Karta alone, without `cloudflared`.

The proxy must reach Karta in one of two ways:

- **On the same machine only:** next to `docker-compose.yml`, create a
  `docker-compose.override.yml` (Docker Compose reads it automatically):

  ```yaml
  services:
    karta:
      ports:
        - "127.0.0.1:8000:8000"     # from this machine only, never from the internet
  ```

  The proxy forwards to `127.0.0.1:8000`.
- **On the same Docker network:** if the proxy runs in a container too, put it on the
  same network as Karta. The proxy forwards to `karta:8000`.

Karta **must not** be reachable directly from the internet, only through the proxy.

## 2. Caddy

```
karta.tokatastimamou.gr {
    reverse_proxy 127.0.0.1:8000 {
        header_up X-Real-IP {remote_host}
    }
}
```

Caddy gets the HTTPS certificate by itself.

## 3. nginx

```nginx
server {
    listen 443 ssl;
    server_name karta.tokatastimamou.gr;
    # ssl_certificate / ssl_certificate_key: your certificates (e.g. from certbot)

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## 4. The admin page always needs Cloudflare Access

Karta accepts `/admin` **only** with the token that Cloudflare Access adds (the
`Cf-Access-Jwt-Assertion` header), and checks it against `CF_ACCESS_TEAM_DOMAIN` and
`CF_ACCESS_AUD`. Without it the admin page doesn't open, by design.

So with your own proxy too:

1. the domain goes through Cloudflare (DNS with the orange cloud, "Proxied");
2. Cloudflare Zero Trust has an Access application for `/admin` (see
   [Installation → Protect `/admin`](Installation-EN)).

Your proxy must pass the `Cf-Access-Jwt-Assertion` header through unchanged. Caddy and
nginx do that without any setting.

## 5. The IP of each punch

With every punch, Karta records the device's IP address. It takes it from the
**`CF-Connecting-IP`** header, which Cloudflare itself writes (the domain always goes
through Cloudflare, step 4), replacing whatever the browser sent. Only when that header is
missing does it use your proxy's `X-Real-IP`, and otherwise the proxy's own address.

- Your proxy passes `CF-Connecting-IP` through unchanged. Caddy and nginx do that without
  any setting.
- **Only** Cloudflare may reach the proxy: in the server's firewall, allow ports 80 and 443
  only from [Cloudflare's addresses](https://www.cloudflare.com/ips/). Otherwise anyone who
  goes to the server directly can write that header themselves. Karta itself must not be
  reachable directly either (step 1).
