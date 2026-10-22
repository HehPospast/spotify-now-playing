# Deployment and maintenance

[README](../README.md) · [Русский](deployment.ru.md) · [Configuration](configuration.md)

## Public hosting

The supplied `docker-compose.yml` builds the frontend and Python backend into one container and binds it to `127.0.0.1:8080`. Uvicorn serves **HTTP**, not HTTPS. For public hosting, terminate TLS at a reverse proxy on the same server and serve the application at the root of its own domain; a prefix such as `/spotify/` is not supported.

```text
Browser / OBS -> https://music.example.com:443 -> Caddy or nginx
                                             -> http://127.0.0.1:8080 -> app
```

You need a server with Docker and Compose, a domain whose DNS A/AAAA records point to it, and inbound TCP ports 80 and 443 available to your proxy. Only publish an AAAA record if IPv6 reaches that server. Keep port 8080 bound to loopback as supplied. The repository does not provision DNS, a proxy or certificates automatically.

### Configure Spotify and start the app

Follow the [quick start](../README.md#quick-start) to generate your own `.env` and set your Spotify Client ID. The example values are placeholders, not shared project credentials. Leave Telegram and lyrics disabled until the base deployment works.

Register the public callback in the Spotify Developer Dashboard and set the identical value in `.env`:

```dotenv
SPOTIFY_REDIRECT_URI=https://music.example.com/auth/callback
```

```sh
docker compose up --build -d
curl --fail http://127.0.0.1:8080/healthz
```

After changing an existing `.env`, use `docker compose up -d --force-recreate`. `docker compose restart` does not reload container environment variables.

Configure one proxy below, then open `https://music.example.com/setup` and connect Spotify there. Use this same HTTPS hostname for the entire login flow. The app chooses the OAuth cookie's `Secure` flag from `SPOTIFY_REDIRECT_URI`, not from forwarded headers. The internal proxy-to-app connection can remain HTTP. Starting login through the loopback HTTP address while the callback uses a public HTTPS domain will lose the browser cookie.

Spotify requires HTTPS for remote redirect URIs; local HTTP is allowed only with explicit loopback IPs such as `127.0.0.1` or `[::1]`, not `localhost`. See [Spotify redirect URI rules](https://developer.spotify.com/documentation/web-api/concepts/redirect_uri).

### Caddy on the host: automatic certificates

Use [the example Caddyfile](examples/Caddyfile), replacing `music.example.com` with your domain:

```caddyfile
music.example.com {
    reverse_proxy 127.0.0.1:8080 {
        flush_interval -1
    }
}
```

For a standard Linux Caddy service, copy it to `/etc/caddy/Caddyfile` (merge it if you already host other sites), then run:

```sh
sudo caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
sudo systemctl reload caddy
```

Caddy must already be installed and its service running. With correct DNS and reachable challenge ports, it obtains and renews a public certificate and redirects HTTP to HTTPS. Retain Caddy's data directory so certificate state survives restarts. Access logging is not enabled in this example. See [automatic HTTPS](https://caddyserver.com/docs/automatic-https) and [reverse proxy streaming](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy).

### nginx on the host: existing certificates

Use [the complete nginx example](examples/nginx.conf) in nginx's `http` context, for example `/etc/nginx/sites-available/spotify-now-playing` with a symlink in `sites-enabled` on Debian/Ubuntu. Replace every domain and both certificate paths.

**Provision a valid certificate before enabling this configuration.** The example does not obtain or renew certificates. Use your ACME client (for example Certbot) or hosting provider, arrange renewal, and reload nginx after renewal. A standalone ACME client needs port 80 available while issuing; a webroot challenge needs a separate challenge location. The supplied redirect-only HTTP block does not serve webroot challenge files.

The core proxy settings in the example are:

```nginx
location / {
    proxy_pass http://127.0.0.1:8080;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header Connection "";
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 90s;
    gzip off;
}
```

Validate and reload after installing the complete configuration:

```sh
sudo nginx -t
sudo systemctl reload nginx
```

These commands assume a running Linux nginx service. The complete example redirects HTTP to HTTPS and disables access logs for this virtual host to keep callback query strings out of them. See [nginx proxy directives](https://nginx.org/en/docs/http/ngx_http_proxy_module.html).

### Streaming, embedding and proxy containers

`/api/v1/spotify/public/stream` uses Server-Sent Events (SSE), not WebSockets. It sends a snapshot immediately and keep-alive comments during idle periods (20-second timeout). Disable buffering, caching and response transformations on this path in any additional CDN/proxy, and keep its idle timeout above 20 seconds. Allow iframe embedding for `/widget`; do not add global `X-Frame-Options: DENY` / `SAMEORIGIN` or a restrictive `frame-ancestors` policy if you embed it on another website. The application's setup and OAuth pages deny framing themselves. An HTTPS website needs an HTTPS widget URL to avoid mixed-content blocking.

Both supplied examples assume a proxy installed **on the host**. If the reverse proxy runs in another container, `127.0.0.1` refers to that container itself. Connect both services to the same Docker network and change the upstream to `spotify:8080` (Caddy) or `http://spotify:8080` (nginx). The existing host loopback mapping alone does not connect two containers. Persist the proxy's certificate data separately from `spotify-data`.

Run exactly one Uvicorn worker and one replica per installation. Polling, SSE subscribers, login-attempt limits and lyrics caches are process-local.

## Verify a deployment

Run these from the server (use `curl.exe` in Windows PowerShell):

```sh
docker compose ps
docker compose logs --tail 50 spotify
curl --fail http://127.0.0.1:8080/healthz
curl --fail https://music.example.com/healthz
curl --fail https://music.example.com/setup
curl --fail https://music.example.com/widget
curl --fail https://music.example.com/api/v1/spotify/public/currently-playing
curl --fail --no-buffer --max-time 25 https://music.example.com/api/v1/spotify/public/stream
```

Health should return `{"status":"ok"}` and pages should return HTML. Take an actual `/assets/...js` URL from the returned HTML and request it too: it must return JavaScript rather than an error page. SSE should produce `retry: 5000` and `event: playing` promptly. The final command intentionally ends with curl timeout code 28 after 25 seconds because the stream stays open. Do not use `-k`: a browser must trust the certificate too.

Alternatively, with Python 3.13+ installed, run the same smoke check used by CI. It uses only the Python standard library and does not need your owner password:

```sh
python scripts/check_deployment.py https://music.example.com
```

It waits for health, checks both pages and their JS/CSS assets, reads playback JSON and the initial SSE event, then exits. It can also target `http://127.0.0.1:8080` for a local check.

Before Spotify is connected, an empty playback snapshot is expected. Complete login in a browser and play a supported track to verify real Spotify access. Then check the widget on your HTTPS website or in OBS. CI builds the image and smoke-tests container health, pages, built assets, playback JSON and SSE with synthetic configuration; it does not verify public DNS, TLS issuance or real provider accounts.

| Symptom | Check |
| --- | --- |
| Container exits on startup | Required `.env` values, encryption key and data directory permissions; inspect container logs |
| `502 Bad Gateway` | Local `/healthz`, upstream address, and whether the proxy runs on the host or in Docker |
| Certificate issuance fails | DNS, stale AAAA records, inbound ports, and another service occupying 80/443 |
| Login fails with invalid state | Begin again at the same public HTTPS `/setup`; callback domain and cookie must match |
| Widget updates arrive in batches | SSE buffering, compression or caching at every proxy/CDN layer |
| Page works but iframe is blocked | HTTPS mixed content, proxy framing headers and the parent site's `frame-src` policy |

## Updates

From the directory containing your configured `.env` and Compose file:

```sh
git pull
docker compose up --build -d
```

Keep the same environment file and Compose project name so the application retains its encryption key and existing data volume. If you use a downloaded source archive, replace the source files while preserving `.env`.

## Data and backups

The `spotify-data` named volume stores encrypted SQLite state, including Spotify tokens and the Telegram message ID. The container runs as UID/GID 10001. A custom bind mount must be writable by that user.

Back up the volume together with the matching `.env`. Stop the application before copying database files so SQLite and its write-ahead log are consistent. Keep backups private; the environment file contains the decryption key.

- `docker compose down` preserves the named volume.
- `docker compose down -v` deletes the volume and stored state.
- Changing `ADMIN_KEY` changes only the setup password.
- Losing `TOKEN_ENCRYPTION_KEY` makes the stored state unreadable.

To recover from a lost key, first restore the original key from backup. If it is unavailable, provision a fresh database and key, then reconnect Spotify. A fresh database also loses the old Telegram message ID, so publication starts a new message.

## Logs and health

Access logs are disabled in the supplied Uvicorn command. Configure your proxy to omit or redact query strings on `/auth/callback` so authorization codes and state do not enter access logs. Avoid HTTP debug logging with live credentials.

```sh
docker compose ps
docker compose logs --tail 50 spotify
curl http://127.0.0.1:8080/healthz
```

The health check confirms that the app is serving requests. It does not certify Spotify, Telegram or lyrics-provider availability. See [troubleshooting](configuration.md#troubleshooting) for provider errors.

## Public playback

The widget and playback endpoints are intentionally public. Visitors can see the current track, playback position, pause state, artwork and enabled lyrics. Keep `/setup` owner credentials private. To stop sharing, disconnect Spotify in `/setup` or stop the application.
