import os
import json
import re
import subprocess
import tempfile
import uuid
import random
from flask import Flask, render_template, request, jsonify, Response
from flask_cors import CORS
import yt_dlp
import requests
from urllib.parse import urlparse, parse_qs

app = Flask(__name__)
CORS(app)

DOWNLOAD_FOLDER = tempfile.gettempdir()
if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

active_downloads = {}

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0',
]

COOKIE_FILE = os.path.join(os.path.dirname(__file__), 'cookies.txt')

def clean_temp_files():
    import time
    current_time = time.time()
    for file_id, info in list(active_downloads.items()):
        if current_time - info.get('created', 0) > 3600:
            try:
                if os.path.exists(info.get('path', '')):
                    os.remove(info['path'])
                del active_downloads[file_id]
            except:
                pass

def get_base_ydl_opts():
    opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'force_generic_extractor': False,
        'user_agent': random.choice(USER_AGENTS),
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web', 'ios'],
                'skip': ['hls', 'dash'],
            }
        },
        'http_headers': {
            'User-Agent': random.choice(USER_AGENTS),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
    }
    
    if os.path.exists(COOKIE_FILE):
        opts['cookiefile'] = COOKIE_FILE
    
    return opts

def get_video_info(url):
    ydl_opts = get_base_ydl_opts()
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
            
            formats = []
            for f in info.get('formats', []):
                if f.get('acodec') != 'none' and f.get('vcodec') != 'none':
                    height = f.get('height', 0)
                    if height and height <= 1080:
                        formats.append({
                            'format_id': f.get('format_id'),
                            'ext': f.get('ext', 'mp4'),
                            'resolution': f.get('resolution'),
                            'filesize': f.get('filesize'),
                            'format_note': f.get('format_note'),
                            'fps': f.get('fps'),
                            'height': height
                        })
            
            formats.sort(key=lambda x: x.get('height', 0), reverse=True)
            
            audio_formats = []
            for f in info.get('formats', []):
                if f.get('acodec') != 'none' and f.get('vcodec') == 'none':
                    audio_formats.append({
                        'format_id': f.get('format_id'),
                        'ext': f.get('ext', 'm4a'),
                        'abr': f.get('abr'),
                        'filesize': f.get('filesize'),
                        'format_note': f.get('format_note')
                    })
            
            return {
                'success': True,
                'id': info.get('id'),
                'title': info.get('title'),
                'duration': info.get('duration'),
                'thumbnail': info.get('thumbnail'),
                'uploader': info.get('uploader'),
                'upload_date': info.get('upload_date'),
                'view_count': info.get('view_count'),
                'like_count': info.get('like_count'),
                'description': info.get('description', '')[:500],
                'formats': formats[:8],
                'audio_formats': audio_formats[:3],
                'webpage_url': info.get('webpage_url'),
                'is_short': info.get('duration', 0) <= 60 and info.get('width', 0) < info.get('height', 0)
            }
        except Exception as e:
            error_msg = str(e)
            if 'Sign in to confirm' in error_msg or 'bot' in error_msg:
                return {
                    'success': False, 
                    'error': 'YouTube requiere verificación. Intenta de nuevo en unos minutos o usa otra URL.',
                    'need_cookies': True
                }
            return {'success': False, 'error': error_msg}

