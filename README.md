# SplitMyVideo

A Flask web app for splitting, trimming, converting and compressing video and
audio. Processing is done by FFmpeg invoked as a subprocess.

## Features

- Split a video into N equal parts, or into fixed-length chunks, with optional overlap
- Extract arbitrary clips by start/end timestamps
- Convert video between MP4, WebM, AVI, MOV, MKV
- Convert audio between MP3, WAV, AAC, OGG, FLAC
- Trim video and audio
- Merge multiple audio files, in a user-controlled order
- Compress video at selectable quality levels
- Download results individually or as a ZIP

## Requirements

- Python 3.12
- FFmpeg and FFprobe available on `PATH`

Install FFmpeg:

```bash
# Debian / Ubuntu
sudo apt install ffmpeg

# macOS
brew install ffmpeg
```

## Running locally

```bash
git clone https://github.com/<your-username>/splitmyvideo.git
cd splitmyvideo

python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# set FLASK_ENV=development for local work

python app.py
```

The app starts on http://localhost:5000.

## Deployment

The included `Procfile`, `Aptfile` and `runtime.txt` target Render.com.
`SECRET_KEY` **must** be set in the environment — the app refuses to start in
production without it.

```
web: gunicorn app:app -c gunicorn.conf.py
```

## Configuration

All settings are read from the environment; see `.env.example`.

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | — | Required in production |
| `FLASK_ENV` | `production` | `development` allows a throwaway key |
| `MAX_CONTENT_LENGTH` | 500 MB | Upload size ceiling |
| `AUTO_DELETE_AFTER_MINUTES` | 30 | Retention for uploads and outputs |
| `FFMPEG_BIN` / `FFPROBE_BIN` | auto | Override binary discovery |
| `FAST_MODE` | `False` | Stream-copy instead of re-encoding |
| `MAX_CONCURRENT_JOBS` | 4 | Concurrent FFmpeg jobs |

## Architecture notes

**File naming.** Uploads are stored as `<random-token>_<original-name>`.
`secure_filename()` alone strips path separators but preserves the basename, so
two users uploading `video.mp4` simultaneously would overwrite each other.

**Path handling.** Endpoints that accept a filename from the request body
resolve it with `werkzeug.utils.safe_join()` and reject anything that resolves
outside the upload or output directory. Joining a client-supplied string
directly onto a directory path would let `../../` escape the sandbox and hand
FFmpeg arbitrary files on the server.

**Cleanup.** `TempFileManager` runs a background thread that deletes tracked
files past their expiry and sweeps the upload/output directories by
modification time. The sweep is the safety net: it also removes orphans left
behind when a request crashed mid-processing.

**Binary discovery.** FFmpeg and FFprobe are located once at import via
`shutil.which()`, with an environment override. No hardcoded paths.

**Fast mode.** With `FAST_MODE=True`, splits use `-c copy` — no re-encoding, so
it is near-instant, at the cost of cuts landing on the nearest keyframe rather
than the exact requested timestamp.


**Storage location.** Uploads and outputs live in `storage/`, not `static/`.
Anything under `static/` is served directly by Flask, so files placed there
were fetchable at `/static/uploads/<name>` by anyone who knew the name,
bypassing the `/download` route.

**Upload validation.** Extension checks are trivially bypassed by renaming a
file, so every upload is probed with FFprobe and rejected unless it really
contains an audio or video stream. This keeps FFmpeg playlist formats
(`ffconcat`, HLS) — which instruct FFmpeg to open other paths — away from the
encoder entirely.

**Error responses.** Routes return a generic message and log the real
exception. Returning `str(e)` handed clients absolute server paths and FFmpeg
internals.

**Rate limiting.** Processing endpoints are limited per IP, since each request
starts an FFmpeg encode. Set `RATELIMIT_STORAGE_URI` to Redis when running more
than one worker, or each process counts separately.

