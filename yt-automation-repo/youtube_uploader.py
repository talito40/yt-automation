"""
youtube_uploader.py
Handles all YouTube Data API v3 operations including playlists,
comments, and internal description linking.
"""

import json
import os
import pickle
import time
import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors
import googleapiclient.http
from google.auth.transport.requests import Request
import config

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]

CATEGORY_ID = "27"
PRIVACY     = "public"
_PLAYLIST_CACHE_FILE = lambda: f"playlists_ch{config.CHANNEL}.json"


def _get_authenticated_service():
    credentials = None
    if os.path.exists(config.YOUTUBE_TOKEN_FILE):
        with open(config.YOUTUBE_TOKEN_FILE, "rb") as f:
            credentials = pickle.load(f)
    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        else:
            flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
                config.YOUTUBE_CLIENT_SECRETS, SCOPES
            )
            credentials = flow.run_local_server(port=0)
        with open(config.YOUTUBE_TOKEN_FILE, "wb") as f:
            pickle.dump(credentials, f)
    return googleapiclient.discovery.build("youtube", "v3", credentials=credentials)


def _do_upload(service, body: dict, video_path: str) -> tuple[str, str]:
    media    = googleapiclient.http.MediaFileUpload(
        video_path, mimetype="video/mp4", resumable=True, chunksize=1024 * 1024 * 10,
    )
    request  = service.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    retry    = 0
    while response is None:
        try:
            print(f"[youtube] Uploading... (attempt {retry + 1})")
            status, response = request.next_chunk()
            if status:
                print(f"[youtube] Upload progress: {int(status.progress() * 100)}%")
        except googleapiclient.errors.HttpError as e:
            if e.resp.status in (500, 502, 503, 504) and retry < config.MAX_RETRIES:
                retry += 1
                time.sleep(5 * retry)
            else:
                raise
    video_id = response["id"]
    return f"https://www.youtube.com/watch?v={video_id}", video_id


def upload_video(video_path, title, description, tags, service=None):
    if service is None:
        service = _get_authenticated_service()
    body = {
        "snippet": {
            "title": title[:100], "description": description[:5000],
            "tags": tags[:500], "categoryId": CATEGORY_ID,
            "defaultLanguage": "en", "defaultAudioLanguage": "en",
        },
        "status": {"privacyStatus": PRIVACY, "selfDeclaredMadeForKids": False},
    }
    url, video_id = _do_upload(service, body, video_path)
    print(f"[youtube] Upload complete -> {url}")
    return url, video_id


def upload_short(video_path, title, description, tags, service=None):
    if service is None:
        service = _get_authenticated_service()
    short_title = title if "#Shorts" in title else f"{title} #Shorts"
    short_desc  = f"{description}\n\n#Shorts #YouTubeShorts"
    short_tags  = list(dict.fromkeys((tags or []) + ["Shorts", "YouTubeShorts"]))
    body = {
        "snippet": {
            "title": short_title[:100], "description": short_desc[:5000],
            "tags": short_tags, "categoryId": CATEGORY_ID,
            "defaultLanguage": "en", "defaultAudioLanguage": "en",
        },
        "status": {"privacyStatus": PRIVACY, "selfDeclaredMadeForKids": False},
    }
    url, video_id = _do_upload(service, body, video_path)
    print(f"[youtube] Short uploaded -> {url}")
    return url, video_id


def upload_thumbnail(service, video_id, thumbnail_path):
    try:
        service.thumbnails().set(
            videoId=video_id,
            media_body=googleapiclient.http.MediaFileUpload(thumbnail_path, mimetype="image/jpeg"),
        ).execute()
        print(f"[youtube] Thumbnail set for {video_id}")
        return True
    except googleapiclient.errors.HttpError as e:
        print(f"[youtube] Thumbnail skipped (channel not verified): {e.reason}")
        return False


# ── Playlist management ───────────────────────────────────────────────────────

def _load_playlist_cache():
    f = _PLAYLIST_CACHE_FILE()
    if os.path.exists(f):
        with open(f) as fh:
            return json.load(fh)
    return {}


def _save_playlist_cache(cache):
    with open(_PLAYLIST_CACHE_FILE(), "w") as f:
        json.dump(cache, f, indent=2)


def get_or_create_playlist(service, playlist_name):
    cache = _load_playlist_cache()
    if playlist_name in cache:
        return cache[playlist_name]
    response = service.playlists().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": playlist_name,
                "description": f"{playlist_name} | {config.CHANNEL_NAME}",
                "defaultLanguage": "en",
            },
            "status": {"privacyStatus": "public"},
        },
    ).execute()
    playlist_id = response["id"]
    cache[playlist_name] = playlist_id
    _save_playlist_cache(cache)
    print(f"[youtube] Created playlist '{playlist_name}' -> {playlist_id}")
    return playlist_id


