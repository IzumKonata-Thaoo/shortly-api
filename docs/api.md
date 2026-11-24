# API

Base: `https://api-prod.shortly.show/api`

Found in `libapp.so` (the app is Flutter; its Dart code is compiled to native, so
these strings are the fastest map available).

## Endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/v2/auth/guest-register` | POST | creates a guest user, returns a token |
| `/v2/page/series` | GET | home rails (tabs + categories + series) |
| `/v2/page/series_details` | GET | one series |
| `/v2/page/series/episodes` | GET | **episode list** |
| `/v2/search` | GET | search |
| `/v2/page/rewards` | GET | rewards page |
| `/v2/watch_history` | GET | watch history |
| `/v2/resume-watch` | GET | resume point |
| `/v2/episode/unlock` · `/v2/episode/ad-unlock-episode` | POST | unlock with coins / ad |
| `/v2/auth/login` · `/v2/auth/authenticate` · `/v2/user/login_token` | POST | auth |
| `/v2/device/setting` | POST | device config |
| `/v2/series/confirm` · `/v2/series/report` | POST | reactions |
| `/v2/notifications/schedule` | GET | push scheduling |

Headers the binary references: `Device-Id`, `App-Version`, `accept-language`,
`platform`, `lang`, `Authorization: Bearer`.

Telemetry lives elsewhere:

```
https://gamegears-prod.gamegears.online/public/aitv/
    event_stat_add.php    user_report.php    crash_report.php
```

## Guest registration works

```http
POST /api/v2/auth/guest-register
Device-Id: <uuid>
Content-Type: application/json

{}
```

```json
{
  "token": "5fc0bdd6…a60bec_6b056ef9264612952c09a5c8",
  "user": { "user_id": 1691797, "geo": "VN", "is_premium": false, "balance": 0 },
  "config": { "series_autostart": true, "show_coins_in_app": true, … }
}
```

`user_id` increments per call — every registration makes a new guest.

## The token problem

Every content endpoint answers `401 {"error":"Token is required"}` without a token,
and `401 {"error":"Invalid token"}` with the guest token:

| how the token was sent | result |
|---|---|
| `Authorization: Bearer <token>` | `401 Invalid token` |
| `Authorization: <token>` | `400 Invalid request parameters` |
| `token` / `X-Token` header | `401 Token is required` (header ignored) |
| `?token=` query param | `401 Token is required` |
| `POST /v2/user/login_token {"token": …}` | `404 Invalid or already used token` |

Tried and ruled out: three `Device-Id` formats (uuid, 16-hex, android_id), three
User-Agents (Dart, app build, okhttp), extra headers (`App-Version`, `platform`,
`lang`, `accept-language`), a device payload in the register body, and sending only
the token's head or only its suffix.

The token is `<64 hex>_<24 hex>`. The head looks like a hash, the suffix like a
nonce. `login_token` does accept a `token` body field — it answers "invalid or
already used", which suggests the value is consumed during registration and a
second, authenticated call is expected.

**Status: open.** The media side does not need it (see [media.md](media.md)), so the
downloader works regardless.

## Why a proxy does not help

Flutter's `dart:io` ships its **own CA bundle** and ignores the Android system proxy
as well. With a mitm proxy configured, the app's own log shows API calls timing out:

```
[WARNING] 🔌 [API] Analytics batch send failed
[INFO]    🔌 [API] DioExceptionType.connectionError
```

Only the native video player (platform HTTP stack) goes through the proxy — which is
exactly how the HLS manifest was captured.

## Local caches (root)

`/data/data/shorts.movies.drama.tv.series/app_flutter/shortly.sqlite`

| table | contents |
|---|---|
| `home_snapshot` | **full `/v2/page/series` JSON** per user — ids, titles, `tech_title`, `episodes_count` |
| `watch_history` | `video_url`, `episode_id`, `episode_index` (stays empty until a full watch) |
| `log_entries_table` | the app's own log — **contains every manifest URL played or prefetched** |
| `library_series_cache` | empty in testing |

`*_box.hive` files hold session/analytics state; `session_data_box.hive` is ~600 B and
does not expose the token in plaintext (Hive AES cipher).

The player log is the practical discovery channel:

```
[DEBUG] 📦 [CACHE] Started | URL: 540P: …/Yes_Sir_Daddy_S1E5_ID10271.mp4.1784102687.m3u8
[DEBUG] ▶️ [PLAYER] ShortlyPlayer first frame: 349ms — 383:9115 (ep3, source=Popular: TOP)
```

Because `series_autostart` is on and the app prefetches two episodes ahead, letting a
series play fills the log with its episode URLs in order — that is what
`shortly.py harvest` reads.
