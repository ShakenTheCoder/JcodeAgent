"""
Intent router — lightweight classifier for user input.

Determines what the user wants to do WITHOUT calling the LLM
for obvious commands. Falls back to LLM for ambiguous input.

Intents:
  BUILD     — create a new project from scratch
  MODIFY    — change/fix/add to existing code (agent mode)
  CHAT      — ask questions, discuss, explain (chat mode)
  GIT       — version control operations
  RUN       — run/start/test the project
  NAVIGATE  — utility commands (files, tree, plan, help, etc.)
  MODE      — switch between agent/chat mode
  QUIT      — exit/back

v0.9.0 — Simplified mode switching: just type "agent" or "chat".
"""

from __future__ import annotations

import re
from enum import Enum


class Intent(str, Enum):
    """User intent categories."""
    BUILD    = "build"      # Create new project from scratch
    MODIFY   = "modify"     # Change/fix/add code (agent mode)
    CHAT     = "chat"       # Discussion, questions, explain
    GIT      = "git"        # Version control
    RUN      = "run"        # Run/start/test project
    NAVIGATE = "navigate"   # Utility: files, tree, plan, help
    MODE     = "mode"       # Switch agent/chat mode
    QUIT     = "quit"       # Exit/back


# ═══════════════════════════════════════════════════════════════════
# Pattern-based intent classification
# ═══════════════════════════════════════════════════════════════════

# Exact-match commands (case-insensitive)
_EXACT_COMMANDS: dict[str, Intent] = {
    # Quit
    "quit": Intent.QUIT,
    "exit": Intent.QUIT,
    "q": Intent.QUIT,
    "back": Intent.QUIT,
    "home": Intent.QUIT,

    # Mode switching — just type "agent" or "chat"
    "agent": Intent.MODE,
    "chat": Intent.MODE,
    "agentic": Intent.MODE,

    # Navigate
    "help": Intent.NAVIGATE,
    "files": Intent.NAVIGATE,
    "tree": Intent.NAVIGATE,
    "plan": Intent.NAVIGATE,
    "clear": Intent.NAVIGATE,
    "status": Intent.NAVIGATE,
    "version": Intent.NAVIGATE,
    "update": Intent.NAVIGATE,
    "uninstall": Intent.NAVIGATE,
    "models": Intent.NAVIGATE,

    # Run
    "run": Intent.RUN,
    "start": Intent.RUN,
    "test": Intent.RUN,
    "tests": Intent.RUN,
    "dev": Intent.RUN,
    "serve": Intent.RUN,
    "rebuild": Intent.RUN,

    # Git (single-word)
    "commit": Intent.GIT,
    "push": Intent.GIT,
    "pull": Intent.GIT,
    "diff": Intent.GIT,
    "log": Intent.GIT,
}

# Prefix-match commands
_PREFIX_COMMANDS: list[tuple[str, Intent]] = [
    ("build ", Intent.BUILD),
    ("create ", Intent.BUILD),
    ("new project", Intent.BUILD),
    ("make ", Intent.BUILD),
    ("scaffold ", Intent.BUILD),
    ("generate project", Intent.BUILD),

    # Git prefix commands
    ("git ", Intent.GIT),
    ("commit ", Intent.GIT),
    ("push to", Intent.GIT),
    ("push ", Intent.GIT),
    ("pull ", Intent.GIT),
    ("clone ", Intent.GIT),
    ("branch ", Intent.GIT),

    # Mode switch (legacy "mode" prefix also works)
    ("mode ", Intent.MODE),
    ("switch to ", Intent.MODE),
    ("switch ", Intent.MODE),
]

