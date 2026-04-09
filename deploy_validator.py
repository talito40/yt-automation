"""Deploy post-run validator to the droplet."""
import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('165.22.33.167', username='root', password='LukaKi2001q', timeout=10)
sftp = client.open_sftp()
BASE = "/opt/yt-automation"

# ─────────────────────────────────────────────────────────────────────────────
VALIDATE_PY = '''\
"""
validate.py
Post-run pipeline validator and auto-fixer.
Runs after every pipeline execution (success or failure).

Checks:
  1.  Last run outcome  — parse log for errors, identify root cause
  2.  Known error patterns — apply automatic fixes where possible
  3.  Required files  — all .py, .sh, presenter photos present
  4.  Module syntax   — py_compile every module
  5.  Env vars        — all required keys non-empty
  6.  API reachability — Leonardo, HeyGen, Telegram
  7.  Disk space      — warn if < 500 MB free
  8.  Stale temp files — delete leftover .mp4 / .jpg from failed runs
  9.  Pictory timeout  — ensure storyboard wait >= 600 s
  10. Package audit    — required pip packages present

Auto-fixes (applied in-place, effective before next run):
  - Stale temp files          -> deleted
  - Pictory timeout too short -> patched in video_generator.py
  - Missing pip package       -> pip installed
  - Syntax error in module    -> reported with line number (cannot auto-fix)
"""

import argparse
import glob
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

import requests

# ── Bootstrap channel config ──────────────────────────────────────────────────
_pre = argparse.ArgumentParser(add_help=False)
_pre.add_argument("--channel", type=int, default=1)
_pre_args, _ = _pre.parse_known_args()
os.environ["CHANNEL"] = str(_pre_args.channel)
import config  # noqa: E402 — must come after env var is set

PIPELINE_LOG = f"pipeline_ch{config.CHANNEL}.log"
VAL_LOG      = f"validation_ch{config.CHANNEL}.log"
VENV_PYTHON  = "/opt/yt-automation/venv/bin/python"

REQUIRED_FILES = [
    "main.py", "config.py", "content_generator.py",
    "video_generator.py", "youtube_uploader.py",
    "thumb_generator.py", "avatar_generator.py",
    "video_stitcher.py",
    f"run.sh", "run_ch2.sh",
    f"presenter_ch{config.CHANNEL}.jpg",
    "client_secrets.json",
    f"youtube_token_ch{config.CHANNEL}.json",
]

REQUIRED_MODULES = [
    "main.py", "config.py", "content_generator.py",
    "video_generator.py", "youtube_uploader.py",
    "thumb_generator.py", "avatar_generator.py",
    "video_stitcher.py",
]

REQUIRED_ENV = [
    "ANTHROPIC_API_KEY", "PICTORY_API_KEY",
    "HEYGEN_API_KEY",    "LEONARDO_API_KEY",
    "TELEGRAM_BOT_TOKEN","TELEGRAM_CHAT_ID",
]

REQUIRED_PACKAGES = [
    "anthropic", "requests", "google-auth-oauthlib",
    "google-api-python-client", "pillow", "pytrends",
]

# Known error patterns and their auto-fix functions
# Each entry: (regex_pattern, description, fix_function_name)
ERROR_PATTERNS = [
    (
        r"Storyboard render params never appeared",
        "Pictory storyboard timeout too short",
        "fix_pictory_timeout",
    ),
    (
        r"module \'video_generator\' has no attribute \'generate_shorts_video\'",
        "generate_shorts_video missing from video_generator",
        "fix_missing_generate_shorts",
    ),
    (
        r"Pictory render timed out",
        "Pictory render poll timeout too short",
        "fix_pictory_render_timeout",
    ),
    (
        r"\\[Errno 101\\] Network is unreachable",
        "Transient network error (no fix — monitor)",
        None,
    ),
    (
        r"json\\.JSONDecodeError|JSONDecodeError|Expecting value",
        "Claude returned invalid JSON — prompt may need tightening",
        "fix_json_decode",
    ),
    (
        r"HttpError 403.*thumbnail",
        "YouTube thumbnail permissions (channel not verified — expected)",
        None,
    ),
    (
        r"credentials.*invalid|Token has been expired|invalid_grant",
        "YouTube OAuth token expired — re-auth required",
        None,
    ),
]

MIN_STORYBOARD_TIMEOUT = 600   # seconds
MIN_RENDER_TIMEOUT     = 1200  # seconds
MIN_DISK_MB            = 500


# ── Logging ───────────────────────────────────────────────────────────────────

_issues:  list[dict] = []
_fixes:   list[str]  = []
_infos:   list[str]  = []


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _vlog(msg: str) -> None:
    line = f"[{_ts()}] {msg}"
    print(line)
    with open(VAL_LOG, "a") as f:
        f.write(line + "\\n")


def _issue(severity: str, msg: str) -> None:
    _issues.append({"severity": severity, "msg": msg})
    _vlog(f"[{severity}] {msg}")


def _fix(msg: str) -> None:
    _fixes.append(msg)
    _vlog(f"[FIX] {msg}")


def _info(msg: str) -> None:
    _infos.append(msg)
    _vlog(f"[OK ] {msg}")


# ── Telegram ──────────────────────────────────────────────────────────────────

def _notify(msg: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat  = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": msg, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception:
        pass


# ── Check 1: Last run outcome ─────────────────────────────────────────────────

def check_last_run() -> list[str]:
    """Parse the pipeline log for the most recent run. Returns list of error strings."""
    if not os.path.exists(PIPELINE_LOG):
        _issue("WARN", f"{PIPELINE_LOG} not found — pipeline may never have run")
        return []

    with open(PIPELINE_LOG) as f:
        lines = f.readlines()

    # Find the start of the last run (last occurrence of "Step 1/6")
    last_run_start = 0
    for i, line in enumerate(lines):
        if "Step 1/6" in line:
            last_run_start = i

    run_lines = lines[last_run_start:]
    run_text  = "".join(run_lines)

    errors = [l.strip() for l in run_lines if "PIPELINE ERROR" in l or "failed" in l.lower()]

    if any("SUCCESS" in l for l in run_lines):
        _info(f"Last run: SUCCESS")
    elif errors:
        _issue("ERROR", f"Last run FAILED — {len(errors)} error(s) found in log")
    else:
        _issue("WARN", "Last run status unclear (no SUCCESS or ERROR marker found)")

    return [re.sub(r"\\[.*?\\] ", "", e) for e in errors]


# ── Check 2: Known error patterns + auto-fixes ───────────────────────────────

def check_and_fix_known_errors(error_lines: list[str]) -> None:
    all_text = " ".join(error_lines)
    for pattern, description, fix_fn in ERROR_PATTERNS:
        if re.search(pattern, all_text, re.IGNORECASE):
            _issue("ERROR", f"Known issue detected: {description}")
            if fix_fn and fix_fn in globals():
                try:
                    globals()[fix_fn]()
                except Exception as exc:
                    _issue("ERROR", f"Auto-fix {fix_fn} failed: {exc}")
            elif fix_fn:
                _issue("WARN", f"Fix function {fix_fn} not implemented — manual action needed")


# ── Check 3: Required files ───────────────────────────────────────────────────

def check_required_files() -> None:
    for fname in REQUIRED_FILES:
        if os.path.exists(fname):
            _info(f"File present: {fname}")
        else:
            _issue("ERROR", f"Missing required file: {fname}")


# ── Check 4: Module syntax ────────────────────────────────────────────────────

def check_module_syntax() -> None:
    for fname in REQUIRED_MODULES:
        if not os.path.exists(fname):
            continue
        result = subprocess.run(
            [VENV_PYTHON, "-m", "py_compile", fname],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            _info(f"Syntax OK: {fname}")
        else:
            _issue("ERROR", f"Syntax error in {fname}: {result.stderr.strip()}")


# ── Check 5: Env vars ─────────────────────────────────────────────────────────

def check_env_vars() -> None:
    for key in REQUIRED_ENV:
        val = os.environ.get(key, "")
        if val:
            _info(f"Env var set: {key}")
        else:
            _issue("ERROR", f"Missing env var: {key}")


# ── Check 6: API reachability ─────────────────────────────────────────────────

def check_apis() -> None:
    # Leonardo
    if config.LEONARDO_API_KEY:
        try:
            r = requests.get(
                "https://cloud.leonardo.ai/api/rest/v1/me",
                headers={"Authorization": f"Bearer {config.LEONARDO_API_KEY}"},
                timeout=10,
            )
            if r.status_code == 200:
                credits = r.json().get("user_details", [{}])[0].get("tokenRenewalDate", "n/a")
                _info(f"Leonardo API: reachable (HTTP 200)")
            else:
                _issue("ERROR", f"Leonardo API returned HTTP {r.status_code}")
        except Exception as exc:
            _issue("WARN", f"Leonardo API unreachable: {exc}")

    # HeyGen
    if config.HEYGEN_API_KEY:
        try:
            r = requests.get(
                "https://api.heygen.com/v2/voices",
                headers={"X-Api-Key": config.HEYGEN_API_KEY},
                timeout=10,
            )
            if r.status_code in (200, 401):
                status = "reachable" if r.status_code == 200 else "invalid key"
                _info(f"HeyGen API: {status} (HTTP {r.status_code})")
            else:
                _issue("WARN", f"HeyGen API returned HTTP {r.status_code}")
        except Exception as exc:
            _issue("WARN", f"HeyGen API unreachable: {exc}")

    # Telegram
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if token:
        try:
            r = requests.get(
                f"https://api.telegram.org/bot{token}/getMe",
                timeout=10,
            )
            if r.status_code == 200:
                bot_name = r.json().get("result", {}).get("username", "unknown")
                _info(f"Telegram bot: @{bot_name} (reachable)")
            else:
                _issue("WARN", f"Telegram bot check failed: HTTP {r.status_code}")
        except Exception as exc:
            _issue("WARN", f"Telegram unreachable: {exc}")

    # Pictory — lightweight auth check
    if config.PICTORY_API_KEY:
        try:
            r = requests.get(
                "https://api.pictory.ai/pictoryapis/v1/user",
                headers={"Authorization": f"Bearer {config.PICTORY_API_KEY}"},
                timeout=10,
            )
            _info(f"Pictory API: reachable (HTTP {r.status_code})")
        except Exception as exc:
            _issue("WARN", f"Pictory API unreachable: {exc}")


# ── Check 7: Disk space ───────────────────────────────────────────────────────

def check_disk_space() -> None:
    stat  = os.statvfs("/opt/yt-automation")
    free  = stat.f_bavail * stat.f_frsize // (1024 * 1024)
    total = stat.f_blocks * stat.f_frsize // (1024 * 1024)
    pct   = int((1 - stat.f_bavail / stat.f_blocks) * 100)
    if free >= MIN_DISK_MB:
        _info(f"Disk space: {free} MB free of {total} MB ({pct}% used)")
    else:
        _issue("WARN", f"Low disk space: only {free} MB free ({pct}% used)")
        fix_disk_space()


# ── Check 8: Stale temp files ─────────────────────────────────────────────────

def check_stale_temp_files() -> None:
    patterns = ["video_*.mp4", "short_*.mp4", "intro_*.mp4",
                "thumb_*.jpg", "video_raw_*.mp4"]
    found = []
    for p in patterns:
        found.extend(glob.glob(p))
    if found:
        _issue("WARN", f"Stale temp files found: {found}")
        fix_stale_temp_files(found)
    else:
        _info("No stale temp files")


# ── Check 9: Pictory timeout values ──────────────────────────────────────────

def check_pictory_timeouts() -> None:
    if not os.path.exists("video_generator.py"):
        return
    with open("video_generator.py") as f:
        content = f.read()

    m1 = re.search(r"_wait_for_render_params.*?max_wait: int = (\\d+)", content)
    m2 = re.search(r"_poll_until_ready.*?max_wait: int = (\\d+)", content)

    sb_timeout  = int(m1.group(1)) if m1 else 0
    pol_timeout = int(m2.group(1)) if m2 else 0

    if sb_timeout >= MIN_STORYBOARD_TIMEOUT:
        _info(f"Pictory storyboard timeout: {sb_timeout}s (OK)")
    else:
        _issue("ERROR", f"Pictory storyboard timeout too short: {sb_timeout}s (min {MIN_STORYBOARD_TIMEOUT}s)")
        fix_pictory_timeout()

    if pol_timeout >= MIN_RENDER_TIMEOUT:
        _info(f"Pictory render poll timeout: {pol_timeout}s (OK)")
    else:
        _issue("WARN", f"Pictory render poll timeout: {pol_timeout}s (min {MIN_RENDER_TIMEOUT}s)")
        fix_pictory_render_timeout()


# ── Check 10: Pip packages ────────────────────────────────────────────────────

def check_packages() -> None:
    result = subprocess.run(
        [VENV_PYTHON, "-m", "pip", "list", "--format=columns"],
        capture_output=True, text=True,
    )
    installed = result.stdout.lower()
    for pkg in REQUIRED_PACKAGES:
        if pkg.lower().replace("-", "_") in installed or pkg.lower() in installed:
            _info(f"Package installed: {pkg}")
        else:
            _issue("ERROR", f"Missing package: {pkg}")
            fix_install_package(pkg)


# ── Auto-fix functions ────────────────────────────────────────────────────────

def fix_pictory_timeout() -> None:
    """Increase _wait_for_render_params timeout to 600s."""
    _patch_timeout("video_generator.py",
                   r"(def _wait_for_render_params.*?max_wait: int = )(\\d+)",
                   str(MIN_STORYBOARD_TIMEOUT))
    _fix(f"Pictory storyboard timeout patched to {MIN_STORYBOARD_TIMEOUT}s")


def fix_pictory_render_timeout() -> None:
    """Increase _poll_until_ready timeout to 1200s."""
    _patch_timeout("video_generator.py",
                   r"(def _poll_until_ready.*?max_wait: int = )(\\d+)",
                   str(MIN_RENDER_TIMEOUT))
    _fix(f"Pictory render poll timeout patched to {MIN_RENDER_TIMEOUT}s")


def _patch_timeout(filepath: str, pattern: str, new_val: str) -> None:
    with open(filepath) as f:
        content = f.read()
    new_content = re.sub(pattern, lambda m: m.group(1) + new_val, content)
    if new_content != content:
        with open(filepath, "w") as f:
            f.write(new_content)


def fix_missing_generate_shorts(dummy=None) -> None:
    """Check if generate_shorts_video is in video_generator.py — alert if missing."""
    with open("video_generator.py") as f:
        content = f.read()
    if "def generate_shorts_video" not in content:
        _issue("ERROR", "generate_shorts_video still missing from video_generator.py — manual re-deploy required")
    else:
        _info("generate_shorts_video is present in video_generator.py")


def fix_json_decode(dummy=None) -> None:
    """Add retry logic nudge — can\'t auto-fix prompt issues, but log clearly."""
    _issue("WARN", "Claude returned invalid JSON. This is usually transient. If recurring, the prompt in content_generator.py may need adjustment.")


def fix_stale_temp_files(files: list) -> None:
    for f in files:
        try:
            os.remove(f)
            _fix(f"Deleted stale temp file: {f}")
        except OSError as e:
            _issue("WARN", f"Could not delete {f}: {e}")


def fix_disk_space() -> None:
    """Clean up old log lines (keep last 500 lines per log)."""
    for log in glob.glob("pipeline_ch*.log") + glob.glob("validation_ch*.log"):
        try:
            with open(log) as f:
                lines = f.readlines()
            if len(lines) > 500:
                with open(log, "w") as f:
                    f.writelines(lines[-500:])
                _fix(f"Trimmed {log} to last 500 lines")
        except Exception:
            pass


def fix_install_package(pkg: str) -> None:
    result = subprocess.run(
        [VENV_PYTHON, "-m", "pip", "install", pkg, "-q"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        _fix(f"Installed missing package: {pkg}")
    else:
        _issue("ERROR", f"Failed to install {pkg}: {result.stderr.strip()}")


# ── Report ────────────────────────────────────────────────────────────────────

def build_report() -> str:
    errors = [i for i in _issues if i["severity"] == "ERROR"]
    warns  = [i for i in _issues if i["severity"] == "WARN"]

    icon  = "&#x2705;" if not errors else "&#x26A0;&#xFE0F;" if not errors else "&#x274C;"
    if errors:
        icon = "&#x274C;"
    elif warns:
        icon = "&#x26A0;&#xFE0F;"
    else:
        icon = "&#x2705;"

    lines = [
        f"{icon} <b>Validator — {config.CHANNEL_NAME}</b>",
        f"&#x1F4CB; {len(errors)} error(s), {len(warns)} warning(s), {len(_fixes)} fix(es) applied",
        "",
    ]

    if errors:
        lines.append("<b>Errors:</b>")
        for e in errors:
            lines.append(f"  &#x2022; {e['msg'][:120]}")
        lines.append("")

    if warns:
        lines.append("<b>Warnings:</b>")
        for w in warns:
            lines.append(f"  &#x2022; {w['msg'][:120]}")
        lines.append("")

    if _fixes:
        lines.append("<b>Auto-fixes applied:</b>")
        for fx in _fixes:
            lines.append(f"  &#x1F527; {fx[:120]}")

    return "\\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--channel", type=int, default=1)
    args = parser.parse_args()

    _vlog(f"=== Validation start — Channel {config.CHANNEL} ({config.CHANNEL_NAME}) ===")

    os.chdir("/opt/yt-automation")

    # Run all checks
    error_lines = check_last_run()
    check_and_fix_known_errors(error_lines)
    check_required_files()
    check_module_syntax()
    check_env_vars()
    check_apis()
    check_disk_space()
    check_stale_temp_files()
    check_pictory_timeouts()
    check_packages()

    # Build and send report
    report = build_report()
    _vlog("=== Validation complete ===")
    _notify(report)

    # Exit with error code if critical issues found so cron logs show it
    errors = [i for i in _issues if i["severity"] == "ERROR"]
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
'''

