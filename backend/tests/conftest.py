"""Test configuration: disable external API calls to keep tests fast and deterministic."""

import os

# Disable weather API calls during tests
os.environ["H2BRAIN_DISABLE_WEATHER"] = "1"
