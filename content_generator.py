"""
content_generator.py
Uses Claude API to produce a full video package:
  - SEO-optimised title
  - Voiceover script (~900 words, 6-8 min video)
  - YouTube description with affiliate links
  - Tags list
"""

import json
import anthropic
import config

_client = None

def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


def generate_video_package(used_topics: list[str] | None = None) -> dict:
    """
    Returns a dict with keys:
        title, script, description, tags, topic
    """
    used_topics = used_topics or []
    avoid_block = ""
    if used_topics:
        avoid_block = f"\nAvoid these already-used topics:\n" + "\n".join(f"- {t}" for t in used_topics[-30:])

    niche_guidance = {
        "personal finance": "personal finance — money saving, investing, tax strategies, budgeting, building wealth",
        "AI tools and technology": "AI tools and technology — practical AI software reviews, productivity tools, ChatGPT tips, automation, new tech gadgets and apps",
    }.get(config.NICHE, config.NICHE)

    prompt = f"""You are a YouTube content strategist for a channel called "{config.CHANNEL_NAME}".
The channel niche is STRICTLY: {niche_guidance}
The audience is US-based adults aged 25-45.

IMPORTANT: Every video MUST be about the niche above. Do not drift into other topics.

Your job: produce ONE complete video package optimised for maximum watch-time and ad revenue.

Rules:
- Title: 60 chars max, strong curiosity hook, no clickbait lies, include a number or year when natural
- Scenes: split the full script into scenes of exactly 20-25 words each. For EACH scene provide:
    - "text": the spoken words for that scene (20-25 words, plain English, no markdown)
    - "keywords": 3 short visual keywords describing what stock footage should appear (e.g. ["person typing laptop", "office desk", "dollar bills"])
- Total scenes should cover ~900 words (about 36-40 scenes)
- Script must feel like a knowledgeable friend talking, structured as: Hook → 5-7 tip sections → CTA
- Description: 3 paragraphs — summary, timestamps placeholder, affiliate CTA
- Tags: 15 tags, mix of broad and long-tail
{avoid_block}

Respond ONLY with valid JSON in this exact shape:
{{
  "topic": "<one-line topic summary>",
  "title": "<YouTube title>",
  "scenes": [
    {{"text": "<20-25 words of script>", "keywords": ["keyword1", "keyword2", "keyword3"]}},
    ...
  ],
  "description": "<YouTube description>",
  "tags": ["tag1", "tag2", ...]
}}"""

    response = _get_client().messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()

    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    package = json.loads(raw)

    # Build a flat script string from scenes (used for logging)
    if "scenes" in package:
        package["script"] = " ".join(s["text"] for s in package["scenes"])

    # Append affiliate links to description
    affiliate_section = "\n\n── Recommended Tools ──\n"
    for name, url in config.AFFILIATE_LINKS.items():
        affiliate_section += f"{name}: {url}\n"
    package["description"] += affiliate_section

    return package


if __name__ == "__main__":
    pkg = generate_video_package()
    print("TITLE:", pkg["title"])
    print("TOPIC:", pkg["topic"])
    print("SCENES:", len(pkg.get("scenes", [])))
    if pkg.get("scenes"):
        print("SAMPLE SCENE:", pkg["scenes"][0])
    print("\nTAGS:", pkg["tags"])
