"""
PULSE Knowledge Base Engine

Feed your company's runbooks, past incident reports, and common fixes.
When an incident fires, PULSE searches the KB for similar cases and:
  1. Injects that context into the AI RCA prompt
  2. Surfaces the exact runbook that fixed it last time
  3. Auto-executes the linked playbook if confidence is high enough

Ingestion methods:
  - POST /api/kb/entries          — add a single entry via API
  - POST /api/kb/import/markdown  — paste or upload a runbook .md file
  - POST /api/kb/import/bulk      — JSON array of entries
  - PUT  /api/kb/entries/{id}     — update an entry

Entry types:
  - runbook       — step-by-step fix for a known issue
  - incident      — past incident + how it was resolved
  - alert_guide   — what a specific alert means + what to do
  - config_note   — known config issue / gotcha
  - escalation    — who to call for what
"""
import re
import os
import json
import math
from datetime import datetime
from collections import defaultdict
from typing import Optional

# ── Simple TF-IDF search (no external vector DB needed) ──────────────────────
# For production, swap _search() to use pgvector or a vector store.

_kb: list[dict] = []          # in-memory KB store
_idf: dict[str, float] = {}   # precomputed IDF scores
_dirty = True                  # recompute IDF on next search


def _tokenize(text: str) -> list[str]:
    return re.findall(r'\b[a-zA-Z0-9_\-\.]{2,}\b', text.lower())


def _tf(tokens: list[str]) -> dict[str, float]:
    counts: dict[str, int] = defaultdict(int)
    for t in tokens:
        counts[t] += 1
    total = len(tokens) or 1
    return {t: c / total for t, c in counts.items()}


def _build_idf():
    global _idf, _dirty
    if not _dirty:
        return
    N = len(_kb) or 1
    df: dict[str, int] = defaultdict(int)
    for entry in _kb:
        text   = _entry_text(entry)
        tokens = set(_tokenize(text))
        for t in tokens:
            df[t] += 1
    _idf   = {t: math.log(N / (df[t] + 1)) + 1 for t in df}
    _dirty = False


def _entry_text(entry: dict) -> str:
    return " ".join(filter(None, [
        entry.get("title", ""),
        entry.get("description", ""),
        entry.get("symptoms", ""),
        entry.get("resolution", ""),
        entry.get("tags", ""),
        entry.get("service", ""),
        " ".join(entry.get("keywords", [])),
    ]))


def _tfidf_score(query_tokens: list[str], entry: dict) -> float:
    _build_idf()
    doc_tokens = _tokenize(_entry_text(entry))
    doc_tf     = _tf(doc_tokens)
    score      = 0.0
    for qt in set(query_tokens):
        tf  = doc_tf.get(qt, 0)
        idf = _idf.get(qt, 0)
        score += tf * idf
    return score


def search(query: str, top_k: int = 5, entry_type: str = "") -> list[dict]:
    """
    Search the KB for entries relevant to the query.
    Returns top_k results with similarity scores.
    """
    if not _kb:
        return []

    q_tokens = _tokenize(query)
    results  = []

    for entry in _kb:
        if entry_type and entry.get("type") != entry_type:
            continue
        if not entry.get("active", True):
            continue

        score = _tfidf_score(q_tokens, entry)

        # Boost if exact keyword match
        entry_text = _entry_text(entry).lower()
        for token in q_tokens:
            if len(token) > 4 and token in entry_text:
                score *= 1.3

        results.append({**entry, "_score": round(score, 4)})

    results.sort(key=lambda x: x["_score"], reverse=True)
    return [r for r in results[:top_k] if r["_score"] > 0]


def search_for_incident(alert_data: dict, event_data: list[dict] = None) -> list[dict]:
    """
    Build a rich query from incident context and search the KB.
    Returns relevant runbooks + past incidents.
    """
    parts = [
        alert_data.get("rule_name", ""),
        alert_data.get("message", ""),
        alert_data.get("category", ""),
        alert_data.get("node_id", ""),
    ]
    if event_data:
        for e in event_data[:5]:
            parts.append(e.get("message", ""))

    query = " ".join(filter(None, parts))
    return search(query, top_k=5)


def add_entry(entry: dict) -> dict:
    """Add or update a KB entry."""
    global _dirty
    entry.setdefault("id",         _next_id())
    entry.setdefault("type",       "runbook")
    entry.setdefault("active",     True)
    entry.setdefault("created_at", datetime.utcnow().isoformat())
    entry.setdefault("use_count",  0)
    entry["updated_at"] = datetime.utcnow().isoformat()

    # Replace if same ID exists
    for i, e in enumerate(_kb):
        if e.get("id") == entry["id"]:
            _kb[i] = entry
            _dirty = True
            return entry

    _kb.append(entry)
    _dirty = True
    return entry


def update_entry(entry_id: str, updates: dict) -> Optional[dict]:
    global _dirty
    for i, e in enumerate(_kb):
        if str(e.get("id")) == str(entry_id):
            _kb[i] = {**e, **updates, "updated_at": datetime.utcnow().isoformat()}
            _dirty = True
            return _kb[i]
    return None


def delete_entry(entry_id: str) -> bool:
    global _dirty
    for i, e in enumerate(_kb):
        if str(e.get("id")) == str(entry_id):
            _kb[i]["active"] = False
            _dirty = True
            return True
    return False


