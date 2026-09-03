// ===== Global Variables =====
let uploadedFile = null;
let videoDuration = 0;
let uploadedFileName = '';
let downloadedFiles = []; // قائمة الملفات المقسمة
let currentTab = 'byParts'; // التبويب النشط الحالي
let clipCount = 1; // عدد المقاطع المضافة

// ===== DOM Elements =====
const uploadArea = document.getElementById('uploadArea');
const videoInput = document.getElementById('videoInput');
const videoInfo = document.getElementById('videoInfo');
const fileName = document.getElementById('fileName');
const videoDurationEl = document.getElementById('videoDuration');
const fileSize = document.getElementById('fileSize');
const splitCard = document.getElementById('splitCard');

// Tab 1: Split by parts
const numPartsInput = document.getElementById('numParts');
const partDuration = document.getElementById('partDuration');
const decreaseBtn = document.getElementById('decreaseBtn');
const increaseBtn = document.getElementById('increaseBtn');
const splitBtn = document.getElementById('splitBtn');
const enableOverlap = document.getElementById('enableOverlap');
const overlapSettings = document.getElementById('overlapSettings');
const overlapSeconds = document.getElementById('overlapSeconds');
const overlapDisplay = document.getElementById('overlapDisplay');
const decreaseOverlapBtn = document.getElementById('decreaseOverlapBtn');
const increaseOverlapBtn = document.getElementById('increaseOverlapBtn');

// Quality selector elements
const qualityPreset = document.getElementById('qualityPreset');
const estimatedTime = document.getElementById('estimatedTime');
const qualityDescription = document.getElementById('qualityDescription');

// Tab 2: Split by seconds
const secondsPerPart = document.getElementById('secondsPerPart');
const expectedParts = document.getElementById('expectedParts');
const decreaseSecondsBtn = document.getElementById('decreaseSecondsBtn');
const increaseSecondsBtn = document.getElementById('increaseSecondsBtn');
const splitBySecondsBtn = document.getElementById('splitBySecondsBtn');
const enableOverlapSeconds = document.getElementById('enableOverlapSeconds');
const overlapSettingsSeconds = document.getElementById('overlapSettingsSeconds');
const overlapSecondsValue = document.getElementById('overlapSecondsValue');
const overlapSecondsDisplay = document.getElementById('overlapSecondsDisplay');
const decreaseOverlapSecondsBtn = document.getElementById('decreaseOverlapSecondsBtn');
const increaseOverlapSecondsBtn = document.getElementById('increaseOverlapSecondsBtn');

// Quality selector elements for seconds tab
const qualityPresetSeconds = document.getElementById('qualityPresetSeconds');
const estimatedTimeSeconds = document.getElementById('estimatedTimeSeconds');
const qualityDescriptionSeconds = document.getElementById('qualityDescriptionSeconds');

// Tab 3: Extract clips
const clipsContainer = document.getElementById('clipsContainer');
const addClipBtn = document.getElementById('addClipBtn');
const removeClipBtn = document.getElementById('removeClipBtn');
const extractClipsBtn = document.getElementById('extractClipsBtn');

// Common elements
const progressCard = document.getElementById('progressCard');
const progressFill = document.getElementById('progressFill');
const progressText = document.getElementById('progressText');
const progressStatus = document.getElementById('progressStatus');
const resultsCard = document.getElementById('resultsCard');
const resultsGrid = document.getElementById('resultsGrid');
const resetBtn = document.getElementById('resetBtn');
const downloadAllBtn = document.getElementById('downloadAllBtn');
const loadingOverlay = document.getElementById('loadingOverlay');

// Tab buttons
const tabBtns = document.querySelectorAll('.tab-btn');
const tabContents = document.querySelectorAll('.tab-content');


// ===== Event Listeners =====

// Upload area click
uploadArea.addEventListener('click', (e) => {
    if (e.target.tagName !== 'LABEL' && e.target.tagName !== 'BUTTON') {
        videoInput.click();
    }
});

// File input change
videoInput.addEventListener('change', handleFileSelect);

