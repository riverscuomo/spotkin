
try:
    from build_artist_genres import build_artist_genres
    from scripts.api import get_audio_features, log, random
    from scripts.bans import FilterTool, log
    from scripts.get_all_tracks import get_all_tracks
    from scripts.post_description import log, post_description, random
    from scripts.utils import log
except:
    from spotkin_tools.build_artist_genres import build_artist_genres
    from spotkin_tools.scripts.api import get_audio_features, log, random
    from spotkin_tools.scripts.bans import FilterTool, log
    from spotkin_tools.scripts.get_all_tracks import get_all_tracks
    from spotkin_tools.scripts.post_description import log, post_description, random
    from spotkin_tools.scripts.utils import log

import random


def process_job(spotify, job):
    log(f"process_job: {job['name']}")

    tracks = get_all_tracks(job, spotify)
    log(f"tracks: {len(tracks)}")

    updated_tracks = []

    # make list of just the track objects while also eliminating duplicates and empty tracks
    tracks = list({v["track"]["id"]: v["track"] for v in tracks}.values())

    track_ids = [x["id"] for x in tracks]
    log(track_ids)

    audio_features = get_audio_features(spotify, track_ids)
    all_artists_genres = build_artist_genres(spotify, tracks)
    filter_tool = FilterTool(job, audio_features)

    # Cull banned items from your list
    for track in tracks:
        track_id = track["id"]
        track_name = track["name"]
        artist_id = track["artists"][0]["id"]
        artist_name = track["artists"][0]["name"]
        this_artist_genres = next(
            (x['genres'] for x in all_artists_genres if x["artist_id"]
             == artist_id and "genres" in x), None
        )

        if filter_tool.is_banned(this_artist_genres, artist_name, track_name, track_id, track, artist_id=artist_id):
            continue

        updated_tracks.append(track["id"])

    random.shuffle(updated_tracks)

    if "last_track_ids" not in job and "last_tracks" in job:
        job["last_track_ids"] = [x["id"] for x in job["last_tracks"]]

    # if you've specify a track or tracks to always add at the end (for easy access, for example,
    # nature sounds or white noise)
    updated_tracks.extend(job["last_track_ids"])

    log("spotify.user_playlist_replace_tracks with an empty list")

    log(spotify.me()["id"])
    log(len(updated_tracks))

    user = spotify.me()
    user_id = user["id"]
    # empty playlist
    result = spotify.user_playlist_replace_tracks(
        user_id, job["playlist_id"], []
    )
    log(result)

    limit = 100

    # log(updated_tracks)

    log("spotify.user_playlist_add_tracks")

    for chunk in (updated_tracks[i:i+limit] for i in range(0, len(updated_tracks), limit)):
        result = spotify.user_playlist_add_tracks(
            spotify.me()["id"], job["playlist_id"], chunk
        )

    # change the playlist description to a random fact
    post_description(spotify, job)
