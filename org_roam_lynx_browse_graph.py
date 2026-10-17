#!/usr/bin/env python3
import argparse
import curses
import html
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import textwrap
import time
from datetime import datetime
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
PREVIEW_MIN_HEIGHT = 16  # hide the pane on very short terminals
MAX_READ_CHARS = 200_000  # cap on how much of a file we read
MAX_CARD_LINES = 100  # cap on flash-card lines kept per node (before wrapping)
STUB_WORDS = 40  # fewer words than this gets flagged as a stub
CARD_CODE_PAIR = 6  # color pair for code/example lines in the flash card

# Row labels in the list -> curses color pair (see init_pair calls in run)
TYPE_PAIRS = {"MAIN": 4, "BIDIR": 5, "OUT": 3, "IN": 2}
# Sort order of linked rows below the MAIN row
TYPE_RANK = {"BIDIR": 0, "OUT": 1, "IN": 2}
LABEL_WIDTH = 5  # len("BIDIR"), so the titles line up
CAME_FROM_PAIR = 7  # color pair for the "you came back from here" reminder row
CAME_FROM_GLYPH = "←"  # margin marker on that row (works without color too)

HEADING_RE = re.compile(r"^(\*+)\s+(.*)")
DRAWER_START_RE = re.compile(r"^\s*:[A-Za-z_-]+:\s*$")
DRAWER_END_RE = re.compile(r"^\s*:END:\s*$", re.IGNORECASE)
LINK_RE = re.compile(r"\[\[[^\]]*\]\[([^\]]*)\]\]|\[\[([^\]]*)\]\]")

# Flash-card preview. These lines are references rather than prose, so they
# are hidden: a link on its own line (optionally followed by "- a note"), a bare
# URL, or a verbatim /path/ on its own line. A sentence that merely starts with
# a link ("[[Python]] is great") is prose and is kept.
_LINK = r"\[\[[^\]\n]*\](?:\[[^\]\n]*\])?\]"
_NOTE = r"(?:(?:--?|[–—:])\s.*)?"  # optional "- annotation" after a reference
REF_LINK_LINE_RE = re.compile(
    rf"^\s*(?:[-+]\s+)?{_LINK}(?:[\s,;|·]*{_LINK})*[\s,;|·]*{_NOTE}$"
)
REF_URL_LINE_RE = re.compile(
    rf"^\s*(?:[-+]\s+)?<?(?:https?|ftp|file|mailto):\S+>?\s*{_NOTE}$"
)
REF_PATH_LINE_RE = re.compile(r"^\s*(?:[-+]\s+)?[=~](?:/|~/|\./)[^\s=~]*[=~]\s*$")
PLANNING_RE = re.compile(r"^\s*(?:SCHEDULED|DEADLINE|CLOSED):")
RULE_RE = re.compile(r"^\s*-{5,}\s*$")
LIST_MARKER_RE = re.compile(r"^(?:[-+*]|\d+[.)])\s+")

# Built-in help = README.md rendered to HTML (pandoc) and shown in Emacs (eww)
HELP_HTML_NAME = "org-roam-lynx-help.html"  # unique, so it can't clash with
# some other README.html. Overwritten each time help is opened.
HELP_ANCHOR = "reading-the-screen"  # README heading to open at ("" = the top)

DATE_FORMAT = "%m/%d/%Y"  # 10/11/2026. For 2026-10-11 use "%Y-%m-%d"
# Timestamp at the start of a filename: 20260311123456-slug.org (org-roam's
# default), 20260311-slug.org, or 2026-03-11.org (org-roam-dailies)
FILENAME_STAMP_RE = re.compile(
    r"^(\d{4})-?(\d{2})-?(\d{2})(?:[-_T]?(\d{2})(\d{2})(\d{2}))?"
)


def elisp_escape(s):
  """Escape a Python string for use inside an elisp "double-quoted" string."""
  return s.replace("\\", "\\\\").replace('"', '\\"')


def find_readme():
  """Locate README.md: $ROAM_LYNX_README, next to this script, then XDG data.

  resolve() follows symlinks, so a symlink in ~/.local/bin that points into a
  git clone finds the clone's README (and its docs/ images).
  """
  candidates = []
  env = os.environ.get("ROAM_LYNX_README")
  if env:
    candidates.append(Path(env).expanduser())
  candidates.append(Path(__file__).resolve().parent / "README.md")
  data = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
  candidates.append(Path(data) / "org-roam-lynx" / "README.md")
  for c in candidates:
    if c.is_file():
      return c.resolve()
  return None


