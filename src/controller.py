import yt_dlp
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

import threading
import concurrent.futures
import os
import time
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

# Default max workers: scale with CPU but bounded
DEFAULT_MAX_WORKERS = min(32, max(4, (os.cpu_count() or 1) * 5))


class _YtdlpLogger:
    def __init__(self, log_hook=None):
        self.log_hook = log_hook

    def debug(self, msg):
        if self.log_hook:
            try:
                self.log_hook(f"[DEBUG] {msg}")
            except Exception:
                pass

    def info(self, msg):
        if self.log_hook:
            try:
                self.log_hook(f"[INFO] {msg}")
            except Exception:
                pass

    def warning(self, msg):
        if self.log_hook:
            try:
                self.log_hook(f"[WARNING] {msg}")
            except Exception:
                pass

    def error(self, msg):
        if self.log_hook:
            try:
                self.log_hook(f"[ERROR] {msg}")
            except Exception:
                pass


class MusicDownloaderController:
    def __init__(self, model, client_id=None, client_secret=None, max_workers: int = None,
                 enable_spotify: bool = True, enable_cover: bool = True):
        self.model = model
        self.spotify_api = None
        # feature flags
        self.enable_spotify = enable_spotify
        self.enable_cover = enable_cover
        self._search_cache = {}  # simple cache: query -> (ts, results)
        self.cache_ttl = 300  # seconds
        self.max_workers = max_workers or DEFAULT_MAX_WORKERS
        # semaphore to limit concurrent external processes (ffmpeg/yt-dlp)
        self._download_semaphore = threading.BoundedSemaphore(self.max_workers)

        # Only authenticate Spotify if enabled and credentials provided
        if self.enable_spotify and client_id and client_secret:
            self.authenticate_spotify(client_id, client_secret)

    def authenticate_spotify(self, client_id, client_secret):
        credentials = SpotifyClientCredentials(
            client_id=client_id, client_secret=client_secret)
        self.spotify_api = spotipy.Spotify(
            client_credentials_manager=credentials)

    def search(self, query):
        # Busca localmente
        results = self.model.search(query)
        # cache check
        now = time.time()
        cached = self._search_cache.get(query)
        if cached and now - cached[0] < self.cache_ttl:
            results.extend(cached[1])
            return results
        # Si es una playlist de youtube (URL explícita de playlist)
        is_playlist = False
        try:
            parts = urlsplit(query)
            hostname = (parts.netloc or '').lower()
            path = (parts.path or '').lower()
            qs = dict(parse_qsl(parts.query, keep_blank_values=True))
            if ('youtube.com' in hostname or 'youtu.be' in hostname) and path.startswith('/playlist'):
                is_playlist = True
        except Exception:
            is_playlist = False

        if is_playlist:
            youtube_results = self.search_youtube_playlist(query)
            results.extend(youtube_results)
            # cache playlist result
            self._search_cache[query] = (now, youtube_results)
        # Si es una url de youtube (video o vídeo con parámetros).
        elif query.startswith("https://youtu.be/") or query.startswith("https://www.youtube.com/"):
            # Algunas URLs de YouTube pueden traer el parámetro `list=` que provoca
            # que yt_dlp intente resolver la playlist y demore la extracción.
            # Para acelerar la búsqueda, removemos el parámetro `list` cuando la URL
            # apunta a un video (p. ej. https://youtu.be/<id>?list=...).
            try:
                parts = urlsplit(query)
                qs = parse_qsl(parts.query, keep_blank_values=True)
                # Filtrar parámetros 'list'
                qs_filtered = [(k, v) for (k, v) in qs if k.lower() != 'list']
                if len(qs_filtered) != len(qs):
                    new_query = urlencode(qs_filtered)
                    cleaned = urlunsplit(
                        (parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))
                else:
                    cleaned = query
            except Exception:
                cleaned = query

            youtube_results = self.search_youtube_url(cleaned)
            results.extend(youtube_results)
        # Si hay Spotify disponible y la búsqueda en Spotify está habilitada,
        # busca también en Spotify y agrega resultados
        elif self.enable_spotify and self.spotify_api:
            spotify_results = self.model.fetch_spotify_metadata(
                self.spotify_api, query)
            results.extend(spotify_results)

        return results

    def search_by_artist_title(self, artist, title):
        query = f"{artist} {title}"
        now = time.time()
        cached = self._search_cache.get(query)
        if cached and now - cached[0] < self.cache_ttl:
            return cached[1]
        results = self.model.search_by_artist_title(artist, title)
        # También busca en Spotify si está disponible y la opción está habilitada
        if self.enable_spotify and self.spotify_api:
            spotify_query = f"{artist} {title}"
            spotify_results = self.model.fetch_spotify_metadata(
                self.spotify_api, spotify_query)
            results.extend(spotify_results)
            self._search_cache[spotify_query] = (now, spotify_results)
        return results

    def download_song(self, song_title, artist, save_path, progress_hook, format_selected, log_hook=None):
        if format_selected == "mp3":
            self.download_audio(song_title, artist, save_path,
                                progress_hook, log_hook=log_hook)
        elif format_selected == "mp4":
            self.download_video(song_title, artist, save_path,
                                progress_hook, log_hook=log_hook)

    def download_audio(self, song_title, artist, save_path, progress_hook, log_hook=None):
        song_obj = None
        # Busca el objeto Song en la lista
        for s in self.model.songs:
            if song_title.lower() in s.title.lower() and artist.lower() in s.artist.lower():
                song_obj = s
                break
        song = self.model.get_song(song_title, artist)
        if not song:
            raise ValueError("Song not found.")
        url = song.get('youtube_url')
        if not url:
            url = self.get_youtube_url(song_title, artist)
            if not url:
                raise ValueError("No YouTube URL found for this song.")
            # Guarda el enlace en el objeto Song
            if song_obj:
                song_obj.youtube_url = url

        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': f'{save_path}/%(title)s.%(ext)s',
            'progress_hooks': [progress_hook],
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'quiet': True,
            'noplaylist': True,
            # Make requests more browser-like to avoid 403s and enable geo bypass
            'nocheckcertificate': True,
            'geo_bypass': True,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36'
            },
            'extractor_args': {
                'youtube': {'player_client': 'web_html5'}
            },
        }
        # Attach logger if provided to forward textual output
        if log_hook:
            ydl_opts['logger'] = _YtdlpLogger(log_hook)

        # Limit concurrent downloads at process level
        try:
            with self._download_semaphore:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
        except Exception as e:
            if log_hook:
                try:
                    log_hook(f"[ERROR] download_audio falló: {e}")
                except Exception:
                    pass
            else:
                print(f"[ERROR] download_audio falló: {e}")

    def download_video(self, video_title, artist, save_path, progress_hook, log_hook=None):
        video_obj = None
        for v in self.model.songs:
            if video_title.lower() in v.title.lower() and artist.lower() in v.artist.lower():
                video_obj = v
                break
        video = self.model.get_song(video_title, artist)
        if not video:
            raise ValueError("Video not found.")
        url = video.get('youtube_url')
        if not url:
            url = self.get_youtube_url(video_title, artist)
            if not url:
                raise ValueError("No YouTube URL found for this video.")
            if video_obj:
                video_obj.youtube_url = url

        ydl_opts = {
            'format': 'bestvideo+bestaudio/best',
            'outtmpl': f'{save_path}/%(title)s.%(ext)s',
            'progress_hooks': [progress_hook],
            'quiet': True,
            'noplaylist': True,
            'nocheckcertificate': True,
            'geo_bypass': True,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36'
            },
            'extractor_args': {
                'youtube': {'player_client': 'web_html5'}
            },
        }
        if log_hook:
            ydl_opts['logger'] = _YtdlpLogger(log_hook)

        try:
            with self._download_semaphore:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
        except Exception as e:
            if log_hook:
                try:
                    log_hook(f"[ERROR] download_video falló: {e}")
                except Exception:
                    pass
            else:
                print(f"[ERROR] download_video falló: {e}")

    def download_multiple_songs(self, song_list, save_path, progress_hook, max_workers=None, log_hook=None, per_file_hook=None):
        """
        Descarga varias canciones en paralelo usando un pool de hilos.
        song_list: lista de dicts con keys 'title', 'artist', 'format'
        """
        workers = max_workers if max_workers else self.max_workers

        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            futures = []

            def _task(idx, song):
                # Notify per-file start if hook provided
                try:
                    if per_file_hook:
                        try:
                            per_file_hook(idx, len(song_list),
                                          song.get('title'))
                        except Exception:
                            pass
                    return self.download_song(song["title"], song["artist"], save_path, progress_hook, song["format"], log_hook=log_hook)
                except Exception as e:
                    if log_hook:
                        try:
                            log_hook(
                                f"[ERROR] descarga de {song.get('title')} falló: {e}")
                        except Exception:
                            pass
                    else:
                        print(
                            f"[ERROR] descarga de {song.get('title')} falló: {e}")

            for idx, song in enumerate(song_list):
                futures.append(executor.submit(_task, idx, song))

            for f in concurrent.futures.as_completed(futures):
                try:
                    f.result()
                except Exception as e:
                    print(f"[ERROR] tarea en pool falló: {e}")

    def search_youtube_url(self, url):
        """Obtiene metadatos de un video de YouTube por URL."""
        ydl_opts = {
            'quiet': True,
            'skip_download': True,
            'nocheckcertificate': True,
            'geo_bypass': True,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36'
            },
            'extractor_args': {
                'youtube': {'player_client': 'web_html5'}
            },
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
            result = {
                'artist': info.get('uploader', ''),
                'title': info.get('title', ''),
                'cover_url': info.get('thumbnail', '') if self.enable_cover else '',
                'youtube_url': url
            }
            # Only enrich model with youtube metadata if cover/metadata fetching enabled
            if self.enable_cover:
                self.model.fetch_youtube_metadata(result)
            return [result]
        except Exception as e:
            print(f"Error obteniendo metadatos de YouTube: {e}")
            return []

    def search_youtube_playlist(self, playlist_url, max_workers=None):
        """Obtiene metadatos ligeros de una playlist de YouTube (flat) para listar rápido.
        Evita descargar metadatos completos de entrada para acelerar la respuesta.
        """
        # Use flat extraction and avoid cache/warnings to minimize I/O and delay
        ydl_opts = {
            'quiet': True,
            'skip_download': True,
            'ignoreerrors': True,
            'extract_flat': True,
            'cachedir': False,
            'no_warnings': True,
        }
        results = []
        seen = set()
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(playlist_url, download=False)
                entries = info.get('entries', [])

                for entry in entries:
                    if not entry:
                        continue
                    # flat entries usually contain only 'title' and 'id' or 'url'
                    title = entry.get('title') or ''
                    # keep artist minimal (avoid extra lookups)
                    uploader = ''
                    webpage = entry.get('webpage_url') or entry.get('url')
                    key = (title.lower(), (webpage or '').lower())
                    if key in seen:
                        continue
                    seen.add(key)
                    # Return only minimal fields: title and youtube_url
                    result = {
                        'title': title,
                        'artist': uploader,
                        'youtube_url': webpage or ''
                    }
                    results.append(result)
            return results
        except Exception as e:
            print(f"Error obteniendo playlist: {e}")
            return []

    def get_youtube_url(self, title, artist):
        query = f"ytsearch1:{artist} {title}"
        ydl_opts = {
            'quiet': True,
            'skip_download': True,
            'default_search': 'auto',
            'nocheckcertificate': True,
            'geo_bypass': True,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36'
            },
            'extractor_args': {
                'youtube': {'player_client': 'web_html5'}
            },
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(query, download=False)
                # Puede venir como dict o lista
                entries = info.get('entries') if isinstance(
                    info, dict) else info
                if entries and len(entries) > 0:
                    entry = entries[0]
                    # Intenta obtener el enlace de varias formas
                    if 'webpage_url' in entry:
                        return entry['webpage_url']
                    elif 'url' in entry and entry['url'].startswith('http'):
                        return entry['url']
                    elif 'id' in entry:
                        return f"https://www.youtube.com/watch?v={entry['id']}"
        except Exception as e:
            print(f"Error buscando en YouTube: {e}")
        return None
