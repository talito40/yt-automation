"""
youtube_uploader.py
Handles all YouTube Data API v3 operations:
  - OAuth authentication (first run opens browser, saves token for all future runs)
  - Upload video with full metadata
  - Rename channel (one-time call)
"""

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

CATEGORY_ID = "27"   # Education
PRIVACY     = "public"


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


def upload_video(video_path: str, title: str, description: str, tags: list[str]) -> str:
    """
    Uploads the MP4 at `video_path` to YouTube.
    Returns the video URL.
    """
    service = _get_authenticated_service()

    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": tags[:500],
            "categoryId": CATEGORY_ID,
            "defaultLanguage": "en",
            "defaultAudioLanguage": "en",
        },
        "status": {
            "privacyStatus": PRIVACY,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = googleapiclient.http.MediaFileUpload(
        video_path,
        mimetype="video/mp4",
        resumable=True,
        chunksize=1024 * 1024 * 10,  # 10 MB chunks
    )

    request = service.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    retry = 0
    while response is None:
        try:
            print(f"[youtube] Uploading... (attempt {retry + 1})")
            status, response = request.next_chunk()
            if status:
                pct = int(status.progress() * 100)
                print(f"[youtube] Upload progress: {pct}%")
        except googleapiclient.errors.HttpError as e:
            if e.resp.status in (500, 502, 503, 504) and retry < config.MAX_RETRIES:
                retry += 1
                time.sleep(5 * retry)
            else:
                raise

    video_id = response["id"]
    url = f"https://www.youtube.com/watch?v={video_id}"
    print(f"[youtube] Upload complete → {url}")
    return url


def rename_channel(new_name: str) -> None:
    """Renames the YouTube channel. Call once during initial setup."""
    service = _get_authenticated_service()
    service.channels().update(
        part="snippet",
        body={
            "id": config.YOUTUBE_CHANNEL_ID,
            "snippet": {"title": new_name},
        },
    ).execute()
    print(f"[youtube] Channel renamed to '{new_name}'")


if __name__ == "__main__":
    # Run this once to rename the channel
    rename_channel(config.CHANNEL_NAME)
