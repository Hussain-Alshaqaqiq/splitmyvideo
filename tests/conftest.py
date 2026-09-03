"""Shared fixtures. Tests run against a temporary storage directory."""
import os
import subprocess
import sys
import tempfile

import pytest

os.environ.setdefault('FLASK_ENV', 'development')
# Generous limits so the suite is not throttled by its own rate limiter.
os.environ.setdefault('PROCESSING_RATE_LIMIT', '100000 per hour')
os.environ.setdefault('UPLOAD_RATE_LIMIT', '100000 per hour')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(scope='session')
def app():
    from app import app as flask_app
    tmp = tempfile.mkdtemp(prefix='smv-test-')
    flask_app.config['UPLOAD_FOLDER'] = os.path.join(tmp, 'uploads')
    flask_app.config['OUTPUT_FOLDER'] = os.path.join(tmp, 'outputs')
    os.makedirs(flask_app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(flask_app.config['OUTPUT_FOLDER'], exist_ok=True)
    flask_app.config['TESTING'] = True
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture(scope='session')
def sample_video(tmp_path_factory):
    """A real 10-second H.264/AAC file, generated so no binary is committed."""
    path = tmp_path_factory.mktemp('media') / 'sample.mp4'
    subprocess.run([
        'ffmpeg', '-f', 'lavfi', '-i', 'testsrc=duration=10:size=320x240:rate=15',
        '-f', 'lavfi', '-i', 'sine=frequency=440:duration=10',
        '-c:v', 'libx264', '-c:a', 'aac', '-shortest', '-y', str(path),
        '-loglevel', 'error',
    ], check=True)
    return path


@pytest.fixture(scope='session')
def sample_audio(tmp_path_factory):
    path = tmp_path_factory.mktemp('media') / 'tone.mp3'
    subprocess.run([
        'ffmpeg', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=4',
        '-y', str(path), '-loglevel', 'error',
    ], check=True)
    return path


def upload(client, path, name):
    """Upload a file and return the stored filename."""
    import io
    with open(path, 'rb') as fh:
        data = {'video': (io.BytesIO(fh.read()), name)}
    response = client.post('/upload', data=data, content_type='multipart/form-data')
    assert response.status_code == 200, response.get_json()
    return response.get_json()['filename']
