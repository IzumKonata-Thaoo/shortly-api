<p align="center">
  <img src="assets/logo.png" width="120" alt="Shortly logo">
</p>

<h1 align="center">Shortly API</h1>

<p align="center">
  <b>Unofficial notes and downloader for Shortly — Short Drama Shorts &amp; Series.</b><br>
  <sub>A Flutter app serving plain HLS. The only thing between you and an episode is one header.</sub>
</p>

<p align="center">
  <img alt="python" src="https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white">
  <img alt="license" src="https://img.shields.io/badge/license-MIT-2ea44f">
  <img alt="status" src="https://img.shields.io/badge/media-verified-brightgreen">
  <img alt="api" src="https://img.shields.io/badge/API-mapped%20%C2%B7%20auth%20open-yellow">
  <img alt="platform" src="https://img.shields.io/badge/package-shorts.movies.drama.tv.series-lightgrey">
</p>

---

```text
$ python shortly.py watch
watching the app log — let the app play; Ctrl+C to stop
  + S01E05 10271     queued
  saved 25.3 MB
  + S01E06 10272     queued
  saved 29.5 MB
collected 2 new episode(s); 7 known total
```

---

## What this is

`shorts.movies.drama.tv.series` (GAMEGEARS LTD, 1M+ installs) is a Flutter app.
Its video is **plain HLS with no encryption and no authentication** — the CDN only
wants the app's User-Agent. That part is solved and verified.

The catalogue API is mapped and guest registration works, but the token it mints is
rejected by the content routes. Details in [`docs/api.md`](docs/api.md).

| piece | state |
|---|---|
| media pipeline | **solved** — HLS, no DRM, direct `ffmpeg` download |
| episode URLs | **solved** — per-episode `{ts}` token, format below |
| episode discovery | **works** — `watch` polls the app's player log and downloads live |
| catalogue API | mapped, auth unresolved |
| complete episode | **verified** — 4 episodes, 1080x1920, H.264 + AAC |

## Media anatomy

```
https://gamegears-cdn-cf.gamegears.online/public/aitv/content
  /aitv_episode_part_video/video_file/{episode_id}/{lang}/
  {Show_Name}_S{season}E{episode}_ID{episode_id}.mp4.{ts}.m3u8
```

* master playlist → variants `...{ts}_0.m3u8` (540x960, 720x1280, 1080x1920)
* media playlist → `...{ts}_0_{seq:05d}.ts`, 2 s segments, `PLAYLIST-TYPE:VOD`
* `{ts}` is a per-episode token and is **required** — swapping it, or dropping it,
  gives `403 AccessDenied`
* `User-Agent: 2.32.0.00578` is the only header required

## Install

```bash
git clone https://github.com/IzumKonata-Thaoo/shortly-api.git
cd shortly-api
```

Python side is stdlib only. You need `ffmpeg`, and `adb` if you use `harvest` or
`watch` (they pull the app database off a rooted device or emulator).

## Quickstart

```bash
cd src

# 1. let the app autoplay a series, then read what it played
python shortly.py harvest
python shortly.py list

# 2. download — either live while the app plays...
python shortly.py watch --interval 15 --workers 2

# ...or from what was already harvested
python shortly.py get --eps 1-6 --workers 2
python shortly.py status

# a single manifest you already have
python shortly.py url "https://gamegears-cdn-cf.gamegears.online/.../Show_S1E1_ID123.mp4.1784101132.m3u8"
```

Output layout:

```
out/
└── Yes Sir Daddy/
    ├── S01E001.mp4   21.9 MB   47.0 s   1080x1920
    ├── S01E002.mp4   20.9 MB   42.1 s
    ├── S01E005.mp4   24.1 MB   56.8 s
    └── S01E006.mp4   28.1 MB   57.2 s
```

## Commands

| Command | What it does |
|---|---|
| `python shortly.py harvest` | pull the app DB, extract every manifest it logged |
| `python shortly.py list` | show what was harvested |
| `python shortly.py watch` | poll the DB while the app plays, download new episodes as they appear |
| `python shortly.py get --eps 1-6` | download a range (or `--all`, `--limit N`, `--workers N`) |
| `python shortly.py url <m3u8>` | download one manifest |
| `python shortly.py status` | what is on disk |

`watch` is the practical way to collect a whole series: the app autoplays and
prefetches two episodes ahead, so each poll yields the next manifest.

## Why discovery goes through the app

The manifest name carries `{ts}`, and `{ts}` is unique per episode — guessing it is
not possible (verified: any other value gives 403). The app itself writes every
manifest it plays **and prefetches** into its own SQLite log:

```
[DEBUG] [CACHE] Started | URL: 540P: .../Yes_Sir_Daddy_S1E5_ID10271.mp4.1784102687.m3u8
```

`harvest` pulls that database; `watch` polls it and downloads as it fills up.

## Documentation

| file | contents |
|---|---|
| [`docs/media.md`](docs/media.md) | HLS structure, variants, the `{ts}` token, verified output |
| [`docs/api.md`](docs/api.md) | endpoints, guest-register, the token problem, local caches |

## Notes

- Episodes are 40-90 s each; a 70-episode series is about an hour of video.
- The app writes its database to
  `/data/data/shorts.movies.drama.tv.series/app_flutter/shortly.sqlite`.
  `harvest` and `watch` pull it with `adb pull`; on a non-rooted device this needs a
  debuggable build.
- Flutter's `dart:io` uses its own CA bundle, so a mitm proxy cannot read the API —
  only the native player's traffic shows up. That is how the HLS format was found.
- Content belongs to its respective owners. This repository documents and automates
  access; it does not grant rights to redistribute anything.

## License

MIT — see [LICENSE](LICENSE). Logo is the property of its owner and is included for
identification only.
