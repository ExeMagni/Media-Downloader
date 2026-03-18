import yt_dlp
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials


class YtdlpLogger:
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


class SpotifyProvider:
    def authenticate(self, client_id, client_secret):
        credentials = SpotifyClientCredentials(
            client_id=client_id,
            client_secret=client_secret,
        )
        return spotipy.Spotify(client_credentials_manager=credentials)


class YouTubeProvider:
    def __init__(self):
        self._base_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
        }

    def _common_options(self):
        return {
            "nocheckcertificate": True,
            "geo_bypass": True,
            "http_headers": self._base_headers,
            "extractor_args": {
                "youtube": {"player_client": "web_html5"}
            },
        }

    def search_video_metadata(self, url, include_cover=True):
        ydl_opts = {
            "quiet": True,
            "skip_download": True,
            **self._common_options(),
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        return {
            "artist": info.get("uploader", ""),
            "title": info.get("title", ""),
            "cover_url": info.get("thumbnail", "") if include_cover else "",
            "youtube_url": url,
            "source": "YouTube",
        }

    def search_text_metadata(self, query, limit=10, include_cover=True):
        search_query = f"ytsearch{max(1, int(limit))}:{query}"
        ydl_opts = {
            "quiet": True,
            "skip_download": True,
            "default_search": "auto",
            **self._common_options(),
        }
        results = []
        seen = set()
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(search_query, download=False)
            entries = info.get("entries", []) if isinstance(info, dict) else []
            for entry in entries:
                if not entry:
                    continue
                title = entry.get("title") or ""
                artist = entry.get("uploader") or entry.get("channel") or ""
                youtube_url = entry.get("webpage_url")
                if not youtube_url and entry.get("id"):
                    youtube_url = f"https://www.youtube.com/watch?v={entry['id']}"
                key = (title.strip().lower(), (artist or "").strip(
                ).lower(), (youtube_url or "").strip().lower())
                if key in seen:
                    continue
                seen.add(key)
                results.append({
                    "title": title,
                    "artist": artist,
                    "youtube_url": youtube_url or "",
                    "cover_url": entry.get("thumbnail", "") if include_cover else "",
                    "source": "YouTube",
                })
        return results

    def search_playlist_metadata(self, playlist_url):
        ydl_opts = {
            "quiet": True,
            "skip_download": True,
            "ignoreerrors": True,
            "extract_flat": True,
            "cachedir": False,
            "no_warnings": True,
        }
        results = []
        seen = set()
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(playlist_url, download=False)
            entries = info.get("entries", [])

            for entry in entries:
                if not entry:
                    continue
                title = entry.get("title") or ""
                webpage = entry.get("webpage_url") or entry.get("url")
                key = (title.lower(), (webpage or "").lower())
                if key in seen:
                    continue
                seen.add(key)
                results.append({
                    "title": title,
                    "artist": "",
                    "youtube_url": webpage or "",
                    "source": "YouTube",
                })
        return results

    def resolve_youtube_url(self, title, artist):
        query = f"ytsearch1:{artist} {title}"
        ydl_opts = {
            "quiet": True,
            "skip_download": True,
            "default_search": "auto",
            **self._common_options(),
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(query, download=False)
            entries = info.get("entries") if isinstance(info, dict) else info
            if entries and len(entries) > 0:
                entry = entries[0]
                if "webpage_url" in entry:
                    return entry["webpage_url"]
                if "url" in entry and entry["url"].startswith("http"):
                    return entry["url"]
                if "id" in entry:
                    return f"https://www.youtube.com/watch?v={entry['id']}"
        return None

    def download_audio(self, url, save_path, progress_hook, log_hook=None):
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": f"{save_path}/%(title)s.%(ext)s",
            "progress_hooks": [progress_hook],
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
            "quiet": True,
            "noplaylist": True,
            **self._common_options(),
        }
        if log_hook:
            ydl_opts["logger"] = YtdlpLogger(log_hook)
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

    def download_video(self, url, save_path, progress_hook, log_hook=None):
        ydl_opts = {
            "format": "bestvideo+bestaudio/best",
            "outtmpl": f"{save_path}/%(title)s.%(ext)s",
            "progress_hooks": [progress_hook],
            "quiet": True,
            "noplaylist": True,
            **self._common_options(),
        }
        if log_hook:
            ydl_opts["logger"] = YtdlpLogger(log_hook)
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
