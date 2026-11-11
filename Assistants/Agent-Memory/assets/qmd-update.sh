#!/usr/bin/env bash
# L4: re-index the local search collections. Run it a few times a day (cron: 0 */<EVERY_N_HOURS> * * *).
# One-time setup, one collection per area (the agent's own memory kept apart from the owner's content):
#   npx @tobilu/qmd collection add ~/Vault/Agent/Journal --name agent-journal
#   npx @tobilu/qmd collection add ~/Vault/Agent/Tools   --name agent-tools
#   npx @tobilu/qmd collection add ~/Vault/Agent/Tasks   --name agent-tasks
#   npx @tobilu/qmd collection add ~/Vault/Agent/Memory  --name agent-memory
#   npx @tobilu/qmd collection add ~/Vault/Notes         --name notes
# Query: npx @tobilu/qmd query "<question>" -c agent-journal     (flags vary by version: check `qmd --help`)
set -euo pipefail
# Force the Node runtime: Bun's SQLite lacks extension loading, which breaks sqlite-vec.
export PATH="/opt/homebrew/bin:$PATH"
unset BUN_INSTALL
npx --yes @tobilu/qmd update
npx --yes @tobilu/qmd embed