# Keyword patterns for intent detection
_BUILD_PATTERNS: list[str] = [
    r"\bbuild\b.*\b(?:app|application|project|website|site|page|tool|game|program|system|platform|service|dashboard)\b",
    r"\b(?:app|application|project|website|site|tool|game|program|system|platform|service|dashboard)\b.*\bbuild\b",
    r"\bcreate\b.*\b(?:app|application|project|website|site|page|tool|game|program|system|platform|service|dashboard)\b",
    r"\bmake\b.*\b(?:app|application|project|website|site|page|tool|game|program|system|platform|service|dashboard)\b",
    r"\b(?:i\s+)?want\s+(?:you\s+)?(?:to\s+)?(?:build|create|make|develop|code|write)\b",
    r"\b(?:develop|code|write)\b.*\b(?:app|application|project|website|site|tool|game|program|system|platform|service|dashboard)\b",
    r"\b(?:build|create|make)\s+(?:a|an|the|me|my)\b",
    r"\b(?:new|from\s+scratch)\b.*\b(?:app|project|website|tool|game|program)\b",
    r"\bscaffold\b", r"\bbootstrap\b",
    r"\bgenerate\s+(?:a|an|the)\b",
    r"\bset\s*up\s+(?:a|an|the|new)\b.*\b(?:app|project|website|tool)\b",
    r"\bstart\s+(?:a|an)\s+(?:new\s+)?(?:app|project|website|tool)\b",
]

_MODIFY_PATTERNS: list[str] = [
    r"\bfix\b", r"\bbug\b", r"\berror\b", r"\bcrash\b",
    r"\badd\b.*\b(?:feature|function|component|page|route|endpoint|button|form)\b",
    r"\bimplement\b", r"\brefactor\b", r"\brewrite\b", r"\bupdate\b",
    r"\bchange\b", r"\bmodify\b", r"\breplace\b", r"\bremove\b",
    r"\bdelete\b", r"\brename\b", r"\bmove\b",
    r"\binstall\b", r"\bupgrade\b", r"\bmigrate\b",
    r"\badd\s+", r"\bcreate\s+a?\s*(?:file|page|component|module)\b",
    r"\bset\s*up\b", r"\bconfigure\b", r"\benable\b", r"\bdisable\b",
    r"\boptimize\b", r"\bimprove\b", r"\benhance\b",
    r"\bdark\s*mode\b", r"\bresponsive\b", r"\bstyle\b",
    r"\bthe\s+\w+\s+(?:is|are|isn't|doesn't|won't|can't)\b.*\b(?:work|broken|wrong|fail)\b",
    r"\bnot\s+working\b", r"\bdoesn't\s+work\b", r"\bwon't\s+(?:start|run|compile|build)\b",
    r"\bmissing\b", r"\bundefined\b", r"\bnull\b",
]

_CHAT_PATTERNS: list[str] = [
    r"^(?:how|what|why|when|where|who|which|explain|describe|tell me|can you)\b",
    r"\bhow\s+(?:does|do|did|is|are|can|could|should|would|to)\b",
    r"\bwhat\s+(?:is|are|does|do|did|should|would|happened)\b",
    r"\bwhy\s+(?:is|are|does|do|did|should|would)\b",
    r"\bexplain\b", r"\bdescribe\b", r"\bsummar",
    r"\bunderstand\b", r"\bmeaning\b",
    r"\bsuggest\b", r"\brecommend\b", r"\bideas?\b",
    r"\bcompare\b", r"\bdifference\b", r"\bbetter\b",
    r"\bhelp me understand\b",
    r"\bshow me\b", r"\bwalk me through\b",
    r"\btell me about\b",
    r"\bwhat (?:technologies|tech|stack|frameworks?)\b",
    r"^is\s+(?:there|it|this)\b",
    r"\?$",  # Ends with question mark
]

_GIT_PATTERNS: list[str] = [
    r"\bgit\b", r"\bcommit\b", r"\bpush\b", r"\bpull\b",
    r"\bmerge\b", r"\bbranch\b", r"\bclone\b",
    r"\bgithub\b", r"\brepository\b", r"\brepo\b",
    r"\bversion\s*control\b", r"\bsave\s+(?:to|my)\s+(?:changes|progress|work)\b",
    r"\bstage\b", r"\bunstage\b",
]

