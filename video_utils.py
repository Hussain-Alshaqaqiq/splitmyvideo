"""
Video Processing Utilities
معالج الفيديوهات - يحتوي على دوال تقسيم الفيديو
"""

import os
import json
import uuid
import subprocess
from pathlib import Path
from config import Config

# Resolved once at import time via shutil.which() (see config.py).
# Replaces the hardcoded '/usr/bin/ffmpeg', which was not portable.
FFMPEG_BIN = Config.FFMPEG_BIN
FFPROBE_BIN = Config.FFPROBE_BIN


# Wall-clock ceiling for a single FFmpeg invocation. Without a timeout a stuck
# encode holds the worker (and the user's browser connection) open forever.
FFMPEG_TIMEOUT_SECONDS = int(os.environ.get('FFMPEG_TIMEOUT_SECONDS', 1800))

# VP9 is single-threaded by default and roughly an order of magnitude slower
# than H.264. These flags are what make WebM output usable:
#   row-mt 1   enable row-based multithreading
#   threads N  use the machine's cores instead of one
#   deadline good + cpu-used 4  trade a little compression for a lot of speed
_VP9_SPEED_FLAGS = [
    '-row-mt', '1',
    '-threads', str(max(1, min(16, os.cpu_count() or 4))),
    '-deadline', 'good',
    '-cpu-used', '4',
]


