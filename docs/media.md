# Media

Shortly streams **plain HLS** from `gamegears-cdn-cf.gamegears.online`. No
encryption, no signed cookies, no DRM, no auth — the only requirement is the app's
User-Agent header.

```
User-Agent: 2.32.0.00578
```

## URL anatomy

```
https://gamegears-cdn-cf.gamegears.online/public/aitv/content
      /aitv_episode_part_video/video_file/{episode_id}/{lang}/
      {Show_Name}_S{season}E{episode}_ID{episode_id}.mp4.{ts}.m3u8
```

| part | example | notes |
|---|---|---|
| `episode_id` | `10269` | numeric, sequential per release |
| `lang` | `en` | audio/subtitle language of the rendition |
| `Show_Name` | `Yes_Sir_Daddy` | the series' `tech_title`, underscores instead of spaces |
| `season` / `episode` | `S1` / `E3` | 1-based |
| `ts` | `1784101866` | **per-episode token, required** |

`{ts}` is not an expiry — it stays valid — but it is unique to each episode. Any
other value, or omitting it, returns S3 `403 AccessDenied`:

| request | result |
|---|---|
| `…ID10269.mp4.1784101866.m3u8` | **200** |
| `…ID10269.mp4.m3u8` | 403 |
| `…ID10269.mp4.1784101132.m3u8` (another episode's ts) | 403 |
| `…ID10270.mp4.1784101866.m3u8` (other id, wrong ts) | 403 |

## Playlists

Master (`…{ts}.m3u8`):

```m3u8
#EXTM3U
#EXT-X-VERSION:3
#EXT-X-STREAM-INF:BANDWIDTH=1670944,AVERAGE-BANDWIDTH=1278406,RESOLUTION=540x960,CODECS="avc1.4d401f,mp4a.40.2"
Yes_Sir_Daddy_S1E3_ID10269.mp4.1784101866_0.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=3353168,AVERAGE-BANDWIDTH=2016298,RESOLUTION=720x1280,CODECS="avc1.4d401f,mp4a.40.2"
…
```

Media playlist (`…{ts}_0.m3u8`):

```m3u8
#EXTM3U
#EXT-X-VERSION:3
#EXT-X-TARGETDURATION:2
#EXT-X-MEDIA-SEQUENCE:0
#EXT-X-PLAYLIST-TYPE:VOD
#EXTINF:2.000000,
#EXT-X-PROGRAM-DATE-TIME:2026-07-15T07:51:10.243+0000
Yes_Sir_Daddy_S1E3_ID10269.mp4.1784101866_0_00000.ts
…
```

Segments are plain MPEG-TS (`47 40 11 10` sync bytes).

## Download

```bash
ffmpeg -headers "User-Agent: 2.32.0.00578" \
       -i "<master m3u8>" -c copy -bsf:a aac_adtstoasc out.mp4
```

`shortly.py` does exactly this, two workers in parallel.

## Verified output

| episode | duration | size | codec |
|---|---|---|---|
| Yes Sir Daddy S01E03 | 40.6 s | 20.3 MB | h264 1080×1920 + aac |
| Yes Sir Daddy S01E01 | 47.0 s | 21.9 MB | h264 + aac |
| Yes Sir Daddy S01E02 | 42.1 s | 20.9 MB | h264 + aac |

Episodes run 40–90 s. A 70-episode series is roughly an hour of video.

## Notes

- The 1080×1920 rung exists in the master but not in every episode — the ladder is
  built per encode, so resolution varies.
- `-c copy` keeps the original bitstream; no re-encode, no quality loss.
- The CDN is CloudFront in front of S3. Objects are addressed by the exact name, so
  the bucket is not listable — you can only fetch a URL you already know.
