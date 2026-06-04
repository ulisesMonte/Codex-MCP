"""Shared runtime constants (single source of truth)."""
from __future__ import annotations

import os

MAX_VALIDATION_RETRIES = int(os.getenv("MAX_VALIDATION_RETRIES", "3"))
