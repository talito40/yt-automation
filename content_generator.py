"""
content_generator.py
SEO research + script generation.
Style: Mark Tilbury — numbered lists, shocking hooks, specific dollar amounts.
"""

import os
import json
import anthropic
from pytrends.request import TrendReq
import config

_client = None

def _get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


# ── SEO research ──────────────────────────────────────────────────────────────

def get_trending_keywords(niche: str) -> list[str]:
    """Returns top trending keywords for the niche via Google Trends."""
    try:
        pt = TrendReq(hl="en-US", tz=360)
        query = niche.split()[0]
        pt.build_payload([query], cat=0, timeframe="now 7-d", geo="US")
        related = pt.related_queries()
        keywords = []
        for val in related.values():
            if val and val.get("top") is not None:
                keywords += val["top"]["query"].tolist()[:5]
        return keywords[:10] if keywords else [niche]
    except Exception as e:
        print(f"[content] Trends error: {e}")
        return [niche]


def research_seo_topic(niche: str, trending_keywords: list[str]) -> dict:
    """Uses Claude to pick the best SEO topic from trending keywords."""
    kw_str = ", ".join(trending_keywords[:10])
    prompt = f"""You are a YouTube SEO expert specialising in {niche}.

Trending keywords right now: {kw_str}

Pick the SINGLE best video topic that:
- Has high search volume + low competition
- Fits the {niche} niche
- Works as a "how to make / save / invest money" style video
- Can be structured as a numbered list (5 tips, 7 ways, 3 mistakes, etc.)

Return JSON only:
{{
  "topic": "...",
  "search_volume": "high/medium",
  "competition": "low/medium",
  "reasoning": "one sentence"
}}"""

    msg = _get_client().messages.create(
        model="claude-haiku-4-5",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    text = msg.content[0].text.strip()
    try:
        return json.loads(text)
    except Exception:
        import re
        m = re.search(r"\{.*\}", text, re.DOTALL)
        return json.loads(m.group()) if m else {"topic": trending_keywords[0]}


def generate_video_package(topic: str, niche: str) -> dict:
    """
    Generates a full Mark Tilbury-style video package:
    - Catchy numbered-list title
    - 18-minute script broken into 8-10 scenes with hook
    - Chapters, playlist, hashtags
    """
    prompt = f"""You are a YouTube scriptwriter copying Mark Tilbury's exact style.

Topic: {topic}
Niche: {niche}

Mark Tilbury's formula:
- Title: Number + Specific Outcome (always include a $ amount or %) — e.g. "7 Ways to Make $1,000/Month", "5 Money Mistakes Costing You $10,000/Year", "The $500/Week Side Hustle Nobody Talks About"
- Hook (scene 1): Open with a SHOCKING STAT or BOLD CLAIM in first 10 seconds. No intro, no greeting. Start mid-sentence with urgency.
  Example: "Most people will never build wealth, and it's not because they don't work hard enough..."
- Structure: numbered sections (e.g. "Number 1:", "Number 2:", etc.)
- Each point: specific, actionable, include real dollar amounts, percentages, timeframes
- Tone: direct, conversational, no fluff, like talking to a friend who is a millionaire
- Length: 8 scenes that together form ~18 minutes of content (~2 min per scene)
- End with a strong CTA: "If this helped, subscribe — I post strategies like this every week"

Return VALID JSON only, no markdown, no extra text:
{{
  "title": "...",
  "description": "...(150 words, includes 5 hashtags like #personalfinance #moneytips at end)",
  "scenes": [
    {{
      "narration": "...(250-300 words, punchy, direct)",
      "visuals": "...(b-roll suggestion)"
    }}
  ],
  "chapters": [
    {{"time": "0:00", "title": "..."}},
    {{"time": "2:00", "title": "..."}}
  ],
  "playlist": "...(pick most relevant playlist from: {config.PLAYLISTS})",
  "tags": ["tag1", "tag2", "tag3", "tag4", "tag5", "tag6", "tag7", "tag8"]
}}"""

    msg = _get_client().messages.create(
        model="claude-haiku-4-5",
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
    )
    text = msg.content[0].text.strip()
    # strip markdown code fences if present
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    try:
        return json.loads(text)
    except Exception as e:
        print(f"[content] JSON parse error: {e}\nRaw: {text[:300]}")
        return {
            "title": f"7 Ways to Build Wealth with {topic}",
            "description": f"In this video we break down {topic}. #personalfinance #moneytips #investing #wealth #finance",
            "scenes": [{"narration": f"Today we are covering {topic}.", "visuals": "charts and graphs"}],
            "chapters": [{"time": "0:00", "title": "Introduction"}],
            "playlist": config.PLAYLISTS[0],
            "tags": [niche, topic, "money", "finance", "investing"],
        }


def generate_shorts_script(topic: str, niche: str, angle: str = "stat") -> dict:
    """
    Generates a 45-60 second Shorts script in Mark Tilbury hook style.
    angle: 'stat' | 'mistake' | 'secret'
    """
    angle_prompts = {
        "stat":    f"Start with a shocking financial stat about {topic}. Make it feel unbelievable but true.",
        "mistake": f"Open with 'The #1 mistake people make with {topic} is...' then flip it with the solution.",
        "secret":  f"Open with 'Nobody talks about this {topic} strategy...' — share one specific, actionable tip.",
    }
    angle_text = angle_prompts.get(angle, angle_prompts["stat"])

    prompt = f"""Write a 45-60 second YouTube Shorts script in Mark Tilbury's style.
Niche: {niche}
Topic: {topic}
Angle: {angle_text}

Rules:
- No greeting, start IMMEDIATELY with the hook
- Every sentence must add value — no filler
- End with "Follow for more" or "Save this for later"
- Include specific numbers/dollar amounts

Return JSON only:
{{
  "title": "...(max 60 chars, curiosity-gap style)",
  "script": "...(full word-for-word script, 120-150 words)",
  "hook": "...(first sentence only)"
}}"""

    msg = _get_client().messages.create(
        model="claude-haiku-4-5",
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )
    text = msg.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    try:
        return json.loads(text)
    except Exception:
        return {
            "title": f"{topic} tip you need to know",
            "script": f"Here is what you need to know about {topic}. Follow for more.",
            "hook": f"Here is what you need to know about {topic}.",
        }
