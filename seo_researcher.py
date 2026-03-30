"""
seo_researcher.py
Finds high-opportunity topics by scoring YouTube search competition.
Picks the topic with the most search demand and lowest competition.
"""

import json
import os
import pickle

import googleapiclient.discovery
from google.auth.transport.requests import Request

import anthropic
import config


def _get_youtube():
    token_file = f"youtube_token_ch{config.CHANNEL}.json"
    if not os.path.exists(token_file):
        token_file = "youtube_token_ch1.json"

    credentials = None
    if os.path.exists(token_file):
        with open(token_file, "rb") as f:
            credentials = pickle.load(f)

    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())

    return googleapiclient.discovery.build("youtube", "v3", credentials=credentials)


def _competition_score(service, query: str) -> int:
    """Returns approximate number of competing videos for this query."""
    try:
        result = service.search().list(
            part="id",
            q=query,
            type="video",
            maxResults=1,
        ).execute()
        return result.get("pageInfo", {}).get("totalResults", 999999)
    except Exception:
        return 999999


def research_best_topic(used_topics: list[str]) -> str | None:
    """
    Generates 8 candidate topics with Claude, scores each against YouTube
    competition, and returns the best low-competition topic.
    Returns None on failure (caller falls back to letting Claude pick freely).
    """
    avoid = "\n".join(f"- {t}" for t in used_topics[-30:]) if used_topics else "(none)"

    try:
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            messages=[{"role": "user", "content": f"""Generate 8 specific YouTube video topic ideas for a channel about: {config.NICHE}
Audience: US adults aged 25-45.

Topics already covered — do NOT repeat these:
{avoid}

Rules:
- Each topic must be something people actively search for on YouTube
- Be specific and concrete (e.g. "How to pay off $40k debt in 18 months" not "debt tips")
- Mix evergreen and trending angles
- Each should work as both a long video AND a 60-second Short

Respond ONLY with a JSON array of exactly 8 strings:
["topic 1", "topic 2", ...]"""}],
        )

        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        candidates = json.loads(raw.strip())

    except Exception as e:
        print(f"[seo] Topic generation failed: {e}")
        return None

    # Score competition for each candidate
    try:
        service = _get_youtube()
        scored = []
        for topic in candidates:
            count = _competition_score(service, topic)
            scored.append((topic, count))
            print(f"[seo]   '{topic}' → {count:,} competing videos")

        scored.sort(key=lambda x: x[1])
        best = scored[0][0]
        print(f"[seo] Best topic: '{best}' ({scored[0][1]:,} competing videos)")
        return best

    except Exception as e:
        print(f"[seo] YouTube scoring failed ({e}), using first candidate")
        return candidates[0] if candidates else None