// Drag and drop
uploadArea.addEventListener('dragover', (e) => {
    e.preventDefault();
    uploadArea.classList.add('dragover');
});

uploadArea.addEventListener('dragleave', () => {
    uploadArea.classList.remove('dragover');
});

uploadArea.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadArea.classList.remove('dragover');
    
    const files = e.dataTransfer.files;
    if (files.length > 0) {
        handleFile(files[0]);
    }
});

// Tab switching
tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
        const tabName = btn.getAttribute('data-tab');
        switchTab(tabName);
    });
});

// Tab 1: Counter buttons
decreaseBtn.addEventListener('click', () => {
    if (numPartsInput.value > 2) {
        numPartsInput.value = parseInt(numPartsInput.value) - 1;
        updatePartDuration();
    }
});

increaseBtn.addEventListener('click', () => {
    if (numPartsInput.value < 20) {
        numPartsInput.value = parseInt(numPartsInput.value) + 1;
        updatePartDuration();
    }
});

numPartsInput.addEventListener('input', updatePartDuration);

// Quality selector event listeners
qualityPreset.addEventListener('change', updateEstimatedTime);
qualityPresetSeconds.addEventListener('change', updateEstimatedTimeSeconds);

// Overlap controls for Tab 1
enableOverlap.addEventListener('change', () => {
    if (enableOverlap.checked) {
        overlapSettings.style.display = 'block';
    } else {
        overlapSettings.style.display = 'none';
    }
});

decreaseOverlapBtn.addEventListener('click', () => {
    if (overlapSeconds.value > 1) {
        overlapSeconds.value = parseInt(overlapSeconds.value) - 1;
        overlapDisplay.textContent = overlapSeconds.value;
    }
});

increaseOverlapBtn.addEventListener('click', () => {
    if (overlapSeconds.value < 30) {
        overlapSeconds.value = parseInt(overlapSeconds.value) + 1;
        overlapDisplay.textContent = overlapSeconds.value;
    }
});

overlapSeconds.addEventListener('input', () => {
    overlapDisplay.textContent = overlapSeconds.value;
});

// Tab 1: Split button
splitBtn.addEventListener('click', startSplitting);

// Tab 2: Seconds counter buttons
decreaseSecondsBtn.addEventListener('click', () => {
    if (secondsPerPart.value > 1) {
        secondsPerPart.value = parseInt(secondsPerPart.value) - 1;
        updateExpectedParts();
    }
});

increaseSecondsBtn.addEventListener('click', () => {
    if (secondsPerPart.value < 3600) {
        secondsPerPart.value = parseInt(secondsPerPart.value) + 1;
        updateExpectedParts();
    }
});

secondsPerPart.addEventListener('input', updateExpectedParts);

// Overlap controls for Tab 2 (Split by seconds)
enableOverlapSeconds.addEventListener('change', () => {
    if (enableOverlapSeconds.checked) {
        overlapSettingsSeconds.style.display = 'block';
    } else {
        overlapSettingsSeconds.style.display = 'none';
    }
});

decreaseOverlapSecondsBtn.addEventListener('click', () => {
    if (overlapSecondsValue.value > 1) {
        overlapSecondsValue.value = parseInt(overlapSecondsValue.value) - 1;
        overlapSecondsDisplay.textContent = overlapSecondsValue.value;
    }
});

increaseOverlapSecondsBtn.addEventListener('click', () => {
    if (overlapSecondsValue.value < 30) {
        overlapSecondsValue.value = parseInt(overlapSecondsValue.value) + 1;
        overlapSecondsDisplay.textContent = overlapSecondsValue.value;
    }
});

overlapSecondsValue.addEventListener('input', () => {
    overlapSecondsDisplay.textContent = overlapSecondsValue.value;
});

// Tab 2: Split by seconds button
splitBySecondsBtn.addEventListener('click', startSplitBySeconds);

// Tab 3: Add/Remove clip buttons
addClipBtn.addEventListener('click', addClip);
removeClipBtn.addEventListener('click', removeClip);

// Tab 3: Extract clips button
extractClipsBtn.addEventListener('click', startExtractClips);

