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
