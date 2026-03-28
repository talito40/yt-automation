"""
prompt_improver.py
Uses Claude to critique yesterday's output and evolve the prompt config daily.

The "prompt config" is a JSON file (prompt_config_ch{N}.json) that stores
the dynamic, improvable parts of the content generation prompt. Every day,
before the pipeline runs, this module:
  1. Reads the current config
  2. Reads recent topics + pipeline log for context
  3. Asks Claude what should change and why
  4. Saves the updated config

content_generator.py then injects the config into the prompt at runtime.
"""

import json
import os
from datetime import datetime, timezone

import anthropic
import config

CONFIG_FILE = f"prompt_config_ch{config.CHANNEL}.json"
TOPICS_FILE = f"used_topics_ch{config.CHANNEL}.json"
LOG_FILE    = f"pipeline_ch{config.CHANNEL}.log"

_DEFAULTS = {
    "version": 1,
    "last_improved": None,
    "current_focus": "Establish the character voice strongly. Prioritize counterintuitive hooks.",
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
        # Backfill any missing keys from defaults
        for k, v in _DEFAULTS.items():
            data.setdefault(k, v)
        return data
    return dict(_DEFAULTS)


def _save_config(cfg: dict) -> None:
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)


def _recent_topics(n: int = 10) -> list[str]:
    if not os.path.exists(TOPICS_FILE):
        return []
    with open(TOPICS_FILE) as f:
        topics = json.load(f)
    return topics[-n:]


def _tail_log(n: int = 40) -> str:
    if not os.path.exists(LOG_FILE):
        return "(no log yet)"
    with open(LOG_FILE) as f:
        lines = f.readlines()
    return "".join(lines[-n:]).strip()


def improve() -> dict:
    """
    Run one improvement iteration. Returns the updated config.
    Logs a summary of what changed to improvement_log inside the config.
    """
    cfg = load_config()
    recent_topics = _recent_topics()
    log_tail = _tail_log()

    current_config_summary = json.dumps({
        k: v for k, v in cfg.items() if k != "improvement_log"
    }, indent=2)

    prompt = f"""You are an expert YouTube content coach iterating on a daily AI-narrated video channel.

CHANNEL: {config.CHANNEL_NAME}
NICHE: {config.NICHE}
CHARACTER: {"ARIA (AI financial analyst, sleek + witty)" if "finance" in config.NICHE else "NEXUS (AI tech guide, enthusiastic + sarcastic)"}

═══════════════════════════════════════
CURRENT PROMPT CONFIG (what we inject into the content prompt today)
═══════════════════════════════════════
{current_config_summary}

═══════════════════════════════════════
RECENT TOPICS COVERED (last {len(recent_topics)})
═══════════════════════════════════════
{chr(10).join(f"- {t}" for t in recent_topics) if recent_topics else "(none yet)"}

═══════════════════════════════════════
RECENT PIPELINE LOG (last 40 lines)
═══════════════════════════════════════
{log_tail}

═══════════════════════════════════════
YOUR TASK
═══════════════════════════════════════
Analyze the above and decide how to evolve the prompt config to make tomorrow's video MORE:
- Creative and unexpected (avoid formula fatigue)
- Visually interesting (better stock footage keywords)
- Emotionally engaging (stronger hooks, better pacing)
- Tonally consistent with the AI character

Consider:
- Are we in a topic rut? Should current_focus push toward a new angle or format?
- Are the hook techniques getting stale? Add a fresh one to extra_hook_techniques.
- Are there voice patterns that should be tried or avoided?
- Are there visual styles to explore or patterns to forbid (e.g. "stop using generic office shots")?
- What ONE thing would most improve tomorrow's video?

Rules for your response:
- extra_hook_techniques: list of short, concrete hook techniques (max 5 total, replace stale ones)
- extra_voice_notes: 1-2 sentences of additional voice direction for the character
- extra_visual_notes: 1-2 sentences of new visual keyword direction to try
- forbidden_patterns: list of patterns to explicitly avoid (max 5, replace resolved ones)
- current_focus: ONE clear directive for tomorrow's video (what to emphasize or experiment with)
- change_summary: 1-2 sentences explaining what you changed and why (for the improvement log)

Respond ONLY with valid JSON:
{{
  "current_focus": "<single directive for tomorrow>",
  "extra_hook_techniques": ["<technique 1>", "<technique 2>", ...],
  "extra_voice_notes": "<additional voice direction>",
  "extra_visual_notes": "<additional visual keyword direction>",
  "forbidden_patterns": ["<pattern to avoid>", ...],
  "change_summary": "<what changed and why>"
}}"""

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    updates = json.loads(raw)

    # Apply updates
    cfg["current_focus"]         = updates["current_focus"]
    cfg["extra_hook_techniques"] = updates["extra_hook_techniques"]
    cfg["extra_voice_notes"]     = updates["extra_voice_notes"]
    cfg["extra_visual_notes"]    = updates["extra_visual_notes"]
    cfg["forbidden_patterns"]    = updates["forbidden_patterns"]
    cfg["version"]              += 1
    cfg["last_improved"]         = datetime.now(timezone.utc).isoformat()

    # Keep a rolling log of the last 30 improvement summaries
    cfg["improvement_log"].append({
        "version": cfg["version"],
        "date": cfg["last_improved"],
        "summary": updates["change_summary"],
    })
    cfg["improvement_log"] = cfg["improvement_log"][-30:]

    _save_config(cfg)

    print(f"[improver] v{cfg['version']} — {updates['change_summary']}")
    return cfg


if __name__ == "__main__":
    result = improve()
    print(json.dumps({k: v for k, v in result.items() if k != "improvement_log"}, indent=2))