// Reset button
resetBtn.addEventListener('click', resetPage);

// Download all button
downloadAllBtn.addEventListener('click', downloadAllFiles);


// ===== Functions =====

function switchTab(tabName) {
    currentTab = tabName;
    
    // Update tab buttons
    tabBtns.forEach(btn => {
        if (btn.getAttribute('data-tab') === tabName) {
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
        }
    });
    
    // Update tab contents
    tabContents.forEach(content => {
        if (content.id === `tab-${tabName}`) {
            content.classList.add('active');
        } else {
            content.classList.remove('active');
        }
    });
}

function handleFileSelect(e) {
    const file = e.target.files[0];
    if (file) {
        handleFile(file);
    }
}

function handleFile(file) {
    // Check file type
    const validTypes = ['video/mp4', 'video/avi', 'video/mov', 'video/quicktime', 
                       'video/x-matroska', 'video/x-flv', 'video/x-ms-wmv', 'video/webm'];
    
    if (!validTypes.includes(file.type) && !file.name.match(/\.(mp4|avi|mov|mkv|flv|wmv|webm)$/i)) {
        alert('❌ صيغة الملف غير مدعومة! الرجاء اختيار ملف فيديو صالح.');
        return;
    }
    
    // Check file size (500 MB max)
    if (file.size > 524288000) {
        alert('❌ حجم الملف كبير جداً! الحد الأقصى 500 ميجابايت.');
        return;
    }
    
    uploadedFile = file;
    
    // Get video duration
    const video = document.createElement('video');
    video.preload = 'metadata';
    
    video.onloadedmetadata = function() {
        window.URL.revokeObjectURL(video.src);
        videoDuration = video.duration;
        
        // Display file info
        displayFileInfo(file, videoDuration);
        
        // Show split card
        splitCard.style.display = 'block';
        updatePartDuration();
        updateExpectedParts();
        
        // Smooth scroll to split card
        splitCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    };
    
    video.src = URL.createObjectURL(file);
}

function displayFileInfo(file, duration) {
    fileName.textContent = file.name;
    videoDurationEl.textContent = formatDuration(duration);
    fileSize.textContent = formatFileSize(file.size);
    uploadedFileName = file.name;
    
    videoInfo.style.display = 'block';
}

