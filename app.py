from flask import Flask, render_template, request, jsonify, send_file, url_for, redirect
import os
from config import Config
from werkzeug.utils import secure_filename, safe_join
import uuid
import secrets
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from jinja2 import TemplateNotFound
from video_processor import video_queue, temp_file_manager, get_system_stats
import json
import zipfile
import tempfile
import subprocess
import sys
from video_utils import (
    parse_time,
    is_real_media,
    split_video as split_video_util, 
    get_video_duration, 
    format_duration, 
    format_file_size,
    convert_video_format,
    convert_audio_format,
    compress_video,
    trim_video,
    trim_audio,
    merge_audio_files,
    split_video_by_seconds,
    extract_video_clips
)

app = Flask(__name__)
app.config.from_object(Config)

# إنشاء المجلدات إذا لم تكن موجودة
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)

# التحقق من تثبيت FFmpeg عند بدء التطبيق
def check_ffmpeg():
    """التحقق من تثبيت FFmpeg"""
    try:
        result = subprocess.run([Config.FFMPEG_BIN, '-version'], 
                              capture_output=True, 
                              text=True, 
                              timeout=5)
        if result.returncode == 0:
            print("✓ FFmpeg is installed and working")
            return True
        else:
            print("✗ FFmpeg found but not working properly")
            return False
    except FileNotFoundError:
        print(f"✗ FFmpeg not found at {Config.FFMPEG_BIN!r}. Please install FFmpeg.")
        print("For Render.com: Make sure Aptfile contains 'ffmpeg'")
        return False
    except Exception as e:
        print(f"✗ Error checking FFmpeg: {e}")
        return False

# فحص FFmpeg عند بدء التطبيق
if not check_ffmpeg():
    print("WARNING: FFmpeg is not available. Video processing will fail!")
    print("Please ensure FFmpeg is installed on your system.")



# ---------------------------------------------------------------------------
# Path safety
#
# Several endpoints accept a filename from the JSON request body and join it
# onto an upload/output directory. Joining an attacker-controlled string with
# os.path.join() allows "../../etc/passwd" to escape the directory, letting
# FFmpeg read arbitrary files off the server. safe_join() returns None instead
# of escaping, so every caller must check the result.
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# Rate limiting
#
# Every processing endpoint spawns an FFmpeg encode, which is expensive in CPU,
# RAM and disk. Without limits a single client can queue unlimited 500 MB
# encodes and exhaust the instance - a denial-of-service that costs the
# attacker almost nothing.
#
# The default in-memory store is per-process and resets on restart, which is
# fine for a single instance. Point RATELIMIT_STORAGE_URI at Redis when running
# more than one worker or instance, or the limits are counted separately by each.
# ---------------------------------------------------------------------------
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per hour"],
    storage_uri=os.environ.get('RATELIMIT_STORAGE_URI', 'memory://'),
    strategy="fixed-window",
)

PROCESSING_LIMIT = os.environ.get('PROCESSING_RATE_LIMIT', '20 per hour;5 per minute')
UPLOAD_LIMIT = os.environ.get('UPLOAD_RATE_LIMIT', '30 per hour;10 per minute')


@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({
        'error': 'عدد كبير من الطلبات. انتظر قليلاً ثم حاول مرة أخرى.'
    }), 429


def server_error(exception, message='حدث خطأ أثناء المعالجة. حاول مرة أخرى.'):
    """
    Log the real exception, return a generic message.

    Routes previously returned jsonify({'error': str(e)}), which handed the
    client absolute server paths ("static/uploads/..."), FFmpeg internals and
    Python exception text. That is free reconnaissance for an attacker and
    means nothing to a normal user.
    """
    app.logger.exception('Request failed: %s', exception)
    return jsonify({'error': message}), 500


@app.after_request
def set_security_headers(response):
    """
    Baseline hardening headers.

    - nosniff stops a browser from re-interpreting an uploaded file as HTML
      or JavaScript based on its bytes rather than its declared type.
    - frame-ancestors/X-Frame-Options block clickjacking via an invisible
      iframe over the upload button.
    - The CSP allows Google AdSense, since the site serves ads; 'unsafe-inline'
      is required by the inline adsbygoogle push() snippets already in the
      templates. Removing those snippets would let the CSP be tightened.
    """
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
    response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
    response.headers.setdefault('Permissions-Policy',
                                'geolocation=(), microphone=(), camera=()')
    response.headers.setdefault('Content-Security-Policy', (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://pagead2.googlesyndication.com "
        "https://googleads.g.doubleclick.net https://www.googletagmanager.com; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; "
        "media-src 'self' blob:; "
        "connect-src 'self'; "
        "frame-src https://googleads.g.doubleclick.net https://tpc.googlesyndication.com; "
        "frame-ancestors 'self'; "
        "base-uri 'self'; "
        "form-action 'self'"
    ))
    if request.is_secure:
        response.headers.setdefault('Strict-Transport-Security',
                                    'max-age=31536000; includeSubDomains')
    return response


