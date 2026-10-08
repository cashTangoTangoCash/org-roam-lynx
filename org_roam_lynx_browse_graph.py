#!/usr/bin/env python3
import subprocess
import curses
import os
import sqlite3
import sys
import time
import re
import argparse
from pathlib import Path

# ----------------------------------------------------------------------
# Configuration / Hardcoded Defaults
# ----------------------------------------------------------------------

def resolve_db_path(cli_db=None):
  """--db, then $ORG_ROAM_DB, then XDG location, then ~/.emacs.d."""
  for explicit in (cli_db, os.environ.get("ORG_ROAM_DB")):
    if explicit:
      return os.path.expanduser(explicit)  # trust it; error later if missing

  xdg = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
  xdg_db = os.path.join(xdg, "emacs", "org-roam.db")
  if os.path.exists(xdg_db):
    return xdg_db
  return os.path.expanduser("~/.emacs.d/org-roam.db")

START_NODE_TITLE = "a bike accident and injury"
PREVIEW_MIN_HEIGHT = 16    # hide the pane on very short terminals
MAX_READ_CHARS = 200_000   # cap on how much of a file we read
MAX_BODY_LINES = 4         # body lines shown per heading (poor man's folding)
STUB_WORDS = 40            # fewer words than this gets flagged as a stub
HEADING_PAIRS = (4, 5, 6, 3)  # curses color pairs for heading levels 1-4+

HEADING_RE = re.compile(r"^(\*+)\s+(.*)")
DRAWER_START_RE = re.compile(r"^\s*:[A-Za-z_-]+:\s*$")
DRAWER_END_RE = re.compile(r"^\s*:END:\s*$", re.IGNORECASE)
LINK_RE = re.compile(r"\[\[[^\]]*\]\[([^\]]*)\]\]|\[\[([^\]]*)\]\]")

