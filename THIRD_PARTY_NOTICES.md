# Third-party notices

## Spicy Lyrics

This project uses the [Spicy Lyrics API](https://developers.spicylyrics.org/) to retrieve optional song lyrics and synchronization data. Spicy Lyrics is an external service and is not distributed as part of this repository.

Enabling the integration requires a Spicy Lyrics application and an API key. Use of the service is subject to the [Spicy Lyrics Terms of Service](https://developers.spicylyrics.org/terms) and [attribution requirements](https://developers.spicylyrics.org/docs/attribution).

The widget displays the provider identified by each response. For community lyrics supplied by Spicy Lyrics, it also displays the uploader and maker credits supplied by the API, with links where available. Responses may identify Spicy Lyrics, Apple Music or Spotify as their source. Source metadata, contributor credits and provenance marks are preserved by the adapter.

Lyrics and synchronization data remain subject to the rights and terms of their respective owners and providers. They are not covered by this project's MIT license. Demo captures in `docs/media` show excerpts with the provider and contributor credits visible. Source code and test fixtures do not contain retrieved lyrics.

## Spotify

Track metadata and album artwork are retrieved from the [Spotify Web API](https://developer.spotify.com/documentation/web-api). They remain subject to Spotify's applicable terms and third-party rights. Spotify names and marks belong to their respective owners.

## Font Awesome

`frontend/src/assets/spotify.svg` is the Spotify icon from Font Awesome Free 6.7.2, Copyright 2024 Fonticons, Inc. The icon is licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) and retains its original attribution comment. See the [Font Awesome Free license](https://fontawesome.com/license/free).

## Code provenance

The player, lyric timing utilities and lyrics normalization adapter include code from these MIT-licensed projects:

- `hehpospast.ru`, Copyright (c) 2025 HehPospast.
- `hehpospast-api`, Copyright (c) 2025 HehPospast.

The copyright and MIT license notices are retained in [LICENSE](LICENSE).

## Dependencies

React, React DOM, Framer Motion, Vite and the Python dependencies retain their respective licenses. Consult the license files included with their packages. The frontend dependency versions are recorded in `frontend/package-lock.json`.

This project is independent of Spotify, Telegram, Spicy Lyrics and Font Awesome. References to these services do not imply affiliation or endorsement.
