#!/usr/bin/env python3
import curses
import os
import sqlite3
import sys

# Default Org-roam database location
DEFAULT_DB = os.path.expanduser("~/.emacs.d/org-roam.db")


class OrgRoamNavigator:

    def __init__(self, db_path):
        self.db_path = db_path
        if not os.path.exists(self.db_path):
            print(f"Error: Database not found at {self.db_path}")
            sys.exit(1)
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()

        # Navigation state
        self.history = []  # Stack of node tuples: (id, title, file)
        self.current_node = None  # (id, title, file)
        self.connections = []  # List of dicts representing links
        self.selected_idx = 0

    def fetch_first_node(self):
        """Fetch the first available node to start browsing."""
        self.cursor.execute("SELECT id, title, file FROM nodes LIMIT 1;")
        row = self.cursor.fetchone()
        if not row:
            print("Error: No nodes found in database.")
            sys.exit(1)
        # Clean title quotes if present in SQLite
        title = row[1].strip('"') if row[1] else "Untitled"
        return (row[0], title, row[2])

    def load_connections(self, node_id):
        """Fetch incoming and outgoing ID links for the current node."""
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
        # Setup curses environment
        curses.curs_set(0)
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_CYAN)  # Selected
        curses.init_pair(2, curses.COLOR_GREEN, -1)  # Backlinks
        curses.init_pair(3, curses.COLOR_YELLOW, -1)  # Outlinks
        curses.init_pair(4, curses.COLOR_BLUE, -1)  # Header/Metadata

        self.current_node = self.fetch_first_node()
        self.connections = self.load_connections(self.current_node[0])

        while True:
            stdscr.clear()
            height, width = stdscr.getmaxyx()

            # Render Header / Node Details
            _, title, file_path = self.current_node
            stdscr.attron(curses.color_pair(4) | curses.A_BOLD)
            stdscr.addstr(0, 0, f" NODE: {title}"[: width - 1])
            stdscr.attroff(curses.color_pair(4) | curses.A_BOLD)

            stdscr.addstr(
                1, 0, f" File: {file_path}"[: width - 1], curses.A_DIM
            )
            stdscr.addstr(
                2,
                0,
                f" History depth: {len(self.history)} | Connections: {len(self.connections)}"[: width - 1],
            )
            stdscr.addstr(3, 0, "─" * (width - 1))

            # Render Connections (List)
            max_items = height - 6
            if not self.connections:
                stdscr.addstr(
                    5, 2, "< No outgoing links or backlinks found >", curses.A_DIM
                )
            else:
                for idx, conn in enumerate(self.connections[:max_items]):
                    row_y = 5 + idx
                    prefix = f"[{conn['type']}] "
                    item_str = f"{prefix}{conn['title']}"[: width - 4]

                    # Highlight selection
                    if idx == self.selected_idx:
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

            # Render Footer Key Hints
            stdscr.addstr(
                height - 1,
                0,
                " [j/k or ↑/↓]: Move | [l or →/Enter]: Jump | [h or ←/Backspace]: Back | [q]: Quit"[: width - 1],
                curses.A_REVERSE,
            )

            stdscr.refresh()

            # Key Handling
            key = stdscr.getch()

            if key in (ord("q"), ord("Q")):
                break

            # Motion Down
            elif key in (curses.KEY_DOWN, ord("j")):
                if self.connections and self.selected_idx < len(
                    self.connections
                ) - 1:
                    self.selected_idx += 1

            # Motion Up
            elif key in (curses.KEY_UP, ord("k")):
                if self.selected_idx > 0:
                    self.selected_idx -= 1

            # Motion Right / Enter (Drill Down)
            elif key in (curses.KEY_RIGHT, ord("l"), 10, 13):
                if self.connections:
                    target = self.connections[self.selected_idx]
                    self.history.append(self.current_node)
                    self.current_node = (
                        target["id"],
                        target["title"],
                        target["file"],
                    )
                    self.connections = self.load_connections(
                        self.current_node[0]
                    )
                    self.selected_idx = 0

            # Motion Left / Backspace (Pop History)
            elif key in (curses.KEY_LEFT, ord("h"), 8, 127, curses.KEY_BACKSPACE):
                if self.history:
                    self.current_node = self.history.pop()
                    self.connections = self.load_connections(
                        self.current_node[0]
                    )
                    self.selected_idx = 0


def main():
    db_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DB
    nav = OrgRoamNavigator(db_path)
    curses.wrapper(nav.run)


if __name__ == "__main__":
    main()
