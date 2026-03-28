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

    character_guidance = {
        "personal finance": (
            "NARRATOR CHARACTER: \"ARIA\" — an AI financial analyst with a sleek, futuristic personality. "
            "She speaks with calm authority, occasionally drops a dry witty remark, and makes complex money "
            "concepts feel like insider secrets being revealed. She addresses the viewer directly, like she's "
            "hacked into their financial future and is showing them what she sees."
        ),
        "AI tools and technology": (
            "NARRATOR CHARACTER: \"NEXUS\" — a self-aware AI guide who lives inside the internet and has "
            "tested every tool so you don't have to. He's enthusiastic, slightly sarcastic about overhyped "
            "tech, and genuinely excited about the stuff that actually works. He speaks like he's giving you "
            "a backstage tour of the future."
        ),
    }.get(config.NICHE, (
        "NARRATOR CHARACTER: An AI guide with a sharp, engaging personality — witty, direct, and makes the "
        "viewer feel like they're getting insider access to knowledge most people don't have."
    ))

    visual_style_guidance = {
        "personal finance": (
            "VISUAL THEME: Futuristic finance aesthetic. Keywords should pull toward: holographic charts, "
            "glowing data dashboards, neon-lit cityscapes, animated money flows, sleek dark-mode UI screens, "
            "AI brain visualizations, digital neural networks, cinematic slow-motion wealth imagery. "
            "Mix in real-world human moments (person reacting with relief/excitement) to keep it relatable."
        ),
        "AI tools and technology": (
            "VISUAL THEME: High-tech digital world aesthetic. Keywords should pull toward: glowing circuit "
            "boards, animated code streams, robot hands interacting with holograms, neon sci-fi environments, "
            "split-screen comparisons, futuristic UI overlays, data visualization animations, tech lab "
            "environments. Occasionally ground it with real person reactions to keep human connection."
        ),
    }.get(config.NICHE, (
        "VISUAL THEME: Sleek futuristic aesthetic. Keywords should pull toward animated, AI-generated, "
        "holographic, and cinematic visuals. Mix cool tech imagery with relatable human moments."
    ))

    prompt = f"""You are a creative director and YouTube content strategist for "{config.CHANNEL_NAME}".
The channel niche is STRICTLY: {niche_guidance}
The audience is US-based adults aged 25-45 who are curious, ambitious, and love content that feels ahead of the curve.

IMPORTANT: Every video MUST stay within the niche above. Do not drift into other topics.

═══════════════════════════════════════
CHARACTER & VOICE
═══════════════════════════════════════
{character_guidance}

The narration must sound like this character throughout — not a generic voiceover. Use "I", rhetorical questions,
direct address ("you", "your"), short punchy lines mixed with fuller explanations, and at least 2 moments of
wit or personality that make the viewer smile or lean in.

═══════════════════════════════════════
VISUAL DIRECTION
═══════════════════════════════════════
{visual_style_guidance}

Keywords drive stock footage selection. Make them SPECIFIC and ACTION/EMOTION-based:
✓ GOOD: "glowing holographic money chart rising", "person gasping at phone screen", "neon data stream flowing"
✗ BAD:  "dollar bills", "happy person", "office"

Match keyword mood to scene mood — tension keywords on problem scenes, triumphant/glowing keywords on win scenes.

═══════════════════════════════════════
NARRATIVE STRUCTURE
═══════════════════════════════════════
Choose ONE of these structures (pick whichever fits the topic best):

A) MYTH-BUSTER: Open with a belief 80% of viewers hold → systematically dismantle it → reveal the truth
B) BEFORE/AFTER: Paint the painful "before" scenario vividly → guide through the transformation → show the after
C) INSIDER ACCESS: Frame the video as classified/hidden knowledge the viewer is lucky to be getting right now

Opening hook rules (first 3 scenes):
- Scene 1: A counterintuitive statement OR shocking stat OR direct challenge to a common belief (NOT a question)
- Scene 2: Agitate — make the viewer feel the cost of not knowing this
- Scene 3: Promise — tell them exactly what they're about to learn, make it feel unmissable

Pacing rules:
- Every 6th scene: insert a short punchy scene (10-15 words max) — a single bold statement or reveal
- Final 4 scenes: build urgency, then deliver the CTA as a natural conclusion, not a sales pitch

═══════════════════════════════════════
PRODUCTION SPECS
═══════════════════════════════════════
- Title: 60 chars max, no clickbait lies, include a number or power word, must pass the "would I click this at midnight?" test
- Scenes: 20-25 words each (except designated short punchy scenes), ~36-40 scenes total (~900 words)
- Each scene needs 3 specific visual keywords (action + emotion + style, not generic nouns)
- Description: 3 paragraphs — hook summary, timestamps placeholder, affiliate CTA with personality
- Tags: 15 tags, mix broad and long-tail
{avoid_block}

Before writing the title, silently ask: "Does this make someone stop scrolling?" If no, rewrite it.

Respond ONLY with valid JSON in this exact shape:
{{
  "topic": "<one-line topic summary>",
  "title": "<YouTube title>",
  "scenes": [
    {{"text": "<script words for this scene>", "keywords": ["specific visual 1", "specific visual 2", "specific visual 3"]}},
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
