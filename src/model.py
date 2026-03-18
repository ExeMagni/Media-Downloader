class Song:
    def __init__(self, title, artist, url, youtube_url=None, result_id=None):
        self.title = title
        self.artist = artist
        self.url = url  # Puede ser Spotify, etc.
        self.youtube_url = youtube_url  # Enlace real de YouTube
        self.result_id = result_id

    def __repr__(self):
        return f"Song(title={self.title}, artist={self.artist}, url={self.url}, youtube_url={self.youtube_url})"


class MediaManager:
    def __init__(self):
        self._songs = []
        # Index for faster text searches (list of dicts with lowercased fields)
        self._index = []

    @property
    def songs(self):
        return list(self._songs)

    def add_song(self, song):
        self._songs.append(song)
        # update index
        try:
            self._index.append({
                'title': song.title.lower(),
                'artist': song.artist.lower(),
                'url': (song.url or '').lower(),
                'result_id': song.result_id,
                'obj': song
            })
        except Exception:
            pass

    def find_song(self, title=None, artist=None):
        results = []
        lt = title.lower() if title else None
        la = artist.lower() if artist else None
        for entry in self._index:
            if (lt and lt in entry['title']) or (la and la in entry['artist']):
                results.append(entry['obj'])
        return results

    def search(self, query):
        q = query.lower()
        results = []
        for entry in self._index:
            if q in entry['title'] or q in entry['artist'] or q in entry['url']:
                s = entry['obj']
                results.append({'type': 'song', 'title': s.title,
                                'artist': s.artist, 'url': s.url,
                                'youtube_url': s.youtube_url,
                                'result_id': s.result_id})
        return results

    def search_by_artist_title(self, artist, title):
        a = artist.lower()
        t = title.lower()
        results = []
        for entry in self._index:
            if a in entry['artist'] and t in entry['title']:
                s = entry['obj']
                results.append({'type': 'song', 'title': s.title,
                                'artist': s.artist, 'url': s.url,
                                'youtube_url': s.youtube_url,
                                'result_id': s.result_id})
        return results

    def get_song(self, title, artist, result_id=None):
        t = title.lower()
        a = artist.lower()

        if result_id:
            for entry in self._index:
                if entry.get('result_id') == result_id:
                    song = entry['obj']
                    return {
                        'title': song.title,
                        'artist': song.artist,
                        'youtube_url': song.youtube_url,
                        'result_id': song.result_id
                    }

        # Prefer exact match first to avoid ambiguous substring matches.
        for entry in self._index:
            if t == entry['title'] and a == entry['artist']:
                song = entry['obj']
                return {
                    'title': song.title,
                    'artist': song.artist,
                    'youtube_url': song.youtube_url,
                    'result_id': song.result_id
                }

        for entry in self._index:
            if t in entry['title'] and a in entry['artist']:
                song = entry['obj']
                return {
                    'title': song.title,
                    'artist': song.artist,
                    'youtube_url': song.youtube_url,
                    'result_id': song.result_id
                }
        return None

    def clear_media(self):
        self._songs.clear()
        self._index.clear()

    def fetch_youtube_metadata(self, metadata):
        if not metadata:
            return []
        # Crear obj con la metadata
        title = metadata.get('title')
        artist = metadata.get('artist') or ''
        result_id = metadata.get('result_id')
        youtube_url = metadata.get(
            'youtube_url') or metadata.get('webpage_url') or ''
        if not title:
            return
        # avoid duplicates (if artist provided use both, otherwise skip exact artist match)
        existing = self.get_song(
            title, artist, result_id=result_id) if artist else None
        if existing:
            # update youtube_url if missing
            if not existing.get('youtube_url') and youtube_url:
                existing_song = self.get_song(
                    title, artist, result_id=result_id)
                # find object and update
                for s in self._songs:
                    if result_id and s.result_id != result_id:
                        continue
                    if title.lower() in s.title.lower() and artist.lower() in s.artist.lower():
                        s.youtube_url = youtube_url
                        break
            return
        # Create Song even if artist is empty; store youtube_url as both url and youtube_url
        song = Song(title, artist, youtube_url,
                    youtube_url, result_id=result_id)
        self.add_song(song)

    def fetch_spotify_metadata(self, spotify_api, query):
        results = []
        search_results = spotify_api.search(q=query, type='track', limit=5)
        for item in search_results['tracks']['items']:
            title = item['name']
            artist = item['artists'][0]['name']
            url = item['external_urls']['spotify']
            result_id = item.get('id')
            # Obtener la imagen del álbum
            cover_url = item['album']['images'][0]['url'] if item['album']['images'] else None
            song = Song(title, artist, url, result_id=result_id)
            self.add_song(song)
            results.append({
                'type': 'song',
                'title': title,
                'artist': artist,
                'url': url,
                'cover_url': cover_url,
                'result_id': result_id
            })
        return results