_RUN_PATTERNS: list[str] = [
    r"^run\b", r"\brun\s+(?:the|this|my|it)\b",
    r"\bstart\s+(?:the|this|my)\b", r"\blaunch\b",
    r"\bexecute\b", r"\btest\s+(?:the|this|my|it)\b",
    r"\bnpm\s+(?:start|run|test)\b",
    r"\bget\s+(?:the\s+)?(?:project|app|it)\s+running\b",
    r"\bauto\s*run\b",
    r"\brun\s+(?:the\s+)?(?:necessary|required|needed)\s+commands\b",
    r"\binstall\s+(?:and\s+)?run\b",
    r"\bstart\s+(?:the\s+)?(?:project|app|server|application)\b",
    r"\bpython\b.*\brun\b",
    r"\bdeploy\b",
    r"\bhelp\s+(?:me\s+)?run\b",
    r"\brun\s+(?:the\s+)?(?:project|app|server|application|code)\b",
    r"\brun\s+(?:this|it)\s+(?:project|app|for me)?\b",
    r"\bcan\s+you\s+run\b",
    r"\bplease\s+run\b",
    r"\brun\s+(?:this|it)\s+for\s+me\b",
]


# ═══════════════════════════════════════════════════════════════════
# Main classifier
# ═══════════════════════════════════════════════════════════════════

def classify_intent(user_input: str) -> tuple[Intent, str]:
    """
    Classify user input into an intent.

    Returns:
        (intent, cleaned_input) — the intent enum and the input
        with any command prefix stripped.

    The classifier uses a priority cascade:
    1. Exact command match (highest confidence)
    2. Prefix command match
    3. Keyword pattern match (scored)
    4. Default: CHAT (lowest confidence — let the LLM handle it)
    """
    raw = user_input.strip()
    if not raw:
        return Intent.NAVIGATE, ""

    lower = raw.lower().strip()

    # 1. Exact match
    if lower in _EXACT_COMMANDS:
        return _EXACT_COMMANDS[lower], raw

    # 2. Prefix match
    for prefix, intent in _PREFIX_COMMANDS:
        if lower.startswith(prefix):
            # Strip the command prefix to get the actual content
            remainder = raw[len(prefix):].strip()
            return intent, remainder or raw

    # 3. Pattern scoring
    scores: dict[Intent, float] = {
        Intent.BUILD: 0,
        Intent.MODIFY: 0,
        Intent.CHAT: 0,
        Intent.GIT: 0,
        Intent.RUN: 0,
    }

    for pattern in _BUILD_PATTERNS:
        if re.search(pattern, lower):
            scores[Intent.BUILD] += 1.5  # BUILD gets a boost — building is the primary action

    for pattern in _MODIFY_PATTERNS:
        if re.search(pattern, lower):
            scores[Intent.MODIFY] += 1

    for pattern in _CHAT_PATTERNS:
        if re.search(pattern, lower):
            scores[Intent.CHAT] += 1

    for pattern in _GIT_PATTERNS:
        if re.search(pattern, lower):
            scores[Intent.GIT] += 1

    for pattern in _RUN_PATTERNS:
        if re.search(pattern, lower):
            scores[Intent.RUN] += 1

    # Get the winner
    max_score = max(scores.values())
    if max_score > 0:
        # Find winning intent
        winner = max(scores, key=scores.get)

        # BUILD always wins over CHAT — "build me an app" is a build, not a chat
        if scores[Intent.BUILD] > 0 and winner == Intent.CHAT:
            return Intent.BUILD, raw

        # If modify and chat are tied or close, check context clues
        if scores[Intent.MODIFY] > 0 and scores[Intent.CHAT] > 0:
            # If there's a question mark, lean chat
            if raw.endswith("?"):
                return Intent.CHAT, raw
            # If there are action verbs, lean modify
            if re.search(r"\b(?:fix|add|change|update|remove|create|implement|refactor)\b", lower):
                return Intent.MODIFY, raw
            # Default to highest score
            return winner, raw

        return winner, raw

    # 4. Default: CHAT (let the LLM figure it out)
    return Intent.CHAT, raw


def intent_label(intent: Intent) -> str:
    """Human-readable label for display."""
    labels = {
        Intent.BUILD:    "🔨 Build",
        Intent.MODIFY:   "⚡ Modify",
        Intent.CHAT:     "💬 Chat",
        Intent.GIT:      "📦 Git",
        Intent.RUN:      "▶️  Run",
        Intent.NAVIGATE: "📂 Navigate",
        Intent.MODE:     "🔄 Mode",
        Intent.QUIT:     "👋 Quit",
    }
    return labels.get(intent, str(intent))
