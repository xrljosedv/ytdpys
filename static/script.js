let currentVideoInfo = null;
let selectedFormat = null;
let currentDownloadType = 'video';
let retryCount = 0;
const MAX_RETRIES = 3;

document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('fetchBtn').addEventListener('click', fetchVideoInfo);
    document.getElementById('urlInput').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') fetchVideoInfo();
    });

    document.querySelectorAll('.example-link').forEach(link => {
        link.addEventListener('click', () => {
            document.getElementById('urlInput').value = link.dataset.url;
            fetchVideoInfo();
        });
    });

    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            btn.classList.add('active');
            const tabId = btn.dataset.tab === 'video' ? 'videoTab' : 'audioTab';
            document.getElementById(tabId).classList.add('active');
            currentDownloadType = btn.dataset.tab;
            updateDownloadButton();
        });
    });

    document.getElementById('downloadVideoBtn').addEventListener('click', () => startDownload('video'));
    document.getElementById('downloadAudioBtn').addEventListener('click', () => startDownload('audio'));
});

async function fetchVideoInfo() {
    const url = document.getElementById('urlInput').value.trim();
    if (!url) {
        showError('Por favor ingresa una URL de YouTube');
        return;
    }

    const loader = document.getElementById('loader');
    const videoInfo = document.getElementById('videoInfo');
    const downloadSection = document.getElementById('downloadSection');
    const errorContainer = document.getElementById('errorContainer');

    loader.style.display = 'block';
    videoInfo.style.display = 'none';
    downloadSection.style.display = 'none';
    errorContainer.style.display = 'none';
    retryCount = 0;

    await attemptFetch(url);
}

async function attemptFetch(url) {
    try {
        const response = await fetch(`/api/info?url=${encodeURIComponent(url)}`);
        const data = await response.json();

        document.getElementById('loader').style.display = 'none';

        if (data.success) {
            currentVideoInfo = data;
            displayVideoInfo(data);
            displayFormats(data);
            document.getElementById('videoInfo').style.display = 'flex';
            document.getElementById('downloadSection').style.display = 'block';
            selectedFormat = null;
        } else {
            if (data.need_cookies && retryCount < MAX_RETRIES) {
                retryCount++;
                document.querySelector('#loader p').textContent = `Reintentando (${retryCount}/${MAX_RETRIES})...`;
                await new Promise(resolve => setTimeout(resolve, 2000));
                return await attemptFetch(url);
            }
            
            let errorMsg = data.error || 'Error al obtener información del video';
            if (data.need_cookies) {
                errorMsg += '\n\nSolución: Usa un VPN o espera unos minutos.';
            }
            showError(errorMsg);
        }
    } catch (error) {
        document.getElementById('loader').style.display = 'none';
        showError('Error de conexión. Intenta de nuevo.');
    }
}

function displayVideoInfo(info) {
    document.getElementById('thumbnail').src = info.thumbnail || '';
    document.getElementById('videoTitle').textContent = info.title || 'Sin título';
    document.getElementById('uploader').textContent = info.uploader || 'Desconocido';
    
    const views = info.view_count ? formatNumber(info.view_count) : 'N/A';
    document.getElementById('views').textContent = `${views} vistas`;
    
    if (info.upload_date) {
        const date = info.upload_date;
        const formatted = `${date.substring(6, 8)}/${date.substring(4, 6)}/${date.substring(0, 4)}`;
        document.getElementById('uploadDate').textContent = formatted;
    }

    if (info.duration) {
        const minutes = Math.floor(info.duration / 60);
        const seconds = info.duration % 60;
        document.getElementById('durationBadge').textContent = `${minutes}:${seconds.toString().padStart(2, '0')}`;
    }
}

function displayFormats(info) {
    const videoFormatsDiv = document.getElementById('videoFormats');
    const audioFormatsDiv = document.getElementById('audioFormats');
    
    videoFormatsDiv.innerHTML = '';
    audioFormatsDiv.innerHTML = '';

    if (info.formats && info.formats.length > 0) {
        const uniqueFormats = [];
        const seenHeights = new Set();
        
        info.formats.forEach(format => {
            const height = format.height || 0;
            if (!seenHeights.has(height) || format.filesize) {
                seenHeights.add(height);
                uniqueFormats.push(format);
            }
        });
        
        uniqueFormats.sort((a, b) => (b.height || 0) - (a.height || 0));
        
        uniqueFormats.slice(0, 6).forEach(format => {
            const card = createFormatCard(format, 'video');
            videoFormatsDiv.appendChild(card);
        });
    } else {
        videoFormatsDiv.innerHTML = '<p style="color: var(--text-muted);">Formatos no disponibles</p>';
    }

    const audioQualities = [
        { format_id: 'bestaudio', abr: '192', ext: 'mp3', format_note: 'MP3 Alta Calidad' },
        { format_id: '140', abr: '128', ext: 'm4a', format_note: 'AAC 128kbps' }
    ];
    
    audioQualities.forEach(format => {
        const card = createFormatCard(format, 'audio');
        audioFormatsDiv.appendChild(card);
    });
    
    if (info.audio_formats && info.audio_formats.length > 0) {
        audioFormatsDiv.innerHTML = '';
        info.audio_formats.slice(0, 3).forEach(format => {
            const card = createFormatCard(format, 'audio');
            audioFormatsDiv.appendChild(card);
        });
    }

    updateDownloadButton();
}