def download_video(url, format_id=None, audio_only=False):
    clean_temp_files()
    
    file_id = str(uuid.uuid4())
    temp_path = os.path.join(DOWNLOAD_FOLDER, f"{file_id}.%(ext)s")
    
    ydl_opts = get_base_ydl_opts()
    
    if audio_only:
        ydl_opts.update({
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'outtmpl': temp_path,
        })
    else:
        format_spec = format_id if format_id else 'best[height<=720]'
        ydl_opts.update({
            'format': format_spec,
            'outtmpl': temp_path,
            'merge_output_format': 'mp4',
        })
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            if audio_only:
                filename = filename.rsplit('.', 1)[0] + '.mp3'
            else:
                if not filename.endswith('.mp4'):
                    filename = filename.rsplit('.', 1)[0] + '.mp4'
            
            if not os.path.exists(filename):
                base = os.path.splitext(filename)[0]
                for ext in ['.mp4', '.mp3', '.mkv', '.webm', '.m4a']:
                    test_path = base + ext
                    if os.path.exists(test_path):
                        filename = test_path
                        break
            
            active_downloads[file_id] = {
                'path': filename,
                'title': info.get('title', 'video'),
                'created': __import__('time').time(),
                'ext': 'mp3' if audio_only else 'mp4'
            }
            
            return {
                'success': True,
                'download_id': file_id,
                'filename': f"{info.get('title', 'video')}.{active_downloads[file_id]['ext']}",
                'filesize': os.path.getsize(filename) if os.path.exists(filename) else 0
            }
        except Exception as e:
            error_msg = str(e)
            if 'Sign in to confirm' in error_msg:
                return {'success': False, 'error': 'Verificación requerida. Intenta de nuevo más tarde.'}
            return {'success': False, 'error': error_msg}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/info')
def get_info():
    url = request.args.get('url', '').strip()
    if not url:
        return jsonify({'success': False, 'error': 'URL requerida'})
    
    if 'youtube.com/shorts/' in url:
        video_id = url.split('/shorts/')[1].split('?')[0]
        url = f'https://www.youtube.com/watch?v={video_id}'
    elif 'youtu.be/' in url:
        video_id = url.split('youtu.be/')[1].split('?')[0]
        url = f'https://www.youtube.com/watch?v={video_id}'
    
    info = get_video_info(url)
    return jsonify(info)

@app.route('/api/download')
def download():
    url = request.args.get('url', '').strip()
    format_id = request.args.get('format_id', '')
    audio_only = request.args.get('audio_only', 'false').lower() == 'true'
    
    if not url:
        return jsonify({'success': False, 'error': 'URL requerida'})
    
    if 'youtube.com/shorts/' in url:
        video_id = url.split('/shorts/')[1].split('?')[0]
        url = f'https://www.youtube.com/watch?v={video_id}'
    elif 'youtu.be/' in url:
        video_id = url.split('youtu.be/')[1].split('?')[0]
        url = f'https://www.youtube.com/watch?v={video_id}'
    
    result = download_video(url, format_id if format_id else None, audio_only)
    return jsonify(result)

@app.route('/api/download/<download_id>')
def serve_download(download_id):
    if download_id not in active_downloads:
        return jsonify({'success': False, 'error': 'Descarga expirada'}), 404
    
    info = active_downloads[download_id]
    filepath = info['path']
    
    if not os.path.exists(filepath):
        return jsonify({'success': False, 'error': 'Archivo no encontrado'}), 404
    
    safe_filename = re.sub(r'[^\w\-_\. ]', '', info['title'])[:100]
    download_name = f"{safe_filename}.{info['ext']}"
    
    def generate():
        with open(filepath, 'rb') as f:
            while chunk := f.read(8192):
                yield chunk
    
    response = Response(generate(), mimetype='application/octet-stream')
    response.headers.set('Content-Disposition', f'attachment; filename="{download_name}"')
    response.headers.set('Content-Length', str(os.path.getsize(filepath)))
    response.headers.set('Cache-Control', 'no-cache')
    return response

@app.route('/api/cookies-help')
def cookies_help():
    return jsonify({
        'instructions': [
            '1. Instala la extensión "Get cookies.txt LOCALLY" en Chrome',
            '2. Inicia sesión en YouTube',
            '3. Haz clic en la extensión y exporta cookies.txt',
            '4. Guarda el archivo como cookies.txt en la raíz del proyecto'
        ]
    })

@app.route('/robots.txt')
def robots():
    return "User-agent: *\nAllow: /", 200, {'Content-Type': 'text/plain'}

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)