def record_use(entry_id: str):
    """Track which entries are actually useful."""
    for e in _kb:
        if str(e.get("id")) == str(entry_id):
            e["use_count"] = e.get("use_count", 0) + 1
            e["last_used"] = datetime.utcnow().isoformat()
            break


def import_markdown(content: str, default_type: str = "runbook") -> list[dict]:
    """
    Parse a Markdown file into KB entries.

    Format:
      # Entry Title
      **Type:** runbook | incident | alert_guide
      **Service:** postgres
      **Tags:** database, slow-query, performance
      **Severity:** critical

      ## Symptoms
      (text)

      ## Resolution
      (text — can include code blocks)

      ## Keywords
      keyword1, keyword2
      ---  ← separator between entries
    """
    entries = []
    sections = content.split("\n---\n")

    for section in sections:
        section = section.strip()
        if not section:
            continue

        entry: dict = {"type": default_type}
        lines  = section.split("\n")
        body_lines: list[str] = []
        in_symptoms = in_resolution = False
        symptoms_lines: list[str] = []
        resolution_lines: list[str] = []

        for line in lines:
            # Title
            if line.startswith("# "):
                entry["title"] = line[2:].strip()
            # Meta fields
            elif line.startswith("**Type:**"):
                entry["type"] = line.split(":", 1)[1].strip().strip("* ")
            elif line.startswith("**Service:**"):
                entry["service"] = line.split(":", 1)[1].strip().strip("* ")
            elif line.startswith("**Tags:**"):
                entry["tags"] = line.split(":", 1)[1].strip().strip("* ")
            elif line.startswith("**Severity:**"):
                entry["severity"] = line.split(":", 1)[1].strip().strip("* ").lower()
            elif line.startswith("**Playbook:**"):
                entry["playbook_id"] = line.split(":", 1)[1].strip().strip("* ")
            elif line.startswith("**Alert:**"):
                entry["alert_rule_id"] = line.split(":", 1)[1].strip().strip("* ")
            elif line.startswith("**Keywords:**"):
                entry["keywords"] = [k.strip() for k in line.split(":", 1)[1].split(",")]
            # Section headers
            elif line.startswith("## Symptoms"):
                in_symptoms, in_resolution = True, False
            elif line.startswith("## Resolution") or line.startswith("## Fix"):
                in_symptoms, in_resolution = False, True
            elif line.startswith("## "):
                in_symptoms, in_resolution = False, False
                body_lines.append(line)
            elif in_symptoms:
                symptoms_lines.append(line)
            elif in_resolution:
                resolution_lines.append(line)
            else:
                body_lines.append(line)

        if symptoms_lines:
            entry["symptoms"]   = "\n".join(symptoms_lines).strip()
        if resolution_lines:
            entry["resolution"] = "\n".join(resolution_lines).strip()
        if body_lines:
            entry["description"] = "\n".join(body_lines).strip()

        if entry.get("title"):
            entries.append(add_entry(entry))

    return entries


def import_bulk(entries: list[dict]) -> list[dict]:
    return [add_entry(e) for e in entries]


def get_all(active_only: bool = True) -> list[dict]:
    if active_only:
        return [e for e in _kb if e.get("active", True)]
    return list(_kb)


def get_entry(entry_id: str) -> Optional[dict]:
    for e in _kb:
        if str(e.get("id")) == str(entry_id):
            return e
    return None


def format_for_rca(entries: list[dict]) -> str:
    """Format KB entries as context for the RCA prompt."""
    if not entries:
        return ""
    lines = ["RELEVANT COMPANY KNOWLEDGE BASE:"]
    for e in entries:
        lines.append(f"\n[{e.get('type','?').upper()}] {e.get('title','?')}")
        if e.get("symptoms"):
            lines.append(f"  Symptoms: {e['symptoms'][:300]}")
        if e.get("resolution"):
            lines.append(f"  Resolution: {e['resolution'][:500]}")
        if e.get("playbook_id"):
            lines.append(f"  Auto-playbook: {e['playbook_id']}")
    return "\n".join(lines)


def _next_id() -> str:
    return str(len(_kb) + 1)


# ── Load seed KB entries from config if present ───────────────────────────────
def load_from_config():
    """Load KB entries from config/knowledge.yaml or config/knowledge/ dir on startup."""
    from pathlib import Path
    import yaml

    roots = [
        Path(__file__).parent.parent / "config",
        Path(__file__).parent / "config",
    ]
    for root in roots:
        # Single file
        kb_file = root / "knowledge.yaml"
        if kb_file.exists():
            with open(kb_file) as f:
                data = yaml.safe_load(f) or {}
                entries = data.get("knowledge", data.get("entries", []))
                for e in entries:
                    add_entry(e)
            print(f"[KB] Loaded {len(entries)} entries from {kb_file}")

        # Directory of .md runbooks
        kb_dir = root / "knowledge"
        if kb_dir.is_dir():
            count = 0
            for md_file in kb_dir.glob("*.md"):
                imported = import_markdown(md_file.read_text(), default_type="runbook")
                count += len(imported)
            if count:
                print(f"[KB] Loaded {count} runbook entries from {kb_dir}")
