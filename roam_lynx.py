#!/usr/bin/env python3
import subprocess
import curses
import os
import sqlite3
import sys
import time

# ----------------------------------------------------------------------
# Configuration / Hardcoded Defaults
# ----------------------------------------------------------------------
DEFAULT_DB = os.path.expanduser("~/.emacs.d/org-roam.db")
START_NODE_TITLE = "a bike accident and injury"


class OrgRoamNavigator:

  def __init__(self, db_path, initial_title):
    self.db_path = db_path
    self.initial_title = initial_title

    if not os.path.exists(self.db_path):
      print(f"Error: Database not found at {self.db_path}")
      sys.exit(1)

    self.conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True, timeout=10)
    self.cursor = self.conn.cursor()

    # Navigation state
    self.history: list[tuple[str, str, str]] = []
    self.selected_idx = 0
    self.top_idx = 0  # Viewport scroll offset
    self.status = ""  # Transient message shown in the footer
    self.db_ok = True  # False if the most recent query failed
    self.current_node: tuple[str, str, str] = self.find_initial_node()
    self.connections = self.load_connections(self.current_node[0])
    
  def find_initial_node(self):
    """Find node matching START_NODE_TITLE or fall back to the first available node."""
    if self.initial_title:
      sql = "SELECT id, title, file FROM nodes WHERE title LIKE ? LIMIT 1;"
      self.cursor.execute(sql, (f"%{self.initial_title}%",))
      row = self.cursor.fetchone()
      if row:
        title = row[1].strip('"') if row[1] else "Untitled"
        return (row[0], title, row[2])

    # Fallback if hardcoded title isn't found
    self.cursor.execute("SELECT id, title, file FROM nodes LIMIT 1;")
    row = self.cursor.fetchone()
    if not row:
      print("Error: No nodes found in database.")
      sys.exit(1)

    title = row[1].strip('"') if row[1] else "Untitled"
    return (row[0], title, row[2])

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
      max_items = max(1, height - 6)

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

      # --- Render Footer ---
      footer = (
          " [j/k/PgDn/PgUp]: Move | [l/→/Enter]: Jump | [h/←/Backspace]: Back |"
          " [r]: Refresh | [e]: Emacs | [q]: Quit"
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
  start_title = sys.argv[1] if len(sys.argv) > 1 else START_NODE_TITLE
  db_path = DEFAULT_DB

  nav = OrgRoamNavigator(db_path, start_title)
  curses.wrapper(nav.run)


if __name__ == "__main__":
  main()
