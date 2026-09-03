"""
نظام معالجة الفيديو المحسّن
يدير العمليات المتزامنة ويمنع استهلاك RAM الزائد
"""

import threading
import queue
import time
import os
from datetime import datetime, timedelta
from config import Config

class VideoProcessorQueue:
    def __init__(self, max_concurrent=20, max_queue_size=100):
        """
        max_concurrent: عدد العمليات المتزامنة (20 مع 24GB RAM)
        max_queue_size: حجم الطابور الأقصى
        """
        self.max_concurrent = max_concurrent
        self.queue = queue.Queue(maxsize=max_queue_size)
        self.active_processes = 0
        self.lock = threading.Lock()
        self.worker_threads = []
        
        # إحصائيات
        self.total_processed = 0
        self.total_failed = 0
        
        # بدء Workers
        self._start_workers()
    
    def _start_workers(self):
        """بدء worker threads"""
        for i in range(self.max_concurrent):
            worker = threading.Thread(target=self._worker, daemon=True)
            worker.start()
            self.worker_threads.append(worker)
        print(f"✅ Started {self.max_concurrent} worker threads")
    
    def _worker(self):
        """Worker thread - يعالج المهام من الطابور"""
        while True:
            try:
                # استلام مهمة من الطابور
                task = self.queue.get(timeout=1)
                
                if task is None:  # إشارة التوقف
                    break
                
                # زيادة عداد العمليات النشطة
                with self.lock:
                    self.active_processes += 1
                
                try:
                    # تنفيذ المهمة
                    func, args, kwargs, result_callback = task
                    result = func(*args, **kwargs)
                    
                    # استدعاء callback مع النتيجة
                    if result_callback:
                        result_callback(result, None)
                    
                    with self.lock:
                        self.total_processed += 1
                        
                except Exception as e:
                    print(f"❌ Error processing task: {e}")
                    if result_callback:
                        result_callback(None, str(e))
                    
                    with self.lock:
                        self.total_failed += 1
                
                finally:
                    # تقليل عداد العمليات النشطة
                    with self.lock:
                        self.active_processes -= 1
                    
                    # إشارة إتمام المهمة
                    self.queue.task_done()
                    
            except queue.Empty:
                continue
    
    def add_task(self, func, args=(), kwargs=None, callback=None):
        """
        إضافة مهمة للطابور
        
        Args:
            func: الدالة للتنفيذ
            args: المعاملات
            kwargs: المعاملات المسماة
            callback: دالة تُستدعى عند الانتهاء (result, error)
        
        Returns:
            True إذا تمت الإضافة، False إذا كان الطابور ممتلئ
        """
        if kwargs is None:
            kwargs = {}
        
        try:
            self.queue.put((func, args, kwargs, callback), block=False)
            return True
        except queue.Full:
            return False
    
    def get_stats(self):
        """الحصول على إحصائيات النظام"""
        with self.lock:
            return {
                'active_processes': self.active_processes,
                'queue_size': self.queue.qsize(),
                'total_processed': self.total_processed,
                'total_failed': self.total_failed,
                'max_concurrent': self.max_concurrent
            }
    
    def wait_for_completion(self):
        """انتظار إتمام جميع المهام"""
        self.queue.join()
    
    def shutdown(self):
        """إيقاف النظام"""
        # إضافة إشارات التوقف
        for _ in self.worker_threads:
            self.queue.put(None)
        
        # انتظار Workers
        for worker in self.worker_threads:
            worker.join()


