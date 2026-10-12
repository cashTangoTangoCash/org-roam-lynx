# org-roam-lynx

**A fast, keyboard-driven terminal browser for your Org-roam network.**

Move through your notes the way you move through directories in Midnight Commander or follow links in Lynx: pick a node, see everything it links to and everything that links back to it, press a key to jump, press another to go back. No browser, no server, no waiting.

In this GIF, we are roaming slowly so you can see what is going on.  Node preview is being turned on and off.
<p align="center">
  <img src="docs/GIFs/simple-demo.gif" alt="Lynx-style Org-Roam Terminal Explorer Demo" width="700">
</p>

Choose a starting node via the shell script:
![Choose a starting node with the shell script](docs/images/choose-starting-node-with-shell-script.jpg)

Roam around your org roam node network (preview turned off):
![Roam around lynx-style without preview](docs/images/roam-around-without-preview.jpg)

Roam around your org roam node network (preview turned on):
![Roam around lynx-style with preview](docs/images/roam-around-with-preview.jpg)

Please note: this is designed for use with an Emacs session running
(e.g. GUI Emacs running in another PC monitor).  The GIF doesn't show
how we can hit the "e" key and visit a node in Emacs.

## Why?

If you use Org-roam, you've probably tried [org-roam-ui](https://github.com/org-roam/org-roam-ui). The graph is beautiful, but it's a web app: it starts a server, opens a browser, and draws a force-directed graph that gets harder to read as your notes grow. It's great for admiring the shape of your network and less great for quickly getting somewhere in it.

org-roam-lynx takes a different approach:

- **Lightweight.** It's a single Python script that reads Org-roam's SQLite database directly. It uses only the Python standard library, and each keypress runs a small query.
- **Keyboard-first.** Everything is one keystroke, with vi-style keys and arrow keys both supported.
- **Link-centric, not graph-centric.** You always see one node and its direct neighbors: where it links to, what links back to it, and what does both. That is usually what you want when you're thinking "where does this lead?"
- **Plays well with Emacs.** Found the node you were looking for? Press `e` and it opens in your running Emacs, or press `i` to drop a link to it into whatever you're writing. The browser stays open so you can keep exploring.

It's not a replacement for org-roam-ui's big-picture view. It's the fast lane for when you just want to get around.

## Features

- Browse a node's **links in one list**: the node itself (`MAIN`), then everything it links to (`OUT`), everything that links to it (`IN`), and nodes that link both ways (`BIDIR`, shown once)
- **Jump** into a linked node, and **go back** through your history. After going back, the node you came from is marked so you can find your place again
- **Preview pane** for the highlighted row, with Org-aware styling: property drawers and `#+` keywords hidden, headings colored by level, long sections collapsed
- **Preview header** per node: its title, word count, subheading count, how many nodes it links to and from, and when it was created and last modified. Nodes with very little content are flagged as **stubs**, so you can tell at a glance whether a node is worth opening
- **Open in Emacs** via `emacsclient` without leaving the browser. `e` works on whichever row is highlighted, including MAIN
- **Insert links into Emacs**: `i` inserts an Org link to the highlighted node at point in Emacs, followed by a space; `I` follows it with a newline. A quick way to paste the same link in several places without calling `org-roam-node-insert` each time
- **Built-in help**: press `?` and this README opens in Emacs, rendered to HTML with pandoc and shown in eww. No separate help page to maintain
- **Refresh** after you've edited in Emacs, with your selection preserved
- **Fuzzy search front end** that searches titles and aliases with fzf, sorts by most recently modified, and hands the chosen node to the browser **by ID**, so duplicate or overlapping titles are never ambiguous
- **Read-only**: the database is opened in read-only mode, so it can't interfere with Emacs

## Requirements