class OrgRoamNavigator:

  def __init__(self, db_path, initial_title, initial_id=None):
    self.db_path = db_path
    self.initial_title = initial_title
    self.initial_id = initial_id
    
    if not os.path.exists(self.db_path):
      print(f"Error: Database not found at {self.db_path}")
      sys.exit(1)

    db_uri = Path(self.db_path).resolve().as_uri() + "?mode=ro"
    self.conn = sqlite3.connect(db_uri, uri=True, timeout=10)
    self.cursor = self.conn.cursor()

    # Navigation state
    self.history: list[tuple[str, str, str]] = []
    self.selected_idx = 0
    self.top_idx = 0  # Viewport scroll offset
    self.status = ""  # Transient message shown in the footer
    self.db_ok = True  # False if the most recent query failed
    self.current_node: tuple[str, str, str] = self.find_initial_node()
    self.connections = self.load_connections(self.current_node[0])
    self.show_preview = True  # set False to start with the pane hidden
    self.preview_cache: dict = {}  # (node_id, file mtime_ns) -> preview
    
  def find_initial_node(self):
    """Start node: by ID if given, else exact title, else substring, else first."""
    if self.initial_id:
      node_id = self.initial_id.strip('"')
      # org-roam stores IDs as printed elisp strings, i.e. wrapped in quotes
      rows = self._query(
          "SELECT id, title, file FROM nodes WHERE id = ? OR id = ? LIMIT 1;",
          (f'"{node_id}"', node_id),
      )
      if rows:
        return (rows[0][0], self._clean(rows[0][1]), rows[0][2])
      print(
          f"Error: No node with ID {node_id} in {self.db_path}",
          file=sys.stderr,
      )
      sys.exit(1)

    if self.initial_title:
      t = self.initial_title
      rows = self._query(
          "SELECT id, title, file FROM nodes WHERE title = ? OR title = ?"
          " LIMIT 1;",
          (f'"{t}"', t),
      )
      if not rows:
        rows = self._query(
            "SELECT id, title, file FROM nodes WHERE title LIKE ? LIMIT 1;",
            (f"%{t}%",),
        )
      if rows:
        return (rows[0][0], self._clean(rows[0][1]), rows[0][2])

    # Fallback if nothing matched
    rows = self._query("SELECT id, title, file FROM nodes LIMIT 1;")
    if not rows:
      print("Error: No nodes found in database.", file=sys.stderr)
      sys.exit(1)
    return (rows[0][0], self._clean(rows[0][1]), rows[0][2])

  @staticmethod
  def _clean(title):
    return title.strip('"') if title else "Untitled"

  def _query(self, sql, params=()):
    """Run a SELECT with one retry. On failure, set status and return []."""
    self.db_ok = True
    for attempt in range(2):
      try:
        self.cursor.execute(sql, params)
        return self.cursor.fetchall()
      except sqlite3.Error as e:
        if attempt == 0:
          time.sleep(0.2)
          continue
        self.db_ok = False
        self.status = f"DB error: {e}"
    return []

  def lookup_node(self, node_id):
    """Re-read (id, title, file) by ID. Returns None if missing or on DB error.

    Check self.db_ok afterward to tell the two apart.
    """
    rows = self._query(
        "SELECT id, title, file FROM nodes WHERE id = ?;", (node_id,)
    )
    if not rows:
      return None
    row = rows[0]
    return (row[0], self._clean(row[1]), row[2])

  @staticmethod
  def _strip_links(s):
    """[[id:x][Desc]] -> Desc, [[target]] -> target."""
    return LINK_RE.sub(lambda m: m.group(1) or m.group(2) or "", s)

  def _count(self, sql, node_id):
    rows = self._query(sql, (node_id,))
    return rows[0][0] if rows else "?"

  def _summarize_org(self, text, level):
    """Return (word_count, subheading_count, styled_lines) for a node's text.

    styled_lines is a list of (text, kind, heading_level) tuples.
    """
    lines = text.splitlines()
    if level:
      # Heading node: stop at the next heading of the same or higher level
      for i, line in enumerate(lines[1:], 1):
        m = HEADING_RE.match(line)
        if m and len(m.group(1)) <= level:
          lines = lines[:i]
          break

    out = []
    words = 0
    subheads = 0
    in_drawer = False
    shown = 0   # body lines shown under the current heading
    hidden = 0  # body lines collapsed under the current heading

    def flush_hidden():
      nonlocal hidden
      if hidden:
        plural = "s" if hidden != 1 else ""
        out.append((f"  … {hidden} more line{plural}", "dim", 0))
        hidden = 0

    for i, line in enumerate(lines):
      if in_drawer:
        if DRAWER_END_RE.match(line):
          in_drawer = False
        continue
      if DRAWER_START_RE.match(line):
        in_drawer = True
        continue
      if line.lstrip().startswith("#+"):
        continue

      m = HEADING_RE.match(line)
      if m:
        flush_hidden()
        shown = 0
        if not (i == 0 and level):  # don't count the node's own heading
          subheads += 1
        words += len(m.group(2).split())
        out.append((self._strip_links(line.rstrip()), "heading", len(m.group(1))))
        continue

      body = self._strip_links(line).strip()
      if not body:
        continue
      words += len(body.split())
      if shown < MAX_BODY_LINES:
        out.append(("  " + body, "body", 0))
        shown += 1
      else:
        hidden += 1

    flush_hidden()
    return words, subheads, out

  def get_preview(self, conn):
    """Build (or fetch from cache) the preview for a connection dict."""
    node_id = conn["id"]
    rows = self._query(
        "SELECT file, level, pos FROM nodes WHERE id = ?;", (node_id,)
    )
    if not rows:
      return {"stats": "Node not found in database", "lines": []}

    file_path, level, pos = rows[0]
    file_path = (file_path or "").strip('"')
    try:
      mtime = os.stat(file_path).st_mtime_ns
    except OSError:
      return {"stats": "File not found", "lines": [(file_path, "dim", 0)]}

    key = (node_id, mtime)
    cached = self.preview_cache.get(key)
    if cached:
      return cached

    try:
      with open(file_path, encoding="utf-8", errors="replace") as f:
        text = f.read(MAX_READ_CHARS)
    except OSError as e:
      return {"stats": f"Cannot read file: {e.strerror}", "lines": []}

    # Heading-level nodes: pos is a 1-based character offset into the file
    if level and pos:
      text = text[pos - 1 :]

    words, subheads, lines = self._summarize_org(text, level)
    n_out = self._count(
        "SELECT COUNT(*) FROM links WHERE source = ? AND type = '\"id\"';",
        node_id,
    )
    n_in = self._count(
        "SELECT COUNT(*) FROM links WHERE dest = ? AND type = '\"id\"';",
        node_id,
    )

    kind = f"heading (level {level})" if level else "file"
    stats = (
        f"{kind} · {words} words · {subheads} subheadings"
        f" · {n_out} out / {n_in} in"
    )
    if words < STUB_WORDS:
      stats += " · looks like a stub"

    result = {"stats": stats, "lines": lines}
    if self.db_ok:  # don't cache a result built from a failed query
      if len(self.preview_cache) > 500:
        self.preview_cache.clear()
      self.preview_cache[key] = result
    return result

  def draw_preview(self, stdscr, top, rows, width):
    """Draw the preview pane into screen rows [top, top + rows)."""

    def put(y, text, attr=0):
      try:
        stdscr.addstr(y, 2, text[: width - 4], attr)
      except curses.error:
        pass

    try:
      stdscr.addstr(top, 0, "─" * (width - 1))
    except curses.error:
      pass

    if not self.connections:
      return
    preview = self.get_preview(self.connections[self.selected_idx])
    put(top + 1, preview["stats"], curses.A_BOLD)

    body_rows = rows - 2
    lines = preview["lines"] or [("(no body text)", "dim", 0)]
    truncated = len(lines) > body_rows
    for i, (text, kind, lvl) in enumerate(lines[:body_rows]):
      if truncated and i == body_rows - 1:
        text, kind, lvl = "  …", "dim", 0
      if kind == "heading":
        pair = HEADING_PAIRS[min(lvl, len(HEADING_PAIRS)) - 1]
        attr = curses.color_pair(pair) | curses.A_BOLD
      elif kind == "dim":
        attr = curses.A_DIM
      else:
        attr = 0
      put(top + 2 + i, text, attr)

  def load_connections(self, node_id):
    """Fetch incoming and outgoing ID links for the given node."""
    connections = []

    sql_out = """
            SELECT n.id, n.title, n.file
            FROM links l
            JOIN nodes n ON l.dest = n.id
            WHERE l.source = ? AND l.type = '"id"';
        """
    for row in self._query(sql_out, (node_id,)):
      connections.append(
          {"type": "OUT", "id": row[0], "title": self._clean(row[1]), "file": row[2]}
      )

    sql_in = """
            SELECT n.id, n.title, n.file
            FROM links l
            JOIN nodes n ON l.source = n.id
            WHERE l.dest = ? AND l.type = '"id"';
        """
    for row in self._query(sql_in, (node_id,)):
      connections.append(
          {"type": "IN ", "id": row[0], "title": self._clean(row[1]), "file": row[2]}
      )

    return connections

  def visit_in_emacs(self, node):
    """Open a node in the running Emacs via emacsclient (non-blocking)."""
    node_id, _, file_path = node

    # org-roam stores ids/files as printed elisp strings, i.e. with quotes
    node_id = node_id.strip('"')
    file_path = (file_path or "").strip('"')

    def esc(s):
      return s.replace("\\", "\\\\").replace('"', '\\"')

    # Visit by ID (lands on the right heading for non-file-level nodes);
    # fall back to just opening the file if the ID isn't found.
    elisp = (
        f'(let ((n (org-roam-node-from-id "{esc(node_id)}")))'
        f' (if n (org-roam-node-visit n)'
        f'   (find-file "{esc(file_path)}"))'
        f' (select-frame-set-input-focus (selected-frame)))'
    )

    try:
      result = subprocess.run(
          ["emacsclient", "-n", "--eval", elisp],
          capture_output=True,
          text=True,
          timeout=5,
      )
      if result.returncode == 0:
        self.status = "Opened in Emacs"
      else:
        err = (result.stderr or result.stdout).strip().splitlines()
        self.status = f"emacsclient failed: {err[0] if err else 'unknown error'}"
    except FileNotFoundError:
      self.status = "emacsclient not found in PATH"
    except subprocess.TimeoutExpired:
      self.status = "emacsclient timed out"

  def go_back(self):
    """Pop history, re-reading each node and skipping any that were deleted."""
    while self.history:
      prev = self.history.pop()
      node = self.lookup_node(prev[0])
      if node:
        self.current_node = node
        self.connections = self.load_connections(node[0])
        self.selected_idx = 0
        self.top_idx = 0
        return
      if not self.db_ok:
        self.history.append(prev)  # DB hiccup, not a deletion: keep it
        return
      self.status = f"Skipped deleted node: {prev[1]}"

  def refresh(self):
    """Re-read the current node and its connections, keeping the selection."""
    if self.current_node is None:
      return
    self.preview_cache.clear() 

    selected_key = None
    if self.connections and self.selected_idx < len(self.connections):
      c = self.connections[self.selected_idx]
      selected_key = (c["type"], c["id"])

    fresh = self.lookup_node(self.current_node[0])
    if fresh is None:
      if not self.db_ok:
        return  # status already set by _query
      # Node was deleted out from under us
      if self.history:
        self.go_back()
        self.status = "Current node was deleted; went back"
      else:
        self.connections = []
        self.selected_idx = 0
        self.top_idx = 0
        self.status = "Current node no longer exists"
      return

    self.current_node = fresh  # picks up renamed title / moved file
    new_conns = self.load_connections(fresh[0])
    if not self.db_ok:
      return  # keep the old list rather than blanking it
    self.connections = new_conns

    # Restore selection by (type, id); otherwise clamp to the new length
    for i, c in enumerate(self.connections):
      if (c["type"], c["id"]) == selected_key:
        self.selected_idx = i
        break
    else:
      self.selected_idx = min(
          self.selected_idx, max(0, len(self.connections) - 1)
      )

    if not self.status:
      self.status = "Refreshed"
      
  def run(self, stdscr):
    curses.curs_set(0)
    curses.use_default_colors()

    # Color setup
    curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_CYAN)  # Selected
    curses.init_pair(2, curses.COLOR_GREEN, -1)  # Backlinks
    curses.init_pair(3, curses.COLOR_YELLOW, -1)  # Outlinks
    curses.init_pair(4, curses.COLOR_BLUE, -1)  # Header
    curses.init_pair(5, curses.COLOR_MAGENTA, -1)  # Heading level 2
    curses.init_pair(6, curses.COLOR_CYAN, -1)  # Heading level 3
    
    while True:
      stdscr.clear()
      height, width = stdscr.getmaxyx()

      # --- Render Header ---
      _, title, file_path = self.current_node
      stdscr.attron(curses.color_pair(4) | curses.A_BOLD)
      stdscr.addstr(0, 0, f" NODE: {title}"[: width - 1])
      stdscr.attroff(curses.color_pair(4) | curses.A_BOLD)

      stdscr.addstr(1, 0, f" File: {file_path}"[: width - 1], curses.A_DIM)

      conn_count = len(self.connections)
      curr_pos = (
          f"{self.selected_idx + 1}/{conn_count}" if conn_count else "0/0"
      )
      stdscr.addstr(
          2,
          0,
          f" History Stack: {len(self.history)} | Connections: {conn_count}"
          f" (Item {curr_pos})"[: width - 1],
      )
      stdscr.addstr(3, 0, "─" * (width - 1))

      # --- Calculate Viewport Bounds ---
      preview_rows = 0
      if self.show_preview and height >= PREVIEW_MIN_HEIGHT:
        preview_rows = (height - 6) // 2
      max_items = max(1, height - 6 - preview_rows)

      # Keep selected item inside viewport
      if self.selected_idx < self.top_idx:
        self.top_idx = self.selected_idx
      elif self.selected_idx >= self.top_idx + max_items:
        self.top_idx = self.selected_idx - max_items + 1

      visible_connections = self.connections[
          self.top_idx : self.top_idx + max_items
      ]

      # --- Render Connections ---
      if not self.connections:
        stdscr.addstr(
            5, 2, "< No outgoing links or backlinks >", curses.A_DIM
        )
      else:
        for idx, conn in enumerate(visible_connections):
          actual_idx = self.top_idx + idx
          row_y = 5 + idx
          prefix = f"[{conn['type']}] "
          item_str = f"{prefix}{conn['title']}"[: width - 4]

          if actual_idx == self.selected_idx:
            stdscr.attron(curses.color_pair(1))
            stdscr.addstr(row_y, 2, item_str.ljust(width - 4))
            stdscr.attroff(curses.color_pair(1))
          else:
            color = (
                curses.color_pair(2)
                if conn["type"] == "IN "
                else curses.color_pair(3)
            )
            stdscr.attron(color)
            stdscr.addstr(row_y, 2, prefix)
            stdscr.attroff(color)
            stdscr.addstr(row_y, 2 + len(prefix), conn["title"])

      if preview_rows:
        self.draw_preview(stdscr, height - 1 - preview_rows, preview_rows, width)
            
      # --- Render Footer ---
      # footer = (
      #     " [j/k/PgDn/PgUp]: Move | [l/→/Enter]: Jump | [h/←/Backspace]: Back |"
      #     " [r]: Refresh | [e]: Emacs | [q]: Quit"
      # )
      footer = (
          " j/k:Move  l:Jump  h:Back  r:Refresh  e:Emacs  p:Preview  q:Quit"
      )
      
      if self.status:
        footer = f" {self.status}"
        self.status = ""  # clears on next redraw (i.e. after next keypress)
      stdscr.addstr(height - 1, 0, footer.ljust(width - 1)[: width - 1], curses.A_REVERSE)

      stdscr.refresh()

      # --- Handle Input ---
      key = stdscr.getch()

      if key in (ord("q"), ord("Q")):
        break

      elif key in (ord("e"), ord("E")):
        node = self.lookup_node(self.current_node[0])
        if node:
          self.visit_in_emacs(node)
        elif self.db_ok:
          self.status = "Node no longer exists in the database"

      elif key in (ord("p"), ord("P")):
        self.show_preview = not self.show_preview
          
      elif key in (ord("r"), ord("R")):
        self.refresh()
        
      # Motion Down (Single Line)
      elif key in (curses.KEY_DOWN, ord("j")):
        if self.connections and self.selected_idx < len(self.connections) - 1:
          self.selected_idx += 1

      # Motion Up (Single Line)
      elif key in (curses.KEY_UP, ord("k")):
        if self.selected_idx > 0:
          self.selected_idx -= 1

      # Page Down (Jump max_items forward)
      elif key in (curses.KEY_NPAGE, 6, ord(" ")):  # KEY_NPAGE, Ctrl+f, Space
        if self.connections:
          self.selected_idx = min(
              len(self.connections) - 1, self.selected_idx + max_items
          )

      # Page Up (Jump max_items backward)
      elif key in (curses.KEY_PPAGE, 2):  # KEY_PPAGE, Ctrl+b
        if self.connections:
          self.selected_idx = max(0, self.selected_idx - max_items)

      # Motion Right / Enter (Traverse node)
      elif key in (curses.KEY_RIGHT, ord("l"), 10, 13):
        if self.connections:
          target = self.connections[self.selected_idx]
          self.history.append(self.current_node)
          self.current_node = (
              target["id"],
              target["title"],
              target["file"],
          )
          self.connections = self.load_connections(self.current_node[0])
          self.selected_idx = 0
          self.top_idx = 0

      # Motion Left / Backspace (Pop history stack)
      elif key in (curses.KEY_LEFT, ord("h"), 8, 127, curses.KEY_BACKSPACE):
          self.go_back()

def main():
  parser = argparse.ArgumentParser(
      description="Browse an Org-roam node network in the terminal."
  )
  parser.add_argument(
      "title",
      nargs="?",
      default=START_NODE_TITLE,
      help="start at the node with this title (exact match preferred)",
  )
  parser.add_argument(
      "--id",
      dest="node_id",
      help="start at the node with this Org-roam ID (overrides title)",
  )
  parser.add_argument(
      "--db", help="path to org-roam.db (default: see resolution order)"
  )
  args = parser.parse_args()

  nav = OrgRoamNavigator(resolve_db_path(args.db), args.title, args.node_id)
  curses.wrapper(nav.run)

if __name__ == "__main__":
  main()
