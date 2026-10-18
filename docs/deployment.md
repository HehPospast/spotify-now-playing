# Deployment and maintenance

[README](../README.md) · [Русский](deployment.ru.md) · [Configuration](configuration.md)

## Public hosting

The supplied `docker-compose.yml` binds the application to `127.0.0.1:8080`. Place an HTTPS reverse proxy in front of this address and serve the application at the root of its own domain.

Register the public callback in the Spotify Developer Dashboard and set the identical value in `.env`:

```dotenv
SPOTIFY_REDIRECT_URI=https://music.example.com/auth/callback
```

Recreate the container and connect through `https://music.example.com/setup`. HTTPS callbacks enable secure OAuth cookies automatically.

For nginx, forward requests to `http://127.0.0.1:8080`, use HTTP/1.1, and set `proxy_buffering off` and `proxy_read_timeout 90s` for `/api/v1/spotify/public/stream`. The stream needs a persistent connection. Allow iframe embedding for `/widget`; the application's setup and OAuth pages deny framing.

If the reverse proxy runs in another container, `127.0.0.1` refers to that container itself. Connect the services through an appropriate Docker network and use the application's service address for upstream requests.

Run exactly one Uvicorn worker and one replica per installation. Polling, SSE subscribers, login-attempt limits and lyrics caches are process-local.

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
