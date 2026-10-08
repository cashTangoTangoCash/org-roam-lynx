# roam-lynx

**A fast, keyboard-driven terminal browser for your Org-roam network.**

Move through your notes the way you move through directories in Midnight Commander or follow links in Lynx: pick a node, see everything it links to and everything that links back to it, press a key to jump, press another to go back. No browser, no server, no waiting.

```
 NODE: Bike accident and injury
 File: /home/you/org/roam/20240312-bike-accident.org
 History Stack: 2 | Connections: 5 (Item 1/5)
────────────────────────────────────────────────────────────
  [OUT] Physical therapy log
  [OUT] Insurance claim
  [IN ] Summer 2024
  [IN ] Helmet research
  [IN ] Things I learned the hard way
────────────────────────────────────────────────────────────
  file · 212 words · 3 subheadings · 2 out / 3 in
  * Physical therapy log
    Week 1: mostly rest. Ice, elevation, and ...
    ... 6 more lines
```

> _Tip: replace the sketch above with a real screenshot or an asciinema recording once you have one. It's the single best thing you can add to this README._

## Why?

If you use Org-roam, you've probably tried [org-roam-ui](https://github.com/org-roam/org-roam-ui). The graph is beautiful, but it's a web app: it starts a server, opens a browser, and draws a force-directed graph that gets harder to read as your notes grow. It's great for admiring the shape of your network and less great for quickly getting somewhere in it.

roam-lynx takes a different approach:

- **Lightweight.** It's a single Python script that reads Org-roam's SQLite database directly. It uses only the Python standard library, and each keypress runs a small query.
- **Keyboard-first.** Everything is one keystroke, with vi-style keys and arrow keys both supported.
- **Link-centric, not graph-centric.** You always see one node and its direct neighbors, split into outgoing links and backlinks. That is usually what you want when you're thinking "where does this lead?"
- **Plays well with Emacs.** Found the node you were looking for? Press `e` and it opens in your running Emacs. The browser stays open so you can keep exploring.

It's not a replacement for org-roam-ui's big-picture view. It's the fast lane for when you just want to get around.

## Features

- Browse any node's **outgoing links** and **backlinks** in one list
- **Jump** into a linked node, and **go back** through your history
- **Preview pane** for the highlighted connection, with Org-aware styling: property drawers and `#+` keywords hidden, headings colored by level, long sections collapsed
- **Stats line** per node: word count, subheading count, and how many links go out and come in. Nodes with very little content are flagged as **stubs**, so you can tell at a glance whether a node is worth opening
- **Open in Emacs** via `emacsclient` without leaving the browser
- **Refresh** after you've edited in Emacs, with your selection preserved
- **Fuzzy search front end** (`roam-lynx-find`) that searches titles and aliases with fzf and sorts by most recently modified
- **Read-only**: the database is opened in read-only mode, so it can't interfere with Emacs

## Requirements

- Python 3.9+ (uses only the standard library: `curses`, `sqlite3`)
- Org-roam v2 with a populated database (usually `~/.emacs.d/org-roam.db`)
- For the search front end: `bash`, [`fzf`](https://github.com/junegunn/fzf), and the `sqlite3` command-line tool
- For the `e` key: a running Emacs server (`M-x server-start`, or `(server-start)` in your init file) and `emacsclient` on your `PATH`
- Linux or macOS (Windows lacks Python's `curses` by default)

## Installation

```bash
git clone https://github.com/YOUR-USERNAME/roam-lynx.git
cd roam-lynx

# Put the files somewhere on your PATH
install -m 755 roam_lynx.py ~/.local/bin/roam_lynx.py
install -m 755 roam-lynx-find ~/.local/bin/roam-lynx-find
```

Make sure `~/.local/bin` is on your `PATH`. If you keep the Python script somewhere else, point the launcher at it:

```bash
export ROAM_LYNX_PY=/path/to/roam_lynx.py
```

## Usage

### Search, then browse

```bash
roam-lynx-find            # fzf over all nodes, most recently modified first
roam-lynx-find bike       # pre-filtered to titles and aliases matching "bike"
```

If exactly one node matches, you go straight into the browser. Otherwise fzf lets you pick one, with a live file preview alongside.

### Browse directly

```bash
python3 roam_lynx.py "Some node title"
```

The title is matched as a substring. With no argument, the script starts at the node named in `START_NODE_TITLE` near the top of the file. Edit that to whatever you like, or leave it and always pass a title.

## Keys

| Key | Action |
| --- | --- |
| `j` / `k`, `↓` / `↑` | Move the selection |
| `PgDn` / `PgUp`, `Space`, `Ctrl-f` / `Ctrl-b` | Page down / up |
| `l`, `→`, `Enter` | Jump to the highlighted node |
| `h`, `←`, `Backspace` | Go back |
| `e` | Open the **current** node in Emacs |
| `r` | Refresh from the database |
| `p` | Toggle the preview pane |
| `q` | Quit |

In the list, `[OUT]` entries are links from the current node and `[IN ]` entries are backlinks to it.

## How it works

Org-roam keeps an index of your notes in a SQLite database. roam-lynx queries the `nodes` and `links` tables for the current node's neighbors, and reads the node's file from disk for the preview (cached by file modification time, so revisiting is free). Opening in Emacs calls `org-roam-node-visit` through `emacsclient --eval`, which lands on the right heading even for nodes that aren't whole files.

Because it reads the database rather than your files, it's only as current as Org-roam's index. Save in Emacs (with `org-roam-db-autosync-mode` on) and press `r` to see changes.

## Known limitations

- Only `id:` links are followed, which are the links Org-roam itself tracks. Plain URLs and file links aren't shown as connections.
- The database location is `~/.emacs.d/org-roam.db`. If yours lives elsewhere (for example under `~/.config/emacs/`), change `DEFAULT_DB` at the top of `roam_lynx.py`.
- The preview is a lightweight approximation of Org's appearance, not a full renderer.
- Heading-level nodes assume UTF-8 files with LF line endings when locating their text.

## Roadmap ideas

- Command-line `--db` option and `ORG_ROAM_DB` environment variable
- Open the *highlighted* node in Emacs (for example on `E`)
- Jump by node ID, so duplicate titles are unambiguous
- Live auto-refresh when the database changes
- Tag display and filtering

## Contributing

Issues and pull requests are welcome. This is a small, single-file project and I'd like to keep it fast and dependency-free.

## License

Choose a license and add a `LICENSE` file. [MIT](https://choosealicense.com/licenses/mit/) is a common choice for small tools like this.

## Acknowledgments

Inspired by the file-browsing feel of [Midnight Commander](https://midnight-commander.org/) and the link-following style of [Lynx](https://lynx.invisible-island.net/), and built on the excellent [Org-roam](https://www.orgroam.com/). Also see [org-roam-ui](https://github.com/org-roam/org-roam-ui) for a graphical alternative.