def _resolve_inside(folder, filename):
    """
    Resolve `filename` inside `folder`, or return None if it is not a plain
    file name living directly in that folder.
    """
    if not filename or not isinstance(filename, str):
        return None

    resolved = safe_join(folder, filename)
    if resolved is None:
        return None

    # safe_join blocks '..' segments, but a payload can still resolve to the
    # directory itself (e.g. '.'). Require a real child path.
    root = os.path.abspath(folder)
    target = os.path.abspath(resolved)
    if target == root or not target.startswith(root + os.sep):
        return None

    return resolved


def safe_upload_path(filename):
    """Resolve a filename inside UPLOAD_FOLDER, or None if it tries to escape."""
    return _resolve_inside(app.config['UPLOAD_FOLDER'], filename)


def safe_output_path(filename):
    """Resolve a filename inside OUTPUT_FOLDER, or None if it tries to escape."""
    return _resolve_inside(app.config['OUTPUT_FOLDER'], filename)


def unique_filename(original_name):
    """
    Build a collision-proof storage name.

    secure_filename() strips path separators but keeps the original basename,
    so two users uploading "video.mp4" at the same time overwrote each other
    (and one received the other's file). Prefixing a short random token makes
    every stored name unique while keeping it recognisable to the user.
    """
    safe_name = secure_filename(original_name) or 'upload'
    return f"{uuid.uuid4().hex[:12]}_{safe_name}"


def track_for_cleanup(*paths):
    """Register files so the TempFileManager deletes them once they expire."""
    minutes = app.config.get('AUTO_DELETE_AFTER_MINUTES', 30)
    for path in paths:
        if path:
            temp_file_manager.register_file(path, retention_minutes=minutes)


def allowed_file(filename):
    """
    Accept both video and audio uploads.

    ALLOWED_AUDIO_EXTENSIONS was defined in config but never read, so uploading
    an .mp3 to the audio page failed with "File type not allowed" even though
    the page's file input advertises audio/*.
    """
    if '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower()
    return (ext in app.config['ALLOWED_EXTENSIONS']
            or ext in app.config['ALLOWED_AUDIO_EXTENSIONS'])


@app.route('/')
def index():
    """الصفحة الرئيسية"""
    return render_template('index.html')


@app.route('/privacy')
def privacy():
    """صفحة سياسة الخصوصية"""
    return render_template('privacy.html')


@app.route('/terms')
def terms():
    """صفحة شروط الاستخدام"""
    return render_template('terms.html')


@app.route('/about')
def about():
    """صفحة من نحن"""
    return render_template('about.html')


@app.route('/convert')
def convert_page():
    """صفحة تحويل صيغ الفيديو"""
    return render_template('convert.html')

@app.route('/faq')
def faq_page():
    """faq"""
    return render_template('FAQ.html')

@app.route('/audio')
def audio_page():
    """صفحة تحويل واستخراج الصوت"""
    return render_template('audio.html')


@app.route('/how-to-use')
def how_to_use():
    """صفحة كيفية الاستخدام"""
    return render_template('how-to-use.html')


@app.route('/sitemap.xml')
def sitemap():
    return send_file('static/sitemap.xml', mimetype='text/xml')

# @app.route("/health") # DISABLED - duplicate
def health_check_old_disabled():
    """فحص صحة التطبيق"""
    health_status = {
        'status': 'healthy',
        'ffmpeg_installed': False,
        'ffmpeg_version': None,
        'upload_folder_exists': os.path.exists(app.config['UPLOAD_FOLDER']),
        'output_folder_exists': os.path.exists(app.config['OUTPUT_FOLDER'])
    }
    
    # فحص FFmpeg
    try:
        result = subprocess.run(['/usr/bin/ffmpeg', '-version'], 
                              capture_output=True, 
                              text=True, 
                              timeout=5)
        if result.returncode == 0:
            health_status['ffmpeg_installed'] = True
            # استخراج رقم الإصدار
            version_line = result.stdout.split('\n')[0]
            health_status['ffmpeg_version'] = version_line
    except Exception:
        health_status['ffmpeg_installed'] = False
    
    # تحديد حالة التطبيق
    if not health_status['ffmpeg_installed']:
        health_status['status'] = 'unhealthy'
        health_status['error'] = 'FFmpeg is not installed'
    
    return jsonify(health_status)


