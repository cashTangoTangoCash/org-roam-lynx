#!/usr/bin/env python3
import curses
import os
import sqlite3
import sys

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

    self.conn = sqlite3.connect(self.db_path)
    self.cursor = self.conn.cursor()

    # Navigation state
    self.history = []  # Stack of node tuples: (id, title, file)
    self.current_node = None  # (id, title, file)
    self.connections = []  # List of connection dicts
    self.selected_idx = 0
    self.top_idx = 0  # Viewport scroll offset

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

  def load_connections(self, node_id):
    """Fetch incoming and outgoing ID links for the given node."""
    connections = []

    # 1. Outgoing Links (Forward Links)
    sql_out = """
            SELECT n.id, n.title, n.file
            FROM links l
            JOIN nodes n ON l.dest = n.id
            WHERE l.source = ? AND l.type = '"id"';
        """
    self.cursor.execute(sql_out, (node_id,))
    for row in self.cursor.fetchall():
      title = row[1].strip('"') if row[1] else "Untitled"
      connections.append(
          {"type": "OUT", "id": row[0], "title": title, "file": row[2]}
      )

    # 2. Incoming Links (Backlinks)
    sql_in = """
            SELECT n.id, n.title, n.file
            FROM links l
            JOIN nodes n ON l.source = n.id
            WHERE l.dest = ? AND l.type = '"id"';
        """
    self.cursor.execute(sql_in, (node_id,))
    for row in self.cursor.fetchall():
      title = row[1].strip('"') if row[1] else "Untitled"
      connections.append(
          {"type": "IN ", "id": row[0], "title": title, "file": row[2]}
      )

    return connections

  def run(self, stdscr):
    curses.curs_set(0)
    curses.use_default_colors()

    # Color setup
    curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_CYAN)  # Selected
    curses.init_pair(2, curses.COLOR_GREEN, -1)  # Backlinks
    curses.init_pair(3, curses.COLOR_YELLOW, -1)  # Outlinks
    curses.init_pair(4, curses.COLOR_BLUE, -1)  # Header

    self.current_node = self.find_initial_node()
    self.connections = self.load_connections(self.current_node[0])

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
      stdscr.addstr(
          height - 1,
          0,
          " [j/k/PgDn/PgUp]: Move | [l/→/Enter]: Jump | [h/←/Backspace]: Back |"
          " [q]: Quit"[: width - 1],
          curses.A_REVERSE,
      )

      stdscr.refresh()

      # --- Handle Input ---
      key = stdscr.getch()

      if key in (ord("q"), ord("Q")):
        break

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
        if self.history:
          self.current_node = self.history.pop()
          self.connections = self.load_connections(self.current_node[0])
          self.selected_idx = 0
          self.top_idx = 0


def main():
  start_title = sys.argv[1] if len(sys.argv) > 1 else START_NODE_TITLE
  db_path = DEFAULT_DB

  nav = OrgRoamNavigator(db_path, start_title)
  curses.wrapper(nav.run)


if __name__ == "__main__":
  main()
