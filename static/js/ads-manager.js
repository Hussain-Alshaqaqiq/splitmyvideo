// ===== AdSense Ads Manager - النسخة المحسّنة =====
// نظام إعلانات متوافق 100% مع سياسات Google AdSense

class AdsManager {
    constructor() {
        this.adShownInSession = sessionStorage.getItem('adShownInSession') === 'true';
        this.minTimeBetweenAds = 30000; // 30 ثانية بين الإعلانات
    }

    /**
     * عرض إعلان Inline قبل التحميل (للملفات الفردية)
     * متوافق تماماً مع سياسات AdSense
     */
    showDownloadAd(callback, numFiles = 1) {
        // إذا ظهر إعلان في هذه الجلسة، تحميل مباشر
        if (this.adShownInSession) {
            console.log('✅ الإعلان ظهر مسبقاً في هذه الجلسة - تحميل مباشر');
            if (callback) callback();
            return;
        }

        // حساب مدة الإعلان (5-15 ثانية)
        let adDuration = Math.max(5, Math.min(15, numFiles + 3));

        // إنشاء الـ overlay
        const overlay = document.createElement('div');
        overlay.className = 'ad-overlay';
        overlay.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.75);
            z-index: 9998;
            display: flex;
            align-items: center;
            justify-content: center;
            animation: fadeIn 0.3s ease-out;
        `;

        // إنشاء container الإعلان
        const adContainer = document.createElement('div');
        adContainer.className = 'ad-inline-container';
        adContainer.style.cssText = `
            background: white;
            border-radius: 20px;
            padding: 35px;
            max-width: 550px;
            width: 92%;
            box-shadow: 0 15px 50px rgba(0,0,0,0.4);
            text-align: center;
            position: relative;
            z-index: 9999;
            animation: slideUp 0.4s ease-out;
        `;

        adContainer.innerHTML = `
            <style>
                @keyframes fadeIn {
                    from { opacity: 0; }
                    to { opacity: 1; }
                }
                @keyframes slideUp {
                    from { transform: translateY(30px); opacity: 0; }
                    to { transform: translateY(0); opacity: 1; }
                }
                @keyframes pulse {
                    0%, 100% { transform: scale(1); }
                    50% { transform: scale(1.05); }
                }
                .countdown-circle {
                    width: 90px;
                    height: 90px;
                    margin: 0 auto 25px;
                    border-radius: 50%;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    box-shadow: 0 8px 25px rgba(102, 126, 234, 0.4);
                    animation: pulse 2s infinite;
                }
                .countdown-number {
                    font-size: 2.5em;
                    font-weight: bold;
                    color: white;
                }
                .skip-button {
                    background: transparent;
                    color: #667eea;
                    border: 2px solid #667eea;
                    padding: 12px 30px;
                    border-radius: 30px;
                    font-weight: bold;
                    cursor: pointer;
                    font-size: 1em;
                    transition: all 0.3s;
                    margin-top: 20px;
                }
                .skip-button:hover {
                    background: #667eea;
                    color: white;
                    transform: translateY(-2px);
                    box-shadow: 0 5px 20px rgba(102, 126, 234, 0.4);
                }
                .skip-button:active {
                    transform: translateY(0);
                }
                .ad-space {
                    min-height: 120px;
                    background: linear-gradient(135deg, #667eea08 0%, #764ba208 100%);
                    border-radius: 15px;
                    padding: 25px;
                    margin: 25px 0;
                    border: 2px dashed #667eea30;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                }
                @media (max-width: 480px) {
                    .ad-inline-container {
                        padding: 25px 20px !important;
                    }
                    .countdown-circle {
                        width: 70px;
                        height: 70px;
                    }
                    .countdown-number {
                        font-size: 2em;
                    }
                }
            </style>

            <!-- أيقونة التحميل -->
            <div style="font-size: 3.5em; margin-bottom: 15px;">⏬</div>
            
            <!-- العنوان -->
            <h3 style="color: #333; margin: 0 0 10px 0; font-size: 1.4em;">
                جاري تحضير التحميل...
            </h3>
            
            <!-- الوصف -->
            <p style="color: #666; margin: 0 0 25px 0; font-size: 1.05em;">
                سيبدأ التحميل تلقائياً بعد انتهاء العداد
            </p>

            <!-- العداد التنازلي -->
            <div class="countdown-circle">
                <span class="countdown-number" id="countdown">${adDuration}</span>
            </div>

            <!-- منطقة الإعلان -->
            <div class="ad-space" id="adSpace">
                <div style="text-align: center;">
                    <p style="color: #667eea; font-weight: bold; margin: 0 0 8px 0; font-size: 1.1em;">
                        📢 إعلان
                    </p>
                    <p style="color: #999; margin: 0; font-size: 0.95em;">
                        ساعدنا في إبقاء هذه الخدمة مجانية
                    </p>
                    <!-- هنا يمكن إضافة كود AdSense -->
                </div>
            </div>

            <!-- زر التخطي -->
            <button class="skip-button" id="skipBtn">
                ⏭️ تخطي الإعلان والتحميل الآن
            </button>
            
            <!-- رسالة صغيرة -->
            <p style="color: #999; font-size: 0.85em; margin: 15px 0 0 0;">
                أو انتظر لدعم الموقع 💙
            </p>
        `;

        overlay.appendChild(adContainer);
        document.body.appendChild(overlay);

        // منع scroll في الخلفية
        document.body.style.overflow = 'hidden';

        // العد التنازلي
        let timeLeft = adDuration;
        const countdownEl = document.getElementById('countdown');
        
        const countdownInterval = setInterval(() => {
            timeLeft--;
            if (countdownEl) {
                countdownEl.textContent = timeLeft;
                
                // تغيير اللون عند الاقتراب من الصفر
                if (timeLeft <= 3) {
                    countdownEl.style.background = 'linear-gradient(135deg, #4caf50 0%, #8bc34a 100%)';
                }
            }

            if (timeLeft <= 0) {
                clearInterval(countdownInterval);
                closeAndDownload();
            }
        }, 1000);

        // وظيفة الإغلاق
        const closeAndDownload = () => {
            clearInterval(countdownInterval);
            
            // تأثير الإغلاق
            adContainer.style.animation = 'slideUp 0.3s ease-out reverse';
            overlay.style.animation = 'fadeIn 0.3s ease-out reverse';
            
            setTimeout(() => {
                overlay.remove();
                document.body.style.overflow = ''; // إعادة scroll
                
                // حفظ في الجلسة
                sessionStorage.setItem('adShownInSession', 'true');
                this.adShownInSession = true;
                
                // تنفيذ callback (التحميل)
                if (callback) callback();
            }, 300);
        };

        // زر التخطي
        document.getElementById('skipBtn').addEventListener('click', closeAndDownload);

        // إغلاق عند النقر على الخلفية (اختياري)
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) {
                closeAndDownload();
            }
        });
    }

    /**
     * عرض إعلان مطول لتحميل جميع الأجزاء
     */
    showLongDownloadAd(callback, numParts = 3) {
        // إذا ظهر إعلان في هذه الجلسة، تحميل مباشر
        if (this.adShownInSession) {
            console.log('✅ الإعلان ظهر مسبقاً - تحميل مباشر');
            if (callback) callback();
            return;
        }

        // حساب المدة: (عدد الأجزاء - 2) لكن بحد أقصى 120 ثانية
        let adDuration = Math.max(8, Math.min(120, (numParts - 2) * 5));

        // استخدام نفس الدالة لكن بمدة أطول
        this.showDownloadAd(callback, numParts);
    }

    /**
     * بوابة إعلانية عامة — تُستخدم في صفحات التحويل والصوت.
     *
     * NOTE: convert.js and audio.js have always called this method, but it was
     * never defined on AdsManager. Every call threw
     *   TypeError: adsManager.showInterstitialAd is not a function
     * and because the whole conversion routine lives inside the callback,
     * nothing ran at all — no request was ever sent. The split page was
     * unaffected because it calls showDownloadAd(), which does exist.
     *
     * Delegating keeps the existing session logic (one ad per session, then
     * straight through) and guarantees the callback always runs.
     */
    showInterstitialAd(callback) {
        if (typeof callback !== 'function') {
            return;
        }
        try {
            this.showDownloadAd(callback, 1);
        } catch (error) {
            // An advertising failure must never take a feature down with it.
            console.error('Ad gate failed, continuing without it:', error);
            callback();
        }
    }

    /**
     * تهيئة الإعلانات عند تحميل الصفحة
     */
    initializeSidebarAds() {
        console.log('📢 Sidebar ads ready for AdSense');
    }

    initializeStickyBanner() {
        console.log('📢 Sticky banner ready for AdSense');
    }
}

// إنشاء instance عام
const adsManager = new AdsManager();

// Safety net. Ad-gate methods wrap core functionality, so a missing or failing
// method must never block the app. Any unknown adsManager.showXxxAd(callback)
// call runs its callback instead of throwing.
const safeAdsManager = new Proxy(adsManager, {
    get(target, prop) {
        const value = target[prop];
        if (typeof value === 'function') {
            return value.bind(target);
        }
        if (typeof prop === 'string' && /^show.*Ad$/.test(prop)) {
            console.warn(`adsManager.${prop}() is not defined - running callback directly`);
            return (callback) => { if (typeof callback === 'function') callback(); };
        }
        return value;
    }
});

// تهيئة عند التحميل
window.adsManager = safeAdsManager;

document.addEventListener('DOMContentLoaded', () => {
    adsManager.initializeSidebarAds();
    adsManager.initializeStickyBanner();
    console.log('✅ Ads Manager initialized');
});
