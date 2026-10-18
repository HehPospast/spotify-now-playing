# Security

Do not post secrets or exploitable security details in public issues. Contact the maintainer through a private contact listed on their profile. If private vulnerability reporting is enabled on the hosting repository, use that channel.

Only the latest source revision is maintained. There is currently no hosted service or published release maintained by this repository.

An installation intentionally exposes current playback and enabled lyrics to visitors. Administrative actions require `ADMIN_KEY`. Spotify tokens and stored application state are encrypted with `TOKEN_ENCRYPTION_KEY`; environment secrets themselves are not encrypted by the app. Protect the environment file, backups and host access.

If a token leaks, revoke it with its provider and replace it locally. If the owner key leaks, replace `ADMIN_KEY` and restart. If the encryption key leaks, treat database backups as compromised; revoke Spotify access and reconnect with a fresh database and key. Do not assume that merely changing the encryption key re-encrypts existing data.
