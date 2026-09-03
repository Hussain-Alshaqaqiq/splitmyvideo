"""
Gunicorn configuration.

Note on concurrency: processing is still synchronous — the browser holds the
connection open for the whole FFmpeg run. Threads let concurrent users make
progress instead of queueing behind one long job, but the real fix is a
background job queue (RQ/Celery + Redis) with the browser polling a job status
endpoint. See the "Known limitations" section of the README.
"""

import multiprocessing
import os

# Server socket
bind = f"0.0.0.0:{os.environ.get('PORT', 10000)}"

# Worker processes.
# gthread lets a worker serve other requests while one is blocked on FFmpeg.
# Previously workers=1, threads=1, which meant a single long video blocked
# every other user for the full duration of the encode.
workers = int(os.environ.get('WEB_CONCURRENCY', 1))
worker_class = "gthread"
threads = int(os.environ.get('GUNICORN_THREADS', 4))

# Timeouts. Long encodes legitimately exceed the 30s default.
timeout = int(os.environ.get('GUNICORN_TIMEOUT', 600))
graceful_timeout = 30
keepalive = 2

# Recycle workers periodically to bound memory growth from FFmpeg subprocesses.
worker_tmp_dir = "/dev/shm"
max_requests = 50
max_requests_jitter = 10

# Logging
accesslog = "-"
errorlog = "-"
loglevel = os.environ.get('LOG_LEVEL', 'info')

# Request limits
limit_request_line = 4094
limit_request_fields = 100
