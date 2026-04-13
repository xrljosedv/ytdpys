import os
import json
import re
import subprocess
import tempfile
import uuid
from flask import Flask, render_template, request, jsonify, send_file, Response
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

def get_video_info(url):
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'force_generic_extractor': False,
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
            
            formats = []
            for f in info.get('formats', []):
                if f.get('acodec') != 'none' and f.get('vcodec') != 'none':
                    formats.append({
                        'format_id': f.get('format_id'),
                        'ext': f.get('ext'),
                        'resolution': f.get('resolution'),
                        'filesize': f.get('filesize'),
                        'format_note': f.get('format_note'),
                        'fps': f.get('fps')
                    })
            
            audio_formats = []
            for f in info.get('formats', []):
                if f.get('acodec') != 'none' and f.get('vcodec') == 'none':
                    audio_formats.append({
                        'format_id': f.get('format_id'),
                        'ext': f.get('ext'),
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
                'formats': formats[:10],
                'audio_formats': audio_formats[:5],
                'webpage_url': info.get('webpage_url'),
                'is_short': info.get('duration', 0) <= 60 and info.get('width', 0) < info.get('height', 0)
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}

def download_video(url, format_id=None, audio_only=False):
    clean_temp_files()
    
    file_id = str(uuid.uuid4())
    temp_path = os.path.join(DOWNLOAD_FOLDER, f"{file_id}.%(ext)s")
    
    if audio_only:
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'outtmpl': temp_path,
            'quiet': True,
            'no_warnings': True,
        }
    else:
        format_spec = format_id if format_id else 'best[height<=720]'
        ydl_opts = {
            'format': format_spec,
            'outtmpl': temp_path,
            'quiet': True,
            'no_warnings': True,
            'merge_output_format': 'mp4',
        }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            if audio_only:
                filename = filename.rsplit('.', 1)[0] + '.mp3'
            else:
                if not filename.endswith('.mp4'):
                    filename = filename.rsplit('.', 1)[0] + '.mp4'
            
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
            return {'success': False, 'error': str(e)}

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
    
    result = download_video(url, format_id if format_id else None, audio_only)
    return jsonify(result)

@app.route('/api/download/<download_id>')
def serve_download(download_id):
    if download_id not in active_downloads:
        return jsonify({'success': False, 'error': 'Descarga expirada o no encontrada'}), 404
    
    info = active_downloads[download_id]
    filepath = info['path']
    
    if not os.path.exists(filepath):
        return jsonify({'success': False, 'error': 'Archivo no encontrado'}), 404
    
    safe_filename = re.sub(r'[^\w\-_\. ]', '', info['title'])
    download_name = f"{safe_filename}.{info['ext']}"
    
    def generate():
        with open(filepath, 'rb') as f:
            while chunk := f.read(8192):
                yield chunk
    
    response = Response(generate(), mimetype='application/octet-stream')
    response.headers.set('Content-Disposition', f'attachment; filename="{download_name}"')
    response.headers.set('Content-Length', str(os.path.getsize(filepath)))
    return response

@app.route('/robots.txt')
def robots():
    return "User-agent: *\nAllow: /", 200, {'Content-Type': 'text/plain'}

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)
