# Full Transcript: 20261005-midnight-commander-style-org-roam-node-explorer


# PROMPT 1
I have found the gemini system to be surpisingly effective at creating scripts that make use of the org roam database to do useful things.  Let's explore a concept that comes to mind.  I like the midnight commander file manager with the lynx-like motion.  my broad concept is a piece of software that runs in the terminal and allows us to do that lynx-like motion through the org roam nodes according to their linking relationships.  I don't know enough about the architecture of org roam to know if what I am talking about is easy or hard.  In emacs, I have of course used the org roam buffer, and it is pretty quick to roam around that way, but there is some friction of using your fingers to do various keyboard combinations.  the lynx like motion in midnight commander AFAIK is just racing around via arrow keys.  another thing I have played with is org roam UI, and I found it to run so very slow and I got fed up with it.  If were a more diligent partner, I would review all the other related stuff we made together, but I lack the patience - I just get an idea and want to throw it against the gemini system, but I don't have all the related past technical learnings at hand.

Edit: (find-file "/home/dad84/Documents/2026/20261005-midnight-commander-style-org-roam-node-explorer/chat/captures/20261005_233252_capture.md")

---

# RESPONSE 1
The concept is not only completely feasible, but SQLite and Org-roam's architecture make it surprisingly fast to implement.

Because Org-roam indexes every node, property, tag, and link directly into a local SQLite database (`org-roam.db`), you do not need to parse Emacs Lisp or scan raw `.org` files on disk every time you move. Quoting the database via a standalone Python or Bash CLI takes milliseconds—giving you instant, zero-lag navigation in the terminal without touching Emacs or spinning up a heavy browser renderer like Org-roam UI.

---

### Why This Concept Works So Well

1. **The Database Is Already Built:** Org-roam maintains a relational schema in `~/.config/emacs/org-roam.db` (or `~/.emacs.d/org-roam.db`).
2. **Minimal Schema, Max Speed:** Querying links to and from a node is just a single SQL `JOIN` across two tables (`nodes` and `links`).
3. **Lynx-Style Navigation Fits Graph Structures:**
* **Left Arrow (`h`):** Jump back to the parent/caller node (or previous step in history).
* **Right Arrow / Enter (`l`):** Drill into the selected linked node.
* **Up / Down (`k` / `j`):** Scroll through outgoing or incoming links for the current node.



---

### Org-roam Database Architecture

To see why this is straightforward, look at how Org-roam tracks links inside SQLite:

```
                      ┌────────────────────────┐
                      │        nodes           │
                      ├────────────────────────┤
                      │ id (UUID)              │◄──────┐
                      │ title                  │       │
                      │ file                   │       │
                      └────────────────────────┘       │
                                  │                    │
                                  │ (source)           │ (destination)
                                  ▼                    │
                      ┌────────────────────────┐       │
                      │        links           │       │
                      ├────────────────────────┤       │
                      │ source (node_id)       │       │
                      │ dest   (node_id) ──────┼───────┘
                      │ type   ("id", etc.)    │
                      └────────────────────────┘

```

#### Key Tables

* **`nodes`**: Stores `id` (UUID), `title`, `file` path, `pos` (character position in file), and tags.
* **`links`**: Stores `source` (node ID where link originates), `dest` (node ID being targeted), and `type` (e.g., `"id"` for node-to-node links).

---

### Sample SQL Queries

Because it's a standard SQLite file, you can interact with it using Python's built-in `sqlite3` library or the `sqlite3` CLI tool.

#### 1. Outgoing Links (Forward Links)

Find all nodes linked **from** the current node (`CURRENT_NODE_ID`):

```sql
SELECT n.id, n.title, n.file
FROM links l
JOIN nodes n ON l.dest = n.id
WHERE l.source = 'CURRENT_NODE_ID' AND l.type = 'id';

```

#### 2. Incoming Links (Backlinks)

Find all nodes that link **to** the current node:

```sql
SELECT n.id, n.title, n.file
FROM links l
JOIN nodes n ON l.source = n.id
WHERE l.dest = 'CURRENT_NODE_ID' AND l.type = 'id';

```

---

### Terminal TUI Options for Implementation

If we build this, there are two primary ways to approach the terminal interface:

| Framework / Tool | Pros | Best For |
| --- | --- | --- |
| **Python + `textual` / `curses**` | Instant interactive TUI, built-in arrow key bindings, rich text preview pane for Org content. | A full-featured Midnight Commander feel with split-pane view (Links on Left, Note Preview on Right). |
| **Bash + `fzf` / `dialog**` | Lightweight script utilizing SQLite CLI, minimal dependencies, near-zero code footprint. | Fast search-and-jump pipeline via terminal keyboard shortcuts. |

---

### Potential Features for a Lynx-Style Roamer

* **Dual Column View:**
* **Left Pane:** Current Node's connections divided into *Backlinks* (above) and *Forward Links* (below).
* **Right Pane:** Live preview of the selected note rendered via `pandoc` or plain text.


* **Direct Emacs Hook:** Hitting `e` or `Enter` on a highlighted node could launch `emacsclient -n +line file.org` to immediately jump to that node inside your running Emacs session.
* **History Stack:** Left arrow cleanly pops your navigation stack so you can explore sub-branches without getting lost.

Edit: (find-file "/home/dad84/Documents/2026/20261005-midnight-commander-style-org-roam-node-explorer/chat/captures/20261005_233258_capture.md")

---

# PROMPT 2
Write a prototype Python script that queries org-roam.db and lets me navigate between nodes using arrow keys in the terminal.