# ── Update run.sh and run_ch2.sh to always call validator ────────────────────
RUN_SH = '''\
#!/bin/bash
cd /opt/yt-automation
set -a; source .env; set +a
source venv/bin/activate
python main.py --channel 1 --run || true
python validate.py --channel 1
'''

RUN_CH2_SH = '''\
#!/bin/bash
cd /opt/yt-automation
set -a; source .env; set +a
source venv/bin/activate
python main.py --channel 2 --run || true
python validate.py --channel 2
'''

# ── Upload ────────────────────────────────────────────────────────────────────
files = {
    "validate.py":  VALIDATE_PY,
    "run.sh":       RUN_SH,
    "run_ch2.sh":   RUN_CH2_SH,
}

for fname, content in files.items():
    with sftp.open(f"{BASE}/{fname}", "w") as f:
        f.write(content)
    print(f"  uploaded {fname}")

sftp.close()

# Make scripts executable + syntax check
stdin, stdout, stderr = client.exec_command(
    "chmod +x /opt/yt-automation/run.sh /opt/yt-automation/run_ch2.sh"
)
stdout.read()

checks = ["validate.py", "run.sh", "run_ch2.sh"]
print("\nSyntax checks:")
for fname in checks:
    if fname.endswith(".py"):
        cmd = f"cd {BASE} && source venv/bin/activate && python -m py_compile {fname} && echo '{fname} OK'"
    else:
        cmd = f"bash -n {BASE}/{fname} && echo '{fname} OK'"
    stdin, stdout, stderr = client.exec_command(cmd)
    out = stdout.read().decode(errors="replace").strip()
    err = stderr.read().decode(errors="replace").strip()
    print(out or err or f"{fname}: no output")

client.close()
print("\nDone.")