@app.route('/convert-audio', methods=['POST'])
@limiter.limit(lambda: PROCESSING_LIMIT)
def convert_audio():
    """تحويل صيغة الصوت أو استخراج الصوت من الفيديو"""
    try:
        data = request.get_json()
        filename = data.get('filename')
        output_format = data.get('output_format', 'mp3')
        quality = data.get('quality', 'medium')
        
        if not filename:
            return jsonify({'error': 'اسم الملف مطلوب'}), 400
        
        # الصيغ المدعومة
        supported_formats = ['mp3', 'wav', 'aac', 'ogg', 'flac', 'm4a']
        if output_format.lower() not in supported_formats:
            return jsonify({'error': f'الصيغة {output_format} غير مدعومة'}), 400
        
        # مسار الملف المدخل
        input_path = safe_upload_path(filename)
        if input_path is None:
            return jsonify({'error': 'اسم الملف غير صالح'}), 400
        
        if not os.path.exists(input_path):
            return jsonify({'error': 'الملف غير موجود'}), 404
        
        # تحويل/استخراج الصوت
        result = convert_audio_format(
            input_path=input_path,
            output_folder=app.config['OUTPUT_FOLDER'],
            output_format=output_format,
            quality=quality
        )
        
        if result['success']:
            action = "استخراج" if result['is_extracted'] else "تحويل"
            return jsonify({
                'success': True,
                'message': f'تم {action} الصوت بنجاح إلى {output_format.upper()}',
                'file': {
                    'filename': result['filename'],
                    'format': result['format'],
                    'quality': result['quality'],
                    'duration': format_duration(result['duration']) if result['duration'] > 0 else 'غير متاح',
                    'size': format_file_size(result['size']),
                    'is_extracted': result['is_extracted'],
                    'download_url': url_for('download_file', filename=result['filename'])
                }
            })
        else:
            return jsonify({'error': 'فشل معالجة الصوت'}), 500
    
    except Exception as e:
        print(f"خطأ في معالجة الصوت: {e}")
        return server_error(e)


@app.route('/compress-video', methods=['POST'])
@limiter.limit(lambda: PROCESSING_LIMIT)
def compress_video_endpoint():
    """ضغط الفيديو"""
    try:
        data = request.get_json()
        filename = data.get('filename')
        compression_level = data.get('compression_level', 'medium')
        
        if not filename:
            return jsonify({'error': 'اسم الملف مطلوب'}), 400
        
        input_path = safe_upload_path(filename)
        if input_path is None:
            return jsonify({'error': 'اسم الملف غير صالح'}), 400
        
        if not os.path.exists(input_path):
            return jsonify({'error': 'الملف غير موجود'}), 404
        
        result = compress_video(
            input_path=input_path,
            output_folder=app.config['OUTPUT_FOLDER'],
            compression_level=compression_level
        )
        
        if result['success']:
            return jsonify({
                'success': True,
                'message': f'تم ضغط الفيديو بنجاح',
                'file': {
                    'filename': result['filename'],
                    'duration': format_duration(result['duration']),
                    'size': format_file_size(result['size']),
                    'original_size': format_file_size(result['original_size']),
                    'reduction_percent': round(result['reduction_percent'], 1),
                    'download_url': url_for('download_file', filename=result['filename'])
                }
            })
        else:
            return jsonify({'error': 'فشل ضغط الفيديو'}), 500
    
    except Exception as e:
        print(f"خطأ في ضغط الفيديو: {e}")
        return server_error(e)


