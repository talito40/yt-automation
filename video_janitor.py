"""
video_janitor.py
Deletes underperforming videos: published more than 30 days ago with fewer
than 10 views. Runs daily after the pipeline to keep the channel clean.

YouTube API flow:
  1. Get uploads playlist ID from the channel
  2. Page through all videos in the playlist
  3. Filter: published > 30 days ago AND views < MIN_VIEWS
  4. Delete each qualifying video
  5. Send Telegram summary
"""

import os
import pickle
from datetime import datetime, timezone, timedelta

import googleapiclient.discovery
import googleapiclient.errors
from google.auth.transport.requests import Request

import config
import notifier

MIN_VIEWS    = 10
MIN_AGE_DAYS = 30


def _get_youtube():
    token_file = f"youtube_token_ch{config.CHANNEL}.json"
    credentials = None
    if os.path.exists(token_file):
        with open(token_file, "rb") as f:
            credentials = pickle.load(f)
    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
    return googleapiclient.discovery.build("youtube", "v3", credentials=credentials)


def _get_uploads_playlist_id(service) -> str:
    resp = service.channels().list(part="contentDetails", mine=True).execute()
    return resp["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]


def _get_all_video_ids(service, playlist_id: str) -> list[str]:
    video_ids = []
    page_token = None
    while True:
        resp = service.playlistItems().list(
            part="contentDetails",
            playlistId=playlist_id,
            maxResults=50,
            pageToken=page_token,
        ).execute()
        for item in resp.get("items", []):
            video_ids.append(item["contentDetails"]["videoId"])
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return video_ids


def _get_video_stats(service, video_ids: list[str]) -> list[dict]:
    """Fetch statistics and snippet for up to 50 videos per call."""
    results = []
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i + 50]
        resp = service.videos().list(
            part="statistics,snippet",
            id=",".join(batch),
        ).execute()
        for item in resp.get("items", []):
            published_at = datetime.fromisoformat(
                item["snippet"]["publishedAt"].replace("Z", "+00:00")
            )
            views = int(item["statistics"].get("viewCount", 0))
            results.append({
                "id":           item["id"],
                "title":        item["snippet"]["title"],
                "published_at": published_at,
                "views":        views,
            })
    return results


def run_cleanup() -> dict:
    """
    Scan the channel, delete videos older than MIN_AGE_DAYS with fewer than
    MIN_VIEWS views. Returns a summary dict.
    """
    service     = _get_youtube()
    playlist_id = _get_uploads_playlist_id(service)
    video_ids   = _get_all_video_ids(service, playlist_id)

    if not video_ids:
        print("[janitor] No videos found on channel.")
        return {"checked": 0, "deleted": [], "skipped": []}

    videos   = _get_video_stats(service, video_ids)
    cutoff   = datetime.now(timezone.utc) - timedelta(days=MIN_AGE_DAYS)
    deleted  = []
    skipped  = []

    for v in videos:
        age_days = (datetime.now(timezone.utc) - v["published_at"]).days
        if v["published_at"] < cutoff and v["views"] < MIN_VIEWS:
            try:
                service.videos().delete(id=v["id"]).execute()
                deleted.append(v)
                print(f"[janitor] DELETED '{v['title']}' — {v['views']} views, {age_days}d old")
            except googleapiclient.errors.HttpError as e:
                print(f"[janitor] Failed to delete '{v['title']}': {e}")
        else:
            skipped.append(v)
            print(f"[janitor] KEPT '{v['title']}' — {v['views']} views, {age_days}d old")

    summary = {"checked": len(videos), "deleted": deleted, "skipped": skipped}

    if deleted:
        lines = "\n".join(f"• {v['title']} ({v['views']} views, {(datetime.now(timezone.utc) - v['published_at']).days}d old)" for v in deleted)
        notifier._send(
            f"🗑️ Janitor ran on {config.CHANNEL_NAME}\n\n"
            f"Deleted {len(deleted)} video(s) with <{MIN_VIEWS} views after {MIN_AGE_DAYS} days:\n"
            f"{lines}\n\n"
            f"Checked {len(videos)} total videos."
        )
    else:
        print(f"[janitor] No videos to delete. Checked {len(videos)} videos.")
        notifier._send(
            f"✅ Janitor ran on {config.CHANNEL_NAME}\n\n"
            f"No videos deleted — all {len(videos)} videos are either under {MIN_AGE_DAYS} days old or have {MIN_VIEWS}+ views."
        )

    return summary
