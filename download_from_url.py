import os
import requests
import subprocess
from yt_dlp import YoutubeDL, DownloadError


def download_direct(url, output_path):
    local_filename = os.path.join(output_path, url.split('/')[-1])
    try:
        with requests.get(url, stream=True) as r:
            r.raise_for_status()
            with open(local_filename, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        print(f"Descarga completada: {local_filename}")
    except Exception as e:
        print(f"Error en descarga directa: {e}")


def download_with_ffmpeg(url, output_path):
    output_file = os.path.join(output_path, "video_ffmpeg.mp4")
    try:
        # ffmpeg intentará descargar el video (requiere ffmpeg instalado)
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", url, "-c", "copy", output_file],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            print(f"Descarga completada con ffmpeg: {output_file}")
            return True
        else:
            print(f"ffmpeg error: {result.stderr}")
            return False
    except Exception as e:
        print(f"Error con ffmpeg: {e}")
        return False


def download_with_streamlink(url, output_path):
    output_file = os.path.join(output_path, "video_streamlink.mp4")
    try:
        # streamlink intentará descargar el stream (requiere streamlink instalado)
        result = subprocess.run(
            ["streamlink", url, "best", "-o", output_file],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            print(f"Descarga completada con streamlink: {output_file}")
            return True
        else:
            print(f"streamlink error: {result.stderr}")
            return False
    except Exception as e:
        print(f"Error con streamlink: {e}")
        return False


def download_with_ytdlp(url, output_path):
    ydl_opts = {
        'outtmpl': os.path.join(output_path, '%(title)s.%(ext)s'),
        'format': 'bestvideo+bestaudio/best',
    }
    try:
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        return True
    except DownloadError as e:
        print(f"URL no soportada por yt-dlp: {url}")
        return False
    except Exception as e:
        print(f"Error inesperado: {e}")
        return False


def download_from_url(url, output_path='.'):
    # Siempre usar yt-dlp para waaw.to
    if "waaw.to" in url:
        success = download_with_ytdlp(url, output_path)
        if not success:
            print("Intentando con ffmpeg...")
            success = download_with_ffmpeg(url, output_path)
        if not success:
            print("Intentando con streamlink...")
            download_with_streamlink(url, output_path)
    elif any(url.lower().endswith(ext) for ext in ['.mp4', '.webm', '.mov', '.avi', '.mkv']):
        download_direct(url, output_path)
    else:
        success = download_with_ytdlp(url, output_path)
        if not success:
            print("Intentando con ffmpeg...")
            success = download_with_ffmpeg(url, output_path)
        if not success:
            print("Intentando con streamlink...")
            download_with_streamlink(url, output_path)


if __name__ == "__main__":
    url = input("Introduce la URL del video: ")
    output_path = input(
        "Carpeta de destino (dejar vacío para actual): ").strip() or '.'
    download_from_url(url, output_path)