function createFormatCard(format, type) {
    const card = document.createElement('div');
    card.className = 'format-card';
    card.dataset.formatId = format.format_id;
    card.dataset.type = type;

    const quality = document.createElement('div');
    quality.className = 'format-quality';
    
    if (type === 'video') {
        quality.textContent = format.resolution || format.format_note || 'Video';
    } else {
        quality.textContent = format.abr ? `${format.abr} kbps` : (format.format_note || 'MP3');
    }

    const detail = document.createElement('div');
    detail.className = 'format-detail';
    detail.textContent = format.ext ? format.ext.toUpperCase() : (type === 'video' ? 'MP4' : 'MP3');

    card.appendChild(quality);
    card.appendChild(detail);

    if (format.filesize) {
        const size = document.createElement('div');
        size.className = 'format-size';
        size.textContent = formatBytes(format.filesize);
        card.appendChild(size);
    }

    card.addEventListener('click', () => {
        document.querySelectorAll(`.format-card[data-type="${type}"]`).forEach(c => {
            c.classList.remove('selected');
        });
        card.classList.add('selected');
        selectedFormat = format.format_id;
        updateDownloadButton();
    });

    return card;
}

function updateDownloadButton() {
    const videoBtn = document.getElementById('downloadVideoBtn');
    const audioBtn = document.getElementById('downloadAudioBtn');
    
    if (currentDownloadType === 'video') {
        videoBtn.style.display = selectedFormat ? 'flex' : 'none';
        audioBtn.style.display = 'none';
    } else {
        videoBtn.style.display = 'none';
        audioBtn.style.display = 'flex';
    }
}

async function startDownload(type) {
    if (!currentVideoInfo) return;

    const url = document.getElementById('urlInput').value.trim();
    const audioOnly = type === 'audio';
    const formatId = type === 'video' ? selectedFormat : 'bestaudio';

    const progressDiv = document.getElementById('downloadProgress');
    const linkDiv = document.getElementById('downloadLink');
    const videoBtn = document.getElementById('downloadVideoBtn');
    const audioBtn = document.getElementById('downloadAudioBtn');

    progressDiv.style.display = 'block';
    linkDiv.style.display = 'none';
    videoBtn.style.display = 'none';
    audioBtn.style.display = 'none';

    document.querySelector('.progress-text').textContent = 'Preparando descarga...';
    document.querySelector('.progress-fill').style.width = '30%';

    try {
        const response = await fetch(`/api/download?url=${encodeURIComponent(url)}&format_id=${formatId}&audio_only=${audioOnly}`);
        const data = await response.json();

        if (data.success) {
            document.querySelector('.progress-fill').style.width = '100%';
            document.querySelector('.progress-text').textContent = '¡Descarga lista!';

            setTimeout(() => {
                progressDiv.style.display = 'none';
                linkDiv.style.display = 'block';
                
                const downloadBtn = document.getElementById('downloadBtn');
                downloadBtn.href = `/api/download/${data.download_id}`;
                downloadBtn.download = data.filename;
            }, 500);
        } else {
            let errorMsg = data.error || 'Error al preparar la descarga';
            if (errorMsg.includes('Sign in') || errorMsg.includes('bot')) {
                errorMsg = 'YouTube requiere verificación. Intenta con otro video o espera unos minutos.';
            }
            showError(errorMsg);
            progressDiv.style.display = 'none';
            updateDownloadButton();
        }
    } catch (error) {
        showError('Error de conexión al descargar');
        progressDiv.style.display = 'none';
        updateDownloadButton();
    }
}

function showError(message) {
    const errorContainer = document.getElementById('errorContainer');
    errorContainer.innerHTML = message.replace(/\n/g, '<br>');
    errorContainer.style.display = 'block';
    
    setTimeout(() => {
        errorContainer.style.display = 'none';
    }, 8000);
}

function formatNumber(num) {
    if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
    if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
    return num.toString();
}

function formatBytes(bytes, decimals = 2) {
    if (!bytes || bytes === 0) return '';
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
            }
