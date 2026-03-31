"""
prompt_improver.py
Daily prompt evolution engine — combines yesterday's performance data with
active research into what's currently working on YouTube to evolve the
content strategy every single day.

Each iteration:
  1. Researches trending angles and low-competition keywords in the niche
  2. Rotates title formula and narrative structure to avoid stagnation
  3. Critiques recent output and adjusts voice/visual/hook guidance
  4. Saves the updated config for content_generator.py to inject at runtime
"""

import json
import os
from datetime import datetime, timezone

import anthropic
import config

CONFIG_FILE = f"prompt_config_ch{config.CHANNEL}.json"
TOPICS_FILE = f"used_topics_ch{config.CHANNEL}.json"
LOG_FILE    = f"pipeline_ch{config.CHANNEL}.log"

# Proven title formulas — rotated daily to prevent stagnation
TITLE_FORMULAS = [
    "Number + Curiosity Gap (e.g. '7 [Niche] Mistakes Nobody Talks About')",
    "Contradiction/Pattern Interrupt (e.g. 'Stop Using [X]. Do This Instead.')",
    "Personal Transformation + Specific Numbers (e.g. 'How I [Did X] in [Timeframe]')",
    "Stacked: Number + Stakes (e.g. '5 [Niche] Traps Destroying Your [Goal] Right Now')",
    "Authority Transfer + Bold Claim (e.g. '[Expert/Event] Says [Claim] — What It Means for You')",
    "Regret/Wish Structure (e.g. '[N] Things I Wish I Knew Before [Common Experience]')",
    "Stacked: Contradiction + Curiosity Gap (e.g. 'The [Niche] Advice Everyone Follows That\'s Actually Wrong')",
    "Year + Urgency (e.g. 'The Only [Niche] Strategy That Works in 2026')",
]

# Narrative structures — rotated to avoid formula fatigue
STRUCTURES = [
    "REVERSE ENGINEERING",
    "MICRO-LOOP",
    "MYTH-BUSTER",
    "REVERSE ENGINEERING",  # weighted double — highest retention data
    "MICRO-LOOP",
]

_DEFAULTS = {
    "version": 1,
    "last_improved": None,
    "current_focus": "Establish the character voice strongly. Prioritize counterintuitive hooks.",
    "title_formula": TITLE_FORMULAS[0],
    "structure": STRUCTURES[0],
    "target_keywords": [],
    "trending_angles": [],
    "extra_hook_techniques": [],
    "extra_voice_notes": "",
    "extra_visual_notes": "",
    "forbidden_patterns": [],
    "improvement_log": [],
}


def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            data = json.load(f)
        for k, v in _DEFAULTS.items():
            data.setdefault(k, v)
        return data
    return dict(_DEFAULTS)


def _save_config(cfg: dict) -> None:
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)


def _recent_topics(n: int = 15) -> list[str]:
    if not os.path.exists(TOPICS_FILE):
        return []
    with open(TOPICS_FILE) as f:
        topics = json.load(f)
    return topics[-n:]


def _tail_log(n: int = 50) -> str:
    if not os.path.exists(LOG_FILE):
        return "(no log yet)"
    with open(LOG_FILE) as f:
        lines = f.readlines()
    return "".join(lines[-n:]).strip()


def _rotate_formula(current: str) -> str:
    try:
        idx = TITLE_FORMULAS.index(current)
        return TITLE_FORMULAS[(idx + 1) % len(TITLE_FORMULAS)]
    except ValueError:
        return TITLE_FORMULAS[0]


def _rotate_structure(current: str) -> str:
    try:
        idx = STRUCTURES.index(current)
        return STRUCTURES[(idx + 1) % len(STRUCTURES)]
    except ValueError:
        return STRUCTURES[0]


def _research_trends(client: anthropic.Anthropic, recent_topics: list[str]) -> dict:
    """
    Uses Claude to research what's currently working in the niche:
    trending angles, low-competition keywords, and fresh hook techniques.
    Returns a dict with research findings.
    """
    avoid = "\n".join(f"- {t}" for t in recent_topics) if recent_topics else "(none yet)"

    niche_context = {
        "personal finance": (
            "personal finance YouTube. High-CPM niche ($12-22 CPM). "
            "Top performers: Minority Mindset, Graham Stephan, Andrei Jikh. "
            "Trending content types: contrarian takes on market news, specific debt payoff stories, "
            "tax strategy reveals, portfolio transparency, 'hidden fee' exposés."
        ),
        "AI tools and technology": (
            "AI tools and technology YouTube. High-CPM niche ($15-22 CPM). "
            "Top performers: Matt Wolfe, Fireship, Marques Brownlee. "
            "Trending content types: new model comparisons, 'I replaced X with AI' demos, "
            "workflow automation reveals, AI income stories, underrated tool discoveries."
        ),
    }.get(config.NICHE, config.NICHE)

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=800,
        messages=[{"role": "user", "content": f"""You are a YouTube growth strategist researching what's working RIGHT NOW in {niche_context}

Topics this channel has already covered (don't suggest repeats):
{avoid}

Your task — research and return:

1. TRENDING ANGLES (3 fresh angles in this niche that haven't been oversaturated yet — things people are searching for or talking about right now in 2026)

2. TARGET KEYWORDS (3 specific search keywords with 1,000-5,000 monthly volume, low competition — suitable for a channel under 10K subscribers. Be very specific, not generic.)

3. HOOK TECHNIQUES (2 fresh hook approaches that fit this niche and haven't been overused — based on what's currently retaining viewers in {config.NICHE} content)

4. CURRENT FOCUS (one specific directive for tomorrow's video that addresses the biggest opportunity in this niche right now)

Think about: seasonal relevance (current month is {datetime.now().strftime('%B %Y')}), recent news or events in the niche, underserved search intent, content gaps.

Respond ONLY with valid JSON:
{{
  "trending_angles": ["angle 1", "angle 2", "angle 3"],
  "target_keywords": ["keyword 1", "keyword 2", "keyword 3"],
  "extra_hook_techniques": ["hook technique 1", "hook technique 2"],
  "current_focus": "<single directive for tomorrow's video>"
}}"""}],
    )

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