Edit: (find-file "/home/dad84/Documents/2026/20261005-midnight-commander-style-org-roam-node-explorer/chat/captures/20261005_233417_capture.md")

---

# RESPONSE 2
Here is a standalone, lightweight terminal navigation script written in Python using `curses` and standard `sqlite3`. It provides instant Lynx-like motion (`j`/`k` or Down/Up to select, `l` or Right/Enter to jump into links, `h` or Left/Backspace to pop back up the history stack).

### Prerequisites

The script requires access to your `org-roam.db` file. By default, it looks in `~/.config/emacs/org-roam.db`, but you can pass a custom path as a command-line argument.

```bash
python3 roam_lynx.py ~/.emacs.d/org-roam.db

```

---

### Prototype Script (`roam_lynx.py`)

```python
#!/usr/bin/env python3
import curses
import os
import sqlite3
import sys

# Default Org-roam database location
DEFAULT_DB = os.path.expanduser("~/.config/emacs/org-roam.db")


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

```

---

### How to Run

1. Make the script executable:
```bash
chmod +x roam_lynx.py

```


2. Execute directly:
```bash
./roam_lynx.py

```



### Key Controls Summary

* **`j` / Down Arrow**: Select next connection.
* **`k` / Up Arrow**: Select previous connection.
* **`l` / Right Arrow / Enter**: Traverse into the highlighted link.
* **`h` / Left Arrow / Backspace**: Step backward in history stack.
* **`q`**: Exit.

Edit: (find-file "/home/dad84/Documents/2026/20261005-midnight-commander-style-org-roam-node-explorer/chat/captures/20261005_233424_capture.md")

---

# PROMPT 3
I think the script has to take a command line input argument of a particular roam node to begin at.  ideally we want to supply a piece of a node title and then use completion to choose which one.   but for now, for quick testing / proof of concept, maybe we should just hard code which roam node to start at, so we can focus on the roaming - if that doesn't work, there is no sense to spend time on the rest of the window dressing.

Edit: (find-file "/home/dad84/Documents/2026/20261005-midnight-commander-style-org-roam-node-explorer/chat/captures/20261005_234718_capture.md")

---

# RESPONSE 3
Hardcoding a initial target node (or allowing a fallback search term in code) lets you validate the motion loop immediately.

Below is an updated version of the prototype. It hardcodes a initial `START_NODE_TITLE` to search for when launched without arguments. If it finds a matching node title in your `org-roam.db`, it opens directly on that node.

---

### Updated Prototype (`roam_lynx.py`)

```python
#!/usr/bin/env python3
import curses
import os
import sqlite3
import sys

# ----------------------------------------------------------------------
# Configuration / Hardcoded Defaults
# ----------------------------------------------------------------------
DEFAULT_DB = os.path.expanduser("~/.config/emacs/org-roam.db")

# HARDCODED STARTING NODE TITLE (substring match)
# Change this to match a note title in your Org-roam database.
START_NODE_TITLE = "Index"


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

            stdscr.addstr(
                1, 0, f" File: {file_path}"[: width - 1], curses.A_DIM
            )
            stdscr.addstr(
                2,
                0,
                f" Stack Depth: {len(self.history)} | Connections: {len(self.connections)}"[: width - 1],
            )
            stdscr.addstr(3, 0, "─" * (width - 1))

            # --- Render Connections ---
            max_items = height - 6
            if not self.connections:
                stdscr.addstr(
                    5, 2, "< No outgoing links or backlinks >", curses.A_DIM
                )
            else:
                for idx, conn in enumerate(self.connections[:max_items]):
                    row_y = 5 + idx
                    prefix = f"[{conn['type']}] "
                    item_str = f"{prefix}{conn['title']}"[: width - 4]

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

            # --- Render Footer ---
            stdscr.addstr(
                height - 1,
                0,
                " [j/k or ↑/↓]: Select | [l or →/Enter]: Jump | [h or ←/Backspace]: Back | [q]: Quit"[: width - 1],
                curses.A_REVERSE,
            )

            stdscr.refresh()

            # --- Handle Input ---
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
                    self.connections = self.load_connections(
                        self.current_node[0]
                    )
                    self.selected_idx = 0

            # Motion Left / Backspace (Pop history stack)
            elif key in (curses.KEY_LEFT, ord("h"), 8, 127, curses.KEY_BACKSPACE):
                if self.history:
                    self.current_node = self.history.pop()
                    self.connections = self.load_connections(
                        self.current_node[0]
                    )
                    self.selected_idx = 0


def main():
    # Pass optional start title as 1st argument, or fallback to START_NODE_TITLE
    start_title = sys.argv[1] if len(sys.argv) > 1 else START_NODE_TITLE
    db_path = DEFAULT_DB

    nav = OrgRoamNavigator(db_path, start_title)
    curses.wrapper(nav.run)


if __name__ == "__main__":
    main()

```

---

### Testing Steps

1. Set `START_NODE_TITLE = "Index"` (or any node title present in your notes) inside the script.
2. Run directly:
```bash
python3 roam_lynx.py

```


3. Test traversing forward through links (`l` or Right Arrow) and stepping back (`h` or Left Arrow).

Edit: (find-file "/home/dad84/Documents/2026/20261005-midnight-commander-style-org-roam-node-explorer/chat/captures/20261005_234723_capture.md")

---

