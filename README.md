# Spotify Now Playing

Share what you're listening to on your website, in OBS, or in Telegram.

[Русский](README.ru.md) · [Configuration](docs/configuration.md) · [Deployment](docs/deployment.md)

![Spotify widget with live playback and synchronized lyrics](docs/media/spotify-widget.gif)

## What it does

- Shows the current track, artist, album artwork and playback progress in a terminal-style widget.
- Follows lyrics line by line or syllable by syllable, with manual scrolling and reduced-motion support.
- Updates one Telegram message as you change tracks, pause and resume.
- Runs in a single Docker container with persistent Spotify login and message state.

Each installation connects one Spotify account. Lyrics and Telegram are optional.

## Quick start

Clone the repository and enter its directory:

```sh
git clone https://github.com/HehPospast/spotify-now-playing.git
cd spotify-now-playing
```

You need Docker with Compose and your own [Spotify developer application](https://developer.spotify.com/dashboard). Spotify's [development-mode restrictions](https://developer.spotify.com/documentation/web-api/concepts/quota-modes) apply to the connected account.

### 1. Register the Spotify callback

In your Spotify application's settings, enable Web API access and add:

```text
http://127.0.0.1:8080/auth/callback
```

Copy the **Client ID**. A client secret is not required. Use `127.0.0.1` throughout setup, including in your browser.

### 2. Create your configuration

From the repository root, run this command in Bash or PowerShell:

```sh
docker run --rm -v "${PWD}:/work" -w /work python:3.13-slim python scripts/configure.py
```

On Linux, add `--user "$(id -u):$(id -g)"` after `--rm` so the generated file belongs to your user.

This creates `.env` with a random owner password and encryption key. It leaves an existing `.env` untouched. If you already have Python installed, you can use `python scripts/configure.py` instead.

Open `.env` and set `SPOTIFY_CLIENT_ID` to your application's Client ID. Keep this file private and retain its encryption key when upgrading.

### 3. Start and connect

```sh
docker compose up --build -d
```

Open [the setup page](http://127.0.0.1:8080/setup), enter the `ADMIN_KEY` from `.env`, and click **Connect with Spotify**. Your player is then available at [127.0.0.1:8080/widget](http://127.0.0.1:8080/widget).

For a public installation, follow the [deployment guide](docs/deployment.md) for HTTPS, your domain's callback URL, ready-to-adapt [Caddy](docs/examples/Caddyfile) / [nginx](docs/examples/nginx.conf) configurations and deployment checks.

## Enable lyrics or Telegram

| Integration | Add to `.env` | Setup |
| --- | --- | --- |
| Synchronized lyrics | `SPICY_LYRICS_SECRET_KEY` | [Spicy Lyrics](docs/configuration.md#lyrics) |
| Telegram message | `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` | [Telegram bot](docs/configuration.md#telegram) |

After editing `.env`, apply the changes:

```sh
docker compose up -d --force-recreate
```

Telegram posts an `Artist - Track` link and edits that same message for subsequent tracks. Paused or inactive playback displays `Not listening to anything right now`. Set `TELEGRAM_LANGUAGE=ru` in `.env` for Russian; the default is `en`. This setting affects Telegram only. The message ID survives restarts.

Lyrics are provided by [Spicy Lyrics](https://developers.spicylyrics.org/), with source and contributor credits shown in the widget.

## Embed the widget

Replace the example domain with your installation's address:

```html
<iframe
  src="https://music.example.com/widget"
  title="Spotify now playing"
  width="100%"
  height="400"
  style="border:0"
  loading="lazy"
></iframe>
```

The page background is transparent and the widget fills the available width. For OBS, add the widget URL as a browser source; 680 x 400 is a useful starting size.

**Playback is public.** Anyone with access to the widget can see your current track and enabled lyrics. Spotify tokens remain on the server. You can disconnect through `/setup` and revoke access in [Spotify account settings](https://www.spotify.com/account/apps/).

## Documentation

- [Configuration and troubleshooting](docs/configuration.md): environment variables, Spotify access, lyrics and Telegram setup.
- [Deployment and maintenance](docs/deployment.md): HTTPS, persistence, updates and backups.
- [Security](SECURITY.md): credentials and vulnerability reporting.

## License

[MIT](LICENSE). External services, artwork and lyrics retain their own terms and rights; see [third-party notices](THIRD_PARTY_NOTICES.md).
