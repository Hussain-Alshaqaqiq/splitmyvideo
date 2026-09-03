"""Functional tests for the media pipeline."""
import io
import subprocess

import pytest

from conftest import upload


def codec_of(path, stream='a'):
    result = subprocess.run(
        ['ffprobe', '-v', 'error', '-select_streams', f'{stream}:0',
         '-show_entries', 'stream=codec_name', '-of', 'csv=p=0', str(path)],
        capture_output=True, text=True,
    )
    return result.stdout.strip()


def test_parse_time_accepts_seconds_and_clock_strings():
    from video_utils import parse_time

    assert parse_time(5) == 5.0
    assert parse_time('12.5') == 12.5
    assert parse_time('00:00:02') == 2.0
    assert parse_time('1:30') == 90.0
    assert parse_time('01:02:03') == 3723.0

    for bad in ('abc', '', None, '1:2:3:4'):
        with pytest.raises((ValueError, TypeError)):
            parse_time(bad)


def test_split_produces_equal_parts(client, sample_video):
    stored = upload(client, sample_video, 'split.mp4')
    response = client.post('/split', json={'filename': stored, 'num_parts': 5})
    assert response.status_code == 200
    files = response.get_json()['files']
    assert len(files) == 5


@pytest.mark.parametrize('fmt', ['mp4', 'avi', 'mov', 'mkv', 'webm', 'flv', 'wmv'])
def test_every_video_format_converts(client, sample_video, fmt):
    stored = upload(client, sample_video, f'conv_{fmt}.mp4')
    response = client.post('/convert-video',
                           json={'filename': stored, 'output_format': fmt, 'quality': 'low'})
    assert response.status_code == 200, response.get_json()


def test_wmv_uses_windows_media_codecs(client, app, sample_video):
    """H.264 in an ASF container is written happily by FFmpeg and refused by WMP."""
    import os
    stored = upload(client, sample_video, 'codec.mp4')
    response = client.post('/convert-video',
                           json={'filename': stored, 'output_format': 'wmv', 'quality': 'low'})
    name = response.get_json()['file']['filename']
    path = os.path.join(app.config['OUTPUT_FOLDER'], name)
    assert codec_of(path, 'v') == 'wmv2'
    assert codec_of(path, 'a') == 'wmav2'


@pytest.mark.parametrize('fmt,expected', [
    ('mp3', 'mp3'), ('wav', 'pcm_s16le'), ('aac', 'aac'),
    ('ogg', 'vorbis'), ('flac', 'flac'), ('m4a', 'aac'),
])
def test_merge_encodes_to_the_requested_format(client, app, sample_audio, fmt, expected):
    """
    Merge used '-c copy', which produced a .wav containing an MP3 stream and
    failed outright for aac/ogg/flac/m4a.
    """
    import os
    with open(sample_audio, 'rb') as fh:
        blob = fh.read()
    data = {
        'audio_files': [(io.BytesIO(blob), 'a.mp3'), (io.BytesIO(blob), 'b.mp3')],
        'output_format': fmt,
    }
    response = client.post('/merge-audio', data=data, content_type='multipart/form-data')
    assert response.status_code == 200, response.get_json()

    name = response.get_json()['file']['filename']
    assert codec_of(os.path.join(app.config['OUTPUT_FOLDER'], name)) == expected


def test_merge_requires_at_least_two_files(client, sample_audio):
    with open(sample_audio, 'rb') as fh:
        data = {'audio_files': [(io.BytesIO(fh.read()), 'only.mp3')], 'output_format': 'mp3'}
    response = client.post('/merge-audio', data=data, content_type='multipart/form-data')
    assert response.status_code == 400


def test_merge_output_names_are_unique(client, sample_audio):
    """A fixed output name let two concurrent merges overwrite each other."""
    with open(sample_audio, 'rb') as fh:
        blob = fh.read()

    names = set()
    for _ in range(3):
        data = {'audio_files': [(io.BytesIO(blob), 'a.mp3'), (io.BytesIO(blob), 'b.mp3')],
                'output_format': 'mp3'}
        response = client.post('/merge-audio', data=data, content_type='multipart/form-data')
        names.add(response.get_json()['file']['filename'])
    assert len(names) == 3


def test_audio_files_can_be_uploaded(client, sample_audio):
    """allowed_file() only checked video extensions, so .mp3 uploads were rejected."""
    stored = upload(client, sample_audio, 'song.mp3')
    assert stored.endswith('_song.mp3')


def test_trim_accepts_clock_timestamps(client, sample_video):
    stored = upload(client, sample_video, 'trim.mp4')
    response = client.post('/trim-video',
                           json={'filename': stored,
                                 'start_time': '00:00:02', 'end_time': '00:00:06'})
    assert response.status_code == 200, response.get_json()