# PROMPT 4
how exciting, this might be working to some degree.  let's try to overcome one bug I am hitting right away.  I start at a node with 60 connections.  I really like how they are clearly labeled OUT and IN, which already is a step beyond what org roam buffer in emacs provides.  now, I scroll down the screen with the arrow key and oops, the focus scrolls right off the screen and is out of sight.  I hope we are not wandering into the 'write a custom pager' territory because past experience makes me think that some struggle would lie ahead, but maybe it's unavoidable.

Edit: (find-file "/home/dad84/Documents/2026/20261005-midnight-commander-style-org-roam-node-explorer/chat/captures/20261005_235725_capture.md")

---

# RESPONSE 4
That bug happens because `curses` renders list rows using `enumerate(self.connections[:max_items])`, while the key handling allows `selected_idx` to keep incrementing all the way to length of `connections`. When `selected_idx` exceeds `max_items`, the highlight ring moves off-screen while the visible list remains anchored at the top!

The good news: **you do not need a full pager.** You only need a rolling offset window (typically 3–5 lines of arithmetic) to keep `selected_idx` pinned inside the visible viewport.

---

### How Viewport Scrolling Works

Instead of rendering starting always from item `0`, we maintain a `top_idx` pointer:

```
  [0] Connection A  ◄── top_idx
  [1] Connection B
  [2] Connection C  ◄── selected_idx (Highlighted)
  [3] Connection D
── Screen Boundary (max_items = 4) ─────────────────
  [4] Connection E  (Hidden off-screen)

```

When moving down, if `selected_idx` hits `top_idx + max_items`, we shift `top_idx += 1`.

When moving up, if `selected_idx` goes below `top_idx`, we shift `top_idx -= 1`.

---

### Fixed Prototype with Rolling Viewport

Here is the updated script with scrolling window logic added. It also adds a scroll indicator `(Item X of Y)` to the section header.

```python
#!/usr/bin/env python3
import curses
import os
import sqlite3
import sys

# ----------------------------------------------------------------------
# Configuration / Hardcoded Defaults
# ----------------------------------------------------------------------
DEFAULT_DB = os.path.expanduser("~/.config/emacs/org-roam.db")
START_NODE_TITLE = "Index"


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

            stdscr.addstr(
                1, 0, f" File: {file_path}"[: width - 1], curses.A_DIM
            )

            conn_count = len(self.connections)
            curr_pos = (
                f"{self.selected_idx + 1}/{conn_count}" if conn_count else "0/0"
            )
            stdscr.addstr(
                2,
                0,
                f" History Stack: {len(self.history)} | Connections: {conn_count} (Item {curr_pos})"[: width - 1],
            )
            stdscr.addstr(3, 0, "─" * (width - 1))

            # --- Calculate Viewport Bounds ---
            max_items = max(1, height - 6)  # Dynamic height calculation

            # Adjust viewport window based on selected index
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
                " [j/k or ↑/↓]: Select | [l or →/Enter]: Jump | [h or ←/Backspace]: Back | [q]: Quit"[: width - 1],
                curses.A_REVERSE,
            )

            stdscr.refresh()

            # --- Handle Input ---
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
                    self.connections = self.load_connections(
                        self.current_node[0]
                    )
                    self.selected_idx = 0
                    self.top_idx = 0

            # Motion Left / Backspace (Pop history stack)
            elif key in (curses.KEY_LEFT, ord("h"), 8, 127, curses.KEY_BACKSPACE):
                if self.history:
                    self.current_node = self.history.pop()
                    self.connections = self.load_connections(
                        self.current_node[0]
                    )
                    self.selected_idx = 0
                    self.top_idx = 0


def main():
    start_title = sys.argv[1] if len(sys.argv) > 1 else START_NODE_TITLE
    db_path = DEFAULT_DB

    nav = OrgRoamNavigator(db_path, start_title)
    curses.wrapper(nav.run)


if __name__ == "__main__":
    main()

```

---

### What Was Changed

1. **`top_idx` offset added:** Tracks which index is rendered at line 5.
2. **Auto-adjusting window:** Before rendering, `self.top_idx` moves up or down as `self.selected_idx` approaches the edges of `max_items`.
3. **Reset on navigation:** Moving to a new node resets both `selected_idx` and `top_idx` back to `0`.

Now when you scroll down on a node with 60 connections, the list glides down naturally and keeps your selection visible.

Edit: (find-file "/home/dad84/Documents/2026/20261005-midnight-commander-style-org-roam-node-explorer/chat/captures/20261005_235731_capture.md")

---

# PROMPT 5
I think you got it.  now the user would like the ability to do page up / page down type motion through the connections (desirable for 60 connections) - how feasible is that?  is that pushing the complexity a little too much?

Edit: (find-file "/home/dad84/Documents/2026/20261005-midnight-commander-style-org-roam-node-explorer/chat/captures/20261006_001203_capture.md")

---

# RESPONSE 5
Page Up / Page Down support is straightforward to add and won't bloat the code or push complexity into "custom pager" territory.

Because we already built the dynamic `max_items` window calculation in the previous step, Page Up and Page Down simply add or subtract `max_items` from `selected_idx` (with safety bounds) whenever the key is pressed.

---

### Key Handling for Page Up / Page Down in `curses`

The terminal sends special keycodes for these keys (`curses.KEY_NPAGE` for Page Down and `curses.KEY_PPAGE` for Page Up). Standard Vim-style shortcuts (`Ctrl+f` / `Ctrl+b` or `Space` / `b`) can also be mapped as backups.

Here is how simple the input logic remains:

