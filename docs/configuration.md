# Configuration

[README](../README.md) · [Русский](configuration.ru.md) · [Deployment](deployment.md)

Settings are read from environment variables. Docker Compose loads them from the repository's `.env`. Start with [.env.example](../.env.example); never commit your populated configuration.

## Environment variables

| Variable | Purpose | Default |
| --- | --- | --- |
| `SPOTIFY_CLIENT_ID` | Client ID of your Spotify application | Required |
| `SPOTIFY_REDIRECT_URI` | Exact callback registered in Spotify | `http://127.0.0.1:8080/auth/callback` |
| `ADMIN_KEY` | Owner password, at least 32 characters | Required |
| `TOKEN_ENCRYPTION_KEY` | URL-safe Base64 Fernet key containing 32 random bytes | Required |
| `DATABASE_PATH` | SQLite file location | `data/state.sqlite3`; Compose sets `/data/state.sqlite3` |
| `POLL_INTERVAL_SECONDS` | Spotify polling interval in seconds, from 5 to 300 | `10` |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token | Empty |
| `TELEGRAM_CHAT_ID` | Telegram channel or chat destination | Empty |
| `SPICY_LYRICS_SECRET_KEY` | Server-side Spicy Lyrics application key | Empty |

The configuration helper creates the owner password and encryption key. It refuses to overwrite an existing `.env`. You can change `ADMIN_KEY` independently; changing the encryption key does not re-encrypt existing data.

After changing configuration, recreate the container:

```sh
docker compose up -d --force-recreate
```

## Spotify

Create an application with Web API access in the [Developer Dashboard](https://developer.spotify.com/dashboard). Register `SPOTIFY_REDIRECT_URI` exactly, including the scheme, port and `/auth/callback` path.

For local HTTP use `127.0.0.1` or `[::1]`. Remote callbacks require HTTPS. `localhost` is not an accepted redirect hostname. See [Spotify's redirect rules](https://developer.spotify.com/documentation/web-api/concepts/redirect_uri).

The app uses Authorization Code with PKCE and requests only `user-read-currently-playing`. Login starts at `/setup` and requires the owner password. Use the same hostname through the login flow so the browser can return its OAuth cookie.

Development-mode applications have Premium and account-allowlist requirements. Consult [Spotify quota modes](https://developer.spotify.com/documentation/web-api/concepts/quota-modes) for current limits. Each self-hosted installation should use its own Spotify application.

All widget viewers and Telegram share a single Spotify poller. The browser advances the progress bar between updates. Rate limits can delay observations; unsupported media such as podcasts, ads and local files appear as idle playback.

Disconnecting in `/setup` deletes local Spotify tokens and clears the current widget state. To revoke Spotify's authorization, remove the application in [your account settings](https://www.spotify.com/account/apps/).

## Telegram

1. Create a bot with [@BotFather](https://t.me/BotFather).
2. Add it to your channel as an administrator with permission to post and edit its own messages. For a direct chat, send `/start` to the bot first.
3. Set both `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.

```dotenv
TELEGRAM_BOT_TOKEN=your-bot-token
TELEGRAM_CHAT_ID=@your_channel
```

Public channels accept an `@username`. Private channels use a numeric chat ID with the `-100` prefix; direct chats use their numeric chat ID. Telegram's [getUpdates](https://core.telegram.org/bots/api#getupdates) method can identify the destination after a message or channel post. It is unavailable while a webhook is set. Inspect responses locally and keep the bot token private.

The integration sends a single text message using [sendMessage](https://core.telegram.org/bots/api#sendmessage), then updates it using [editMessageText](https://core.telegram.org/bots/api#editmessagetext). It does not receive commands or require a webhook.

Only changes to the message text trigger edits. The message ID is persisted, and a deleted message is replaced on the next playback change. Telegram's retry interval is respected. Spotify errors leave the last message unchanged until playback can be checked again.

Leave both Telegram variables empty to disable publication. Setting only one is a configuration error.

## Lyrics

Create an application in the [Spicy Lyrics dashboard](https://developers.spicylyrics.org/dashboard/applications) and put its secret key in `SPICY_LYRICS_SECRET_KEY`. The key stays on the server. No key is needed for track information and playback progress.

The adapter supports static, line-synchronized and syllable-synchronized lyrics, including background vocals. The widget permits manual scrolling and returns to the current line after inactivity. Provider and contributor credits remain visible alongside the text.

Lyrics are cached only in memory for up to 24 hours. Review the [service terms](https://developers.spicylyrics.org/terms), [attribution rules](https://developers.spicylyrics.org/docs/attribution) and [third-party notices](../THIRD_PARTY_NOTICES.md) before enabling the integration.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| Spotify rejects the callback | The registered URI and `SPOTIFY_REDIRECT_URI` match exactly; use `127.0.0.1` for local setup |
| Login reports invalid or expired state | Start again from `/setup` in the same browser; the login attempt expires after 10 minutes |
| Spotify returns `403` | The account satisfies the application's access requirements |
| Spotify returns `429` | Allow the retry interval to pass or increase `POLL_INTERVAL_SECONDS` |
| Spotify requires another login | Reconnect through `/setup`; the refresh token may have been revoked |
| Telegram returns `403` | The bot can access the destination and has channel permissions |
| Telegram message does not appear | Both variables are set, the destination is correct and a private-chat user has sent `/start` |
| Lyrics are unavailable | The key is configured and the provider has lyrics for that track |
| Stored state cannot be decrypted | Restore the original `TOKEN_ENCRYPTION_KEY` from your backup |

Check **Check connection** on `/setup` for configured integrations. `GET /healthz` reports that the application is running; it does not test external providers. Container logs include sanitized upstream error codes:

```sh
docker compose logs --tail 50 spotify
```
