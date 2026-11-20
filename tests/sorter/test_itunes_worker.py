from itunes_tools.common.artwork_cache import ArtworkCache
from itunes_tools.common.itunes_client import ItunesClient
from itunes_tools.common.models import ItunesPersistentID
from itunes_tools.sorter.itunes_worker import ItunesWorker, capture_playlist


def test_capture_playlist_returns_songs_in_order_and_fills_the_artwork_cache(
    tmp_path, fake_itunes, make_com_track, make_com_playlist, make_artwork
):
    with_art = make_com_track(0, 1, name="With art", artworks=[make_artwork()])
    without_art = make_com_track(0, 2, name="Without art")
    fake_itunes.set_library_tracks(with_art, without_art)
    fake_itunes.set_playlists(make_com_playlist(5, 5, name="Mix", tracks=[without_art, with_art]))
    artwork_cache = ArtworkCache(tmp_path)

    playlist = capture_playlist(ItunesClient(), ItunesPersistentID(high=5, low=5), artwork_cache)

    assert [song.name for song in playlist.tracks] == ["Without art", "With art"]
    with_art_song, without_art_song = playlist.tracks[1], playlist.tracks[0]
    assert artwork_cache.get_path(with_art_song).read_bytes() == b"fake image"
    assert artwork_cache.get_path(without_art_song) is None


def test_worker_lists_playlist_names_sorted_case_insensitively(tmp_path, fake_itunes, make_com_playlist):
    fake_itunes.set_playlists(make_com_playlist(0, 1, "beta"), make_com_playlist(0, 2, "Alpha"))
    worker = ItunesWorker(ArtworkCache(tmp_path))
    listed = []
    worker.playlistsListed.connect(listed.append)

    worker.listPlaylists()

    assert listed == [["Alpha", "beta"]]


def test_worker_imports_a_listed_playlist(tmp_path, fake_itunes, make_com_track, make_com_playlist):
    track = make_com_track(0, 1)
    fake_itunes.set_library_tracks(track)
    fake_itunes.set_playlists(make_com_playlist(0, 9, "Mix", tracks=[track]))
    worker = ItunesWorker(ArtworkCache(tmp_path))
    imported = []
    worker.playlistImported.connect(imported.append)

    worker.listPlaylists()
    worker.importPlaylist("Mix")

    [playlist] = imported
    assert playlist.name == "Mix"
    assert len(playlist.tracks) == 1


def test_worker_reports_client_errors_as_failed(tmp_path, fake_itunes, make_com_playlist):
    fake_itunes.set_playlists(make_com_playlist(0, 1, "Same"), make_com_playlist(0, 2, "Same"))
    worker = ItunesWorker(ArtworkCache(tmp_path))
    failures = []
    worker.failed.connect(failures.append)

    worker.listPlaylists()

    [message] = failures
    assert "Same" in message


def test_worker_rejects_a_playlist_that_was_not_listed(tmp_path):
    worker = ItunesWorker(ArtworkCache(tmp_path))
    failures = []
    worker.failed.connect(failures.append)

    worker.importPlaylist("Unknown")

    assert len(failures) == 1


def test_worker_commits_a_playlist_in_the_given_order(tmp_path, fake_itunes, make_com_track):
    fake_itunes.set_library_tracks(make_com_track(0, 1, name="First"), make_com_track(0, 2, name="Second"))
    worker = ItunesWorker(ArtworkCache(tmp_path))
    committed = []
    worker.playlistCommitted.connect(committed.append)

    worker.commitPlaylist("Sorted", [ItunesPersistentID(high=0, low=2), ItunesPersistentID(high=0, low=1)])

    [playlist] = committed
    assert playlist.name == "Sorted"
    assert [song.name for song in playlist.tracks] == ["Second", "First"]


def test_worker_rejects_committing_under_a_taken_name(tmp_path, fake_itunes, make_com_track, make_com_playlist):
    fake_itunes.set_library_tracks(make_com_track(0, 1))
    fake_itunes.set_playlists(make_com_playlist(0, 9, "Taken"))
    worker = ItunesWorker(ArtworkCache(tmp_path))
    committed = []
    failures = []
    worker.playlistCommitted.connect(committed.append)
    worker.failed.connect(failures.append)

    worker.commitPlaylist("Taken", [ItunesPersistentID(high=0, low=1)])

    [message] = failures
    assert "'Taken' already exists" in message
    assert committed == []
    assert fake_itunes.LibrarySource.Playlists.Count == 1


def test_worker_reports_unexpected_commit_errors_as_failed(tmp_path, fake_itunes, monkeypatch):
    def broken_create_playlist(self, name, track_ids):
        raise RuntimeError("boom")

    monkeypatch.setattr(ItunesClient, "create_playlist", broken_create_playlist)
    worker = ItunesWorker(ArtworkCache(tmp_path))
    failures = []
    worker.failed.connect(failures.append)

    worker.commitPlaylist("Sorted", [])

    [message] = failures
    assert "Unexpected error while creating 'Sorted'" in message