```python
# Page Down (KEY_NPAGE, Ctrl+f, or Space)
elif key in (curses.KEY_NPAGE, 6, ord(" ")):
  if self.connections:
    self.selected_idx = min(
        len(self.connections) - 1, self.selected_idx + max_items
    )

# Page Up (KEY_PPAGE, Ctrl+b)
elif key in (curses.KEY_PPAGE, 2):
  if self.connections:
    self.selected_idx = max(0, self.selected_idx - max_items)

```

Because the rendering loop already checks `if self.selected_idx >= self.top_idx + max_items` on every frame, jumping `selected_idx` by a full page automatically shifts `top_idx` along with it.

---

### Updated Script with Paging (`roam_lynx.py`)

```python
#!/usr/bin/env python3
import curses
import os
import sqlite3
import sys

# ----------------------------------------------------------------------
# Configuration / Hardcoded Defaults
# ----------------------------------------------------------------------
DEFAULT_DB = os.path.expanduser("~/.config/emacs/org-roam.db")
START_NODE_TITLE = "Index"


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

```

Edit: (find-file "/home/dad84/Documents/2026/20261005-midnight-commander-style-org-roam-node-explorer/chat/captures/20261006_001217_capture.md")

---

# PROMPT 6
in another chat, we already made a script which can be imitated in order to add a front-end on to our lynx-style org roam browser.  this previous script results in visiting a selected roam node in emacs - we can adapt it to instead provide the initial roam node for lynx style roaming.  previous script:

#!/usr/bin/env bash

# Paths
DB_PATH="${XDG_CONFIG_HOME:-$HOME/.config}/emacs/org-roam.db"
[[ ! -f "$DB_PATH" ]] && DB_PATH="$HOME/.emacs.d/org-roam.db"
HELP_FILE="$HOME/Documents/2026/20260901-standalone-org-roam/roam-find-verbose-help.md"

# --- HELP HANDLERS ---
show_brief_help() {
    cat << 'EOF'
Usage: roam-find [OPTION] [SEARCH_TERM]

Instantly search and open pre-existing Org-roam nodes in Emacs using SQLite and fzf.  supports org-roam aliases.

Options:
  -h, --help           Show this brief command-line help message and exit.
  -v, --verbose-help   Open the full Markdown manual in Emacs.

Examples:
  roam-find            Interactive search through all notes (sorted by mtime).
  roam-find bashrc     Direct hit or pre-filtered fzf search for "bashrc".
EOF
}

show_verbose_help() {
    if [[ -f "$HELP_FILE" ]]; then
        emacsclient -n "$HELP_FILE"
    else
        echo "Error: Help file not found at $HELP_FILE" >&2
        exit 1
    fi
}

case "$1" in
    -h|--help) show_brief_help; exit 0 ;;
    -v|--verbose-help) show_verbose_help; exit 0 ;;
esac

[[ ! -f "$DB_PATH" ]] && { echo "Error: Database not found at $DB_PATH" >&2; exit 1; }

SEARCH_TERM="$1"

# Base SQL incorporating LEFT JOIN on aliases
BASE_SQL="SELECT nodes.title, COALESCE(GROUP_CONCAT(aliases.alias, ' | '), '') AS alias_list, nodes.file FROM nodes JOIN files ON nodes.file = files.file LEFT JOIN aliases ON nodes.id = aliases.node_id WHERE nodes.title IS NOT NULL AND nodes.title != '' GROUP BY nodes.id"

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
    # Format fzf display: show Title (and Aliases if present in col 2)
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
    FILE=$(echo "$SELECTION" | cut -f3)
    if [[ ! -f "$FILE" ]]; then
        echo "Error: Node file does not exist: $FILE" >&2
        exit 1
    fi
    emacsclient -n "$FILE" > /dev/null
    echo "Visited node file: $FILE"
fi

Edit: (find-file "/home/dad84/Documents/2026/20261005-midnight-commander-style-org-roam-node-explorer/chat/captures/20261008_121043_capture.md")

---

# RESPONSE 6
We can adapt that exact wrapper pattern to launch our Python `roam_lynx.py` script instead of `emacsclient`.

By querying SQLite for primary titles and aliases, feeding them through `fzf` (with live node file previewing!), and taking the primary node title directly from field 1, we get an instant front-end selector.

---

### Wrapper Script (`roam-lynx-find`)

Save this executable script in your path (e.g., `~/.local/bin/roam-lynx-find`):

```bash
#!/usr/bin/env bash

# Paths
DB_PATH="${XDG_CONFIG_HOME:-$HOME/.config}/emacs/org-roam.db"
[[ ! -f "$DB_PATH" ]] && DB_PATH="$HOME/.emacs.d/org-roam.db"
PYTHON_NAV_SCRIPT="${ROAM_LYNX_PY:-$HOME/bin/roam_lynx.py}"

# --- HELP HANDLERS ---
show_brief_help() {
    cat << 'EOF'
Usage: roam-lynx-find [OPTION] [SEARCH_TERM]

Search Org-roam nodes/aliases using fzf and open the selection in the terminal Lynx-style node browser.

Options:
  -h, --help            Show this brief command-line help message and exit.

Examples:
  roam-lynx-find        Interactive fzf search through all notes (sorted by mtime).
  roam-lynx-find bashrc Pre-filtered fzf search for "bashrc" before entering browser.
EOF
}

case "$1" in
    -h|--help) show_brief_help; exit 0 ;;
esac

# Validations
[[ ! -f "$DB_PATH" ]] && { echo "Error: Database not found at $DB_PATH" >&2; exit 1; }
[[ ! -f "$PYTHON_NAV_SCRIPT" ]] && { echo "Error: Python navigator not found at $PYTHON_NAV_SCRIPT" >&2; exit 1; }

SEARCH_TERM="$1"

# Base SQL incorporating LEFT JOIN on aliases
BASE_SQL="SELECT nodes.title, COALESCE(GROUP_CONCAT(aliases.alias, ' | '), '') AS alias_list, nodes.file FROM nodes JOIN files ON nodes.file = files.file LEFT JOIN aliases ON nodes.id = aliases.node_id WHERE nodes.title IS NOT NULL AND nodes.title != '' GROUP BY nodes.id"

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
    # Format fzf display: Title + Aliases in col 1/2, live file preview from col 3
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
    NODE_TITLE=$(echo "$SELECTION" | cut -f1)
    
    # Hand off execution to the Python terminal browser using the selected title
    python3 "$PYTHON_NAV_SCRIPT" "$NODE_TITLE"
fi

```