def _critique_recent_output(client: anthropic.Anthropic, cfg: dict, log_tail: str, recent_topics: list[str]) -> dict:
    """
    Critiques the recent pipeline output and suggests specific improvements
    to voice, visual direction, and patterns to avoid.
    """
    config_summary = json.dumps({
        k: v for k, v in cfg.items()
        if k not in ("improvement_log", "trending_angles", "target_keywords")
    }, indent=2)

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=600,
        messages=[{"role": "user", "content": f"""You are a YouTube retention expert reviewing an AI-narrated channel's recent output.

CHANNEL: {config.CHANNEL_NAME} | NICHE: {config.NICHE}
CHARACTER: {"ARIA (AI financial analyst)" if "finance" in config.NICHE else "NEXUS (AI tech guide)"}

RECENT PIPELINE LOG:
{log_tail}

RECENT TOPICS COVERED:
{chr(10).join(f"- {t}" for t in recent_topics) if recent_topics else "(none yet)"}

CURRENT PROMPT CONFIG:
{config_summary}

CRITICAL CONTEXT (YouTube 2025-2026 data):
- 55% of viewers are lost by the 60-second mark — the hook is everything
- Videos perceived as heavily AI-generated (robotic, templated) show 70% lower retention
- Monotonous AI narration causes 35% drop-off within 45 seconds
- The January 2026 enforcement wave targeted channels that were template-swapping with no genuine creative layer
- Solutions: strong character personality, genuine opinions, surprising takes, emotional oscillation

Your job: critique what might be getting stale or weak, and suggest specific fixes for:
- voice_notes: is the character voice strong enough or drifting generic?
- visual_notes: are the keywords producing interesting footage or getting repetitive?
- forbidden_patterns: what specific patterns should be banned to prevent formula fatigue?
- change_summary: what's the single most important improvement for tomorrow?

Respond ONLY with valid JSON:
{{
  "extra_voice_notes": "<1-2 sentences of specific voice direction>",
  "extra_visual_notes": "<1-2 sentences of specific visual direction>",
  "forbidden_patterns": ["<specific pattern to ban>", ...],
  "change_summary": "<what changed and why, 1-2 sentences>"
}}"""}],
    )

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


def improve() -> dict:
    """
    Run one full improvement iteration:
      1. Research trending angles + low-competition keywords
      2. Critique recent output for voice/visual/pattern issues
      3. Rotate title formula and narrative structure
      4. Save updated config
    """
    cfg = load_config()
    recent_topics = _recent_topics()
    log_tail = _tail_log()
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    print("[improver] Researching current trends in niche...")
    try:
        research = _research_trends(client, recent_topics)
    except Exception as e:
        print(f"[improver] Research step failed: {e}")
        research = {}

    print("[improver] Critiquing recent output...")
    try:
        critique = _critique_recent_output(client, cfg, log_tail, recent_topics)
    except Exception as e:
        print(f"[improver] Critique step failed: {e}")
        critique = {}

    # Rotate formula and structure
    new_formula   = _rotate_formula(cfg.get("title_formula", ""))
    new_structure = _rotate_structure(cfg.get("structure", ""))

    # Apply all updates
    cfg["title_formula"]        = new_formula
    cfg["structure"]            = new_structure
    cfg["trending_angles"]      = research.get("trending_angles", cfg.get("trending_angles", []))
    cfg["target_keywords"]      = research.get("target_keywords", cfg.get("target_keywords", []))
    cfg["extra_hook_techniques"]= research.get("extra_hook_techniques", cfg.get("extra_hook_techniques", []))
    cfg["current_focus"]        = research.get("current_focus", cfg.get("current_focus", ""))
    cfg["extra_voice_notes"]    = critique.get("extra_voice_notes", cfg.get("extra_voice_notes", ""))
    cfg["extra_visual_notes"]   = critique.get("extra_visual_notes", cfg.get("extra_visual_notes", ""))
    cfg["forbidden_patterns"]   = critique.get("forbidden_patterns", cfg.get("forbidden_patterns", []))[:5]
    cfg["version"]             += 1
    cfg["last_improved"]        = datetime.now(timezone.utc).isoformat()

    change_summary = critique.get("change_summary", f"Rotated to {new_formula} formula with {new_structure} structure.")
    cfg["improvement_log"].append({
        "version":   cfg["version"],
        "date":      cfg["last_improved"],
        "formula":   new_formula,
        "structure": new_structure,
        "keywords":  cfg["target_keywords"],
        "summary":   change_summary,
    })
    cfg["improvement_log"] = cfg["improvement_log"][-30:]

    _save_config(cfg)
    print(f"[improver] v{cfg['version']} — Formula: {new_formula[:40]}... | Structure: {new_structure}")
    print(f"[improver] Keywords: {cfg['target_keywords']}")
    print(f"[improver] {change_summary}")
    return cfg


if __name__ == "__main__":
    result = improve()
    print(json.dumps({k: v for k, v in result.items() if k != "improvement_log"}, indent=2))
