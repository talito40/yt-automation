"""
content_generator.py
Uses Claude API to produce a full video package:
  - SEO-optimised title (proven formula, 55-60 chars)
  - Voiceover script (~900 words, 8-12 min video)
  - YouTube description with affiliate links and chapters
  - Tags list
  - Shorts script (20-40 sec, loop-closing structure)
"""

import json
import anthropic
import config
import prompt_improver

_client = None

def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


def generate_video_package(used_topics: list[str] | None = None, forced_topic: str | None = None) -> dict:
    """
    Returns a dict with keys: title, script, description, tags, topic, scenes
    """
    used_topics = used_topics or []
    avoid_block = ""
    if used_topics:
        avoid_block = "\nAvoid these already-used topics:\n" + "\n".join(f"- {t}" for t in used_topics[-30:])
    if forced_topic:
        avoid_block += f"\n\nFOCUS THIS VIDEO ON: {forced_topic}"

    niche_guidance = {
        "personal finance": "personal finance — money saving, investing, tax strategies, budgeting, building wealth",
        "AI tools and technology": "AI tools and technology — practical AI software reviews, productivity tools, ChatGPT tips, automation, new tech gadgets and apps",
    }.get(config.NICHE, config.NICHE)

    character_guidance = {
        "personal finance": (
            "NARRATOR CHARACTER: \"ARIA\" — an AI financial analyst with a sleek, futuristic personality. "
            "She speaks with calm authority, drops dry witty remarks, and makes complex money concepts feel "
            "like insider secrets being revealed. She addresses the viewer directly, as if she's hacked into "
            "their financial future and is showing them what she sees. She has opinions. She uses \"I\" often. "
            "She occasionally says something that makes you stop and think."
        ),
        "AI tools and technology": (
            "NARRATOR CHARACTER: \"NEXUS\" — a self-aware AI guide who lives inside the internet and has "
            "tested every tool so you don't have to. He's enthusiastic, slightly sarcastic about overhyped "
            "tech, and genuinely excited about the stuff that actually works. He speaks like he's giving you "
            "a backstage tour of the future. He has strong opinions on what's overrated vs. underrated."
        ),
    }.get(config.NICHE, (
        "NARRATOR CHARACTER: An AI guide with sharp opinions and genuine personality — witty, direct, "
        "and makes the viewer feel like they're getting insider access most people don't have."
    ))

    visual_style_guidance = {
        "personal finance": (
            "VISUAL THEME: Futuristic finance aesthetic. Keywords must be action+emotion+style specific:\n"
            "✓ 'person gasping at rising portfolio chart', 'glowing holographic debt counter dropping', "
            "'slow-motion gold coins falling through neon light'\n"
            "✗ 'dollar bills', 'business meeting', 'calculator'\n"
            "Match mood: tension visuals on problem scenes, triumphant/glowing visuals on win scenes."
        ),
        "AI tools and technology": (
            "VISUAL THEME: High-tech digital world aesthetic. Keywords must be action+emotion+style specific:\n"
            "✓ 'robot hand typing on glowing keyboard', 'person jaw-dropping at holographic AI interface', "
            "'neon data stream exploding into visualization'\n"
            "✗ 'laptop', 'coding', 'tech person'\n"
            "Match mood: skeptical visuals on hype scenes, awe visuals on breakthrough scenes."
        ),
    }.get(config.NICHE, (
        "VISUAL THEME: Sleek futuristic aesthetic. Keywords must be action+emotion+style specific — "
        "never generic nouns. Match visual mood to scene emotional tone."
    ))

    # Load daily-evolved prompt config
    pcfg = prompt_improver.load_config()
    title_formula   = pcfg.get("title_formula", "Number + Curiosity Gap")
    structure       = pcfg.get("structure", "REVERSE ENGINEERING")
    target_keywords = pcfg.get("target_keywords", [])
    trending_angles = pcfg.get("trending_angles", [])

    evolved_blocks = ""
    if pcfg.get("current_focus"):
        evolved_blocks += f"\nTODAY'S FOCUS: {pcfg['current_focus']}\n"
    if pcfg.get("extra_hook_techniques"):
        evolved_blocks += "\nHOOK TECHNIQUES TO USE:\n" + "\n".join(f"- {t}" for t in pcfg["extra_hook_techniques"]) + "\n"
    if pcfg.get("extra_voice_notes"):
        evolved_blocks += f"\nVOICE DIRECTION: {pcfg['extra_voice_notes']}\n"
    if pcfg.get("extra_visual_notes"):
        evolved_blocks += f"\nVISUAL DIRECTION UPDATE: {pcfg['extra_visual_notes']}\n"
    if pcfg.get("forbidden_patterns"):
        evolved_blocks += "\nFORBIDDEN (never use these):\n" + "\n".join(f"- {p}" for p in pcfg["forbidden_patterns"]) + "\n"
    if target_keywords:
        evolved_blocks += f"\nSEO TARGET KEYWORDS (weave these naturally into scenes 1-3): {', '.join(target_keywords)}\n"
    if trending_angles:
        evolved_blocks += "\nTRENDING ANGLES IN NICHE RIGHT NOW (consider using one):\n" + "\n".join(f"- {a}" for a in trending_angles) + "\n"

    prompt = f"""You are a creative director for "{config.CHANNEL_NAME}", a YouTube channel about {niche_guidance}.
Audience: US adults 25-45, curious and ambitious.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CHARACTER & VOICE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{character_guidance}

Voice rules:
- Never start with "Hey guys", "Welcome back", or any intro greeting — this kills retention immediately
- Use "I", "you", "your" constantly. This is a conversation, not a lecture.
- Include at least 2 moments of genuine wit or a surprising opinion that makes the viewer stop and think
- Vary sentence length aggressively: one short punchy line, then a fuller explanation, then another short hit

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VISUAL DIRECTION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{visual_style_guidance}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TITLE FORMULA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Use this proven formula: {title_formula}

All titles must follow these rules (data-backed):
- 55-60 characters max (mobile truncation point)
- 7-10 words (statistical CTR sweet spot)
- Front-load the emotional hook or keyword in the first 4 words
- STACK two formulas when possible — stacked titles outperform single-formula by 15-25%
- No clickbait lies. The title must accurately represent what the video delivers.
- Self-check: "Would I stop scrolling at 1am for this?" If no, rewrite.

Niche-proven title patterns to draw from:
- "The REAL Cost of [X] Nobody Talks About"
- "[Number] [Niche] Mistakes Killing Your [Goal] (Fix These Now)"
- "I [Did Specific Bold Thing] for [Timeframe]. Here's What Happened."
- "Stop [Common Behavior]. Do This Instead."
- "[Authority] Just Said [Bold Claim] — What It Means for You"
- "How to [Achieve Goal] Without [Common Objection]"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NARRATIVE STRUCTURE: {structure}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
REVERSE ENGINEERING: Open by stating the RESULT or OUTCOME first (with proof/numbers). Then walk backward through exactly how. Eliminates the need for viewer trust — they see the payoff immediately and stay to learn the path.

MICRO-LOOP: Each section ends with a curiosity gap that forces the viewer into the next section. Label each gap with [CURIOSITY GAP] in your planning. "Before I show you the final strategy, here's why 90% of people fail at the next step..."

MYTH-BUSTER: State a belief 80% of viewers hold in scene 1. Spend the video systematically dismantling it. Reveal the truth in the final third.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RETENTION ENGINEERING (follow precisely — these are data-backed timing rules)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Scene 1 (0-5 sec): COLD OPEN. No greeting. Start mid-claim or mid-result. A shocking stat, the outcome, or a bold contrarian statement. This is the make-or-break moment — 33% of viewers leave in the first 30 seconds.

Scene 2 (5-15 sec): AGITATE. Make the viewer feel the exact cost of not knowing what you're about to share.

Scene 3 (15-25 sec): PROMISE. Tell them precisely what they'll learn. Make it feel unmissable.

Scene 4-5 (~25-35 sec): PATTERN INTERRUPT. One scene of 10-12 words — a bold single statement, a surprising fact, or a tonal shift. This is the "mini wake-up call" that stops the natural attention dip at 30 seconds.

Every 6th scene: SHORT PUNCHY SCENE (10-15 words max) — a reveal, bold statement, or mini-cliffhanger. These act as retention anchors throughout.

Scenes 20-22 (~55-65% of video): MID-ROLL RE-ENGAGEMENT HOOK. Remind the viewer the best part is still coming. "I saved the most counterintuitive strategy for the end — stay with me."

Final 4 scenes: URGENCY BUILD → CTA. Build toward the conclusion naturally, then deliver a CTA that feels like a logical next step, not a sales pitch.

PRIMARY KEYWORD: Speak the primary search keyword naturally within scenes 1-3. YouTube indexes spoken content.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PRODUCTION SPECS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Scenes: 20-25 words each (except pattern interrupt scenes: 10-15 words), ~36-40 scenes total (~900 words)
- Each scene: 3 visual keywords (action + emotion + style — never generic nouns)
- Description: 200-250 words — hook summary paragraph, chapter timestamps placeholder, affiliate CTA with personality
- Tags: 12-15 tags — first tag = exact primary keyword, then variations, then related long-tail terms
{avoid_block}

{evolved_blocks}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Respond ONLY with valid JSON:
{{
  "topic": "<one-line topic summary>",
  "title": "<YouTube title>",
  "scenes": [
    {{"text": "<scene script>", "keywords": ["action+emotion visual 1", "action+emotion visual 2", "action+emotion visual 3"]}},
    ...
  ],
  "description": "<200-250 word YouTube description with chapters>",
  "tags": ["primary keyword", "variation 1", ...]
}}"""

    response = _get_client().messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    package = json.loads(raw)

    if "scenes" in package:
        package["script"] = " ".join(s["text"] for s in package["scenes"])

    affiliate_section = "\n\n── Recommended Tools ──\n"
    for name, url in config.AFFILIATE_LINKS.items():
        affiliate_section += f"{name}: {url}\n"
    package["description"] += affiliate_section

    return package