---

### How to Hook It Together

1. **Set script locations:** Ensure `PYTHON_NAV_SCRIPT` points to where your updated `roam_lynx.py` lives (e.g., `$HOME/bin/roam_lynx.py` or export `ROAM_LYNX_PY=/path/to/roam_lynx.py`).
2. **Make executable:**
```bash
chmod +x roam-lynx-find

```


3. **Usage:**
* Run `roam-lynx-find` to browse all recent notes with live file previewing in `fzf`.
* Press `Enter` on a selection, and `fzf` hands off control seamlessly to `roam_lynx.py` anchored on that exact node title.
* Run `roam-lynx-find term` to jump straight into `fzf` filtered by `term`.

Edit: (find-file "/home/dad84/Documents/2026/20261005-midnight-commander-style-org-roam-node-explorer/chat/captures/20261008_121049_capture.md")

---

# PROMPT 7
I started this project in Gemini, but Gemini is crashing / not working at this time.  Let's try to continue it so I don't lose my train of thought.  We have a script that roams around the org roam database.  The next step is to add the ability to hit 'e' and visit the current roam node via emacsclient, without exiting/completing the script run.  existing script:

Edit: (find-file "/home/dad84/Documents/2026/20261005-midnight-commander-style-org-roam-node-explorer/chat/captures/20261008_130404_capture.md")

---

# RESPONSE 7
Since `emacsclient -n` returns immediately, you don't need to suspend curses. The script can fire the command and keep running. Here are the changes.

**1. Imports** (top of file):

```python
import subprocess
```

**2. Add a status field in `__init__`** (next to the other navigation state):

```python
    self.status = ""  # Transient message shown in the footer
```

**3. Add this method to the class** (e.g. after `load_connections`):

```python
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
```

**4. Replace the footer rendering** so it shows the status message once, then reverts:

```python
      # --- Render Footer ---
      footer = (
          " [j/k/PgDn/PgUp]: Move | [l/→/Enter]: Jump | [h/←/Backspace]: Back |"
          " [e]: Emacs | [q]: Quit"
      )
      if self.status:
        footer = f" {self.status}"
        self.status = ""  # clears on next redraw (i.e. after next keypress)
      stdscr.addstr(height - 1, 0, footer.ljust(width - 1)[: width - 1], curses.A_REVERSE)
```

**5. Add the key handler** in the input section (e.g. right after the quit handler):

```python
      elif key in (ord("e"), ord("E")):
        self.visit_in_emacs(self.current_node)
```

A few notes:

- **Requires a running Emacs server** (`M-x server-start`, or `(server-start)` in your init). If it isn't running, you'll see the error in the footer rather than a crash.
- **Focus:** the `select-frame-set-input-focus` call raises the Emacs frame if it's a GUI frame. If you run Emacs in another terminal, it'll still switch buffers there; you'll just switch windows yourself.
- **Visiting by ID** uses org-roam's own `org-roam-node-visit`, so it jumps to the exact heading for sub-file nodes, not just the top of the file.
- **Easy extension:** if you'd rather open the *highlighted* connection instead of the current node, change the call to `self.visit_in_emacs((t["id"], t["title"], t["file"]))` using `t = self.connections[self.selected_idx]`. You could even bind that to `E` and keep `e` for the current node.

Edit: (find-file "/home/dad84/Documents/2026/20261005-midnight-commander-style-org-roam-node-explorer/chat/captures/20261008_130410_capture.md")

---

# PROMPT 8
so, what happens if the user is working in org roam in emacs, and does things that cause the roam database to be updated, while at the same time our python script is still running?  is there an issue there?  does the python script end up using an outdated roam database, leading to unexpected results?

Edit: (find-file "/home/dad84/Documents/2026/20261005-midnight-commander-style-org-roam-node-explorer/chat/captures/20261008_133837_capture.md")

---

# RESPONSE 8
Short answer: no crashes or corruption to worry about, but yes, there are a few staleness quirks. Some are worth handling.

**Why it's mostly safe**

- Your script only reads. SQLite handles a reader and a writer on the same file fine, and each query sees a consistent snapshot.
- Your script never holds a long-lived read transaction. Python's `sqlite3` only opens implicit transactions for INSERT/UPDATE/DELETE, so each `SELECT` runs and finishes on its own. That means every call to `load_connections` sees the database as it is *at that moment*, not as it was at startup.

So the database isn't "outdated" in the sense of being a frozen copy. The staleness comes from what your script caches in memory.

**Where staleness can actually bite you**

1. **The connection list is only loaded on navigation.** If you're sitting on a node and add a link in Emacs, the list on screen won't change until you move to another node (or back). That's the most common "huh?" moment.

