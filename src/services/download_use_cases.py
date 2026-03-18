class DownloadUseCaseService:
    def __init__(self, model, youtube_provider):
        self._model = model
        self._youtube_provider = youtube_provider

    @staticmethod
    def _normalize(text):
        return (text or "").strip().lower()

    def _find_song_object(self, title, artist, result_id=None):
        normalized_title = self._normalize(title)
        normalized_artist = self._normalize(artist)

        if result_id:
            for song in self._model.songs:
                if song.result_id == result_id:
                    return song

        for song in self._model.songs:
            if self._normalize(song.title) == normalized_title and self._normalize(song.artist) == normalized_artist:
                return song

        for song in self._model.songs:
            if normalized_title in self._normalize(song.title) and normalized_artist in self._normalize(song.artist):
                return song
        return None

    def _find_song_by_youtube_url(self, youtube_url):
        normalized_url = self._normalize(youtube_url)
        if not normalized_url:
            return None

        for song in self._model.songs:
            if self._normalize(song.youtube_url) == normalized_url:
                return song
        return None

    def _resolve_youtube_url(self, title, artist, not_found_message, no_url_message, youtube_url=None, result_id=None):
        if youtube_url:
            linked_song = self._find_song_object(
                title, artist, result_id=result_id) or self._find_song_by_youtube_url(youtube_url)
            if linked_song and not linked_song.youtube_url:
                linked_song.youtube_url = youtube_url
            return youtube_url

        song_obj = self._find_song_object(title, artist, result_id=result_id)
        song = self._model.get_song(title, artist, result_id=result_id)
        if not song:
            raise ValueError(not_found_message)

        youtube_url = song.get("youtube_url")
        if youtube_url:
            return youtube_url

        youtube_url = self._youtube_provider.resolve_youtube_url(title, artist)
        if not youtube_url:
            raise ValueError(no_url_message)

        if song_obj is not None:
            song_obj.youtube_url = youtube_url

        return youtube_url

    def download_audio_by_title_artist(self, song_title, artist, save_path, progress_hook, log_hook=None, youtube_url=None, result_id=None):
        url = self._resolve_youtube_url(
            title=song_title,
            artist=artist,
            not_found_message="Song not found.",
            no_url_message="No YouTube URL found for this song.",
            youtube_url=youtube_url,
            result_id=result_id,
        )
        self._youtube_provider.download_audio(
            url=url,
            save_path=save_path,
            progress_hook=progress_hook,
            log_hook=log_hook,
        )

    def download_video_by_title_artist(self, video_title, artist, save_path, progress_hook, log_hook=None, youtube_url=None, result_id=None):
        url = self._resolve_youtube_url(
            title=video_title,
            artist=artist,
            not_found_message="Video not found.",
            no_url_message="No YouTube URL found for this video.",
            youtube_url=youtube_url,
            result_id=result_id,
        )
        self._youtube_provider.download_video(
            url=url,
            save_path=save_path,
            progress_hook=progress_hook,
            log_hook=log_hook,
        )