**Security headers.** CSP, `nosniff`, `X-Frame-Options`, `Referrer-Policy` and
`Permissions-Policy` are set on every response. The CSP allows AdSense and
`'unsafe-inline'` scripts, which the inline `adsbygoogle` snippets in the
templates require; removing those would let it be tightened.

**/stats is off by default.** It exposed RAM, swap, CPU, disk and queue depth
to anyone. Enable with `STATS_PUBLIC=true` or protect it with `STATS_TOKEN`.

**Merge ordering.** The audio page's merge mode concatenates files in the
order shown in the list, which the user reorders by drag or arrow buttons. Each
merge writes a uniquely named concat list and output file; fixed names in a
shared folder let two concurrent merges overwrite each other. Audio is
re-encoded to the requested format rather than stream-copied, since `-c copy`
only works when every input already carries the output container's codec.

**Container/codec pairing.** Each output container gets codecs it can actually
carry: VP9 + Opus for WebM, WMV2 + WMAV2 for WMV, H.264 + AAC elsewhere. Muxing
H.264/AAC into a `.wmv` produces a file FFmpeg writes happily and Windows Media
Player refuses to open. "Original" quality (stream copy) falls back to
re-encoding for WebM and WMV, since copying H.264 into those containers cannot
work.

**WebM speed.** libvpx-vp9 is single-threaded by default and roughly an order
of magnitude slower than H.264. `-row-mt 1 -threads N -deadline good
-cpu-used 4` cuts encode time substantially for a small compression cost.

**Timeouts.** Every FFmpeg invocation goes through `run_ffmpeg()`, which
enforces `FFMPEG_TIMEOUT_SECONDS` (default 1800) and surfaces the last lines of
FFmpeg's stderr on failure instead of a generic error.

**Timestamps.** `parse_time()` accepts seconds (`12`, `"12.5"`) or clock strings
(`"00:01:30"`, `"1:30"`), so the trim and clip endpoints return 400 on bad input
rather than a 500 from a failed `float()`.

## Known limitations

These are deliberate trade-offs for a project of this size, listed so they are
not mistaken for oversights.

1. **Processing is synchronous.** The browser holds the connection open for the
   whole FFmpeg run, bounded by a 600-second Gunicorn timeout. Threads let
   concurrent users make progress, but the correct fix is a background job
   queue (RQ or Celery with Redis) plus a `/job/<id>/status` endpoint the
   browser polls. This is the single largest architectural gap.

2. **Local disk storage.** Files are written to the instance's filesystem,
   which does not survive a restart and does not work across multiple
   instances. Object storage (S3 or equivalent) with pre-signed URLs is the
   scale-out answer.

3. **All routes live in `app.py`.** At this size that is manageable; splitting
   by feature area with Flask Blueprints (`video`, `audio`, `pages`) is the
   next refactor.

4. **Tests cover the pipeline and security surface, not the frontend.** The
   JavaScript has no test coverage; a broken ad-gate call once disabled the
   entire conversion page silently, which a browser test would have caught.

5. **Rate limits are per-process and in-memory by default.** With more than
   one Gunicorn worker each counts separately, so the effective limit is
   multiplied. Point `RATELIMIT_STORAGE_URI` at Redis for a real deployment.

6. **No authentication.** Anyone who learns an output filename can download it
   until it expires. Filenames carry a random token, which makes guessing
   impractical, but this is obscurity rather than access control.

## Testing

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

31 tests covering path traversal, filename collisions, disguised-media uploads,
error sanitisation, security headers, and the full conversion and merge matrix
with codec verification via FFprobe. Every security test corresponds to a bug
that actually existed in this codebase.

CI runs the suite plus `pip-audit` on push and weekly, so advisories filed
against pinned dependencies surface without anyone remembering to check.

## License

MIT — see [LICENSE](LICENSE).

FFmpeg is invoked as an external process, not linked as a library, so its
LGPL/GPL terms do not extend to this code. Anyone deploying this must still
install FFmpeg themselves and comply with the licence of the build they use.

## Contact

WhalesEC2021@hotmail.com