2. **The history stack holds `(id, title, file)` tuples.** If you rename a node or move/rename its file, going back pops the old title and file path. The *connections* will be fresh, but the header will show the old title and file. The `e` command passes the ID to `org-roam-node-from-id`, so it still works for renames, but the fallback `find-file` would use a stale path.

3. **Deleted nodes.** If a node in your history or connection list gets deleted, `load_connections` just returns an empty list (the joins find nothing), and `e` falls into the `find-file` fallback, which could open a nonexistent file or create a new empty buffer. Not catastrophic, but surprising.

4. **Locking and `database is locked`.** org-roam writes in bursts (on save, during `org-roam-db-sync`). Python's default busy timeout is 5 seconds, so short writes are fine. A full sync on a large database could, in theory, exceed that and raise `sqlite3.OperationalError`, which would currently crash your curses UI. Whether the DB is in WAL mode matters here too. In rollback-journal mode (the default, which I believe org-roam uses), a writer holding the lock blocks readers briefly.

5. **Emacs-side DB staleness is the other direction.** org-roam only updates the DB when it saves a file (with `org-roam-db-autosync-mode`). So if you edit a link in Emacs but haven't saved, your script won't see it. That's not a bug in the script, just something to keep in mind.

**Cheap fixes, in order of value**

- **Refresh key.** Bind `r` to reload connections for the current node, preserving the selection if possible. This directly solves #1.
- **Reload node info on navigation, including back.** Instead of trusting the history tuple, re-query `id, title, file` by ID when popping history. If the node is gone, show a status message and skip it.
- **Catch `sqlite3.OperationalError` around queries** and put the message in `self.status` instead of crashing. Optionally retry once.
- **Open read-only** to guarantee you never interfere with Emacs:
  ```python
  self.conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True, timeout=10)
  ```
  The longer `timeout` also reduces lock errors.
- **Optional auto-refresh:** check the DB file's mtime (`os.stat(self.db_path).st_mtime`) each loop and reload connections when it changes. With `stdscr.timeout(1000)`, `getch()` returns `-1` periodically so the loop can notice changes without a keypress. This is the "live" approach, but it's more machinery than most people need; a manual `r` is usually enough.

I can write up the `r` refresh, the by-ID re-lookup helper, and the error handling as a patch in the same style as the `e` changes if you'd like.

Edit: (find-file "/home/dad84/Documents/2026/20261005-midnight-commander-style-org-roam-node-explorer/chat/captures/20261008_133843_capture.md")

---

# PROMPT 9
write up the `r` refresh, the by-ID re-lookup helper, and the error handling as a patch in the same style as the `e` changes

Edit: (find-file "/home/dad84/Documents/2026/20261005-midnight-commander-style-org-roam-node-explorer/chat/captures/20261008_133845_capture.md")

---

# RESPONSE 9
Same format as the `e` patch. It assumes you've already applied that one, so `self.status` and the footer status logic exist.

**1. Imports** (top of file):

```python
import time
```

**2. Open the DB read-only with a longer timeout** (in `__init__`, replacing the `sqlite3.connect` line):

```python
    self.conn = sqlite3.connect(
        f"file:{self.db_path}?mode=ro", uri=True, timeout=10
    )
```

Also add this next to the other navigation state:

```python
    self.db_ok = True  # False if the most recent query failed
```

**3. Add the query wrapper and helpers** (after `find_initial_node`):

```python
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
```

**4. Replace `load_connections`** so it uses the wrapper:

```python
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
```

**5. Add `go_back` and `refresh` methods** (after `visit_in_emacs`, or after `load_connections` if you skipped that one):

```python
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
```

**6. Update the key handlers** (in the input section):

Add the refresh key, e.g. right after the `e` handler:

```python
      elif key in (ord("r"), ord("R")):
        self.refresh()
```

Replace the body of the existing back handler so it re-reads nodes instead of trusting the stale tuple:

```python
      # Motion Left / Backspace (Pop history stack)
      elif key in (curses.KEY_LEFT, ord("h"), 8, 127, curses.KEY_BACKSPACE):
        self.go_back()
```

