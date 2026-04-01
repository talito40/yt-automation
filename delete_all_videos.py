"""
delete_all_videos.py
Deletes all videos from both YouTube channels.
Usage: python delete_all_videos.py
"""

import os
import pickle
import time
import googleapiclient.discovery
import googleapiclient.errors
from google.auth.transport.requests import Request

SCOPES = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]


def _get_service(token_file):
    credentials = None
    if os.path.exists(token_file):
        with open(token_file, "rb") as f:
            credentials = pickle.load(f)

    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        else:
            raise RuntimeError(f"Token file {token_file} is missing or invalid. Re-run OAuth.")

    return googleapiclient.discovery.build("youtube", "v3", credentials=credentials)


def delete_all_videos(token_file, channel_label):
    print(f"\n[{channel_label}] Fetching videos...")
    service = _get_service(token_file)

    video_ids = []
    next_page = None

    while True:
        params = {
            "part": "id,snippet",
            "mine": True,
            "type": "video",
            "maxResults": 50,
        }
        if next_page:
            params["pageToken"] = next_page

        response = service.search().list(**params).execute()

        for item in response.get("items", []):
            vid_id = item["id"].get("videoId")
            title = item["snippet"]["title"]
            if vid_id:
                video_ids.append((vid_id, title))

        next_page = response.get("nextPageToken")
        if not next_page:
            break

    if not video_ids:
        print(f"[{channel_label}] No videos found.")
        return

    print(f"[{channel_label}] Found {len(video_ids)} video(s). Deleting...")

    for vid_id, title in video_ids:
        try:
            service.videos().delete(id=vid_id).execute()
            print(f"[{channel_label}] Deleted: {title} ({vid_id})")
            time.sleep(0.5)
        except googleapiclient.errors.HttpError as e:
            print(f"[{channel_label}] Failed to delete {vid_id}: {e}")

    print(f"[{channel_label}] Done. {len(video_ids)} video(s) deleted.")


if __name__ == "__main__":
    delete_all_videos("youtube_token_ch1.json", "Channel 1 - Smart Money Daily")
    delete_all_videos("youtube_token_ch2.json", "Channel 2 - AI Advantage Daily")