function formatDuration(seconds) {
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    
    if (hrs > 0) {
        return `${hrs}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    } else {
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    }
}

function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' بايت';
    if (bytes < 1048576) return (bytes / 1024).toFixed(2) + ' كيلوبايت';
    if (bytes < 1073741824) return (bytes / 1048576).toFixed(2) + ' ميجابايت';
    return (bytes / 1073741824).toFixed(2) + ' جيجابايت';
}

function updatePartDuration() {
    const numParts = parseInt(numPartsInput.value);
    if (videoDuration > 0 && numParts > 0) {
        const partDurationSeconds = videoDuration / numParts;
        partDuration.textContent = formatDuration(partDurationSeconds);
        updateEstimatedTime(); // تحديث الوقت المتوقع
    }
}

function updateExpectedParts() {
    const seconds = parseInt(secondsPerPart.value);
    if (videoDuration > 0 && seconds > 0) {
        const parts = Math.ceil(videoDuration / seconds);
        expectedParts.textContent = `${parts} ${parts > 10 ? 'جزءاً' : 'أجزاء'}`;
        updateEstimatedTimeSeconds(); // تحديث الوقت المتوقع
    }
}

// دالة حساب الوقت المتوقع للتقسيم بعدد الأجزاء
function updateEstimatedTime() {
    const numParts = parseInt(numPartsInput.value);
    const quality = qualityPreset.value;
    
    if (videoDuration > 0 && numParts > 0) {
        const estimatedMinutes = calculateEstimatedTime(videoDuration, numParts, quality);
        estimatedTime.textContent = estimatedMinutes;
        updateQualityDescription(quality, qualityDescription);
    }
}

// دالة حساب الوقت المتوقع للتقسيم بالثواني
function updateEstimatedTimeSeconds() {
    const seconds = parseInt(secondsPerPart.value);
    const quality = qualityPresetSeconds.value;
    
    if (videoDuration > 0 && seconds > 0) {
        const numParts = Math.ceil(videoDuration / seconds);
        const estimatedMinutes = calculateEstimatedTime(videoDuration, numParts, quality);
        estimatedTimeSeconds.textContent = estimatedMinutes;
        updateQualityDescription(quality, qualityDescriptionSeconds);
    }
}

// حساب الوقت المتوقع بناءً على preset
function calculateEstimatedTime(duration, parts, preset) {
    // معاملات السرعة لكل preset (بالنسبة للوقت الحقيقي)
    const presetMultipliers = {
        'ultrafast': 0.3,   // أسرع - ~30% من الوقت الحقيقي
        'veryfast': 0.5     // سريع - ~50% من الوقت الحقيقي
    };
    
    const multiplier = presetMultipliers[preset] || 0.5;
    const totalSeconds = duration * multiplier;
    
    if (totalSeconds < 60) {
        return `أقل من دقيقة`;
    } else if (totalSeconds < 120) {
        return `حوالي دقيقة واحدة`;
    } else if (totalSeconds < 180) {
        return `حوالي دقيقتين`;
    } else {
        const minutes = Math.round(totalSeconds / 60);
        return `حوالي ${minutes} دقائق`;
    }
}

// تحديث وصف الجودة
function updateQualityDescription(preset, descElement) {
    const descriptions = {
        'ultrafast': '🚀 أسرع معالجة - جودة جيدة جداً - مناسب للمشاركة السريعة',
        'veryfast': '⚡ جودة ممتازة مع سرعة متوسطة - مثالي لمعظم الاستخدامات'
    };
    descElement.textContent = descriptions[preset] || descriptions['veryfast'];
}

function addClip() {
    if (clipCount >= 20) {
        alert('❌ الحد الأقصى 20 مقاطع في المرة الواحدة');
        return;
    }
    
    clipCount++;
    
    const clipDiv = document.createElement('div');
    clipDiv.className = 'clip-input-group';
    clipDiv.setAttribute('data-clip', clipCount);
    clipDiv.innerHTML = `
        <div class="clip-header">
            <span class="clip-number">المقطع ${clipCount}</span>
        </div>
        <div class="clip-times">
            <div class="time-input">
                <label>من (ثانية):</label>
                <input type="number" class="clip-start" min="0" step="0.1" value="0" placeholder="0">
            </div>
            <div class="time-input">
                <label>إلى (ثانية):</label>
                <input type="number" class="clip-end" min="0" step="0.1" value="10" placeholder="10">
            </div>
        </div>
    `;
    
    clipsContainer.appendChild(clipDiv);
    
    if (clipCount > 1) {
        removeClipBtn.style.display = 'block';
    }
}

function removeClip() {
    if (clipCount <= 1) {
        return;
    }
    
    const lastClip = clipsContainer.querySelector(`[data-clip="${clipCount}"]`);
    if (lastClip) {
        lastClip.remove();
        clipCount--;
    }
    
    if (clipCount <= 1) {
        removeClipBtn.style.display = 'none';
    }
}


async function startSplitting() {
    if (!uploadedFile) {
        alert('❌ الرجاء اختيار ملف فيديو أولاً!');
        return;
    }
    
    const numParts = parseInt(numPartsInput.value);
    
    if (numParts < 2 || numParts > 20) {
        alert('❌ الرجاء اختيار عدد أجزاء بين 2 و 20!');
        return;
    }
    
    // Get overlap settings
    const useOverlap = enableOverlap.checked;
    const overlap = useOverlap ? parseInt(overlapSeconds.value) : 0;
    
    // Show loading overlay
    loadingOverlay.style.display = 'flex';
    
    try {
        // Upload file
        const formData = new FormData();
        formData.append('video', uploadedFile);
        
        const uploadResponse = await fetch('/upload', {
            method: 'POST',
            body: formData
        });
        
        if (!uploadResponse.ok) {
            throw new Error('فشل رفع الملف');
        }
        
        const uploadData = await uploadResponse.json();
        
        // Hide loading overlay
        loadingOverlay.style.display = 'none';
        
        // Show progress card
        progressCard.style.display = 'block';
        splitCard.style.display = 'none';
        progressCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        
        // Simulate progress
        let progress = 0;
        const progressInterval = setInterval(() => {
            progress += 5;
            if (progress <= 90) {
                updateProgress(progress, 'جاري تقسيم الفيديو...');
            }
        }, 200);
        
        // Split video
        const quality = qualityPreset.value;
        const splitResponse = await fetch('/split', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                filename: uploadData.filename,
                num_parts: numParts,
                overlap_seconds: overlap,
                quality_preset: quality
            })
        });
        
        clearInterval(progressInterval);
        
        if (!splitResponse.ok) {
            const errorData = await splitResponse.json();
            throw new Error(errorData.error || 'فشل تقسيم الفيديو');
        }
        
        const result = await splitResponse.json();
        
        // Update progress to 100%
        updateProgress(100, 'اكتمل التقسيم!');
        
        // Wait a bit then show results
        setTimeout(() => {
            displayResults(result.files);
        }, 500);
        
    } catch (error) {
        console.error('Error:', error);
        alert('❌ حدث خطأ: ' + error.message);
        loadingOverlay.style.display = 'none';
        progressCard.style.display = 'none';
        splitCard.style.display = 'block';
    }
}

async function startSplitBySeconds() {
    if (!uploadedFile) {
        alert('❌ الرجاء اختيار ملف فيديو أولاً!');
        return;
    }
    
    const seconds = parseInt(secondsPerPart.value);
    
    if (seconds < 1 || seconds > 3600) {
        alert('❌ الرجاء اختيار عدد ثواني بين 1 و 3600!');
        return;
    }
    
    // Get overlap settings for split by seconds
    const useOverlap = enableOverlapSeconds.checked;
    const overlap = useOverlap ? parseInt(overlapSecondsValue.value) : 0;
    
    // Show loading overlay
    loadingOverlay.style.display = 'flex';
    
    try {
        // Upload file
        const formData = new FormData();
        formData.append('video', uploadedFile);
        
        const uploadResponse = await fetch('/upload', {
            method: 'POST',
            body: formData
        });
        
        if (!uploadResponse.ok) {
            throw new Error('فشل رفع الملف');
        }
        
        const uploadData = await uploadResponse.json();
        
        // Hide loading overlay
        loadingOverlay.style.display = 'none';
        
        // Show progress card
        progressCard.style.display = 'block';
        splitCard.style.display = 'none';
        progressCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        
        // Simulate progress
        let progress = 0;
        const progressInterval = setInterval(() => {
            progress += 5;
            if (progress <= 90) {
                updateProgress(progress, 'جاري تقسيم الفيديو حسب الثواني...');
            }
        }, 200);
        
        // Split video by seconds
        const quality = qualityPresetSeconds.value;
        const splitResponse = await fetch('/split-by-seconds', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                filename: uploadData.filename,
                seconds_per_part: seconds,
                overlap_seconds: overlap,
                quality_preset: quality
            })
        });
        
        clearInterval(progressInterval);
        
        if (!splitResponse.ok) {
            const errorData = await splitResponse.json();
            throw new Error(errorData.error || 'فشل تقسيم الفيديو');
        }
        
        const result = await splitResponse.json();
        
        // Update progress to 100%
        updateProgress(100, 'اكتمل التقسيم!');
        
        // Wait a bit then show results
        setTimeout(() => {
            displayResults(result.files);
        }, 500);
        
    } catch (error) {
        console.error('Error:', error);
        alert('❌ حدث خطأ: ' + error.message);
        loadingOverlay.style.display = 'none';
        progressCard.style.display = 'none';
        splitCard.style.display = 'block';
    }
}

async function startExtractClips() {
    if (!uploadedFile) {
        alert('❌ الرجاء اختيار ملف فيديو أولاً!');
        return;
    }
    
    // Get all clips
    const clipElements = clipsContainer.querySelectorAll('.clip-input-group');
    const clips = [];
    
    for (let i = 0; i < clipElements.length; i++) {
        const clipEl = clipElements[i];
        const startInput = clipEl.querySelector('.clip-start');
        const endInput = clipEl.querySelector('.clip-end');
        
        const start = parseFloat(startInput.value);
        const end = parseFloat(endInput.value);
        
        if (isNaN(start) || isNaN(end)) {
            alert(`❌ المقطع ${i + 1}: الرجاء إدخال أرقام صحيحة`);
            return;
        }
        
        if (start < 0 || end <= start) {
            alert(`❌ المقطع ${i + 1}: وقت النهاية يجب أن يكون أكبر من وقت البداية`);
            return;
        }
        
        if (end > videoDuration) {
            alert(`❌ المقطع ${i + 1}: وقت النهاية (${end}s) يتجاوز مدة الفيديو (${videoDuration.toFixed(1)}s)`);
            return;
        }
        
        clips.push({ start_time: start, end_time: end });
    }
    
    if (clips.length === 0) {
        alert('❌ الرجاء إضافة مقطع واحد على الأقل');
        return;
    }
    
    // Show loading overlay
    loadingOverlay.style.display = 'flex';
    
    try {
        // Upload file
        const formData = new FormData();
        formData.append('video', uploadedFile);
        
        const uploadResponse = await fetch('/upload', {
            method: 'POST',
            body: formData
        });
        
        if (!uploadResponse.ok) {
            throw new Error('فشل رفع الملف');
        }
        
        const uploadData = await uploadResponse.json();
        
        // Hide loading overlay
        loadingOverlay.style.display = 'none';
        
        // Show progress card
        progressCard.style.display = 'block';
        splitCard.style.display = 'none';
        progressCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        
        // Simulate progress
        let progress = 0;
        const progressInterval = setInterval(() => {
            progress += 5;
            if (progress <= 90) {
                updateProgress(progress, 'جاري اقتطاع المقاطع...');
            }
        }, 200);
        
        // Extract clips
        const extractResponse = await fetch('/extract-clips', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                filename: uploadData.filename,
                clips: clips
            })
        });
        
        clearInterval(progressInterval);
        
        if (!extractResponse.ok) {
            const errorData = await extractResponse.json();
            throw new Error(errorData.error || 'فشل اقتطاع المقاطع');
        }
        
        const result = await extractResponse.json();
        
        // Update progress to 100%
        updateProgress(100, 'اكتمل الاقتطاع!');
        
        // Wait a bit then show results
        setTimeout(() => {
            displayResults(result.files);
        }, 500);
        
    } catch (error) {
        console.error('Error:', error);
        alert('❌ حدث خطأ: ' + error.message);
        loadingOverlay.style.display = 'none';
        progressCard.style.display = 'none';
        splitCard.style.display = 'block';
    }
}

function updateProgress(percentage, status) {
    progressFill.style.width = percentage + '%';
    progressText.textContent = percentage + '%';
    progressStatus.textContent = status;
}

function displayResults(files) {
    downloadedFiles = files.map(f => f.filename);
    
    // Hide progress card
    progressCard.style.display = 'none';
    
    // Clear previous results
    resultsGrid.innerHTML = '';
    
    // Add result cards
    files.forEach((file, index) => {
        const resultCard = createResultCard(file, index);
        resultsGrid.appendChild(resultCard);
    });
    
    // Show results card
    resultsCard.style.display = 'block';
    resultsCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function createResultCard(file, index) {
    const card = document.createElement('div');
    card.className = 'result-item';
    
    // Determine label based on file properties
    let label = '';
    if (file.part_number) {
        label = `الجزء ${file.part_number}`;
    } else if (file.clip_number) {
        label = `المقطع ${file.clip_number}`;
    } else {
        label = `ملف ${index + 1}`;
    }
    
    card.innerHTML = `
        <div class="result-header">
            <span class="result-title">${label}</span>
            <span class="result-badge">${file.duration || '---'}</span>
        </div>
        <div class="result-info">
            <div class="result-info-item">
                <span>📁 ${file.filename}</span>
            </div>
            <div class="result-info-item">
                <span>📏 الحجم: ${file.size}</span>
            </div>
            ${file.start_time ? `<div class="result-info-item"><span>⏱️ من: ${file.start_time}</span></div>` : ''}
            ${file.end_time ? `<div class="result-info-item"><span>⏱️ إلى: ${file.end_time}</span></div>` : ''}
        </div>
        <div class="result-actions">
            <button class="btn btn-sm btn-primary" onclick="downloadSingleFile('${file.filename}', '${file.filename}')">
                <span class="btn-icon">⬇️</span>
                تحميل
            </button>
            <button class="btn btn-sm btn-secondary" onclick="shareFile('${file.filename}', '${file.filename}')">
                <span class="btn-icon">📤</span>
                مشاركة
            </button>
        </div>
    `;
    
    return card;
}

function downloadSingleFile(filename, buttonId) {
    // عرض إعلان inline قبل التحميل
    adsManager.showDownloadAd(() => {
        window.location.href = `/download/${filename}`;
    }, 1); // ملف واحد
}

function shareFile(filename, buttonId) {
    // عرض إعلان inline قبل المشاركة
    adsManager.showDownloadAd(() => {
        const shareUrl = `${window.location.origin}/download/${filename}`;

        if (navigator.share) {
            navigator.share({
                title: 'تقسيم فيديو - SplitMyVideo',
                text: `حمل الجزء: ${filename}`,
                url: shareUrl
            }).catch(err => console.log('Error sharing:', err));
        } else {
            // Fallback: Copy to clipboard
            navigator.clipboard.writeText(shareUrl).then(() => {
                alert('✅ تم نسخ الرابط!');
            }).catch(err => {
                console.log('Error copying:', err);
                alert('الرابط: ' + shareUrl);
            });
        }
    }, 1); // ملف واحد
}

async function downloadAllFiles() {
    if (downloadedFiles.length === 0) {
        alert('❌ لا توجد ملفات للتحميل');
        return;
    }

    // عرض إعلان مطول قبل تحميل جميع الأجزاء
    const numParts = downloadedFiles.length;
    adsManager.showLongDownloadAd(async () => {
        try {
            const response = await fetch('/download-all', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    files: downloadedFiles
                })
            });

            if (!response.ok) {
                throw new Error('فشل تحميل الملفات');
            }

            // Download the ZIP file
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'video_parts.zip';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);

        } catch (error) {
            console.error('Error:', error);
            alert('❌ حدث خطأ في تحميل الملفات');
        }
    }, numParts); // عدد الأجزاء
}

function resetPage() {
    // Reset all variables
    uploadedFile = null;
    videoDuration = 0;
    uploadedFileName = '';
    downloadedFiles = [];
    clipCount = 1;
    
    // Reset UI
    videoInput.value = '';
    videoInfo.style.display = 'none';
    splitCard.style.display = 'none';
    progressCard.style.display = 'none';
    resultsCard.style.display = 'none';
    
    // Reset form values
    numPartsInput.value = 2;
    secondsPerPart.value = 10;
    enableOverlap.checked = false;
    overlapSettings.style.display = 'none';
    overlapSeconds.value = 5;
    enableOverlapSeconds.checked = false;
    overlapSettingsSeconds.style.display = 'none';
    overlapSecondsValue.value = 5;
    
    // Reset clips
    clipsContainer.innerHTML = `
        <div class="clip-input-group" data-clip="1">
            <div class="clip-header">
                <span class="clip-number">المقطع 1</span>
            </div>
            <div class="clip-times">
                <div class="time-input">
                    <label>من (ثانية):</label>
                    <input type="number" class="clip-start" min="0" step="0.1" value="0" placeholder="0">
                </div>
                <div class="time-input">
                    <label>إلى (ثانية):</label>
                    <input type="number" class="clip-end" min="0" step="0.1" value="10" placeholder="10">
                </div>
            </div>
        </div>
    `;
    removeClipBtn.style.display = 'none';
    
    // Switch to first tab
    switchTab('byParts');
    
    // Scroll to top
    window.scrollTo({ top: 0, behavior: 'smooth' });
}