def run_ffmpeg(cmd, timeout=None):
    """
    Run an FFmpeg command with a timeout and a readable error on failure.

    FFmpeg writes its diagnostics to stderr, so on failure the last few lines
    are the actual reason (missing codec, unsupported pixel format, etc).
    Surfacing them beats a generic "conversion failed".
    """
    if timeout is None:
        timeout = FFMPEG_TIMEOUT_SECONDS
    try:
        return subprocess.run(cmd, capture_output=True, text=True,
                              check=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise Exception(
            f"انتهت مهلة المعالجة بعد {timeout} ثانية. "
            f"Processing timed out after {timeout}s - the file may be too large."
        )
    except subprocess.CalledProcessError as e:
        tail = (e.stderr or '').strip().splitlines()[-4:]
        raise Exception("FFmpeg failed: " + " | ".join(tail))



# Encoder settings per audio container. Both convert_audio_format() and
# merge_audio_files() read this, so the two cannot drift apart.
AUDIO_ENCODERS = {
    'mp3':  ['-c:a', 'libmp3lame', '-b:a', '192k'],
    'wav':  ['-c:a', 'pcm_s16le'],
    'aac':  ['-c:a', 'aac', '-b:a', '192k'],
    'ogg':  ['-c:a', 'libvorbis', '-b:a', '192k'],
    'flac': ['-c:a', 'flac'],
    'm4a':  ['-c:a', 'aac', '-b:a', '192k'],
}



def is_real_media(path):
    """
    Confirm a file actually contains an audio or video stream.

    Extension checks alone are trivially bypassed: any file renamed to .mp4 is
    accepted, including FFmpeg playlist formats (ffconcat, HLS) that instruct
    FFmpeg to open other paths. FFmpeg's own -safe default blocks the worst of
    that, but validating with ffprobe first means such files never reach an
    encoder at all.
    """
    try:
        result = subprocess.run(
            [FFPROBE_BIN, '-v', 'error',
             '-show_entries', 'stream=codec_type',
             '-of', 'csv=p=0', path],
            capture_output=True, text=True, timeout=30
        )
    except (subprocess.TimeoutExpired, OSError):
        return False

    if result.returncode != 0:
        return False

    kinds = {line.strip() for line in result.stdout.splitlines() if line.strip()}
    return bool(kinds & {'audio', 'video'})


def parse_time(value):
    """
    Accept a timestamp as seconds (12, "12", 12.5) or as a clock string
    ("00:01:30", "1:30"), and return float seconds.

    trim_video/trim_audio previously did float(start_time) directly, so any
    "00:00:02" from the UI raised
        ValueError: could not convert string to float: '00:00:02'
    and surfaced as a 500.
    """
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    if not text:
        raise ValueError("Empty timestamp")

    if ':' in text:
        parts = text.split(':')
        if len(parts) > 3:
            raise ValueError(f"Invalid timestamp: {value}")
        seconds = 0.0
        for part in parts:
            seconds = seconds * 60 + float(part or 0)
        return seconds

    return float(text)


def get_video_duration(video_path):
    """
    الحصول على مدة الفيديو بالثواني
    
    Args:
        video_path: مسار ملف الفيديو
    
    Returns:
        float: مدة الفيديو بالثواني
    """
    try:
        # استخدام FFprobe (يجي مع FFmpeg) للحصول على معلومات الفيديو
        cmd = [
            FFPROBE_BIN,
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            video_path
        ]
        
        result = run_ffmpeg(cmd)
        data = json.loads(result.stdout)
        
        # الحصول على المدة من معلومات الصيغة
        duration = float(data['format']['duration'])
        return duration
        
    except Exception as e:
        print(f"خطأ في الحصول على مدة الفيديو: {e}")
        raise


def split_video(input_path, output_folder, num_parts, base_filename, overlap_seconds=0, fast_mode=False, quality_preset='veryfast'):
    """
    تقسيم الفيديو إلى أجزاء متساوية مع دعم التداخل
    
    Args:
        input_path: مسار الفيديو المدخل
        output_folder: مجلد حفظ الأجزاء
        num_parts: عدد الأجزاء المطلوبة
        base_filename: الاسم الأساسي للملف (بدون الامتداد)
        overlap_seconds: عدد ثواني التداخل بين الأجزاء (افتراضي: 0)
        fast_mode: استخدام نسخ سريع بدلاً من إعادة الترميز (افتراضي: False)
        quality_preset: جودة المعالجة (ultrafast, veryfast, fast) (افتراضي: veryfast)
    
    Returns:
        list: قائمة بأسماء الملفات الناتجة
    """
    try:
        # الحصول على مدة الفيديو
        total_duration = get_video_duration(input_path)
        print(f"مدة الفيديو الكلية: {total_duration} ثانية")
        
        # حساب مدة كل جزء
        part_duration = total_duration / num_parts
        print(f"مدة كل جزء: {part_duration} ثانية")
        
        if overlap_seconds > 0:
            print(f"تداخل بين الأجزاء: {overlap_seconds} ثانية")
        
        if fast_mode:
            print(f"⚡ وضع سريع: استخدام النسخ المباشر (قد تكون هناك مشاكل صغيرة)")
        else:
            print(f"🎬 وضع جودة عالية: إعادة ترميز كامل (أبطأ)")
        
        # إنشاء مجلد المخرجات إذا لم يكن موجوداً
        os.makedirs(output_folder, exist_ok=True)
        
        # قائمة الملفات الناتجة
        output_files = []
        
        # تقسيم الفيديو
        for i in range(num_parts):
            # حساب نقطة البداية لكل جزء
            # الجزء الأول يبدأ من 0
            # الأجزاء التالية تبدأ من (نهاية الجزء السابق - التداخل)
            if i == 0:
                start_time = 0
            else:
                start_time = (i * part_duration) - overlap_seconds
            
            # التأكد من أن نقطة البداية لا تكون سالبة
            start_time = max(0, start_time)
            
            # حساب مدة هذا الجزء
            if i == 0:
                # الجزء الأول: المدة الأساسية فقط (بدون إضافة التداخل)
                duration = part_duration
            elif i == num_parts - 1:
                # الجزء الأخير: من نقطة البداية حتى نهاية الفيديو
                duration = total_duration - start_time
            else:
                # الأجزاء الوسطى: المدة الأساسية + التداخل
                duration = part_duration + overlap_seconds
            
            # اسم الملف الناتج
            output_filename = f"{base_filename}_part{i + 1}.mp4"
            output_path = os.path.join(output_folder, output_filename)
            
            print(f"جاري معالجة الجزء {i + 1}/{num_parts}...")
            print(f"  - البداية: {start_time:.2f} ثانية")
            print(f"  - المدة: {duration:.2f} ثانية")
            print(f"  - النهاية: {start_time + duration:.2f} ثانية")
            
            # أمر FFmpeg - اختيار بناءً على الوضع
            if fast_mode:
                # وضع سريع - نسخ مباشر
                cmd = [
                    FFMPEG_BIN,
                    '-ss', str(start_time),
                    '-i', input_path,
                    '-t', str(duration),
                    '-c', 'copy',
                    '-avoid_negative_ts', '1',
                    '-y',
                    output_path
                ]
            else:
                # تحديد CRF بناءً على preset - محسّن لـ 512MB RAM
                crf_values = {
                    'ultrafast': '23',  # أسرع - جودة جيدة جداً
                    'veryfast': '21'    # سريع - جودة عالية (الافتراضي)
                }
                crf = crf_values.get(quality_preset, '21')
                
                # وضع جودة عالية مع preset قابل للتخصيص
                cmd = [
                    FFMPEG_BIN,
                    '-ss', str(start_time),
                    '-i', input_path,
                    '-t', str(duration),
                    '-c:v', 'libx264',
                    '-preset', quality_preset,
                    '-crf', crf,
                    '-c:a', 'aac',
                    '-b:a', '128k',
                    '-bufsize', '2000k',
                    '-maxrate', '6000k',
                    '-movflags', '+faststart',
                    '-avoid_negative_ts', '1',
                    '-threads', '2',
                    '-max_muxing_queue_size', '2048',
                    '-y',
                    output_path
                ]
            
            # تشغيل الأمر
            result = run_ffmpeg(cmd)
            
            # التحقق من نجاح العملية
            if os.path.exists(output_path):
                output_files.append({
                    'filename': output_filename,
                    'path': output_path,
                    'part_number': i + 1,
                    'start_time': start_time,
                    'duration': duration,
                    'size': os.path.getsize(output_path)
                })
                print(f"✓ تم إنشاء: {output_filename}")
            else:
                raise Exception(f"فشل إنشاء الملف: {output_filename}")
        
        print(f"✓ تم تقسيم الفيديو بنجاح إلى {num_parts} أجزاء!")
        if overlap_seconds > 0:
            print(f"  مع تداخل {overlap_seconds} ثانية بين كل جزء")
        return output_files
        
    except subprocess.CalledProcessError as e:
        print(f"خطأ في تشغيل FFmpeg: {e}")
        print(f"الخطأ: {e.stderr}")
        raise Exception(f"فشل تقسيم الفيديو: {e.stderr}")
    except Exception as e:
        print(f"خطأ عام: {e}")
        raise


def format_duration(seconds):
    """
    تحويل الثواني إلى صيغة قابلة للقراءة
    
    Args:
        seconds: عدد الثواني
    
    Returns:
        str: الوقت بصيغة HH:MM:SS أو MM:SS
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    else:
        return f"{minutes:02d}:{secs:02d}"


def format_file_size(size_bytes):
    """
    تحويل حجم الملف بالبايتات إلى صيغة قابلة للقراءة
    
    Args:
        size_bytes: حجم الملف بالبايتات
    
    Returns:
        str: حجم الملف بصيغة مفهومة
    """
    for unit in ['بايت', 'كيلوبايت', 'ميجابايت', 'جيجابايت']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} تيرابايت"


def check_ffmpeg_installed():
    """
    التحقق من تثبيت FFmpeg
    
    Returns:
        bool: True إذا كان FFmpeg مثبتاً
    """
    try:
        subprocess.run(
            [FFMPEG_BIN, '-version'],
            capture_output=True,
            check=True,
            timeout=10
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError,
            subprocess.TimeoutExpired, OSError):
        return False


def convert_video_format(input_path, output_folder, output_format, quality='medium'):
    """
    تحويل صيغة الفيديو
    
    Args:
        input_path: مسار الفيديو المدخل
        output_folder: مجلد حفظ الملف المحول
        output_format: الصيغة المطلوبة (mp4, avi, mov, mkv, webm, flv, wmv)
        quality: جودة التحويل (low, medium, high, original)
    
    Returns:
        dict: معلومات الملف المحول
    """
    try:
        # إنشاء مجلد المخرجات إذا لم يكن موجوداً
        os.makedirs(output_folder, exist_ok=True)
        
        # الاسم الأساسي بدون الامتداد
        base_name = os.path.splitext(os.path.basename(input_path))[0]
        
        # اسم الملف الناتج
        output_filename = f"{base_name}_converted.{output_format}"
        output_path = os.path.join(output_folder, output_filename)
        
        print(f"جاري تحويل الفيديو من {os.path.splitext(input_path)[1]} إلى .{output_format}...")
        
        # إعدادات الجودة
        quality_settings = {
            'low': {
                'video_bitrate': '500k',
                'audio_bitrate': '96k',
                'crf': '28'
            },
            'medium': {
                'video_bitrate': '1500k',
                'audio_bitrate': '128k',
                'crf': '23'
            },
            'high': {
                'video_bitrate': '3000k',
                'audio_bitrate': '192k',
                'crf': '18'
            },
            'original': {
                'copy': True  # نسخ بدون إعادة ترميز
            }
        }
        
        settings = quality_settings.get(quality, quality_settings['medium'])
        
        # بناء أمر FFmpeg
        cmd = [FFMPEG_BIN, '-i', input_path]
        
        # Stream copy cannot target a container that will not carry the source
        # codecs. Asking for "original" quality into WebM or WMV silently
        # produced a broken file, so fall back to re-encoding for those.
        if settings.get('copy') and output_format.lower() in ('webm', 'wmv'):
            settings = quality_settings['medium']

        if settings.get('copy'):
            # نسخ بدون إعادة ترميز (أسرع)
            cmd.extend(['-c', 'copy'])
        else:
            # إعادة ترميز مع إعدادات الجودة
            cmd.extend([
                '-c:v', 'libx264',  # codec الفيديو
                '-b:v', settings['video_bitrate'],  # bitrate الفيديو
                '-c:a', 'aac',  # codec الصوت
                '-b:a', settings['audio_bitrate'],  # bitrate الصوت
                '-crf', settings['crf']  # معامل الجودة
            ])
        
        # ترميزات خاصة بكل حاوية
        #
        # Containers are not interchangeable with codecs. Muxing H.264/AAC into
        # a .wmv produced a file that FFmpeg accepted but Windows Media Player
        # refuses to open - a silent failure, worse than an error. WebM likewise
        # only carries VP8/VP9 + Vorbis/Opus.
        fmt = output_format.lower()

        if fmt == 'webm':
            cmd = [FFMPEG_BIN, '-i', input_path]
            cmd.extend([
                '-c:v', 'libvpx-vp9',
                '-b:v', settings.get('video_bitrate', '1500k'),
            ])
            cmd.extend(_VP9_SPEED_FLAGS)
            cmd.extend([
                '-c:a', 'libopus',
                '-b:a', settings.get('audio_bitrate', '128k'),
            ])

        elif fmt == 'wmv':
            # ASF wants the Windows Media codecs, not H.264/AAC.
            cmd = [FFMPEG_BIN, '-i', input_path]
            cmd.extend([
                '-c:v', 'wmv2',
                '-b:v', settings.get('video_bitrate', '1500k'),
                '-c:a', 'wmav2',
                '-b:a', settings.get('audio_bitrate', '128k'),
            ])
        
        # إضافة مسار الملف الناتج
        cmd.extend(['-y', output_path])  # -y للكتابة فوق الملف إذا كان موجوداً
        
        print(f"تنفيذ الأمر: {' '.join(cmd)}")
        
        # تشغيل الأمر
        result = run_ffmpeg(cmd)
        
        # التحقق من نجاح العملية
        if os.path.exists(output_path):
            file_size = os.path.getsize(output_path)
            duration = get_video_duration(output_path)
            
            print(f"✓ تم التحويل بنجاح إلى: {output_filename}")
            
            return {
                'success': True,
                'filename': output_filename,
                'path': output_path,
                'size': file_size,
                'duration': duration,
                'format': output_format,
                'quality': quality
            }
        else:
            raise Exception(f"فشل إنشاء الملف: {output_filename}")
        
    except subprocess.CalledProcessError as e:
        print(f"خطأ في تشغيل FFmpeg: {e}")
        print(f"الخطأ: {e.stderr}")
        raise Exception(f"فشل تحويل الفيديو: {e.stderr}")
    except Exception as e:
        print(f"خطأ عام: {e}")
        raise


if __name__ == "__main__":
    # اختبار سريع
    if check_ffmpeg_installed():
        print("✓ FFmpeg مثبت بنجاح!")
    else:
        print("✗ FFmpeg غير مثبت!")


def convert_audio_format(input_path, output_folder, output_format, quality='medium'):
    """
    تحويل صيغة الصوت أو استخراج الصوت من الفيديو
    
    Args:
        input_path: مسار الملف المدخل (صوت أو فيديو)
        output_folder: مجلد حفظ الملف المحول
        output_format: الصيغة المطلوبة (mp3, wav, aac, ogg, flac, m4a)
        quality: جودة الصوت (low, medium, high, best)
    
    Returns:
        dict: معلومات الملف المحول
    """
    try:
        # إنشاء مجلد المخرجات إذا لم يكن موجوداً
        os.makedirs(output_folder, exist_ok=True)
        
        # الاسم الأساسي بدون الامتداد
        base_name = os.path.splitext(os.path.basename(input_path))[0]
        
        # اسم الملف الناتج
        output_filename = f"{base_name}_audio.{output_format}"
        output_path = os.path.join(output_folder, output_filename)
        
        # التحقق من نوع الملف المدخل
        input_ext = os.path.splitext(input_path)[1].lower()
        is_video = input_ext in ['.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv', '.webm']
        
        if is_video:
            print(f"جاري استخراج الصوت من الفيديو...")
        else:
            print(f"جاري تحويل الصوت من {input_ext} إلى .{output_format}...")
        
        # إعدادات جودة الصوت
        quality_settings = {
            'low': {
                'bitrate': '96k',
                'sample_rate': '22050'
            },
            'medium': {
                'bitrate': '128k',
                'sample_rate': '44100'
            },
            'high': {
                'bitrate': '192k',
                'sample_rate': '48000'
            },
            'best': {
                'bitrate': '320k',
                'sample_rate': '48000'
            }
        }
        
        settings = quality_settings.get(quality, quality_settings['medium'])
        
        # بناء أمر FFmpeg
        cmd = [FFMPEG_BIN, '-i', input_path]
        
        # إعدادات خاصة لكل صيغة
        if output_format.lower() == 'mp3':
            cmd.extend([
                '-vn',  # بدون فيديو
                '-c:a', 'libmp3lame',  # codec MP3
                '-b:a', settings['bitrate'],
                '-ar', settings['sample_rate']
            ])
        elif output_format.lower() == 'wav':
            cmd.extend([
                '-vn',
                '-c:a', 'pcm_s16le',  # WAV codec
                '-ar', settings['sample_rate']
            ])
        elif output_format.lower() == 'aac':
            cmd.extend([
                '-vn',
                '-c:a', 'aac',
                '-b:a', settings['bitrate'],
                '-ar', settings['sample_rate']
            ])
        elif output_format.lower() == 'ogg':
            cmd.extend([
                '-vn',
                '-c:a', 'libvorbis',  # OGG codec
                '-b:a', settings['bitrate'],
                '-ar', settings['sample_rate']
            ])
        elif output_format.lower() == 'flac':
            cmd.extend([
                '-vn',
                '-c:a', 'flac',  # FLAC codec (lossless)
                '-ar', settings['sample_rate']
            ])
        elif output_format.lower() == 'm4a':
            cmd.extend([
                '-vn',
                '-c:a', 'aac',
                '-b:a', settings['bitrate'],
                '-ar', settings['sample_rate']
            ])
        else:
            # صيغة افتراضية
            cmd.extend([
                '-vn',
                '-c:a', 'aac',
                '-b:a', settings['bitrate']
            ])
        
        # إضافة مسار الملف الناتج
        cmd.extend(['-y', output_path])
        
        print(f"تنفيذ الأمر: {' '.join(cmd)}")
        
        # تشغيل الأمر
        result = run_ffmpeg(cmd)
        
        # التحقق من نجاح العملية
        if os.path.exists(output_path):
            file_size = os.path.getsize(output_path)
            
            # الحصول على مدة الصوت
            try:
                duration = get_audio_duration(output_path)
            except (OSError, ValueError):
                duration = 0
            
            action = "استخراج" if is_video else "تحويل"
            print(f"✓ تم {action} الصوت بنجاح إلى: {output_filename}")
            
            return {
                'success': True,
                'filename': output_filename,
                'path': output_path,
                'size': file_size,
                'duration': duration,
                'format': output_format,
                'quality': quality,
                'is_extracted': is_video
            }
        else:
            raise Exception(f"فشل إنشاء الملف: {output_filename}")
        
    except subprocess.CalledProcessError as e:
        print(f"خطأ في تشغيل FFmpeg: {e}")
        print(f"الخطأ: {e.stderr}")
        raise Exception(f"فشل معالجة الصوت: {e.stderr}")
    except Exception as e:
        print(f"خطأ عام: {e}")
        raise


def get_audio_duration(audio_path):
    """
    الحصول على مدة الملف الصوتي بالثواني
    
    Args:
        audio_path: مسار ملف الصوت
    
    Returns:
        float: مدة الصوت بالثواني
    """
    try:
        cmd = [
            FFPROBE_BIN,
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            audio_path
        ]
        
        result = run_ffmpeg(cmd)
        data = json.loads(result.stdout)
        
        duration = float(data['format']['duration'])
        return duration
        
    except Exception as e:
        print(f"خطأ في الحصول على مدة الصوت: {e}")
        return 0


def compress_video(input_path, output_folder, compression_level='medium'):
    """
    ضغط الفيديو لتقليل الحجم
    
    Args:
        input_path: مسار الفيديو المدخل
        output_folder: مجلد حفظ الملف المضغوط
        compression_level: مستوى الضغط (low, medium, high)
    
    Returns:
        dict: معلومات الملف المضغوط
    """
    try:
        os.makedirs(output_folder, exist_ok=True)
        
        base_name = os.path.splitext(os.path.basename(input_path))[0]
        output_filename = f"{base_name}_compressed.mp4"
        output_path = os.path.join(output_folder, output_filename)
        
        print(f"جاري ضغط الفيديو...")
        
        # إعدادات الضغط
        compression_settings = {
            'low': {'crf': '28', 'preset': 'fast'},      # ضغط خفيف
            'medium': {'crf': '23', 'preset': 'medium'}, # ضغط متوسط
            'high': {'crf': '18', 'preset': 'slow'}      # ضغط عالي (حجم أصغر)
        }
        
        settings = compression_settings.get(compression_level, compression_settings['medium'])
        
        cmd = [
            FFMPEG_BIN, '-i', input_path,
            '-c:v', 'libx264',
            '-crf', settings['crf'],
            '-preset', settings['preset'],
            '-c:a', 'aac',
            '-b:a', '128k',
            '-y', output_path
        ]
        
        run_ffmpeg(cmd)
        
        if os.path.exists(output_path):
            original_size = os.path.getsize(input_path)
            compressed_size = os.path.getsize(output_path)
            reduction = ((original_size - compressed_size) / original_size) * 100
            
            return {
                'success': True,
                'filename': output_filename,
                'path': output_path,
                'size': compressed_size,
                'original_size': original_size,
                'reduction_percent': reduction,
                'duration': get_video_duration(output_path)
            }
        else:
            raise Exception("فشل ضغط الفيديو")
            
    except Exception as e:
        print(f"خطأ في ضغط الفيديو: {e}")
        raise


def trim_video(input_path, output_folder, start_time, end_time):
    """
    قص الفيديو (اختيار جزء معين)
    
    Args:
        input_path: مسار الفيديو المدخل
        output_folder: مجلد حفظ الملف المقصوص
        start_time: وقت البداية بالثواني
        end_time: وقت النهاية بالثواني
    
    Returns:
        dict: معلومات الملف المقصوص
    """
    try:
        # Normalise timestamps: the UI may send seconds or HH:MM:SS.
        start_time = parse_time(start_time)
        end_time = parse_time(end_time)

        os.makedirs(output_folder, exist_ok=True)
        
        base_name = os.path.splitext(os.path.basename(input_path))[0]
        output_filename = f"{base_name}_trimmed.mp4"
        output_path = os.path.join(output_folder, output_filename)
        
        duration = end_time - start_time
        
        print(f"جاري قص الفيديو من {start_time}s إلى {end_time}s...")
        
        cmd = [
            FFMPEG_BIN, '-i', input_path,
            '-ss', str(start_time),
            '-t', str(duration),
            '-c', 'copy',  # نسخ بدون إعادة ترميز (أسرع)
            '-y', output_path
        ]
        
        run_ffmpeg(cmd)
        
        if os.path.exists(output_path):
            return {
                'success': True,
                'filename': output_filename,
                'path': output_path,
                'size': os.path.getsize(output_path),
                'duration': duration,
                'start_time': start_time,
                'end_time': end_time
            }
        else:
            raise Exception("فشل قص الفيديو")
            
    except Exception as e:
        print(f"خطأ في قص الفيديو: {e}")
        raise


def trim_audio(input_path, output_folder, start_time, end_time, output_format='mp3'):
    """
    قص الملف الصوتي (اختيار جزء معين)
    
    Args:
        input_path: مسار الملف الصوتي المدخل
        output_folder: مجلد حفظ الملف المقصوص
        start_time: وقت البداية بالثواني
        end_time: وقت النهاية بالثواني
        output_format: صيغة الملف الناتج
    
    Returns:
        dict: معلومات الملف المقصوص
    """
    try:
        # Normalise timestamps: the UI may send seconds or HH:MM:SS.
        start_time = parse_time(start_time)
        end_time = parse_time(end_time)

        os.makedirs(output_folder, exist_ok=True)
        
        base_name = os.path.splitext(os.path.basename(input_path))[0]
        output_filename = f"{base_name}_trimmed.{output_format}"
        output_path = os.path.join(output_folder, output_filename)
        
        duration = end_time - start_time
        
        print(f"جاري قص الصوت من {start_time}s إلى {end_time}s...")
        
        cmd = [
            FFMPEG_BIN, '-i', input_path,
            '-ss', str(start_time),
            '-t', str(duration),
            '-c', 'copy',
            '-y', output_path
        ]
        
        run_ffmpeg(cmd)
        
        if os.path.exists(output_path):
            return {
                'success': True,
                'filename': output_filename,
                'path': output_path,
                'size': os.path.getsize(output_path),
                'duration': duration,
                'start_time': start_time,
                'end_time': end_time,
                'format': output_format
            }
        else:
            raise Exception("فشل قص الصوت")
            
    except Exception as e:
        print(f"خطأ في قص الصوت: {e}")
        raise


def merge_audio_files(input_paths, output_folder, output_format='mp3'):
    """
    دمج عدة ملفات صوتية في ملف واحد
    
    Args:
        input_paths: قائمة بمسارات الملفات الصوتية
        output_folder: مجلد حفظ الملف المدموج
        output_format: صيغة الملف الناتج
    
    Returns:
        dict: معلومات الملف المدموج
    """
    try:
        os.makedirs(output_folder, exist_ok=True)
        
        # Unique token per merge: fixed names in a shared folder let two
        # concurrent merges overwrite each other's list file and output.
        token = uuid.uuid4().hex[:12]
        output_filename = f"merged_audio_{token}.{output_format}"
        output_path = os.path.join(output_folder, output_filename)
        
        # إنشاء ملف قائمة للدمج
        list_file = os.path.join(output_folder, f'merge_list_{token}.txt')
        with open(list_file, 'w') as f:
            for path in input_paths:
                # Absolute path: concat entries resolve relative to the list
                # file, not the CWD. Single quotes must be escaped for the
                # concat demuxer's own quoting rules.
                abs_path = os.path.abspath(path).replace("'", "'\\''")
                f.write(f"file '{abs_path}'\n")
        
        print(f"جاري دمج {len(input_paths)} ملفات صوتية...")
        
        cmd = [
            FFMPEG_BIN,
            '-f', 'concat',
            '-safe', '0',
            '-i', list_file,
            # Re-encode rather than stream-copy. '-c copy' only works when every
            # input already carries exactly the codec the output container
            # wants: merging MP3s into .wav produced a WAV file with an MP3
            # stream inside, and aac/ogg/flac/m4a failed outright.
            *AUDIO_ENCODERS.get(output_format.lower(), AUDIO_ENCODERS['mp3']),
            '-y', output_path
        ]
        
        try:
            run_ffmpeg(cmd)
        finally:
            # Remove the temp list even if FFmpeg failed, otherwise every
            # failed merge leaves a stray .txt in the output folder.
            if os.path.exists(list_file):
                os.remove(list_file)
        
        if os.path.exists(output_path):
            total_duration = sum([get_audio_duration(p) for p in input_paths])
            
            return {
                'success': True,
                'filename': output_filename,
                'path': output_path,
                'size': os.path.getsize(output_path),
                'duration': total_duration,
                'files_count': len(input_paths),
                'format': output_format
            }
        else:
            raise Exception("فشل دمج الملفات الصوتية")
            
    except Exception as e:
        print(f"خطأ في دمج الصوت: {e}")
        raise


def split_video_by_seconds(input_path, output_folder, seconds_per_part, base_filename, overlap_seconds=0):
    """
    تقسيم الفيديو إلى أجزاء بناءً على عدد ثوان محدد لكل جزء
    
    Args:
        input_path: مسار الفيديو المدخل
        output_folder: مجلد حفظ الأجزاء
        seconds_per_part: عدد الثواني لكل جزء
        base_filename: الاسم الأساسي للملف (بدون الامتداد)
        overlap_seconds: عدد ثواني التداخل بين الأجزاء (افتراضي: 0)
    
    Returns:
        list: قائمة بأسماء الملفات الناتجة
    """
    try:
        # الحصول على مدة الفيديو
        total_duration = get_video_duration(input_path)
        print(f"مدة الفيديو الكلية: {total_duration} ثانية")
        print(f"مدة كل جزء: {seconds_per_part} ثانية")
        
        if overlap_seconds > 0:
            print(f"تداخل بين الأجزاء: {overlap_seconds} ثانية")
        
        # حساب عدد الأجزاء المطلوبة
        num_parts = int(total_duration / seconds_per_part)

        if num_parts > 42:
            raise ValueError(f'عدد الأجزاء ({num_parts}) يتجاوز الحد الأقصى (42 جزء). حاول زيادة عدد الثواني لكل جزء.')

        if total_duration % seconds_per_part > 0:
            num_parts += 1
        
        print(f"عدد الأجزاء المتوقعة: {num_parts}")
        
        # إنشاء مجلد المخرجات إذا لم يكن موجوداً
        os.makedirs(output_folder, exist_ok=True)
        
        # قائمة الملفات الناتجة
        output_files = []
        
        # تقسيم الفيديو
        for i in range(num_parts):
            # حساب نقطة البداية لكل جزء
            if i == 0:
                start_time = 0
            else:
                start_time = (i * seconds_per_part) - overlap_seconds
            
            # التأكد من أن نقطة البداية لا تكون سالبة
            start_time = max(0, start_time)
            
            # حساب مدة هذا الجزء
            if i == 0:
                # الجزء الأول: المدة الأساسية فقط
                duration = seconds_per_part
            elif i == num_parts - 1:
                # الجزء الأخير: من نقطة البداية حتى نهاية الفيديو
                duration = total_duration - start_time
            else:
                # الأجزاء الوسطى: المدة الأساسية + التداخل
                duration = seconds_per_part + overlap_seconds
            
            # اسم الملف الناتج
            output_filename = f"{base_filename}_part{i + 1}.mp4"
            output_path = os.path.join(output_folder, output_filename)
            
            print(f"جاري معالجة الجزء {i + 1}/{num_parts}...")
            print(f"  - البداية: {start_time:.2f} ثانية")
            print(f"  - المدة: {duration:.2f} ثانية")
            
            # أمر FFmpeg - جودة عالية متوازن
            cmd = [
                FFMPEG_BIN,
                '-ss', str(start_time),
                '-i', input_path,
                '-t', str(duration),
                '-c:v', 'libx264',
                '-preset', 'veryfast',
                '-crf', '21',
                '-c:a', 'aac',
                '-b:a', '128k',
                '-bufsize', '2000k',
                '-maxrate', '6000k',
                '-movflags', '+faststart',
                '-avoid_negative_ts', '1',
                '-threads', '2',
                '-max_muxing_queue_size', '2048',
                '-y',
                output_path
            ]
            
            # تشغيل الأمر
            result = run_ffmpeg(cmd)
            
            # التحقق من نجاح العملية
            if os.path.exists(output_path):
                output_files.append({
                    'filename': output_filename,
                    'path': output_path,
                    'part_number': i + 1,
                    'start_time': start_time,
                    'duration': duration,
                    'size': os.path.getsize(output_path)
                })
                print(f"✓ تم إنشاء: {output_filename}")
            else:
                raise Exception(f"فشل إنشاء الملف: {output_filename}")
        
        message = f"✓ تم تقسيم الفيديو بنجاح إلى {num_parts} أجزاء!"
        if overlap_seconds > 0:
            message += f" مع تداخل {overlap_seconds} ثانية"
        print(message)
        return output_files
        
    except subprocess.CalledProcessError as e:
        print(f"خطأ في تشغيل FFmpeg: {e}")
        print(f"الخطأ: {e.stderr}")
        raise Exception(f"فشل تقسيم الفيديو: {e.stderr}")
    except Exception as e:
        print(f"خطأ عام: {e}")
        raise


def extract_video_clips(input_path, output_folder, clips, base_filename):
    """
    اقتطاع مقاطع متعددة من الفيديو
    
    Args:
        input_path: مسار الفيديو المدخل
        output_folder: مجلد حفظ المقاطع
        clips: قائمة من المقاطع، كل مقطع عبارة عن dict مع start_time و end_time
        base_filename: الاسم الأساسي للملف (بدون الامتداد)
    
    Returns:
        list: قائمة بأسماء الملفات الناتجة
    """
    try:
        # الحصول على مدة الفيديو
        total_duration = get_video_duration(input_path)
        print(f"مدة الفيديو الكلية: {total_duration} ثانية")
        print(f"عدد المقاطع المطلوب اقتطاعها: {len(clips)}")
        
        # إنشاء مجلد المخرجات إذا لم يكن موجوداً
        os.makedirs(output_folder, exist_ok=True)
        
        # قائمة الملفات الناتجة
        output_files = []
        
        # اقتطاع كل مقطع
        for i, clip in enumerate(clips):
            start_time = clip['start_time']
            end_time = clip['end_time']
            duration = end_time - start_time
            
            # التحقق من صحة الأوقات
            if start_time < 0 or end_time > total_duration or start_time >= end_time:
                print(f"تحذير: المقطع {i + 1} يحتوي على أوقات غير صحيحة، سيتم تخطيه")
                continue
            
            # اسم الملف الناتج
            output_filename = f"{base_filename}_clip{i + 1}.mp4"
            output_path = os.path.join(output_folder, output_filename)
            
            print(f"جاري اقتطاع المقطع {i + 1}/{len(clips)}...")
            print(f"  - من: {start_time:.2f} ثانية")
            print(f"  - إلى: {end_time:.2f} ثانية")
            print(f"  - المدة: {duration:.2f} ثانية")
            
            # أمر FFmpeg - جودة عالية متوازن
            cmd = [
                FFMPEG_BIN,
                '-ss', str(start_time),
                '-i', input_path,
                '-t', str(duration),
                '-c:v', 'libx264',
                '-preset', 'veryfast',
                '-crf', '21',
                '-c:a', 'aac',
                '-b:a', '128k',
                '-bufsize', '2000k',
                '-maxrate', '6000k',
                '-movflags', '+faststart',
                '-avoid_negative_ts', '1',
                '-threads', '2',
                '-max_muxing_queue_size', '2048',
                '-y',
                output_path
            ]
            
            # تشغيل الأمر
            result = run_ffmpeg(cmd)
            
            # التحقق من نجاح العملية
            if os.path.exists(output_path):
                output_files.append({
                    'filename': output_filename,
                    'path': output_path,
                    'clip_number': i + 1,
                    'start_time': start_time,
                    'end_time': end_time,
                    'duration': duration,
                    'size': os.path.getsize(output_path)
                })
                print(f"✓ تم إنشاء: {output_filename}")
            else:
                raise Exception(f"فشل إنشاء الملف: {output_filename}")
        
        print(f"✓ تم اقتطاع {len(output_files)} مقاطع بنجاح!")
        return output_files
        
    except subprocess.CalledProcessError as e:
        print(f"خطأ في تشغيل FFmpeg: {e}")
        print(f"الخطأ: {e.stderr}")
        raise Exception(f"فشل اقتطاع المقاطع: {e.stderr}")
    except Exception as e:
        print(f"خطأ عام: {e}")
        raise