def help_dir():
  """A private per-user directory for the generated help page."""
  runtime = os.environ.get("XDG_RUNTIME_DIR")
  if runtime and os.path.isdir(runtime):
    d = Path(runtime) / "org-roam-lynx"
  else:
    d = Path(tempfile.gettempdir()) / f"org-roam-lynx-{os.getuid()}"
  d.mkdir(mode=0o700, exist_ok=True)
  # Another user could have pre-created this name (or a symlink) in /tmp
  if d.is_symlink() or d.lstat().st_uid != os.getuid():
    raise OSError(f"refusing to use {d}: not a private directory of yours")
  d.chmod(0o700)
  return d


def wrap_card_line(text, width):
  """Word-wrap one flash-card line, hanging list items under their text."""
  text = text.expandtabs(2).rstrip()
  if not text.strip():
    return [""]
  indent = len(text) - len(text.lstrip())
  marker = LIST_MARKER_RE.match(text.lstrip())
  hang = " " * (indent + (len(marker.group(0)) if marker else 0))
  return textwrap.wrap(
      text,
      width=max(10, width),
      subsequent_indent=hang,
      break_long_words=True,
      break_on_hyphens=False,  # keep flags like -xzf in one piece
  ) or [""]


def pluralize(n, word):
  return f"{n} {word}" + ("" if n == 1 else "s")


def format_date(ts):
  """Epoch seconds -> a plain date such as 10/11/2026."""
  return datetime.fromtimestamp(ts).strftime(DATE_FORMAT)


def humanize_ago(ts):
  """Epoch seconds -> '8 days ago'. Deliberately coarse."""
  secs = max(0, int(time.time() - ts))
  for unit, size in (
      ("year", 365 * 86400),
      ("month", 30 * 86400),
      ("day", 86400),
      ("hour", 3600),
      ("minute", 60),
  ):
    n = secs // size
    if n >= 1:
      return f"{pluralize(n, unit)} ago"
  return "just now"


def pack_parts(parts, max_width, sep=" · "):
  """Join parts with sep, starting a new line whenever one would overflow."""
  lines, cur = [], ""
  for part in parts:
    cand = f"{cur}{sep}{part}" if cur else part
    if cur and len(cand) > max_width:
      lines.append(cur)
      cur = part
    else:
      cur = cand
  if cur:
    lines.append(cur)
  return lines