def add_to_playlist(service, video_id, playlist_name):
    try:
        playlist_id = get_or_create_playlist(service, playlist_name)
        service.playlistItems().insert(
            part="snippet",
            body={
                "snippet": {
                    "playlistId": playlist_id,
                    "resourceId": {"kind": "youtube#video", "videoId": video_id},
                }
            },
        ).execute()
        print(f"[youtube] Added {video_id} to playlist '{playlist_name}'")
        return True
    except googleapiclient.errors.HttpError as e:
        print(f"[youtube] Playlist add failed (non-fatal): {e.reason}")
        return False


# ── Recent videos ─────────────────────────────────────────────────────────────

def get_recent_videos(service, exclude_id: str = "", max_results: int = 3) -> list[dict]:
    """
    Returns list of {title, url, video_id, description} for the channel's
    most recent public videos, excluding exclude_id.
    """
    try:
        # The uploads playlist ID = channel ID with UC -> UU prefix
        uploads_playlist = "UU" + config.YOUTUBE_CHANNEL_ID[2:]
        resp = service.playlistItems().list(
            part="snippet",
            playlistId=uploads_playlist,
            maxResults=max_results + 1,
        ).execute()
        videos = []
        for item in resp.get("items", []):
            vid_id = item["snippet"]["resourceId"]["videoId"]
            if vid_id == exclude_id:
                continue
            videos.append({
                "video_id":    vid_id,
                "title":       item["snippet"]["title"],
                "url":         f"https://www.youtube.com/watch?v={vid_id}",
                "description": item["snippet"].get("description", ""),
            })
            if len(videos) >= max_results:
                break
        return videos
    except Exception as e:
        print(f"[youtube] Could not fetch recent videos (non-fatal): {e}")
        return []


# ── Auto comment ──────────────────────────────────────────────────────────────

def post_channel_comment(service, video_id: str, recent_videos: list[dict]) -> bool:
    """
    Posts a first comment on the video with links to related recent videos.
    Channel owner comments are displayed prominently by YouTube.
    """
    if not recent_videos:
        print("[youtube] No recent videos to link — skipping comment")
        return False
    try:
        lines = [f"👇 More videos you'll love:"]
        for v in recent_videos[:3]:
            lines.append(f"• {v['title']} → {v['url']}")
        lines += [
            "",
            f"🔔 Subscribe for daily {config.NICHE} tips!",
        ]
        comment_text = "\n".join(lines)

        service.commentThreads().insert(
            part="snippet",
            body={
                "snippet": {
                    "videoId": video_id,
                    "topLevelComment": {
                        "snippet": {"textOriginal": comment_text}
                    },
                }
            },
        ).execute()
        print(f"[youtube] Comment posted on {video_id}")
        return True
    except googleapiclient.errors.HttpError as e:
        print(f"[youtube] Comment post failed (non-fatal): {e.reason}")
        return False


# ── Internal linking ──────────────────────────────────────────────────────────

def update_older_descriptions(service, new_title: str, new_url: str, max_videos: int = 3) -> None:
    """
    Appends a 'New video' link to the descriptions of the last N older videos.
    Only adds the link if it's not already there (idempotent).
    """
    older = get_recent_videos(service, exclude_id="", max_results=max_videos + 1)
    link_line = f"\n🆕 New: {new_title} → {new_url}"

    for v in older[:max_videos]:
        try:
            # Fetch full snippet
            resp = service.videos().list(
                part="snippet", id=v["video_id"]
            ).execute()
            items = resp.get("items", [])
            if not items:
                continue
            snippet = items[0]["snippet"]
            current_desc = snippet.get("description", "")

            # Skip if already linked
            if new_url in current_desc:
                continue

            new_desc = current_desc + link_line
            snippet["description"] = new_desc[:5000]

            service.videos().update(
                part="snippet",
                body={"id": v["video_id"], "snippet": snippet},
            ).execute()
            print(f"[youtube] Updated description of '{v['title']}' with link to new video")
        except googleapiclient.errors.HttpError as e:
            print(f"[youtube] Description update failed for {v['video_id']} (non-fatal): {e.reason}")


def rename_channel(new_name):
    service = _get_authenticated_service()
    service.channels().update(
        part="snippet",
        body={"id": config.YOUTUBE_CHANNEL_ID, "snippet": {"title": new_name}},
    ).execute()
    print(f"[youtube] Channel renamed to '{new_name}'")