**7. Guard the `e` handler** against a deleted node (so it doesn't fall into the `find-file` fallback with a stale path):

```python
      elif key in (ord("e"), ord("E")):
        node = self.lookup_node(self.current_node[0])
        if node:
          self.visit_in_emacs(node)
        elif self.db_ok:
          self.status = "Node no longer exists in the database"
```

**8. Add `[r]: Refresh` to the footer string:**

```python
      footer = (
          " [j/k/PgDn/PgUp]: Move | [l/→/Enter]: Jump | [h/←/Backspace]: Back |"
          " [r]: Refresh | [e]: Emacs | [q]: Quit"
      )
```

Notes:

- **Why `db_ok`:** `_query` returns `[]` on both "no rows" and "query failed," so `db_ok` lets callers tell a deleted node from a locked DB. Without it, a lock timeout would look like a deletion and `refresh` would pop your history.
- **Failure behavior:** a transient lock now costs one 0.2s retry. If that also fails, you get `DB error: ...` in the footer and the screen keeps its old contents instead of crashing or blanking.
- **Read-only mode:** `mode=ro` guarantees the script can't interfere with Emacs. If org-roam ever runs the DB in WAL mode, read-only still works as long as the directory is writable, which `~/.emacs.d` normally is.
- **Not covered:** `find_initial_node` still uses the cursor directly. It runs once before curses starts, so a crash there prints a normal traceback. If you want auto-refresh on DB mtime changes (`stdscr.timeout(1000)` plus an `os.stat` check calling `self.refresh()`), it slots in cleanly on top of this.

Edit: (find-file "/home/dad84/Documents/2026/20261005-midnight-commander-style-org-roam-node-explorer/chat/captures/20261008_133858_capture.md")

---

# PROMPT 10
pyright is complaining on this line:

fresh = self.lookup_node(self.current_node[0])

 178  29 error Pyright reportOptionalSubscript Object of type "None" is not subscriptable

Edit: (find-file "/home/dad84/Documents/2026/20261005-midnight-commander-style-org-roam-node-explorer/chat/captures/20261008_133859_capture.md")

---

# RESPONSE 10
Pyright is right to complain: `self.current_node` is initialized to `None` in `__init__` and only assigned later in `run`, so its declared type is `None` plus whatever gets assigned. It can't know `refresh` is only called after `run` sets it.

The cleanest fix is to give the attributes real types in `__init__`, so that `current_node` is `Optional[...]` explicitly, and then narrow it at the top of `refresh`.

**1. Imports** (top of file):

```python
from typing import Optional
```

**2. Annotate the state in `__init__`:**

```python
    self.history: list[tuple[str, str, str]] = []
    self.current_node: Optional[tuple[str, str, str]] = None
```

**3. Narrow at the top of `refresh`:**

```python
  def refresh(self):
    """Re-read the current node and its connections, keeping the selection."""
    if self.current_node is None:
      return
    ...
```

After that guard, Pyright knows `self.current_node` is a tuple for the rest of the method, so `self.current_node[0]` is fine.

You'll likely see the same error in other places that subscript `self.current_node`: the `e` handler, `visit_in_emacs`'s caller, and the header rendering in `run`. The same fix applies to each: a guard or a local variable.

**Alternative: skip the Optional entirely.** If you'd rather not sprinkle guards everywhere, set `current_node` in `__init__` instead of in `run`. Move the `find_initial_node()` call and the first `load_connections` into `__init__`:

```python
    self.current_node: tuple[str, str, str] = self.find_initial_node()
    self.connections = self.load_connections(self.current_node[0])
```

Then remove those two lines from the top of `run`. The attribute is never `None`, so no guards are needed anywhere. This works well here because `find_initial_node` already runs before curses starts in practice, and it exits with a normal error message if the DB is empty.

One caveat on that alternative: `find_initial_node` uses `self.cursor` directly, and `load_connections` uses `self._query`, which sets `self.status` on errors. Both attributes need to exist before the call, so put those two lines at the *end* of `__init__`, after `self.status`, `self.db_ok`, and the cursor are set up.

I'd go with the second option, since it removes the whole class of "might be None" warnings in one move rather than patching each use site.

Edit: (find-file "/home/dad84/Documents/2026/20261005-midnight-commander-style-org-roam-node-explorer/chat/captures/20261008_133904_capture.md")

---

# PROMPT 11
what do you think about adding a preview pane?  I am not sure about this.  a basic one doesn't show an org file with headings folded up and it just looks like a plain text file - 'doesn't look right.'  gemini mentioned pandoc - wouldn't that slow things down, and what does that do?  I like the responsiveness of the current script.  sometimes a preview is useful if a node looks worth visiting in emacs but you see in the preview that it's just a stub.

Edit: (find-file "/home/dad84/Documents/2026/20261005-midnight-commander-style-org-roam-node-explorer/chat/captures/20261008_140948_capture.md")

---

# RESPONSE 11
I'd add one, but keep it much simpler than what Gemini was heading toward. Your use case ("is this node a stub?") doesn't need a faithful rendering of Org. It needs a quick sense of size and substance.

**What pandoc does here**

Pandoc converts between markup formats. For this, it would read the Org file and emit something else (plain text, markdown, ANSI-colored text). It would give you cleaner prose, with `#+TITLE:` lines and property drawers stripped and links rendered as text.

**Would it slow things down?**

It would be a subprocess launch per preview, typically 20 to 100 ms, more for big files. That's tolerable if you only preview on demand, but noticeable if it runs on every `j`/`k`. And it doesn't solve your actual complaint: pandoc turns Org into flattened text, with no folding. So you'd pay the latency and still not get the Emacs-like look. I'd skip pandoc.

**Why a basic preview feels wrong, and a cheap fix**

Raw Org looks like a text file because it is one. But you can fake the useful parts of Org's visual style in a few lines of Python, with no external tools:

- Hide the noise: skip `:PROPERTIES:` ... `:END:` drawers and `#+` keyword lines (or show just the title).
- Color headings by level and dim everything else, using the curses color pairs you already have.
- Collapse long bodies: show the first N lines of body text under each heading, as a rough stand-in for folding.
- Show a stub indicator: a header line like `42 words, 3 headings, 2 links` is arguably more useful than the text itself for your stub-spotting purpose.

**Making it responsive**

The existing script is snappy because it only runs small SQLite queries. To keep that:

- Read only the first ~50 lines of the file (`itertools.islice`), not the whole thing.
- Cache previews in a dict keyed by `(file, mtime)`, so revisiting is free and edits invalidate automatically.
- Optionally, render lazily: draw the list immediately and fill the preview on the next loop iteration, or only when the selection has rested for a moment. In practice, reading 50 lines is fast enough that this is unnecessary.

**One wrinkle: file-level vs. heading-level nodes**

org-roam nodes can be a whole file or a single heading inside a file. The `nodes` table has a `level` and `pos` column, so for heading nodes you'd want to start reading at `pos` (a character offset) instead of the top of the file, and stop at the next heading of the same or higher level. Otherwise the preview shows the wrong content. This is the main thing that makes a "basic" preview more work than it looks.

**Layout**

A bottom pane (list on top, preview below, split roughly 50/50, or toggled with `p`) works better than a side pane on typical terminals, since titles and Org prose are wide. A toggle key also means you can hide it when you just want to fly through the graph.

**My recommendation**

Start with the stats line plus a lightly styled, truncated body, and toggle it with `p`. If you find yourself wanting true Org rendering, the better route is asking Emacs itself, since you already have `emacsclient` wired up. But that costs a round trip per preview, and Emacs would have to be running, so I'd treat it as a later experiment rather than the first move.

Want me to write the patch? If so, one question: should it preview the highlighted connection, the current node, or both (current node in the header area, highlighted connection in the pane)? I'd lean toward the highlighted connection, since that's the "should I jump there?" decision.

Edit: (find-file "/home/dad84/Documents/2026/20261005-midnight-commander-style-org-roam-node-explorer/chat/captures/20261008_140954_capture.md")

---

# PROMPT 12
let's see a patch for previewing the highlighted connection - go with your recommendations.  stats that give how many links are associated with the highlighted connection sounds quite useful

Edit: (find-file "/home/dad84/Documents/2026/20261005-midnight-commander-style-org-roam-node-explorer/chat/captures/20261008_140956_capture.md")

---

# RESPONSE 12
Same format as before. It assumes the `e`, `r`, and error-handling patches are applied, since it uses `_query`, `db_ok`, and `status`. The pane shows the highlighted connection, toggles with `p`, and is on by default.

**1. Imports** (top of file):

```python
import re
```

**2. Constants** (after `START_NODE_TITLE`):

```python
PREVIEW_MIN_HEIGHT = 16    # hide the pane on very short terminals
MAX_READ_CHARS = 200_000   # cap on how much of a file we read
MAX_BODY_LINES = 4         # body lines shown per heading (poor man's folding)
STUB_WORDS = 40            # fewer words than this gets flagged as a stub
HEADING_PAIRS = (4, 5, 6, 3)  # curses color pairs for heading levels 1-4+

HEADING_RE = re.compile(r"^(\*+)\s+(.*)")
DRAWER_START_RE = re.compile(r"^\s*:[A-Za-z_-]+:\s*$")
DRAWER_END_RE = re.compile(r"^\s*:END:\s*$", re.IGNORECASE)
LINK_RE = re.compile(r"\[\[[^\]]*\]\[([^\]]*)\]\]|\[\[([^\]]*)\]\]")
```

**3. State in `__init__`** (next to the other navigation state):

```python
    self.show_preview = True  # set False to start with the pane hidden
    self.preview_cache: dict = {}  # (node_id, file mtime_ns) -> preview
```

**4. Extra heading colors** (in `run`, after the existing `init_pair` calls):

```python
    curses.init_pair(5, curses.COLOR_MAGENTA, -1)  # Heading level 2
    curses.init_pair(6, curses.COLOR_CYAN, -1)  # Heading level 3
```

**5. Add these methods to the class** (e.g. after `lookup_node`):

```python
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
```

**6. Shrink the list when the pane is showing** (in `run`, replacing `max_items = max(1, height - 6)`):

```python
      preview_rows = 0
      if self.show_preview and height >= PREVIEW_MIN_HEIGHT:
        preview_rows = (height - 6) // 2
      max_items = max(1, height - 6 - preview_rows)
```

**7. Draw the pane** (in `run`, right after the "Render Connections" block and before "Render Footer"):

```python
      if preview_rows:
        self.draw_preview(stdscr, height - 1 - preview_rows, preview_rows, width)
```

**8. Key handler** (in the input section):

```python
      elif key in (ord("p"), ord("P")):
        self.show_preview = not self.show_preview
```

**9. Clear the cache on refresh** (in `refresh`, right after the `current_node is None` guard):

```python
    self.preview_cache.clear()
```

**10. Footer.** It's getting long and will truncate at 80 columns, so here's a compact version:

```python
      footer = (
          " j/k:Move  l:Jump  h:Back  r:Refresh  e:Emacs  p:Preview  q:Quit"
      )
```

Notes:

- **Read-the-whole-file correction:** I earlier suggested reading only the first ~50 lines, but the word count and stub detection need the whole node. Files are read once per `(node, mtime)` and cached, and capped at 200K characters, so `j`/`k` stays instant. Revisiting a node or scrolling back costs nothing.
- **What the stats mean:** "out" is the number of ID links in that node, and "in" is the number of ID links pointing at it. These are the same links your connection list uses, so plain URLs aren't counted.
- **Cache staleness:** the cache invalidates when the highlighted node's file changes. A new backlink added from a different file won't change that mtime, so press `r` to refresh those counts.
- **Stub threshold:** `STUB_WORDS = 40` counts heading text too. Adjust it to taste. Any node under the threshold gets "looks like a stub" in the stats line.
- **Folding stand-in:** each heading shows its first 4 body lines, then `… N more lines`. Property drawers and `#+` keyword lines are hidden, and `[[id:...][Desc]]` links are shown as just `Desc`. Heading stars are kept so you can see the depth.
- **Heading-node offsets:** `pos` is Emacs's character offset. It's exact for normal UTF-8 files with LF line endings, but CRLF files could land a few characters off.
- **Short terminals:** below 16 rows the pane hides itself automatically, so the list never gets squeezed to nothing.

Edit: (find-file "/home/dad84/Documents/2026/20261005-midnight-commander-style-org-roam-node-explorer/chat/captures/20261008_141009_capture.md")

---