class TempFileManager:
    """
    Deletes uploaded and generated files once they expire.

    Two mechanisms, deliberately:

      1. register_file() — explicit tracking for files the app knows about.
      2. watch_directory() — a periodic sweep by modification time. This is the
         safety net: it also removes orphans left behind when a request crashed
         mid-processing, which explicit tracking alone would miss.

    Before this, AUTO_DELETE_AFTER_MINUTES was defined in config but nothing
    ever read it, so uploads and outputs accumulated until the disk filled.
    """

    def __init__(self, retention_minutes=30, sweep_interval_seconds=300):
        self.retention_minutes = retention_minutes
        self.sweep_interval_seconds = sweep_interval_seconds
        self.files = {}          # {file_path: expiry_time}
        self.watched_dirs = []   # directories swept by mtime
        self.lock = threading.Lock()

        self.cleanup_thread = threading.Thread(target=self._cleanup_worker, daemon=True)
        self.cleanup_thread.start()

    def watch_directory(self, directory):
        """Sweep this directory for files older than the retention window."""
        with self.lock:
            if directory not in self.watched_dirs:
                self.watched_dirs.append(directory)
        print(f"👁️  Watching for cleanup: {directory} "
              f"(retention {self.retention_minutes} min)")

    def register_file(self, file_path, retention_minutes=None):
        """Track a specific file for deletion."""
        if retention_minutes is None:
            retention_minutes = self.retention_minutes

        expiry_time = datetime.now() + timedelta(minutes=retention_minutes)
        with self.lock:
            self.files[file_path] = expiry_time

    def extend_retention(self, file_path, minutes=30):
        with self.lock:
            if file_path in self.files:
                self.files[file_path] += timedelta(minutes=minutes)

    def remove_file_now(self, file_path):
        with self.lock:
            self.files.pop(file_path, None)
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                print(f"🗑️  Deleted: {file_path}")
        except OSError as e:
            print(f"❌ Error deleting {file_path}: {e}")

    def _sweep_directories(self):
        """Delete anything in the watched directories older than the window."""
        cutoff = time.time() - (self.retention_minutes * 60)
        removed = 0

        with self.lock:
            directories = list(self.watched_dirs)

        for directory in directories:
            if not os.path.isdir(directory):
                continue
            for entry in os.listdir(directory):
                path = os.path.join(directory, entry)
                try:
                    if os.path.isfile(path) and os.path.getmtime(path) < cutoff:
                        os.remove(path)
                        with self.lock:
                            self.files.pop(path, None)
                        removed += 1
                except OSError as e:
                    print(f"❌ Error sweeping {path}: {e}")
        return removed

    def _cleanup_worker(self):
        while True:
            try:
                time.sleep(self.sweep_interval_seconds)

                now = datetime.now()
                with self.lock:
                    expired = [p for p, t in self.files.items() if now >= t]

                for file_path in expired:
                    self.remove_file_now(file_path)

                swept = self._sweep_directories()
                total = len(expired) + swept
                if total:
                    print(f"🧹 Cleanup removed {total} expired file(s)")

            except Exception as e:
                print(f"❌ Cleanup error: {e}")

    def get_stats(self):
        with self.lock:
            tracked = list(self.files)

        total_size = 0
        for file_path in tracked:
            try:
                if os.path.exists(file_path):
                    total_size += os.path.getsize(file_path)
            except OSError:
                pass

        return {
            'total_files': len(tracked),
            'total_size_mb': round(total_size / (1024 * 1024), 2),
            'retention_minutes': self.retention_minutes,
        }


# Global instances, sized from configuration rather than hardcoded for one host.
video_queue = VideoProcessorQueue(max_concurrent=Config.MAX_CONCURRENT_JOBS)
temp_file_manager = TempFileManager(
    retention_minutes=Config.AUTO_DELETE_AFTER_MINUTES,
    sweep_interval_seconds=Config.CLEANUP_INTERVAL_SECONDS,
)
temp_file_manager.watch_directory(Config.UPLOAD_FOLDER)
temp_file_manager.watch_directory(Config.OUTPUT_FOLDER)


def get_system_stats():
    """الحصول على إحصائيات النظام"""
    queue_stats = video_queue.get_stats()
    file_stats = temp_file_manager.get_stats()
    
    return {
        'queue': queue_stats,
        'files': file_stats,
        'ram_usage': _get_ram_usage()
    }


def _get_ram_usage():
    """الحصول على استهلاك RAM"""
    try:
        import psutil
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        return {
            'total_gb': round(mem.total / (1024**3), 2),
            'used_gb': round(mem.used / (1024**3), 2),
            'available_gb': round(mem.available / (1024**3), 2),
            'percent': mem.percent,
            'swap_total_gb': round(swap.total / (1024**3), 2),
            'swap_used_gb': round(swap.used / (1024**3), 2),
            'swap_percent': swap.percent
        }
    except Exception:
        return None
