"""
social_poster.py
Posts video announcements to social media after each upload.

Required env vars (all optional — feature is silently skipped if not set):
  TWITTER_API_KEY
  TWITTER_API_SECRET
  TWITTER_ACCESS_TOKEN
  TWITTER_ACCESS_TOKEN_SECRET
"""

import os


def post_to_twitter(title: str, url: str, tags: list[str]) -> bool:
    api_key      = os.environ.get("TWITTER_API_KEY", "")
    api_secret   = os.environ.get("TWITTER_API_SECRET", "")
    token        = os.environ.get("TWITTER_ACCESS_TOKEN", "")
    token_secret = os.environ.get("TWITTER_ACCESS_TOKEN_SECRET", "")

    if not all([api_key, api_secret, token, token_secret]):
        print("[social] Twitter credentials not configured — skipping.")
        return False

    try:
        import tweepy

        client = tweepy.Client(
            consumer_key=api_key,
            consumer_secret=api_secret,
            access_token=token,
            access_token_secret=token_secret,
        )

        hashtags = " ".join(f"#{t.replace(' ', '').replace('-', '')}" for t in tags[:5])
        tweet = f"{title}\n\n{url}\n\n{hashtags}"[:280]

        client.create_tweet(text=tweet)
        print(f"[social] Posted to Twitter/X: {title}")
        return True

    except Exception as e:
        print(f"[social] Twitter post failed: {e}")
        return False
