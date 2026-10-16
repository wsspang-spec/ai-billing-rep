"""Settings. Keys come from .env in this repo (see .env.example), or from a parent folder's .env."""

import os
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
LOCAL = ROOT / "local-data"  # gitignored: database, cached parses, audio, portal url
LOCAL.mkdir(exist_ok=True)

load_dotenv(ROOT / ".env")
load_dotenv(find_dotenv(str(ROOT.parent / ".env")) or None)  # a parent checkout's .env, never overriding

REGION = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-west-2"
MODEL = os.environ.get("BEDROCK_MODEL") or "us.anthropic.claude-opus-5-5"
DB_URL = os.environ.get("BILLING_DB_URL") or f"surrealkv://{LOCAL / 'billing'}"
PORTAL_URL = os.environ.get("PORTAL_URL", "")
ARIZE_PROJECT = os.environ.get("BILLINGREP_ARIZE_PROJECT") or "ai-billing-rep"
ARIZE_URL = os.environ.get("ARIZE_URL") or "https://app.arize.com"
VOICE = os.environ.get("BILLINGREP_VOICE") == "1"  # ElevenLabs message: off for the demo
TODAY = os.environ.get("DEMO_TODAY") or "2026-10-16"  # the demo's "now", so dates stay stable


def has(*keys: str) -> bool:
    return all(os.environ.get(k) for k in keys)
