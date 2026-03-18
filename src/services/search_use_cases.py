from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


class SearchUseCaseService:
    def __init__(self, model, state_service, youtube_provider):
        self._model = model
        self._state_service = state_service
        self._youtube_provider = youtube_provider

    @staticmethod
    def _is_youtube_playlist_url(query: str):
        try:
            parts = urlsplit(query)
            hostname = (parts.netloc or "").lower()
            path = (parts.path or "").lower()
            return ("youtube.com" in hostname or "youtu.be" in hostname) and path.startswith("/playlist")
        except Exception:
            return False

    @staticmethod
    def _is_youtube_url(query: str):
        return query.startswith("https://youtu.be/") or query.startswith("https://www.youtube.com/")

    @staticmethod
    def _remove_list_parameter_if_present(query: str):
        try:
            parts = urlsplit(query)
            qs = parse_qsl(parts.query, keep_blank_values=True)
            qs_filtered = [(k, v) for (k, v) in qs if k.lower() != "list"]
            if len(qs_filtered) == len(qs):
                return query
            new_query = urlencode(qs_filtered)
            return urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))
        except Exception:
            return query

    @staticmethod
    def _result_key(item):
        result_id = (item.get("result_id") or "").strip().lower()
        if result_id:
            return (result_id,)
        return (
            (item.get("title") or "").strip().lower(),
            (item.get("artist") or "").strip().lower(),
            (item.get("url") or "").strip().lower(),
            (item.get("youtube_url") or "").strip().lower(),
        )

    def _merge_unique(self, base_results, extra_results):
        merged = list(base_results or [])
        seen = {self._result_key(item) for item in merged}
        for item in extra_results or []:
            key = self._result_key(item)
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
        return merged

    @staticmethod
    def _cached_query_key(query: str, include_cover: bool, include_youtube: bool):
        return (
            f"{query}::cover={1 if include_cover else 0}"
            f"::youtube={1 if include_youtube else 0}"
        )

    @staticmethod
    def _artist_title_cache_key(query: str, include_spotify: bool, include_cover: bool):
        return (
            f"{query}::spotify={1 if include_spotify else 0}"
            f"::cover={1 if include_cover else 0}"
        )

    def search(self, query, enable_spotify=False, spotify_api=None, enable_cover=True, enable_youtube=True):
        results = self._model.search(query)

        cache_key = self._cached_query_key(
            query,
            include_cover=enable_cover,
            include_youtube=enable_youtube,
        )
        cached = self._state_service.get_cached_search(cache_key)
        cached_youtube_results = list(cached or [])
        if cached_youtube_results:
            results = self._merge_unique(results, cached_youtube_results)

        if enable_youtube and self._is_youtube_playlist_url(query):
            youtube_results = self._youtube_provider.search_playlist_metadata(
                query)
            results = self._merge_unique(results, youtube_results)
            self._state_service.set_cached_search(cache_key, youtube_results)
            return results

        if enable_youtube and self._is_youtube_url(query):
            cleaned = self._remove_list_parameter_if_present(query)
            info = self._youtube_provider.search_video_metadata(
                url=cleaned,
                include_cover=enable_cover,
            )
            if enable_cover:
                self._model.fetch_youtube_metadata(info)
            results.append(info)
            return results

        if enable_spotify and spotify_api:
            spotify_results = self._model.fetch_spotify_metadata(
                spotify_api, query)
            results = self._merge_unique(results, spotify_results)

        youtube_results = cached_youtube_results if enable_youtube else []
        if enable_youtube and not youtube_results:
            youtube_results = self._youtube_provider.search_text_metadata(
                query=query,
                limit=10,
                include_cover=enable_cover,
            )
            if youtube_results:
                self._state_service.set_cached_search(
                    cache_key, youtube_results)

        results = self._merge_unique(results, youtube_results)

        return results

    def search_by_artist_title(self, artist, title, enable_spotify=False, spotify_api=None, enable_cover=True):
        query = f"{artist} {title}"
        local_results = self._model.search_by_artist_title(artist, title)

        cache_key = self._artist_title_cache_key(
            query,
            include_spotify=enable_spotify,
            include_cover=enable_cover,
        )
        cached = self._state_service.get_cached_search(cache_key)
        if cached:
            return self._merge_unique(local_results, cached)

        results = list(local_results)

        if enable_spotify and spotify_api:
            spotify_query = f"{artist} {title}"
            spotify_results = self._model.fetch_spotify_metadata(
                spotify_api, spotify_query)
            results = self._merge_unique(results, spotify_results)
            self._state_service.set_cached_search(
                cache_key, spotify_results)

        return results