@app.route('/trim-video', methods=['POST'])
@limiter.limit(lambda: PROCESSING_LIMIT)
def trim_video_endpoint():
    """قص الفيديو"""
    try:
        data = request.get_json()
        filename = data.get('filename')
        try:
            start_time = parse_time(data.get('start_time', 0))
            end_time = parse_time(data.get('end_time', 0))
        except (ValueError, TypeError):
            return jsonify({'error': 'صيغة الوقت غير صالحة'}), 400
        
        if not filename:
            return jsonify({'error': 'اسم الملف مطلوب'}), 400
        
        if end_time <= start_time:
            return jsonify({'error': 'وقت النهاية يجب أن يكون أكبر من وقت البداية'}), 400
        
        input_path = safe_upload_path(filename)
        if input_path is None:
            return jsonify({'error': 'اسم الملف غير صالح'}), 400
        
        if not os.path.exists(input_path):
            return jsonify({'error': 'الملف غير موجود'}), 404
        
        result = trim_video(
            input_path=input_path,
            output_folder=app.config['OUTPUT_FOLDER'],
            start_time=start_time,
            end_time=end_time
        )
        
        if result['success']:
            return jsonify({
                'success': True,
                'message': f'تم قص الفيديو بنجاح',
                'file': {
                    'filename': result['filename'],
                    'duration': format_duration(result['duration']),
                    'size': format_file_size(result['size']),
                    'start_time': format_duration(result['start_time']),
                    'end_time': format_duration(result['end_time']),
                    'download_url': url_for('download_file', filename=result['filename'])
                }
            })
        else:
            return jsonify({'error': 'فشل قص الفيديو'}), 500
    
    except Exception as e:
        print(f"خطأ في قص الفيديو: {e}")
        return server_error(e)


@app.route('/trim-audio', methods=['POST'])
@limiter.limit(lambda: PROCESSING_LIMIT)
def trim_audio_endpoint():
    """قص الصوت"""
    try:
        data = request.get_json()
        filename = data.get('filename')
        try:
            start_time = parse_time(data.get('start_time', 0))
            end_time = parse_time(data.get('end_time', 0))
        except (ValueError, TypeError):
            return jsonify({'error': 'صيغة الوقت غير صالحة'}), 400
        output_format = data.get('output_format', 'mp3')
        
        if not filename:
            return jsonify({'error': 'اسم الملف مطلوب'}), 400
        
        if end_time <= start_time:
            return jsonify({'error': 'وقت النهاية يجب أن يكون أكبر من وقت البداية'}), 400
        
        input_path = safe_upload_path(filename)
        if input_path is None:
            return jsonify({'error': 'اسم الملف غير صالح'}), 400
        
        if not os.path.exists(input_path):
            return jsonify({'error': 'الملف غير موجود'}), 404
        
        result = trim_audio(
            input_path=input_path,
            output_folder=app.config['OUTPUT_FOLDER'],
            start_time=start_time,
            end_time=end_time,
            output_format=output_format
        )
        
        if result['success']:
            return jsonify({
                'success': True,
                'message': f'تم قص الصوت بنجاح',
                'file': {
                    'filename': result['filename'],
                    'duration': format_duration(result['duration']),
                    'size': format_file_size(result['size']),
                    'start_time': format_duration(result['start_time']),
                    'end_time': format_duration(result['end_time']),
                    'download_url': url_for('download_file', filename=result['filename'])
                }
            })
        else:
            return jsonify({'error': 'فشل قص الصوت'}), 500
    
    except Exception as e:
        print(f"خطأ في قص الصوت: {e}")
        return server_error(e)


