import os
import shutil
from dotenv import load_dotenv

load_dotenv()


def _resolve_binary(name, env_var):
    """
    Locate an executable portably.

    Order of preference:
      1. An explicit path from the environment (e.g. FFMPEG_BIN=/opt/bin/ffmpeg)
      2. Whatever is on PATH (shutil.which)
      3. The bare name, so the failure message is readable

    This replaces the old hardcoded '/usr/bin/ffmpeg', which only worked on the
    deployment target and broke on macOS, Windows and most Docker images.
    """
    explicit = os.environ.get(env_var)
    if explicit:
        return explicit
    return shutil.which(name) or name


class Config:
    # ---- Security -------------------------------------------------------
    # In production a real SECRET_KEY must be supplied. Falling back to a
    # known development value in production would let anyone forge sessions.
    SECRET_KEY = os.environ.get('SECRET_KEY')
    ENV = os.environ.get('FLASK_ENV', 'production')

    if not SECRET_KEY:
        if ENV == 'development':
            SECRET_KEY = 'dev-only-not-for-production'
        else:
            raise RuntimeError(
                "SECRET_KEY is not set. Set it in the environment before "
                "starting in production, or set FLASK_ENV=development for "
                "local work. See .env.example."
            )

    # ---- Uploads --------------------------------------------------------
    # Maximum upload size (default 500 MB)
    MAX_CONTENT_LENGTH = int(os.environ.get('MAX_CONTENT_LENGTH', 524288000))

    # Storage lives OUTSIDE static/. Anything under static/ is served directly
    # by Flask, so uploads there were fetchable at /static/uploads/<name> by
    # anyone who knew or guessed the name, bypassing the /download route
    # entirely. Files are now only reachable through /download/<filename>.
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', 'storage/uploads')
    OUTPUT_FOLDER = os.environ.get('OUTPUT_FOLDER', 'storage/outputs')

    ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv', 'flv', 'wmv', 'webm'}
    ALLOWED_AUDIO_EXTENSIONS = {'mp3', 'wav', 'aac', 'ogg', 'flac', 'm4a', 'wma'}

    # ---- Automatic cleanup ----------------------------------------------
    # Uploads and generated outputs are deleted this many minutes after they
    # are created. Previously defined but never used, which meant the disk
    # filled up indefinitely.
    AUTO_DELETE_AFTER_MINUTES = int(os.environ.get('AUTO_DELETE_AFTER_MINUTES', 30))
    CLEANUP_INTERVAL_SECONDS = int(os.environ.get('CLEANUP_INTERVAL_SECONDS', 300))

    # ---- External binaries ----------------------------------------------
    FFMPEG_BIN = _resolve_binary('ffmpeg', 'FFMPEG_BIN')
    FFPROBE_BIN = _resolve_binary('ffprobe', 'FFPROBE_BIN')

    # ---- Processing ------------------------------------------------------
    FAST_MODE = os.environ.get('FAST_MODE', 'False').lower() == 'true'
    MAX_CONCURRENT_JOBS = int(os.environ.get('MAX_CONCURRENT_JOBS', 4))
