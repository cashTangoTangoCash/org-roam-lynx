#!/usr/bin/env bash

# Paths: ORG_ROAM_DB wins; otherwise XDG location, then ~/.emacs.d
if [[ -n "$ORG_ROAM_DB" ]]; then
    DB_PATH="$ORG_ROAM_DB"
else
    DB_PATH="${XDG_CONFIG_HOME:-$HOME/.config}/emacs/org-roam.db"
    [[ ! -f "$DB_PATH" ]] && DB_PATH="$HOME/.emacs.d/org-roam.db"
fi
PYTHON_NAV_SCRIPT="${ROAM_LYNX_PY:-$HOME/.local/bin/org_roam_lynx_browse_graph.py}"

# --- HELP HANDLERS ---
show_brief_help() {
    cat << 'EOF'
Usage: org-roam-lynx-find-starting-node-then-browse-graph.sh [OPTION] [SEARCH_TERM]

Search Org-roam nodes/aliases using fzf and open the selection in the terminal Lynx-style node browser.

Options:
  -h, --help            Show this brief command-line help message and exit.

Environment:
  ORG_ROAM_DB           Path to org-roam.db (default: ~/.config/emacs/org-roam.db,
                        then ~/.emacs.d/org-roam.db)
  ROAM_LYNX_PY          Path to org_roam_lynx_browse_graph.py

Examples:
  <script>              Interactive fzf search through all notes (sorted by mtime).
  <script> bashrc       Pre-filtered fzf search for "bashrc" before entering browser.
EOF
}

case "$1" in
    -h|--help) show_brief_help; exit 0 ;;
esac

# Validations
[[ ! -f "$DB_PATH" ]] && { echo "Error: Database not found at $DB_PATH" >&2; exit 1; }
[[ ! -f "$PYTHON_NAV_SCRIPT" ]] && { echo "Error: Python navigator not found at $PYTHON_NAV_SCRIPT" >&2; exit 1; }

SEARCH_TERM="$1"

# Columns: 1=title, 2=aliases, 3=file, 4=id (hidden in fzf, used for handoff)
BASE_SQL="SELECT nodes.title, COALESCE(GROUP_CONCAT(aliases.alias, ' | '), '') AS alias_list, nodes.file, nodes.id FROM nodes JOIN files ON nodes.file = files.file LEFT JOIN aliases ON nodes.id = aliases.node_id WHERE nodes.title IS NOT NULL AND nodes.title != '' GROUP BY nodes.id"

if [[ -z "$SEARCH_TERM" ]]; then
    QUERY="$BASE_SQL ORDER BY files.mtime DESC;"
    RESULTS=$(sqlite3 -separator $'\t' "$DB_PATH" "$QUERY" | tr -d '"')
else
    SAFE_TERM="${SEARCH_TERM//\'/\'\'}"
    # Search both primary title AND alias columns
    QUERY="$BASE_SQL HAVING nodes.title LIKE '%$SAFE_TERM%' OR alias_list LIKE '%$SAFE_TERM%' ORDER BY files.mtime DESC;"
    RESULTS=$(sqlite3 -separator $'\t' "$DB_PATH" "$QUERY" | tr -d '"')
fi

MATCH_COUNT=$(echo "$RESULTS" | sed '/^$/d' | wc -l)

if [[ $MATCH_COUNT -eq 0 ]]; then
    echo "No Org-roam nodes or aliases matching: \"$SEARCH_TERM\"" >&2
    exit 1
elif [[ $MATCH_COUNT -eq 1 ]]; then
    SELECTION="$RESULTS"
else
    # fzf shows columns 1-2 only; live file preview comes from column 3
    SELECTION=$(echo "$RESULTS" \
        | fzf --exact \
              --delimiter=$'\t' \
              --with-nth=1,2 \
              --tiebreak=index \
              ${SEARCH_TERM:+--query="$SEARCH_TERM"} \
              --preview 'head -n 30 {3}' \
              --preview-window=right:50%:wrap)
fi

if [[ -n "$SELECTION" ]]; then
    NODE_ID=$(echo "$SELECTION" | cut -f4)

    # Hand off by ID (unambiguous) and pass the DB path so both scripts agree
    python3 "$PYTHON_NAV_SCRIPT" --db "$DB_PATH" --id "$NODE_ID"
fi
