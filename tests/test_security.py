"""
Security regression tests.

Each test here corresponds to a real bug that existed in this codebase.
"""
import io
import os

import pytest

from conftest import upload

TRAVERSAL_PAYLOADS = [
    '../../config.py',
    '/etc/passwd',
    '../.env',
    'a/../../../etc/passwd',
    '..\\..\\config.py',
    '..%2f..%2fconfig.py',
    '....//....//config.py',
    '.',
    '..',
]


def test_traversal_payloads_never_escape_storage(app):
    """
    Endpoints take a filename from the JSON body. Joining that with
    os.path.join() let '../../' escape the storage directory and hand FFmpeg
    arbitrary server files.
    """
    from app import safe_upload_path, safe_output_path

    with app.app_context():
        for payload in TRAVERSAL_PAYLOADS:
            for resolver, key in ((safe_upload_path, 'UPLOAD_FOLDER'),
                                  (safe_output_path, 'OUTPUT_FOLDER')):
                resolved = resolver(payload)
                if resolved is None:
                    continue
                root = os.path.abspath(app.config[key])
                assert os.path.abspath(resolved).startswith(root + os.sep), payload


def test_split_rejects_traversal_filename(client):
    response = client.post('/split', json={'filename': '../../config.py', 'num_parts': 2})
    assert response.status_code == 400


def test_upload_filenames_do_not_collide(app):
    """Two users uploading video.mp4 simultaneously used to overwrite each other."""
    from app import unique_filename

    with app.app_context():
        names = {unique_filename('video.mp4') for _ in range(500)}
    assert len(names) == 500
    assert all(name.endswith('_video.mp4') for name in names)


@pytest.mark.parametrize('payload,label', [
    (b"ffconcat version 1.0\nfile '/etc/passwd'\n", 'ffconcat playlist'),
    (b"#EXTM3U\n#EXTINF:10.0,\n/etc/passwd\n#EXT-X-ENDLIST\n", 'HLS playlist'),
    (b'not a video at all', 'plain text'),
])
def test_disguised_non_media_is_rejected(client, payload, label):
    """
    A file renamed to .mp4 passes an extension check. FFmpeg playlist formats
    instruct FFmpeg to open other paths, so they must never reach an encoder.
    """
    response = client.post(
        '/upload',
        data={'video': (io.BytesIO(payload), 'evil.mp4')},
        content_type='multipart/form-data',
    )
    assert response.status_code == 400, label


def test_errors_do_not_leak_server_internals(client, sample_video):
    """Routes used to return str(e): server paths, FFmpeg output, exception text."""
    stored = upload(client, sample_video, 'leak.mp4')
    response = client.post('/trim-video',
                           json={'filename': stored, 'start_time': 'nonsense', 'end_time': 'x'})
    body = response.get_data(as_text=True).lower()
    assert 'traceback' not in body
    assert 'storage/' not in body
    assert 'ffmpeg' not in body


def test_upload_response_does_not_expose_server_path(client, sample_video):
    import io
    with open(sample_video, 'rb') as fh:
        data = {'video': (io.BytesIO(fh.read()), 'v.mp4')}
    body = client.post('/upload', data=data, content_type='multipart/form-data').get_json()
    assert 'filepath' not in body


def test_security_headers_present(client):
    headers = client.get('/').headers
    for header in ('Content-Security-Policy', 'X-Content-Type-Options',
                   'X-Frame-Options', 'Referrer-Policy', 'Permissions-Policy'):
        assert header in headers, header


def test_stats_is_not_public_by_default(client):
    assert client.get('/stats').status_code in (403, 404)


def test_storage_is_not_served_as_static(client, sample_video):
    """Uploads lived in static/, so anyone knowing a name could fetch them."""
    stored = upload(client, sample_video, 'private.mp4')
    assert client.get(f'/static/uploads/{stored}').status_code == 404
