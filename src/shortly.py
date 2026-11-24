"""shortly — download episodes from the Shortly app (shorts.movies.drama.tv.series).

Media is plain HLS on `gamegears-cdn-cf.gamegears.online`; the only requirement is
the app's User-Agent. The manifest name carries a per-episode token:

    .../video_file/{episode_id}/{lang}/{Show}_S{season}E{episode}_ID{id}.mp4.{ts}.m3u8

`{ts}` is required and unique per episode, so the URLs have to be discovered rather
than guessed. Two sources work:

  1. `harvest` — read the app's own SQLite log on the device (root). The player
     logs every manifest it plays or prefetches, which is how a series gets
     enumerated: let the app autoplay, then harvest.
  2. `url` — you already have a manifest URL (copy it from the app log).

Usage
-----
    python shortly.py harvest                # pull + parse the app DB -> harvest.json
    python shortly.py list                   # what was harvested
    python shortly.py get --eps 1-6          # download a range
    python shortly.py get --all --workers 2
    python shortly.py url <m3u8>             # download one manifest
    python shortly.py status
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import concurrent.futures
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out"
CACHE = ROOT / "harvest.json"
TMP = ROOT / "tmp"
for d in (OUT, TMP):
    d.mkdir(exist_ok=True)

PACKAGE = "shorts.movies.drama.tv.series"
DB_ON_DEVICE = "/data/data/%s/app_flutter/shortly.sqlite" % PACKAGE
ADB = os.environ.get("ADB") or "adb"
UA = "2.32.0.00578"

MANIFEST = re.compile(
    r"https://gamegears-cdn-cf\.gamegears\.online/public/aitv/content/"
    r"aitv_episode_part_video/video_file/\d+/[a-z]{2}/"
    r"[A-Za-z0-9_]+?_S\d+E\d+_ID\d+\.mp4\.\d+\.m3u8")
PARTS = re.compile(
    r"video_file/(\d+)/([a-z]{2})/(.+?)_S(\d+)E(\d+)_ID(\d+)\.mp4\.(\d+)\.m3u8")


def adb(*args, check=False):
    r = subprocess.run([ADB, *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        raise SystemExit("adb %s failed: %s" % (" ".join(args), r.stderr[-300:]))
    return r.stdout


def pull_db() -> Path:
    """Copy the app database off the device (needs root or a debuggable app)."""
    local = TMP / ("shortly_%d.sqlite" % int(time.time()))
    adb("pull", DB_ON_DEVICE, str(local), check=True)
    return local


def harvest(db: Path | None = None):
    db = db or pull_db()
    import sqlite3
    con = sqlite3.connect(str(db))
    rows = {}
    for (msg,) in con.execute("select message from log_entries_table"):
        for url in MANIFEST.findall(msg or ""):
            rows[url] = True
    out = []
    for url in sorted(rows):
        m = PARTS.search(url)
        out.append({
            "episode_id": int(m.group(1)),
            "lang": m.group(2),
            "show": m.group(3),
            "season": int(m.group(4)),
            "episode": int(m.group(5)),
            "ts": m.group(7),
            "url": url,
        })
    out.sort(key=lambda r: (r["show"], r["season"], r["episode"]))
    CACHE.write_text(json.dumps(out, indent=1), encoding="utf-8")
    save_series(con)
    return out


def save_series(con):
    """The app caches the whole `/v2/page/series` payload — keep the series list."""
    try:
        payload = con.execute("select payload from home_snapshot limit 1").fetchone()
    except Exception:
        return
    if not payload:
        return
    try:
        doc = json.loads(payload[0])
    except Exception:
        return
    seen, series = set(), []
    for cat in doc.get("categories") or []:
        for s in cat.get("series") or []:
            if not s.get("id") or s["id"] in seen:
                continue
            seen.add(s["id"])
            series.append({
                "id": s.get("id"),
                "title": s.get("title"),
                "tech_title": s.get("tech_title"),
                "episodes": s.get("episodes_count"),
                "category": cat.get("title"),
                "is_finished": s.get("is_finished"),
                "tags": s.get("tags"),
            })
    (ROOT / "series.json").write_text(json.dumps(series, indent=1), encoding="utf-8")


def load():
    if not CACHE.exists():
        raise SystemExit("no harvest.json — run: python shortly.py harvest")
    return json.loads(CACHE.read_text(encoding="utf-8"))


def dest_for(row) -> Path:
    folder = OUT / row["show"].replace("_", " ")
    folder.mkdir(parents=True, exist_ok=True)
    return folder / ("S%02dE%03d.mp4" % (row["season"], row["episode"]))


def download(url: str, dest: Path) -> tuple[bool, str]:
    if dest.exists() and dest.stat().st_size > 200_000:
        return True, "exists"
    tmp = dest.with_suffix(".part.mp4")
    cmd = ["ffmpeg", "-y", "-v", "error",
           "-headers", "User-Agent: %s\r\n" % UA,
           "-i", url, "-c", "copy", "-bsf:a", "aac_adtstoasc", str(tmp)]
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if tmp.exists() and tmp.stat().st_size > 200_000:
        tmp.replace(dest)
        return True, "%.1f MB" % (dest.stat().st_size / 1e6)
    if tmp.exists():
        tmp.unlink(missing_ok=True)
    return False, (r.stderr or "")[-200:]


def cmd_harvest(args):
    rows = harvest(Path(args.db) if args.db else None)
    print("%d episode manifest(s) harvested -> %s" % (len(rows), CACHE))


def cmd_list(args):
    rows = load()
    print("%d episode(s)" % len(rows))
    for r in rows:
        print("  %-9d %-28s S%02dE%02d  ts=%s" %
              (r["episode_id"], r["show"][:28], r["season"], r["episode"], r["ts"]))


def pick(rows, spec):
    if not spec:
        return rows
    m = re.match(r"^(\d+)\s*-\s*(\d+)$", spec.strip())
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        return [r for r in rows if lo <= r["episode"] <= hi]
    want = {int(x) for x in re.split(r"[,\s]+", spec.strip()) if x.isdigit()}
    return [r for r in rows if r["episode"] in want]


def cmd_get(args):
    rows = pick(load(), args.eps)
    if args.limit:
        rows = rows[: args.limit]
    if not rows:
        print("nothing selected")
        return
    print("%d episode(s), %d worker(s)" % (len(rows), args.workers))
    fails = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(download, r["url"], dest_for(r)): r for r in rows}
        for fut in concurrent.futures.as_completed(futs):
            r = futs[fut]
            try:
                ok, info = fut.result()
            except Exception as e:  # noqa: BLE001
                ok, info = False, str(e)[:120]
            if ok:
                print("  ok    S%02dE%02d %-9s %s" %
                      (r["season"], r["episode"], r["episode_id"], info))
            else:
                fails += 1
                print("  FAIL  S%02dE%02d %-9s %s" %
                      (r["season"], r["episode"], r["episode_id"], info))
    if fails:
        sys.exit(1)


def cmd_url(args):
    m = PARTS.search(args.url)
    if m:
        row = {"episode_id": int(m.group(1)), "lang": m.group(2), "show": m.group(3),
               "season": int(m.group(4)), "episode": int(m.group(5)), "ts": m.group(7),
               "url": args.url}
        dest = dest_for(row)
    else:
        dest = OUT / "download.mp4"
    ok, info = download(args.url, dest)
    print(("ok " if ok else "FAIL ") + str(dest) + " " + info)
    sys.exit(0 if ok else 1)


def cmd_watch(args):
    """Poll the app DB while it plays, downloading every new manifest it logs.

    This is how a whole series is collected without the API: the app autoplays and
    prefetches, so each poll yields the next episode's manifest URL.
    """
    print("watching the app log — let the app play; Ctrl+C to stop")
    known = {r["url"] for r in (load() if CACHE.exists() else [])}
    deadline = time.time() + args.minutes * 60 if args.minutes else None
    idle = 0
    got = 0
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=args.workers)
    pending = []

    def finish():
        nonlocal got
        for fut in list(pending):
            if not fut.done():
                continue
            pending.remove(fut)
            try:
                ok, info = fut.result()
            except Exception as e:  # noqa: BLE001
                ok, info = False, str(e)[:120]
            if ok:
                got += 1
                print("  saved %s" % info, flush=True)

    try:
        while True:
            if deadline and time.time() > deadline:
                break
            try:
                db = pull_db()
                rows = harvest(db)
            except SystemExit:
                print("  ! cannot read the app DB (root / adb?)")
                break
            new = []
            for r in rows:
                if r["url"] in known:
                    continue
                dest = dest_for(r)
                if dest.exists() and dest.stat().st_size > 200_000:
                    known.add(r["url"])
                    continue
                known.add(r["url"])
                new.append(r)
                pending.append(pool.submit(download, r["url"], dest))
                print("  + S%02dE%02d %-9s queued" %
                      (r["season"], r["episode"], r["episode_id"]), flush=True)
            finish()
            idle = 0 if new else idle + 1
            if args.stop_when_idle and idle >= args.stop_when_idle:
                print("  no new episodes for %d polls, stopping" % idle)
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        for fut in pending:
            try:
                ok, info = fut.result()
                if ok:
                    got += 1
            except Exception:  # noqa: BLE001
                pass
        pool.shutdown(wait=True)
    print("collected %d new episode(s); %d known total" % (got, len(known)))


def cmd_series(args):
    path = ROOT / "series.json"
    if not path.exists():
        raise SystemExit("no series.json — run: python shortly.py harvest")
    rows = json.loads(path.read_text(encoding="utf-8"))
    print("%d series" % len(rows))
    for r in rows:
        print("  %-5s %-44s %3s eps  %s" %
              (r["id"], (r["title"] or "")[:44], r["episodes"],
               r.get("category") or ""))


def cmd_status(args):
    files = list(OUT.rglob("*.mp4"))
    total = sum(f.stat().st_size for f in files)
    print("%d episode(s) on disk, %.2f GB" % (len(files), total / 1e9))
    by = {}
    for f in files:
        by[f.parent.name] = by.get(f.parent.name, 0) + 1
    for k in sorted(by):
        print("  %-40s %3d" % (k, by[k]))


def main():
    p = argparse.ArgumentParser(prog="shortly", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    h = sub.add_parser("harvest", help="pull the app DB and extract manifests")
    h.add_argument("--db", help="use a local sqlite instead of pulling")
    h.set_defaults(fn=cmd_harvest)

    sub.add_parser("list").set_defaults(fn=cmd_list)
    sub.add_parser("series", help="series list cached by the app").set_defaults(fn=cmd_series)

    g = sub.add_parser("get", help="download harvested episodes")
    g.add_argument("--eps", help="1-6 or 1,3,7")
    g.add_argument("--all", action="store_true")
    g.add_argument("--limit", type=int)
    g.add_argument("--workers", type=int, default=2)
    g.set_defaults(fn=cmd_get)

    u = sub.add_parser("url", help="download one manifest URL")
    u.add_argument("url")
    u.set_defaults(fn=cmd_url)

    w = sub.add_parser("watch", help="poll the app while it plays, download new episodes")
    w.add_argument("--interval", type=int, default=10, help="seconds between polls")
    w.add_argument("--workers", type=int, default=2)
    w.add_argument("--minutes", type=int, help="stop after N minutes")
    w.add_argument("--stop-when-idle", type=int, default=0,
                   help="stop after N polls with no new episode (0 = never)")
    w.set_defaults(fn=cmd_watch)

    sub.add_parser("status").set_defaults(fn=cmd_status)

    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
