class DownloadUseCaseService:
    def __init__(self, model, youtube_provider):
        self._model = model
        self._youtube_provider = youtube_provider

    def _find_song_object(self, title, artist):
        for song in self._model.songs:
            if title.lower() in song.title.lower() and artist.lower() in song.artist.lower():
                return song
        return None

    def _resolve_youtube_url(self, title, artist, not_found_message, no_url_message):
        song_obj = self._find_song_object(title, artist)
        song = self._model.get_song(title, artist)
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

    def download_audio_by_title_artist(self, song_title, artist, save_path, progress_hook, log_hook=None):
        url = self._resolve_youtube_url(
            title=song_title,
            artist=artist,
            not_found_message="Song not found.",
            no_url_message="No YouTube URL found for this song.",
        )
        self._youtube_provider.download_audio(
            url=url,
            save_path=save_path,
            progress_hook=progress_hook,
            log_hook=log_hook,
        )

    def download_video_by_title_artist(self, video_title, artist, save_path, progress_hook, log_hook=None):
        url = self._resolve_youtube_url(
            title=video_title,
            artist=artist,
            not_found_message="Video not found.",
            no_url_message="No YouTube URL found for this video.",
        )
        self._youtube_provider.download_video(
            url=url,
            save_path=save_path,
            progress_hook=progress_hook,
            log_hook=log_hook,
        )