def created_time(path):
  """Best available creation time (epoch seconds), or None.

  Org-roam's database does not record this, so: first a timestamp in the
  filename (reliable when your files are named that way), then the
  filesystem's creation time (which copying, syncing or a git checkout can
  reset to the day it landed on this machine).
  """
  m = FILENAME_STAMP_RE.match(os.path.basename(path))
  if m:
    y, mo, d, hh, mm, ss = m.groups()
    try:
      if 1990 <= int(y) <= 2100:
        return datetime(
            int(y), int(mo), int(d), int(hh or 0), int(mm or 0), int(ss or 0)
        ).timestamp()
    except ValueError:
      pass  # digits that are not a real date; fall through

  try:
    birth = getattr(os.stat(path), "st_birthtime", None)  # macOS/BSD
    if birth:
      return birth
    # Linux: Python does not expose it, but GNU stat does (%W; 0 or "-" if
    # the filesystem does not track it)
    out = subprocess.run(
        ["stat", "-c", "%W", path], capture_output=True, text=True, timeout=2
    ).stdout.strip()
    return int(out) if int(out) > 0 else None
  except (OSError, ValueError, subprocess.SubprocessError):
    return None


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
    self.selected_idx = 0  # 0 is always the MAIN row
    self.top_idx = 0  # Viewport scroll offset
    # ID of the node we just came Back from. Drawn as a reminder row and
    # cleared on the next jump. Separate from selected_idx, the live cursor.
    self.came_from_id = None
    self.status = ""  # Transient message shown in the footer
    self.db_ok = True  # False if the most recent query failed
    self.show_preview = True  # set False to start with the pane hidden
    self.preview_cache: dict = {}  # (node_id, file mtime_ns) -> preview
    self.current_node: tuple[str, str, str] = self.find_initial_node()
    self.connections = self.load_connections(self.current_node)

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
    """Return (word_count, subheading_count, card_lines) for a node's text.

    The counts describe the whole node. card_lines is the flash card: the
    plain prose before the node's first (sub)heading, as (text, kind) pairs
    where kind is "body" or "code". Property drawers, #+ keywords, comments,
    planning lines, and lines that are only a link, URL or file path are left
    out, and runs of blank lines collapse to one.
    """
    lines = text.splitlines()
    if level:
      # Heading node: stop at the next heading of the same or higher level
      for i, line in enumerate(lines[1:], 1):
        m = HEADING_RE.match(line)
        if m and len(m.group(1)) <= level:
          lines = lines[:i]
          break

    card = []
    words = 0
    subheads = 0
    in_drawer = False
    in_card = True  # still before the node's first subheading
    block = None  # name of the #+begin_ block we are inside, if any

    def add_card(line_text, kind):
      if not in_card or len(card) >= MAX_CARD_LINES:
        return
      if not line_text.strip():
        if card and card[-1][0]:  # at most one blank line, never a leading one
          card.append(("", kind))
        return
      card.append((line_text.rstrip(), kind))

    for i, line in enumerate(lines):
      if in_drawer:
        if DRAWER_END_RE.match(line):
          in_drawer = False
        continue
      if block is None and DRAWER_START_RE.match(line):
        in_drawer = True
        continue

      stripped = line.strip()
      low = stripped.lower()
      if low.startswith("#+begin_"):
        parts = low[len("#+begin_") :].split()
        block = parts[0] if parts else ""  # "src", "example", "comment", ...
        continue
      if low.startswith("#+end_"):
        block = None
        continue
      if low.startswith("#+"):  # keywords: #+title:, #+filetags:, ...
        continue

      if block is None:
        m = HEADING_RE.match(line)
        if m:
          words += len(m.group(2).split())
          if not (i == 0 and level):  # the node's own heading isn't a subheading
            subheads += 1
            in_card = False
          continue

      body = self._strip_links(line).strip()
      if not body:
        add_card("", "body")
        continue
      words += len(body.split())

      if block == "comment":
        continue
      if block is not None:  # source/example block: keep, drawn as code
        add_card(line.rstrip(), "code")
        continue
      if (
          stripped == "#"
          or stripped.startswith("# ")  # Org comment line
          or PLANNING_RE.match(line)
          or RULE_RE.match(line)
          or REF_LINK_LINE_RE.match(line)
          or REF_URL_LINE_RE.match(line)
          or REF_PATH_LINE_RE.match(line)
      ):
        continue
      add_card(self._strip_links(line).rstrip(), "body")

    while card and not card[-1][0]:
      card.pop()
    return words, subheads, card

  @staticmethod
  def _preview_note(conn, message, lines=()):
    """A preview that only carries a message (missing node, unreadable file)."""
    return {"title": conn["title"], "parts": [message], "lines": list(lines)}

  def get_preview(self, conn):
    """Build (or fetch from cache) the preview for a connection dict."""
    node_id = conn["id"]
    rows = self._query(
        "SELECT file, level, pos FROM nodes WHERE id = ?;", (node_id,)
    )
    if not rows:
      return self._preview_note(conn, "Node not found in database")

    file_path, level, pos = rows[0]
    file_path = (file_path or "").strip('"')
    try:
      mtime = os.stat(file_path).st_mtime_ns
    except OSError:
      return self._preview_note(
          conn, "File not found", [(file_path, "dim")]
      )

    key = (node_id, mtime)
    cached = self.preview_cache.get(key)
    if cached:
      return cached

    try:
      with open(file_path, encoding="utf-8", errors="replace") as f:
        text = f.read(MAX_READ_CHARS)
    except OSError as e:
      return self._preview_note(conn, f"Cannot read file: {e.strerror}")

    # Heading-level nodes: pos is a 1-based character offset into the file
    if level and pos:
      text = text[pos - 1 :]

    words, subheads, lines = self._summarize_org(text, level)
    # Distinct linked nodes (not raw link rows), excluding self-links and
    # broken links, so the numbers agree with the rows in the list
    n_out = self._count(
        "SELECT COUNT(DISTINCT l.dest) FROM links l"
        " JOIN nodes n ON l.dest = n.id"
        " WHERE l.source = ? AND l.dest != l.source AND l.type = '\"id\"';",
        node_id,
    )
    n_in = self._count(
        "SELECT COUNT(DISTINCT l.source) FROM links l"
        " JOIN nodes n ON l.source = n.id"
        " WHERE l.dest = ? AND l.source != l.dest AND l.type = '\"id\"';",
        node_id,
    )

    parts = []
    if level:
      parts.append(f"heading (level {level})")
    parts += [
        pluralize(words, "word"),
        pluralize(subheads, "subheading"),
        f"{n_out} out / {n_in} in",
    ]
    if words < STUB_WORDS:
      parts.append("looks like a stub")

    # Raw timestamps are what gets cached; "8 days ago" is built at draw time
    # so it cannot go stale while the entry sits in the cache.
    result = {
        "title": conn["title"],
        "parts": parts,
        "created": created_time(file_path),
        "modified": mtime / 1e9,
        "lines": lines,
    }
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
    put(top + 1, preview["title"], curses.A_BOLD)

    info = list(preview["parts"])
    if preview.get("created"):
      info.append(f"created {format_date(preview['created'])}")
    if preview.get("modified"):
      m = preview["modified"]
      info.append(f"modified {format_date(m)} ({humanize_ago(m)})")
    # Wraps onto a second line on narrow terminals; always leave a body row
    info_lines = pack_parts(info, width - 4)[: max(0, rows - 3)]
    for i, text in enumerate(info_lines):
      put(top + 2 + i, text)

    body_top = top + 2 + len(info_lines)
    body_rows = rows - 2 - len(info_lines)
    if body_rows > 3:  # a blank row between the header and the card
      body_top += 1
      body_rows -= 1
    if body_rows <= 0:
      return

    card = preview["lines"] or [
        ("(no flash-card text before the first heading)", "dim")
    ]
    wrapped = []
    for text, kind in card:
      for piece in wrap_card_line(text, width - 4):
        wrapped.append((piece, kind))

    truncated = len(wrapped) > body_rows
    for i, (text, kind) in enumerate(wrapped[:body_rows]):
      if truncated and i == body_rows - 1:
        text, kind = "…", "dim"
      if kind == "code":
        attr = curses.color_pair(CARD_CODE_PAIR)
      elif kind == "dim":
        attr = curses.A_DIM
      else:
        attr = 0
      put(body_top + i, text, attr)

  def load_connections(self, node):
    """Return the MAIN row followed by one row per linked node.

    node is an (id, title, file) tuple. Row types:
      MAIN   the node itself (always first)
      BIDIR  it links to this node AND this node links to it
      OUT    this node links to it
      IN     it links to this node (backlink)
    Each linked node appears once, however many links connect the two.
    Self-links are skipped, since MAIN already represents the node.
    """
    node_id, title, file_path = node
    main = {"type": "MAIN", "id": node_id, "title": title, "file": file_path}

    sql_out = """
            SELECT n.id, n.title, n.file
            FROM links l
            JOIN nodes n ON l.dest = n.id
            WHERE l.source = ? AND l.type = '"id"';
        """
    sql_in = """
            SELECT n.id, n.title, n.file
            FROM links l
            JOIN nodes n ON l.source = n.id
            WHERE l.dest = ? AND l.type = '"id"';
        """

    # _query resets db_ok every call, so remember a failure from either one
    rows_out = self._query(sql_out, (node_id,))
    ok = self.db_ok
    rows_in = self._query(sql_in, (node_id,))
    self.db_ok = ok and self.db_ok

    linked: dict = {}  # node id -> row dict; guarantees one row per node
    for row in rows_out:
      if row[0] == node_id:
        continue
      linked[row[0]] = {
          "type": "OUT",
          "id": row[0],
          "title": self._clean(row[1]),
          "file": row[2],
      }
    for row in rows_in:
      if row[0] == node_id:
        continue
      if row[0] in linked:
        linked[row[0]]["type"] = "BIDIR"
      else:
        linked[row[0]] = {
            "type": "IN",
            "id": row[0],
            "title": self._clean(row[1]),
            "file": row[2],
        }

    # sorted() is stable, so query order is kept within each group
    ordered = sorted(linked.values(), key=lambda c: TYPE_RANK[c["type"]])
    return [main] + ordered

  def _emacs_eval(self, elisp):
    """Evaluate elisp in the running Emacs via emacsclient (non-blocking).

    Returns (ok, text): emacsclient's printed result on success, or a short
    human-readable error message on failure.
    """
    try:
      result = subprocess.run(
          ["emacsclient", "-n", "--eval", elisp],
          capture_output=True,
          text=True,
          timeout=5,
      )
    except FileNotFoundError:
      return False, "emacsclient not found in PATH"
    except subprocess.TimeoutExpired:
      return False, "emacsclient timed out"

    if result.returncode == 0:
      return True, result.stdout.strip()
    err = (result.stderr or result.stdout).strip().splitlines()
    msg = err[0].removeprefix("*ERROR*:").strip() if err else "unknown error"
    return False, f"emacsclient failed: {msg}"

  def visit_in_emacs(self, node):
    """Open a node in the running Emacs and raise its frame."""
    node_id, _, file_path = node

    # org-roam stores ids/files as printed elisp strings, i.e. with quotes
    node_id = node_id.strip('"')
    file_path = (file_path or "").strip('"')

    # Visit by ID (lands on the right heading for non-file-level nodes);
    # fall back to just opening the file if the ID isn't found.
    elisp = (
        f'(let ((n (org-roam-node-from-id "{elisp_escape(node_id)}")))'
        f" (if n (org-roam-node-visit n)"
        f'   (find-file "{elisp_escape(file_path)}"))'
        f" (select-frame-set-input-focus (selected-frame)))"
    )
    ok, text = self._emacs_eval(elisp)
    self.status = "Opened in Emacs" if ok else text

  def insert_link_in_emacs(self, node, newline=False):
    """Insert an Org link to node at point in Emacs, then a space or newline.

    The text goes into the buffer shown in Emacs's selected window, i.e. the
    one you were last working in (or, if a minibuffer prompt is open, the
    window you came from). Emacs is not raised, so you can insert again
    straight away. The link is built by Emacs itself, from the node's
    current title there, so non-ASCII titles and brackets are handled by
    org-link-make-string. Our own copy of the title is only a fallback for
    when Emacs does not know the ID.
    """
    node_id, title, _ = node
    node_id = node_id.strip('"')  # org-roam stores IDs wrapped in quotes
    nid = elisp_escape(node_id)
    sep = "\\n" if newline else " "  # an elisp string escape, or a space

    elisp = (
        "(let* ((win (or (minibuffer-selected-window) (selected-window)))"
        " (n (and (fboundp (quote org-roam-node-from-id))"
        f'      (org-roam-node-from-id "{nid}")))'
        f' (title (if n (org-roam-node-title n) "{elisp_escape(title)}")))'
        " (with-selected-window win"
        f'   (insert (org-link-make-string "id:{nid}" title) "{sep}")'
        "   (buffer-name)))"
    )
    ok, text = self._emacs_eval(elisp)
    if ok:
      self.status = f'Inserted link to "{title}" in Emacs buffer {text.strip(chr(34))}'
    else:
      self.status = text

  def show_help(self):
    """Open README.md in Emacs: rendered to HTML for eww, else as plain text."""
    readme = find_readme()
    if readme is None:
      self.status = "README.md not found (set ROAM_LYNX_README to its path)"
      return

    if shutil.which("pandoc") is None:
      # No converter available: show the Markdown source instead
      elisp = (
          f'(progn (find-file-read-only "{elisp_escape(str(readme))}")'
          " (select-frame-set-input-focus (selected-frame)))"
      )
      ok, text = self._emacs_eval(elisp)
      self.status = "pandoc not found; opened README.md as text" if ok else text
      return

    try:
      out_dir = help_dir()
      help_html = out_dir / HELP_HTML_NAME
      head = out_dir / (HELP_HTML_NAME + ".head")
      # Relative paths in the README (images) should resolve against the
      # README's own folder, not the temp directory the HTML lives in.
      base = html.escape(readme.parent.as_uri() + "/", quote=True)
      head.write_text(f'<base href="{base}">\n', encoding="utf-8")
      subprocess.run(
          [
              "pandoc",
              "-f", "gfm",
              "-t", "html5",
              "--standalone",
              "--metadata", "pagetitle=org-roam-lynx help",
              "--include-in-header", str(head),
              "-o", str(help_html),
              str(readme),
          ],
          capture_output=True,
          text=True,
          timeout=20,
          check=True,
      )
    except subprocess.CalledProcessError as e:
      err = (e.stderr or "").strip().splitlines()
      self.status = f"pandoc failed: {err[0] if err else e.returncode}"
      return
    except (OSError, subprocess.SubprocessError) as e:
      self.status = f"Could not build the help page: {e}"
      return

    url = help_html.as_uri() + (f"#{HELP_ANCHOR}" if HELP_ANCHOR else "")
    elisp = (
        f'(progn (eww "{elisp_escape(url)}")'
        " (select-frame-set-input-focus (selected-frame)))"
    )
    ok, text = self._emacs_eval(elisp)
    self.status = "Help opened in Emacs (q closes it)" if ok else text

  def go_back(self):
    """Pop history, re-reading each node and skipping any that were deleted."""
    came_from = self.current_node[0]
    while self.history:
      prev = self.history.pop()
      node = self.lookup_node(prev[0])
      if node:
        self.current_node = node
        self.connections = self.load_connections(node)
        self.selected_idx = 0  # live cursor lands on MAIN
        self.top_idx = 0
        self.came_from_id = came_from  # reminder marker, not the cursor
        return
      if not self.db_ok:
        self.history.append(prev)  # DB hiccup, not a deletion: keep it
        return
      self.status = f"Skipped deleted node: {prev[1]}"

  def refresh(self):
    """Re-read the current node and its connections, keeping the selection."""
    self.preview_cache.clear()

    # Node IDs are unique within the list (self-links are skipped), so the
    # ID alone identifies the highlighted row even if its label changes
    # (for example OUT -> BIDIR after you add a backlink in Emacs).
    selected_id = None
    if self.connections and self.selected_idx < len(self.connections):
      selected_id = self.connections[self.selected_idx]["id"]

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
    new_conns = self.load_connections(fresh)
    if not self.db_ok:
      return  # keep the old list rather than blanking it
    self.connections = new_conns

    # Restore selection by ID; otherwise clamp to the new length
    for i, c in enumerate(self.connections):
      if c["id"] == selected_id:
        self.selected_idx = i
        break
    else:
      self.selected_idx = min(
          self.selected_idx, max(0, len(self.connections) - 1)
      )

    if not self.status:
      self.status = "Refreshed"

  def footer_text(self, width=80):
    """Key hints that depend on what is highlighted."""
    cur = self.connections[self.selected_idx] if self.connections else None
    on_main = cur is not None and cur["type"] == "MAIN"

    parts = ["j/k:Move"]
    if cur is not None and not on_main:
      parts.append("l:Jump")  # on MAIN there is nowhere to jump
    if self.history:
      parts.append("h:Back")
    if cur is not None:
      parts += ["e:Emacs", "i/I:Link"]
    parts += ["r:Refresh", "p:Preview", "?:Help", "q:Quit"]
    text = " " + "  ".join(parts)
    if len(text) > width - 1:  # narrow terminal: single-space separators
      text = " " + " ".join(parts)
    return text

  def run(self, stdscr):
    curses.curs_set(0)
    curses.use_default_colors()

    # Color setup
    curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_CYAN)  # Selected
    curses.init_pair(2, curses.COLOR_GREEN, -1)  # IN (backlinks)
    curses.init_pair(3, curses.COLOR_YELLOW, -1)  # OUT (outlinks)
    curses.init_pair(4, curses.COLOR_BLUE, -1)  # Header / MAIN
    curses.init_pair(5, curses.COLOR_MAGENTA, -1)  # BIDIR
    curses.init_pair(6, curses.COLOR_CYAN, -1)  # Code lines in the flash card
    # Reminder row after Back; must differ from the cursor (pair 1)
    curses.init_pair(CAME_FROM_PAIR, curses.COLOR_BLACK, curses.COLOR_YELLOW)

    while True:
      stdscr.clear()
      height, width = stdscr.getmaxyx()

      # --- Render Header ---
      _, title, file_path = self.current_node
      stdscr.attron(curses.color_pair(4) | curses.A_BOLD)
      stdscr.addstr(0, 0, f" NODE: {title}"[: width - 1])
      stdscr.attroff(curses.color_pair(4) | curses.A_BOLD)

      stdscr.addstr(1, 0, f" File: {file_path}"[: width - 1], curses.A_DIM)

      link_count = max(0, len(self.connections) - 1)  # MAIN is not a link
      if not self.connections:
        curr_pos = "-"
      elif self.selected_idx == 0:
        curr_pos = "MAIN"
      else:
        curr_pos = f"{self.selected_idx}/{link_count}"

      # Row index of the node we came Back from (None if absent or not linked
      # any more). Index 0 is MAIN, so it is never the came-from row.
      came_idx = None
      if self.came_from_id is not None:
        for i, c in enumerate(self.connections):
          if i > 0 and c["id"] == self.came_from_id:
            came_idx = i
            break

      # Named in the header too, because on a long list the row itself may be
      # scrolled out of view while the cursor sits on MAIN.
      came_note = ""
      if came_idx is not None:
        came_title = self.connections[came_idx]["title"]
        came_note = f" | {CAME_FROM_GLYPH} came from: {came_title} ({came_idx}/{link_count})"
      info_line = (
          f" History Stack: {len(self.history)} | Connections: {link_count}"
          f" (Item {curr_pos})" + came_note
      )
      stdscr.addstr(2, 0, info_line[: width - 1])
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
        stdscr.addstr(5, 2, "< Node no longer available >", curses.A_DIM)
      else:
        for idx, conn in enumerate(visible_connections):
          actual_idx = self.top_idx + idx
          row_y = 5 + idx
          prefix = f"[{conn['type']:<{LABEL_WIDTH}}] "
          item_str = f"{prefix}{conn['title']}"[: width - 4]

          if actual_idx == came_idx:
            stdscr.addstr(row_y, 0, CAME_FROM_GLYPH, curses.A_BOLD)

          if actual_idx == self.selected_idx:
            stdscr.attron(curses.color_pair(1))
            stdscr.addstr(row_y, 2, item_str.ljust(width - 4))
            stdscr.attroff(curses.color_pair(1))
          elif actual_idx == came_idx:
            stdscr.attron(curses.color_pair(CAME_FROM_PAIR))
            stdscr.addstr(row_y, 2, item_str.ljust(width - 4))
            stdscr.attroff(curses.color_pair(CAME_FROM_PAIR))
          else:
            color = curses.color_pair(TYPE_PAIRS[conn["type"]])
            stdscr.attron(color)
            stdscr.addstr(row_y, 2, prefix)
            stdscr.attroff(color)
            room = max(0, width - 4 - len(prefix))
            title_attr = curses.A_BOLD if conn["type"] == "MAIN" else 0
            stdscr.addstr(
                row_y, 2 + len(prefix), conn["title"][:room], title_attr
            )

        if len(self.connections) == 1 and max_items > 1:
          stdscr.addstr(
              6, 2, "  (no links to or from this node)", curses.A_DIM
          )

      if preview_rows:
        self.draw_preview(stdscr, height - 1 - preview_rows, preview_rows, width)

      # --- Render Footer ---
      footer = self.footer_text(width)
      if self.status:
        footer = f" {self.status}"
        self.status = ""  # clears on next redraw (i.e. after next keypress)
      stdscr.addstr(
          height - 1, 0, footer.ljust(width - 1)[: width - 1], curses.A_REVERSE
      )

      stdscr.refresh()

      # --- Handle Input ---
      key = stdscr.getch()

      if key in (ord("q"), ord("Q")):
        break

      # Open the highlighted row (MAIN or any linked node) in Emacs
      elif key in (ord("e"), ord("E")):
        if not self.connections:
          self.status = "Nothing to open"
        else:
          target = self.connections[self.selected_idx]
          node = self.lookup_node(target["id"])
          if node:
            self.visit_in_emacs(node)
          elif self.db_ok:
            self.status = "Node no longer exists in the database"

      # Insert an Org link to the highlighted row at point in Emacs:
      # i = followed by a space, I = followed by a newline
      elif key in (ord("i"), ord("I")):
        if not self.connections:
          self.status = "Nothing to link to"
        else:
          target = self.connections[self.selected_idx]
          node = self.lookup_node(target["id"])
          if node:
            self.insert_link_in_emacs(node, newline=(key == ord("I")))
          elif self.db_ok:
            self.status = "Node no longer exists in the database"

      # Built-in help. "h" is already Back, so use "?" (as in less) and F1
      # (as in Midnight Commander).
      elif key in (ord("?"), curses.KEY_F1):
        self.show_help()

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
          if target["type"] == "MAIN":
            self.status = "Already at this node"
          else:
            self.history.append(self.current_node)
            self.came_from_id = None  # the reminder only applies after Back
            self.current_node = (
                target["id"],
                target["title"],
                target["file"],
            )
            self.connections = self.load_connections(self.current_node)
            self.selected_idx = 0  # land on MAIN of the new node
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