- Python 3.9+ (uses only the standard library: `curses`, `sqlite3`)
- Org-roam v2 with a populated database
- For the search front end: `bash`, [`fzf`](https://github.com/junegunn/fzf), and the `sqlite3` command-line tool
- For the `e`, `i`/`I`, and `?` keys: a running Emacs server (`M-x server-start`, or `(server-start)` in your init file) and `emacsclient` on your `PATH`. Browsing itself works without Emacs
- Optional: [`pandoc`](https://pandoc.org/) for the built-in help. Without it, `?` opens the README as plain text
- Optional: on Linux, GNU `stat` (part of coreutils) lets the preview show a file's creation date when its filename has no timestamp
- Linux or macOS (Windows lacks Python's `curses` by default)

## Installation

```bash
git clone https://github.com/cashTangoTangoCash/org-roam-lynx.git
cd org-roam-lynx

# Symlink the files onto your PATH
chmod +x org_roam_lynx_browse_graph.py org-roam-lynx-find-starting-node-then-browse-graph.sh
ln -s "$PWD/org_roam_lynx_browse_graph.py" ~/.local/bin/
ln -s "$PWD/org-roam-lynx-find-starting-node-then-browse-graph.sh" ~/.local/bin/
```

Symlinks are the recommended install: the built-in help finds `README.md` (and the screenshots in `docs/`) next to the real script, and `git pull` updates everything at once. If you would rather copy the files (for example with `install -m 755`), also copy `README.md` to `~/.local/share/org-roam-lynx/` or point `ROAM_LYNX_README` at it, or the help won't find it.

Make sure `~/.local/bin` is on your `PATH`. The script names are long on purpose (they say what they do), so a short alias is handy. Add something like this to your shell config:

```bash
alias roam='org-roam-lynx-find-starting-node-then-browse-graph.sh'
```

If you keep the Python script somewhere other than `~/.local/bin`, point the launcher at it:

```bash
export ROAM_LYNX_PY=/path/to/org_roam_lynx_browse_graph.py
```

## Usage

### Search, then browse

```bash
org-roam-lynx-find-starting-node-then-browse-graph.sh              # fzf over all nodes, most recently modified first
org-roam-lynx-find-starting-node-then-browse-graph.sh bike         # pre-filtered to titles and aliases matching "bike"
org-roam-lynx-find-starting-node-then-browse-graph.sh "bike shop"  # put a phrase in double quotes
org-roam-lynx-find-starting-node-then-browse-graph.sh --help       # brief help
```

If exactly one node matches, you go straight into the browser. Otherwise fzf lets you pick one, with a live file preview alongside.

### Browse directly

```bash
python3 org_roam_lynx_browse_graph.py "Some node title"        # by title
python3 org_roam_lynx_browse_graph.py --id <org-roam-id>       # by ID
python3 org_roam_lynx_browse_graph.py --db /path/to/org-roam.db "Some node title"
```

A title is matched exactly if possible, otherwise as a substring. `--id` is unambiguous and overrides the title. With no arguments, the script starts at the node named in `START_NODE_TITLE` near the top of the file; edit that to whatever you like.

## Reading the screen

The first row of the list is always `[MAIN ]`, the node you are visiting. The cursor starts there, and the preview shows that node. Below it, each linked node appears once:

| Label | Meaning |
| --- | --- |
| `[MAIN ]` | The node you are visiting |
| `[BIDIR]` | It links to this node **and** this node links to it |
| `[OUT  ]` | This node links to it |
| `[IN   ]` | It links to this node (a backlink) |

Move the cursor down to any row to preview that node and act on it. Jumping to a row makes it the new MAIN.

**Where you came from.** When you go back, the cursor lands on MAIN as usual, and the node you just came back from is marked with a yellow row and a `←` in the margin. It's only a reminder: it doesn't move the cursor or change what the preview shows. The header line names it too, with its position in the list, in case a long list has scrolled it out of view. The mark disappears the next time you jump forward.

**The preview header.** The first lines of the preview pane show the node's title, then a summary such as:

```
212 words · 3 subheadings · 2 out / 3 in · looks like a stub
created 03/12/2024 · modified 10/03/2026 (8 days ago)
```

`out / in` counts distinct nodes this one links to and is linked from, so the numbers match the rows in the list. On a narrow terminal the summary wraps onto more lines.

Where the dates come from (Org-roam's database doesn't record either one):

- **Modified** is the file's modification time. For a heading-level node, that is the whole file's date, not the heading's.
- **Created** is a timestamp at the start of the filename if there is one (`20240312123456-slug.org`, `20240312-slug.org`, or `2024-03-12.org`). Otherwise it falls back to the filesystem's creation time, which copying, syncing, or a git checkout can reset to the day the file arrived on your machine. If neither is available, it's left out.

## Keys

| Key | Action |
| --- | --- |
| `j` / `k`, `↓` / `↑` | Move the cursor |
| `PgDn` / `PgUp`, `Space`, `Ctrl-f` / `Ctrl-b` | Page down / up |
| `l`, `→`, `Enter` | Jump to the highlighted node (does nothing on MAIN, since you're already there) |
| `h`, `←`, `Backspace` | Go back through your history |
| `e` | Open the highlighted row (MAIN or any linked node) in Emacs |
| `i` | Insert an Org link to the highlighted row at point in Emacs, followed by a space |
| `I` | Same, followed by a newline |
| `?`, `F1` | Open the built-in help (this README) in Emacs. `h` is already Back, so help lives on `?` |
| `r` | Refresh from the database |
| `p` | Toggle the preview pane |
| `q` | Quit |

The hints along the bottom of the screen change with the highlighted row: for example, `l:Jump` isn't offered on MAIN, and `h:Back` only appears when there is history to go back through.

## Inserting links into Emacs

Press `i` on any row (MAIN, a link, or a backlink) and an Org link to that node is inserted at point in Emacs, followed by a space: `[[id:...][Node title]] `. `I` does the same and ends with a newline instead.

This is for adding links quickly. Visit the note you are writing in Emacs and put point where the first link should go. Then move the cursor in the browser to a node and press `i`. Repeat for as many nodes as you like: each link lands right after the previous one, and you never leave the terminal or wait on `org-roam-node-insert`.

A few details:

- The link goes into the buffer shown in Emacs's selected window, which is the one you were last working in, at point. If a minibuffer prompt is open, it goes to the window you came from.
- Emacs is not raised, so you can keep going from the terminal. The footer confirms which buffer received the link, for example `Inserted link to "Alpha" in Emacs buffer notes.org`.
- Emacs builds the link itself (with `org-link-make-string`, the function org-roam's own insert command uses), using the title org-roam has there. Titles with quotes, non-ASCII characters, or brackets are handled the standard Org way.
- If the buffer is read-only, nothing is inserted and the footer shows Emacs's error. Each insertion is a single edit, so one undo removes it.
- A new link isn't in org-roam's database until Emacs saves that buffer and syncs. Press `r` in the browser afterward to see it as a new row.
- If the built-in help page is the selected window in Emacs, press `q` there first, since it's read-only.

## Built-in help

Press `?` (or `F1`) and this README opens in Emacs. It is converted to HTML with pandoc and shown with eww, and it opens at the "Reading the screen" heading so the legend and key table come first. Scroll up for the rest. Press `q` in eww to close it and return to your previous buffer.

The help *is* the README, so there is no second page to keep in sync.

A few details:

- The generated page is written as `org-roam-lynx-help.html` in a private per-user directory (`$XDG_RUNTIME_DIR/org-roam-lynx/`, else `/tmp/org-roam-lynx-<uid>/`) and is overwritten each time.
- The README is found at `$ROAM_LYNX_README`, then next to the script (symlinks are followed), then at `~/.local/share/org-roam-lynx/README.md`.
- Images in the README resolve against the README's own folder, so the screenshots show up if `docs/` is next to it.
- Without pandoc, the README opens read-only as plain text instead.
- Like `e`, help needs a running Emacs server.

## Configuration

The database location is resolved in this order, by both the shell launcher and the Python script:

1. `--db PATH` (Python script only; the launcher passes its resolved path this way)
2. the `ORG_ROAM_DB` environment variable
3. `$XDG_CONFIG_HOME/emacs/org-roam.db` (default `~/.config/emacs/org-roam.db`)
4. `~/.emacs.d/org-roam.db`

If your `org-roam-db-location` is customized, or you use a distribution such as Doom Emacs that keeps the database under a cache directory, set it once in your shell profile:

```bash
export ORG_ROAM_DB="$HOME/path/to/org-roam.db"
```

| Variable | Purpose |
| --- | --- |
| `ORG_ROAM_DB` | Path to `org-roam.db` |
| `ROAM_LYNX_PY` | Path to `org_roam_lynx_browse_graph.py` (used by the launcher) |
| `ROAM_LYNX_README` | Path to `README.md` for the built-in help (optional; see [Built-in help](#built-in-help)) |

### Tweaking the look

A few constants near the top of `org_roam_lynx_browse_graph.py` are meant to be edited:

| Constant | What it controls |
| --- | --- |
| `START_NODE_TITLE` | Starting node when none is given |
| `DATE_FORMAT` | How dates look in the preview (default `%m/%d/%Y`; use `%Y-%m-%d` for 2026-10-11) |
| `STUB_WORDS` | Word count below which a node is flagged as a stub |
| `MAX_BODY_LINES` | Body lines shown under each heading in the preview |
| `TYPE_RANK` | Order of the list rows below MAIN (default: BIDIR, OUT, IN) |
| `CAME_FROM_PAIR`, `CAME_FROM_GLYPH` | Color pair and margin arrow for the came-from reminder |
| `HELP_ANCHOR` | README heading the help opens at (default `reading-the-screen`). If you rename that heading, change this to match: lowercase, with hyphens for spaces |

## How it works

Org-roam keeps an index of your notes in a SQLite database. org-roam-lynx queries the `nodes` and `links` tables for the current node's neighbors, and reads the node's file from disk for the preview (cached by file modification time, so revisiting is free). Opening in Emacs calls `org-roam-node-visit` through `emacsclient --eval`, which lands on the right heading even for nodes that aren't whole files. Inserting links and showing help work the same way: a short piece of Emacs Lisp sent through `emacsclient --eval`.

Because it reads the database rather than your files, it's only as current as Org-roam's index. Save in Emacs (with `org-roam-db-autosync-mode` on) and press `r` to see changes.

## Known limitations

- Only `id:` links are followed, which are the links Org-roam itself tracks. Plain URLs and file links aren't shown as connections.
- The preview is a lightweight approximation of Org's appearance, not a full renderer.
- Heading-level nodes assume UTF-8 files with LF line endings when locating their text.
- Dates in the preview belong to the file, so every heading-level node in a file shows the same dates. The created date can be wrong for files whose names have no timestamp and whose creation time was reset by copying or syncing.
- `i`/`I` insert into whatever buffer Emacs's selected window is showing, so glance at the footer message the first time to confirm the link landed where you meant.
- The built-in help needs Emacs, and ideally pandoc. Browsing works without them.
- In the fzf front end, double-quote characters are stripped from displayed titles (the browser itself shows them correctly, since it looks nodes up by ID).

## Roadmap ideas

- Live auto-refresh when the database changes
- Tag display and filtering
- Read a `:CREATED:` property or `#+date:` line for the created date

## Contributing

This is a personal project that I share in case it’s useful. I may not respond to issues or pull requests, and I make no promises about support. Feel free to fork it.

## How it was Developed

This script was built through an iterative dialogue with Gemini (free
version) and Claude (free version). For a detailed look at the logic,
the alternative approaches considered, and the evolution of the code,
check the contents of the chat/ folder in this repository.

## License

See LICENSE file

## Acknowledgments

Inspired by the file-browsing feel of [Midnight Commander](https://midnight-commander.org/) and the link-following style of [Lynx](https://lynx.invisible-island.net/), and built on the excellent [Org-roam](https://www.orgroam.com/). Also see [org-roam-ui](https://github.com/org-roam/org-roam-ui) for a graphical alternative.
