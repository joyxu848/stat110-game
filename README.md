# STAT110 Game — README

This repository contains a small Flask web app used for practicing STAT 110 problems.
It provides a study/practice interface, progress tracking, and utilities to import problems.


## Requirements

- Python 3.11+ 
- The Python helper packages included in `requirements.txt`
- Pandoc (run 'brew install pandoc')

## Quick start (development)

1. Open a terminal in the project root.
2. Install requirements (Python, Pandoc) in terminal with Homebrew (brew install python3, brew install pandoc)
3. Create a python virtual environment:

```bash
python3 -m venv cs50
source cs50/bin/activate
pip install -r requirements.txt
```

4. Activate website

```bash
flask run
```

5. Visit http://127.0.0.1:5000 in your browser.

Notes:
- If `flask` is not in your PATH, use `./cs50/bin/python3 -m flask run`.
- When making changes to templates or Python code, restart the dev server as needed.

## Key files and folders

- `app.py` — main Flask application and routes.
- `templates/` — Jinja2 templates (pages like `study.html`, `progress.html`, `layout.html`).
- `static/` — static assets (CSS, `figures/`, `stat110-logo.png`, etc.).
- `problems.db` — primary problems database (if present in the repo or created by import scripts).
- `scripts/import_problems.py` — helper to import problems from CSV into the problem DB.
- `scripts/` — miscellaneous utility scripts related to importing and managing problems.

## Running the import script

If you have a CSV of problems and want to populate `problems.db`:

```bash
./cs50/bin/python3 scripts/import_problems.py
```

The import script detects common older/newer schema shapes and attempts a best-effort migration of problem attempts. Check the console output for warnings about unmapped attempts or missing topics.

## Database notes

- The app expects two SQLite databases by default:
  - `users.db` — stores user accounts and session info (the app uses `db = SQL("sqlite:///users.db")`).
  - `problems.db` — stores problems, topics, and attempts.


## LaTeX and images

- Problem statements and answers may contain LaTeX. The app uses a server-side Pandoc conversion pipeline to render LaTeX snippets to HTML.
- Images referenced inside LaTeX using `\\includegraphics{figures/...}` are expected to live in `static/figures/` as PNGs. The app includes logic to rewrite image `src` attributes to `/static/figures/<name>.png` at render time.

## Styling and CSS

- Main CSS file: `static/styles.css`.
- The project contains a `computer-modern.css` file to mimic LaTeX fonts.

## Troubleshooting

- If the server starts but pages return 403/401/redirects, check whether a route requires login and confirm your session state or test with a new browser incognito window.
- If Pandoc conversion fails, ensure Pandoc is installed on your system or that `pypandoc` is available in the environment.