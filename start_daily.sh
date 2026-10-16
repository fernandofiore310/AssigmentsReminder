#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
: "${CANVAS_TOKEN:?Configure CANVAS_TOKEN nas configurações do ambiente}"
: "${TELEGRAM_BOT_TOKEN:?Configure TELEGRAM_BOT_TOKEN nas configurações do ambiente}"
: "${TELEGRAM_CHAT_ID:?Configure TELEGRAM_CHAT_ID nas configurações do ambiente}"
exec python3 -u reminder.py --channel telegram --daily-at 08:00 --timezone America/Los_Angeles
