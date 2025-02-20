#!/bin/bash
# Load environment variables from .env file

# Export only what's needed for external tools
export LOG_LEVEL=ERROR
export ANTHROPIC_API_KEY="$(grep ANTHROPIC_API_KEY eloo/.env | cut -d '=' -f2-)"