def generate_shorts_script(full_package: dict) -> list[dict]:
    """
    Generates a 20-40 second Short optimised for completion rate and replays.
    Uses a loop-closing structure: final line callbacks to first line's hook word,
    triggering compulsive replays which count as extra views since March 2025.
    """
    client = _get_client()
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        messages=[{"role": "user", "content": f"""Create a YouTube Short (20-40 seconds) from this video.

Title: {full_package['title']}
Topic: {full_package['topic']}
Key insight (first 200 words): {full_package['script'][:200]}

STRUCTURE (follow precisely):
- 4-5 scenes, 15-20 words each (~80 words total = ~25 seconds)
- Scene 1: HOOK — explosive 5-8 word statement that stops the scroll. Pick ONE shocking word (e.g. "broke", "wrong", "secret") — this is your CALLBACK WORD.
- Scenes 2-3: Single most valuable insight from the full video, punchy and fast
- Scene 4: The result or proof statement
- Scene 5: CALLBACK — end with a phrase that echoes the CALLBACK WORD from scene 1. This creates a loop that triggers replays. Example: if scene 1 said "Most investors are broke..." — end with "...don't be one of them."

VOICE: Fast, punchy, zero patience. Every word earns its place.
KEYWORDS: 3 vertical-video-friendly keywords per scene (close-ups, reaction shots, text-overlay style)

Respond ONLY with valid JSON:
{{"scenes": [{{"text": "...", "keywords": ["...", "...", "..."]}}]}}"""}],
    )

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip()).get("scenes", [])


if __name__ == "__main__":
    pkg = generate_video_package()
    print("TITLE:", pkg["title"])
    print("TOPIC:", pkg["topic"])
    print("SCENES:", len(pkg.get("scenes", [])))
    if pkg.get("scenes"):
        print("SAMPLE SCENE:", pkg["scenes"][0])
    print("\nTAGS:", pkg["tags"])
