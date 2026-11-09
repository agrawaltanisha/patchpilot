"""
Central configuration for the Agentic GitHub Issue Resolver.

Loads secrets/settings from a .env file (see .env.example) or from
real environment variables. Nothing in this file should be edited
directly -- override values via .env instead.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# --- GitHub -----------------------------------------------------------------
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
GITHUB_API_URL = "https://api.github.com"

# --- LLM (Anthropic Claude) ---------------------------------------------------
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
# Check https://docs.claude.com for the current recommended model name.
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

# --- Agent behaviour ----------------------------------------------------------
# Directories/files the code search + repo copy step should never touch.
IGNORED_DIRS = {
    ".git", "__pycache__", ".venv", "venv", "env", "node_modules",
    ".pytest_cache", ".mypy_cache", "dist", "build", ".idea", ".vscode",
}
# File extensions considered "source code" for search/read purposes.
SOURCE_EXTENSIONS = {".py"}

# Where cloned/copied repos and generated artifacts are placed.
WORKDIR_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "workdir")
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

MAX_FILES_TO_INSPECT = 5       # top-N files the agent reads in full
MAX_FILE_CHARS = 6000          # truncate huge files before sending to the LLM
TEST_TIMEOUT_SECONDS = 120
