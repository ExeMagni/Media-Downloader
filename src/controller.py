import threading
import concurrent.futures
import os
from uuid import uuid4
from src.services.media_providers import SpotifyProvider, YouTubeProvider
from src.services.application_state import ApplicationStateService
from src.services.download_use_cases import DownloadUseCaseService
from src.services.search_use_cases import SearchUseCaseService

# Default max workers: scale with CPU but bounded
DEFAULT_MAX_WORKERS = min(32, max(4, (os.cpu_count() or 1) * 5))


class MusicDownloaderController:
    def __init__(self, model, client_id=None, client_secret=None, max_workers: int = None,
                 enable_spotify: bool = True, enable_cover: bool = True):
        self.model = model
        self.spotify_api = None
        # feature flags
        self.enable_spotify = enable_spotify
        self.enable_cover = enable_cover
        # Limit concurrent download tasks to avoid saturating the system.
        # Enforce at most 5 concurrent downloads by default (can still be overridden by max_workers arg).
        requested = max_workers or DEFAULT_MAX_WORKERS
        self.max_workers = min(requested, 5)
        # semaphore to limit concurrent external processes (ffmpeg/yt-dlp)
        self._download_semaphore = threading.BoundedSemaphore(self.max_workers)
        self._spotify_provider = SpotifyProvider()
        self._youtube_provider = YouTubeProvider()
        self._download_use_cases = DownloadUseCaseService(
            model=self.model,
            youtube_provider=self._youtube_provider,
        )
        self._state_service = ApplicationStateService(cache_ttl_seconds=300)
        self._search_use_cases = SearchUseCaseService(
            model=self.model,
            state_service=self._state_service,
            youtube_provider=self._youtube_provider,
        )

        # Only authenticate Spotify if enabled and credentials provided
        if self.enable_spotify and client_id and client_secret:
            self.authenticate_spotify(client_id, client_secret)

    def authenticate_spotify(self, client_id, client_secret):
        self.spotify_api = self._spotify_provider.authenticate(
            client_id=client_id,
            client_secret=client_secret,
        )

    @staticmethod
    def _normalize_format(format_selected: str):
        return "mp4" if str(format_selected).lower() == "mp4" else "mp3"

    @staticmethod
    def _build_display_item(result: dict, format_selected: str):
        fmt = MusicDownloaderController._normalize_format(format_selected)
        fmt_label = "MP4" if fmt == "mp4" else "MP3"
        artist = result.get("artist", "")
        title = result.get("title", "")
        return {
            "artist": artist,
            "title": title,
            "format": fmt,
            "display": f"({fmt_label}) {artist} - {title}",
            "youtube_url": result.get("youtube_url", ""),
            "result_id": result.get("result_id")
        }

    @staticmethod
    def _ensure_result_ids(results):
        normalized = []
        for result in results or []:
            item = dict(result)
            if not item.get("result_id"):
                item["result_id"] = str(uuid4())
            normalized.append(item)
        return normalized

    def search_from_inputs(self, query: str, artist: str, title: str):
        query = (query or "").strip()
        artist = (artist or "").strip()
        title = (title or "").strip()

        if title:
            results = self.search_by_artist_title(
                artist, title) if artist else self.search(title)
        elif query:
            results = self.search(query)
        else:
            raise ValueError(
                "Ingrese un término de búsqueda, canción o artista.")

        results = self._ensure_result_ids(results)
        self._state_service.set_last_results(results)
        return list(results)

    def add_result_to_download_queue(self, result_index: int, format_selected: str):
        results = self._state_service.get_last_results()
        if result_index < 0 or result_index >= len(results):
            raise IndexError("Índice de resultado inválido.")
        result = results[result_index]

        if result.get("youtube_url"):
            try:
                self.model.fetch_youtube_metadata(result)
            except Exception:
                pass

        queue_item = self._build_display_item(result, format_selected)
        self._state_service.add_to_download_queue(queue_item)
        return dict(queue_item)

    def add_all_results_to_download_queue(self, format_selected: str):
        results = self._state_service.get_last_results()

        added = []
        for result in results:
            if result.get("youtube_url"):
                try:
                    self.model.fetch_youtube_metadata(result)
                except Exception:
                    pass
            queue_item = self._build_display_item(result, format_selected)
            added.append(queue_item)

        self._state_service.extend_download_queue(added)
        return [dict(item) for item in added]

    def remove_from_download_queue(self, queue_index: int):
        return self._state_service.remove_from_download_queue(queue_index)

    def clear_download_queue(self):
        self._state_service.clear_download_queue()

    def get_download_queue_snapshot(self):
        return self._state_service.get_download_queue_snapshot()

    def get_download_queue_size(self):
        return self._state_service.get_download_queue_size()

    def search(self, query):
        return self._search_use_cases.search(
            query=query,
            enable_spotify=self.enable_spotify,
            spotify_api=self.spotify_api,
            enable_cover=self.enable_cover,
        )

    def search_by_artist_title(self, artist, title):
        return self._search_use_cases.search_by_artist_title(
            artist=artist,
            title=title,
            enable_spotify=self.enable_spotify,
            spotify_api=self.spotify_api,
        )

    def download_song(self, song_title, artist, save_path, progress_hook, format_selected, log_hook=None, youtube_url=None, result_id=None):
        if format_selected == "mp3":
            self.download_audio(song_title, artist, save_path,
                                progress_hook, log_hook=log_hook, youtube_url=youtube_url, result_id=result_id)
        elif format_selected == "mp4":
            self.download_video(song_title, artist, save_path,
                                progress_hook, log_hook=log_hook, youtube_url=youtube_url, result_id=result_id)

    def download_audio(self, song_title, artist, save_path, progress_hook, log_hook=None, youtube_url=None, result_id=None):
        # Limit concurrent downloads at process level
        try:
            with self._download_semaphore:
                self._download_use_cases.download_audio_by_title_artist(
                    song_title=song_title,
                    artist=artist,
                    youtube_url=youtube_url,
                    result_id=result_id,
                    save_path=save_path,
                    progress_hook=progress_hook,
                    log_hook=log_hook,
                )
        except Exception as e:
            if log_hook:
                try:
                    log_hook(f"[ERROR] download_audio falló: {e}")
                except Exception:
                    pass
            else:
                print(f"[ERROR] download_audio falló: {e}")
            raise

    def download_video(self, video_title, artist, save_path, progress_hook, log_hook=None, youtube_url=None, result_id=None):
        try:
            with self._download_semaphore:
                self._download_use_cases.download_video_by_title_artist(
                    video_title=video_title,
                    artist=artist,
                    youtube_url=youtube_url,
                    result_id=result_id,
                    save_path=save_path,
                    progress_hook=progress_hook,
                    log_hook=log_hook,
                )
        except Exception as e:
            if log_hook:
                try:
                    log_hook(f"[ERROR] download_video falló: {e}")
                except Exception:
                    pass
            else:
                print(f"[ERROR] download_video falló: {e}")
            raise

    def download_multiple_songs(self, song_list, save_path, progress_hook, max_workers=None, log_hook=None, per_file_hook=None, per_file_progress_hook=None):
        """
        Descarga varias canciones en paralelo usando un pool de hilos.
        song_list: lista de dicts con keys 'title', 'artist', 'format'
        """
        workers = max_workers if max_workers else self.max_workers
        failed_downloads = []

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
                    # Log thread info for debug
                    if log_hook:
                        try:
                            log_hook(
                                f"[DEBUG] Starting download idx={idx} title={song.get('title')} thread={threading.current_thread().name}:{threading.get_ident()}")
                        except Exception:
                            pass

                    # Create a per-task progress wrapper that informs the caller which index is reporting.
                    def _task_progress(info):
                        try:
                            if per_file_progress_hook:
                                try:
                                    per_file_progress_hook(idx, info)
                                except Exception:
                                    pass
                        except Exception:
                            pass
                        try:
                            progress_hook(info)
                        except Exception:
                            pass

                    return self.download_song(
                        song["title"],
                        song["artist"],
                        save_path,
                        _task_progress,
                        song["format"],
                        log_hook=log_hook,
                        youtube_url=song.get("youtube_url"),
                        result_id=song.get("result_id"),
                    )
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
                    raise

            for idx, song in enumerate(song_list):
                futures.append(executor.submit(_task, idx, song))

            for f in concurrent.futures.as_completed(futures):
                try:
                    f.result()
                except Exception as e:
                    failed_downloads.append(str(e))

        if failed_downloads:
            unique_errors = list(dict.fromkeys(failed_downloads))
            summary = "; ".join(unique_errors[:3])
            if len(unique_errors) > 3:
                summary += "; ..."
            raise RuntimeError(
                f"Fallaron {len(failed_downloads)} descargas. {summary}")