@app.route('/merge-audio', methods=['POST'])
@limiter.limit(lambda: PROCESSING_LIMIT)
def merge_audio_endpoint():
    """دمج ملفات صوتية"""
    try:
        # استقبال عدة ملفات
        files = request.files.getlist('audio_files')
        output_format = request.form.get('output_format', 'mp3')
        
        if len(files) < 2:
            return jsonify({'error': 'يجب رفع ملفين صوتيين على الأقل'}), 400
        
        # حفظ الملفات مؤقتاً
        temp_paths = []
        for file in files:
            if file and file.filename:
                filename = unique_filename(file.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                
                if not is_real_media(filepath):
                    try:
                        os.remove(filepath)
                    except OSError:
                        pass
                    return jsonify({'error': f'الملف {file.filename} ليس ملف صوت صالح'}), 400
                
                track_for_cleanup(filepath)
                temp_paths.append(filepath)
        
        if len(temp_paths) < 2:
            return jsonify({'error': 'فشل رفع الملفات'}), 400
        
        # دمج الملفات
        result = merge_audio_files(
            input_paths=temp_paths,
            output_folder=app.config['OUTPUT_FOLDER'],
            output_format=output_format
        )
        
        if result['success']:
            return jsonify({
                'success': True,
                'message': f'تم دمج {result["files_count"]} ملفات صوتية بنجاح',
                'file': {
                    'filename': result['filename'],
                    'duration': format_duration(result['duration']),
                    'size': format_file_size(result['size']),
                    'files_count': result['files_count'],
                    'download_url': url_for('download_file', filename=result['filename'])
                }
            })
        else:
            return jsonify({'error': 'فشل دمج الملفات الصوتية'}), 500
    
    except Exception as e:
        print(f"خطأ في دمج الصوت: {e}")
        return server_error(e)


@app.route('/convert-video', methods=['POST'])
@limiter.limit(lambda: PROCESSING_LIMIT)
def convert_video():
    """تحويل صيغة الفيديو"""
    try:
        data = request.get_json()
        filename = data.get('filename')
        output_format = data.get('output_format', 'mp4')
        quality = data.get('quality', 'medium')
        
        if not filename:
            return jsonify({'error': 'اسم الملف مطلوب'}), 400
        
        # الصيغ المدعومة
        supported_formats = ['mp4', 'avi', 'mov', 'mkv', 'webm', 'flv', 'wmv']
        if output_format.lower() not in supported_formats:
            return jsonify({'error': f'الصيغة {output_format} غير مدعومة'}), 400
        
        # مسار الملف المدخل
        input_path = safe_upload_path(filename)
        if input_path is None:
            return jsonify({'error': 'اسم الملف غير صالح'}), 400
        
        if not os.path.exists(input_path):
            return jsonify({'error': 'الملف غير موجود'}), 404
        
        # تحويل الفيديو
        result = convert_video_format(
            input_path=input_path,
            output_folder=app.config['OUTPUT_FOLDER'],
            output_format=output_format,
            quality=quality
        )
        
        if result['success']:
            return jsonify({
                'success': True,
                'message': f'تم تحويل الفيديو بنجاح إلى {output_format.upper()}',
                'file': {
                    'filename': result['filename'],
                    'format': result['format'],
                    'quality': result['quality'],
                    'duration': format_duration(result['duration']),
                    'size': format_file_size(result['size']),
                    'download_url': url_for('download_file', filename=result['filename'])
                }
            })
        else:
            return jsonify({'error': 'فشل تحويل الفيديو'}), 500
    
    except Exception as e:
        print(f"خطأ في تحويل الفيديو: {e}")
        return server_error(e)


@app.route('/upload', methods=['POST'])
@limiter.limit(lambda: UPLOAD_LIMIT)
def upload_video():
    """رفع الفيديو"""
    try:
        print("📤 Upload request received")
        
        # التحقق من وجود الملف
        if 'video' not in request.files:
            print("❌ No file in request")
            return jsonify({'error': 'لم يتم اختيار ملف'}), 400
        
        file = request.files['video']
        
        if file.filename == '':
            print("❌ Empty filename")
            return jsonify({'error': 'لم يتم اختيار ملف'}), 400
        
        if not allowed_file(file.filename):
            print(f"❌ File type not allowed: {file.filename}")
            return jsonify({'error': 'صيغة الملف غير مدعومة'}), 400
        
        # حفظ الملف باسم فريد لتجنب تعارض الأسماء بين المستخدمين
        filename = unique_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        print(f"💾 Saving file: {filename}")
        file.save(filepath)
        
        # التحقق من حفظ الملف
        if not os.path.exists(filepath):
            print(f"❌ File not saved: {filepath}")
            return jsonify({'error': 'فشل حفظ الملف'}), 500
        
        print(f"✓ File saved: {filepath}")
        
        # Defence in depth: the extension check above is trivially bypassed by
        # renaming any file to .mp4. Confirm it really decodes as media before
        # it is allowed anywhere near an encoder.
        if not is_real_media(filepath):
            try:
                os.remove(filepath)
            except OSError:
                pass
            return jsonify({'error': 'الملف ليس ملف صوت أو فيديو صالح'}), 400
        
        track_for_cleanup(filepath)
        
        # الحصول على معلومات الفيديو
        try:
            print("📊 Getting video duration...")
            duration = get_video_duration(filepath)
            duration_formatted = format_duration(duration)
            print(f"✓ Duration: {duration_formatted}")
        except Exception as e:
            print(f"⚠️ Could not get duration: {e}")
            duration = 0
            duration_formatted = "غير معروف"
        
        response_data = {
            'success': True,
            'filename': filename,
            'duration': duration,
            'duration_formatted': duration_formatted
        }
        
        print(f"✓ Upload successful: {filename}")
        return jsonify(response_data)
    
    except Exception as e:
        print(f"❌ Upload error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'خطأ في رفع الملف: {str(e)}'}), 500


@app.route('/split', methods=['POST'])
@limiter.limit(lambda: PROCESSING_LIMIT)
def split_video():
    """تقسيم الفيديو"""
    try:
        print("✂️ Split request received")
        data = request.get_json()
        
        if not data:
            print("❌ No JSON data received")
            return jsonify({'error': 'لم يتم إرسال بيانات'}), 400
        
        filename = data.get('filename')
        num_parts = int(data.get('num_parts', 2))
        overlap_seconds = int(data.get('overlap_seconds', 0))
        quality_preset = data.get('quality_preset', 'veryfast')  # الجودة من المستخدم
        
        # الوضع الافتراضي: جودة عالية (False = لا وضع سريع)
        # يمكن تفعيل الوضع السريع بـ FAST_MODE=True في متغيرات البيئة
        fast_mode = os.environ.get('FAST_MODE', 'False').lower() == 'true'
        
        print(f"📋 Split parameters: file={filename}, parts={num_parts}, overlap={overlap_seconds}, quality={quality_preset}, fast_mode={fast_mode}")
        
        if not filename:
            print("❌ No filename provided")
            return jsonify({'error': 'اسم الملف مطلوب'}), 400
        
        if num_parts < 2 or num_parts > 20:
            print(f"❌ Invalid num_parts: {num_parts}")
            return jsonify({'error': 'عدد الأجزاء يجب أن يكون بين 2 و 20'}), 400
        
        if overlap_seconds < 0 or overlap_seconds > 30:
            print(f"❌ Invalid overlap: {overlap_seconds}")
            return jsonify({'error': 'التداخل يجب أن يكون بين 0 و 30 ثانية'}), 400
        
        # مسار الملف المدخل
        input_path = safe_upload_path(filename)
        if input_path is None:
            return jsonify({'error': 'اسم الملف غير صالح'}), 400
        
        if not os.path.exists(input_path):
            print(f"❌ File not found: {input_path}")
            return jsonify({'error': 'الملف غير موجود'}), 404
        
        print(f"✓ Input file found: {input_path}")
        
        # الاسم الأساسي بدون الامتداد
        base_filename = os.path.splitext(filename)[0]
        
        # تقسيم الفيديو مع التداخل
        print(f"🎬 Starting video split...")
        output_files = split_video_util(
            input_path=input_path,
            output_folder=app.config['OUTPUT_FOLDER'],
            num_parts=num_parts,
            base_filename=base_filename,
            overlap_seconds=overlap_seconds,
            fast_mode=fast_mode,
            quality_preset=quality_preset
        )
        
        print(f"✓ Split completed: {len(output_files)} files created")
        
        # تنسيق النتائج للإرجاع
        results = []
        for file_info in output_files:
            results.append({
                'filename': file_info['filename'],
                'part_number': file_info['part_number'],
                'duration': format_duration(file_info['duration']),
                'size': format_file_size(file_info['size']),
                'download_url': url_for('download_file', filename=file_info['filename'])
            })
        
        message = f'تم تقسيم الفيديو بنجاح إلى {num_parts} أجزاء'
        if overlap_seconds > 0:
            message += f' مع تداخل {overlap_seconds} ثانية'
        
        response_data = {
            'success': True,
            'message': message,
            'files': results
        }
        
        print(f"✓ Returning response with {len(results)} files")
        return jsonify(response_data)
    
    except Exception as e:
        print(f"❌ Split error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'خطأ في تقسيم الفيديو: {str(e)}'}), 500


@app.route('/split-by-seconds', methods=['POST'])
@limiter.limit(lambda: PROCESSING_LIMIT)
def split_by_seconds():
    """تقسيم الفيديو حسب عدد الثواني لكل جزء"""
    try:
        data = request.get_json()
        filename = data.get('filename')
        seconds_per_part = int(data.get('seconds_per_part', 10))
        overlap_seconds = int(data.get('overlap_seconds', 0))
        
        if not filename:
            return jsonify({'error': 'اسم الملف مطلوب'}), 400
        
        if seconds_per_part < 1 or seconds_per_part > 3600:
            return jsonify({'error': 'عدد الثواني يجب أن يكون بين 1 و 3600'}), 400
        
        if overlap_seconds < 0 or overlap_seconds > 30:
            return jsonify({'error': 'التداخل يجب أن يكون بين 0 و 30 ثانية'}), 400
        
        # مسار الملف المدخل
        input_path = safe_upload_path(filename)
        if input_path is None:
            return jsonify({'error': 'اسم الملف غير صالح'}), 400
        
        if not os.path.exists(input_path):
            return jsonify({'error': 'الملف غير موجود'}), 404
        
        # الاسم الأساسي بدون الامتداد
        base_filename = os.path.splitext(filename)[0]
        
        # تقسيم الفيديو حسب الثواني مع التداخل
        output_files = split_video_by_seconds(
            input_path=input_path,
            output_folder=app.config['OUTPUT_FOLDER'],
            seconds_per_part=seconds_per_part,
            base_filename=base_filename,
            overlap_seconds=overlap_seconds
        )
        
        # تنسيق النتائج للإرجاع
        results = []
        for file_info in output_files:
            results.append({
                'filename': file_info['filename'],
                'part_number': file_info['part_number'],
                'duration': format_duration(file_info['duration']),
                'size': format_file_size(file_info['size']),
                'download_url': url_for('download_file', filename=file_info['filename'])
            })
        
        message = f'تم تقسيم الفيديو بنجاح إلى {len(results)} أجزاء (كل جزء {seconds_per_part} ثانية)'
        if overlap_seconds > 0:
            message += f' مع تداخل {overlap_seconds} ثانية'
        
        return jsonify({
            'success': True,
            'message': message,
            'files': results
        })
    
    except Exception as e:
        print(f"خطأ في تقسيم الفيديو: {e}")
        return server_error(e)


@app.route('/extract-clips', methods=['POST'])
@limiter.limit(lambda: PROCESSING_LIMIT)
def extract_clips():
    """اقتطاع مقاطع متعددة من الفيديو"""
    try:
        data = request.get_json()
        filename = data.get('filename')
        clips = data.get('clips', [])
        
        if not filename:
            return jsonify({'error': 'اسم الملف مطلوب'}), 400
        
        if not clips or len(clips) == 0:
            return jsonify({'error': 'يجب تحديد مقطع واحد على الأقل'}), 400
        
        if len(clips) > 20 :
            return jsonify({'error': 'يمكن اقتطاع 20 مقاطع كحد أقصى في المرة الواحدة'}), 400
        
        # التحقق من صحة المقاطع وتحويل الأوقات إلى ثوانٍ
        # Validation alone was not enough: the original dicts (with string
        # timestamps) were passed straight through to extract_video_clips,
        # which then did end - start on two strings.
        normalized_clips = []
        for i, clip in enumerate(clips):
            if 'start_time' not in clip or 'end_time' not in clip:
                return jsonify({'error': f'المقطع {i + 1} يجب أن يحتوي على start_time و end_time'}), 400
            
            try:
                start = parse_time(clip['start_time'])
                end = parse_time(clip['end_time'])
            except (ValueError, TypeError):
                return jsonify({'error': f'المقطع {i + 1}: صيغة الوقت غير صالحة'}), 400
            
            if start < 0 or end <= start:
                return jsonify({'error': f'المقطع {i + 1}: وقت النهاية يجب أن يكون أكبر من وقت البداية'}), 400
            
            normalized_clips.append({**clip, 'start_time': start, 'end_time': end})
        
        clips = normalized_clips
        
        # مسار الملف المدخل
        input_path = safe_upload_path(filename)
        if input_path is None:
            return jsonify({'error': 'اسم الملف غير صالح'}), 400
        
        if not os.path.exists(input_path):
            return jsonify({'error': 'الملف غير موجود'}), 404
        
        # الاسم الأساسي بدون الامتداد
        base_filename = os.path.splitext(filename)[0]
        
        # اقتطاع المقاطع
        output_files = extract_video_clips(
            input_path=input_path,
            output_folder=app.config['OUTPUT_FOLDER'],
            clips=clips,
            base_filename=base_filename
        )
        
        # تنسيق النتائج للإرجاع
        results = []
        for file_info in output_files:
            results.append({
                'filename': file_info['filename'],
                'clip_number': file_info['clip_number'],
                'start_time': format_duration(file_info['start_time']),
                'end_time': format_duration(file_info['end_time']),
                'duration': format_duration(file_info['duration']),
                'size': format_file_size(file_info['size']),
                'download_url': url_for('download_file', filename=file_info['filename'])
            })
        
        return jsonify({
            'success': True,
            'message': f'تم اقتطاع {len(results)} مقاطع بنجاح من الفيديو',
            'files': results
        })
    
    except Exception as e:
        print(f"خطأ في اقتطاع المقاطع: {e}")
        return server_error(e)


@app.route('/download/<filename>')
def download_file(filename):
    """تحميل ملف"""
    try:
        filepath = safe_output_path(filename)
        
        if filepath is None:
            return jsonify({'error': 'اسم الملف غير صالح'}), 400
        
        if not os.path.exists(filepath):
            return jsonify({'error': 'الملف غير موجود'}), 404
        
        return send_file(filepath, as_attachment=True)
    
    except Exception as e:
        return server_error(e)


@app.route('/download-all', methods=['POST'])
@limiter.limit(lambda: PROCESSING_LIMIT)
def download_all():
    """تحميل جميع الأجزاء في ملف مضغوط واحد"""
    try:
        data = request.get_json()
        files = data.get('files', [])
        
        if not files:
            return jsonify({'error': 'لا توجد ملفات للتحميل'}), 400
        
        # إنشاء ملف مؤقت للـ zip
        temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
        
        try:
            # إنشاء ملف ZIP
            with zipfile.ZipFile(temp_zip.name, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # zipfile happily writes duplicate entries, producing an
                # archive that some extractors reject and others silently
                # truncate. Deduplicate before writing.
                added_names = set()
                
                for filename in files:
                    filepath = safe_output_path(filename)
                    
                    if filepath is None:
                        print(f"تحذير: اسم ملف غير صالح: {filename}")
                        continue
                    
                    if filename in added_names:
                        continue
                    added_names.add(filename)
                    
                    if os.path.exists(filepath):
                        # إضافة الملف للـ ZIP
                        zipf.write(filepath, arcname=filename)
                    else:
                        print(f"تحذير: الملف غير موجود: {filename}")
            
            # إرسال ملف الـ ZIP
            return send_file(
                temp_zip.name,
                as_attachment=True,
                download_name='video_parts.zip',
                mimetype='application/zip'
            )
        
        finally:
            # حذف الملف المؤقت بعد الإرسال
            # Flask سيحذفه تلقائياً بعد إرسال الملف
            pass
    
    except Exception as e:
        print(f"خطأ في تحميل جميع الملفات: {e}")
        return server_error(e)

@app.route('/stats')
def system_stats():
    """
    إحصائيات النظام - JSON

    This endpoint was public and returned RAM totals, swap usage, CPU load,
    disk free space and queue depth to anyone who asked. That is an
    infrastructure map for an attacker sizing a denial-of-service attempt, and
    it tells a normal visitor nothing useful. It is now off unless
    STATS_PUBLIC=true, and can be protected with a token via STATS_TOKEN.
    """
    stats_token = os.environ.get('STATS_TOKEN')
    stats_public = os.environ.get('STATS_PUBLIC', 'false').lower() == 'true'

    if stats_token:
        supplied = request.headers.get('X-Stats-Token') or request.args.get('token')
        if not supplied or not secrets.compare_digest(supplied, stats_token):
            return jsonify({'error': 'غير مصرح'}), 403
    elif not stats_public:
        return jsonify({'error': 'غير متاح'}), 404

    try:
        stats = get_system_stats()
        return jsonify(stats)
    except Exception as e:
        return server_error(e)


@app.route('/stats-page')
def stats_page():
    """
    صفحة الإحصائيات - HTML

    Hidden alongside /stats, otherwise this page renders and then fails to
    fetch its data, which looks like a broken site rather than a closed door.
    """
    if not (os.environ.get('STATS_PUBLIC', 'false').lower() == 'true'
            or os.environ.get('STATS_TOKEN')):
        return render_template('index.html'), 404
    return render_template('stats.html')

@app.route('/ads.txt')
def ads_txt():
    """ملف ads.txt لـ Google AdSense"""
    return send_file('static/ads.txt', mimetype='text/plain')

@app.route('/google7b320551755216e9.html')
def google_verification():
    """ملف التحقق من Google Search Console"""
    return send_file('static/google7b320551755216e9.html', mimetype='text/html')

@app.route('/blog')
def blog():
    """صفحة المدونة"""
    return render_template('blog.html')

@app.route('/blog/<article_slug>')
def blog_article(article_slug):
    """مقالات المدونة"""
    try:
        return render_template(f'blog/{article_slug}.html')
    except TemplateNotFound:
        # إذا لم يوجد المقال، أرجع للمدونة
        return redirect(url_for('blog'))

if __name__ == '__main__':
    # debug=True enables the interactive Werkzeug debugger, which is a remote
    # code execution console. It must never be on outside local development,
    # and it is never used in production anyway (Gunicorn serves the app there).
    debug = os.environ.get('FLASK_ENV') == 'development'

    # Bind to localhost by default. Set HOST=0.0.0.0 deliberately if you want
    # to reach the dev server from your phone on the same Wi-Fi.
    host = os.environ.get('HOST', '127.0.0.1')
    port = int(os.environ.get('PORT', 5000))

    print(f"→ http://{host}:{port}  (debug={debug})")
    app.run(debug=debug, host=host, port=port)
