# DESIGN.md

## High-level architecture

- Python Flask application (`app.py`) serving HTML via Jinja2 templates.
- SQLite databases for persistent storage:
  - `users.db` (users, sessions, authentication-related data)
  - `problems.db` (problems, topics, attempts)
- Static files served from `/static` (CSS, images, fonts, figures).
- Server-side Pandoc pipeline to convert LaTeX snippets (problem text and answers) into HTML.

## Routes and responsibilities

- `/` — dashboard/index (redirects or shows landing based on session).
- `/register`, `/login`, `/logout` — user authentication flows. After registering a user is automatically logged in.
- `/study` — practice page; selects problems and presents them to the user. Converts LaTeX problem text and answer to HTML before rendering.
- `/progress` — shows study statistics and lists problems you got wrong with topics and metadata.
- `/break` - minigame for users to play that is stat110-themed.
- `/account_settings` — manages username/password changes (template created and wired in `app.py`).

See `app.py` for concrete route implementations and helper functions.

## Templates and static assets

- Templates are in `templates/`. The main layout is `layout.html` which includes Bootstrap and the site favicon/logo.
- `static/styles.css` contains project CSS. There is a `computer-modern.css` file to bring LaTeX-like fonts closer to the original look.
- Figures referenced from LaTeX are stored in `static/figures/` and the server rewrites their `src` attributes for web consumption.

## LaTeX rendering pipeline

1. Raw LaTeX-like snippets (from DB fields) are pre-processed by `_clean_latex_text()` in `app.py`:
   - Removes TeX comments and other problematic constructs.
   - Rewrites certain macros (for example `\\displaylimits` -> `\\limits`) to avoid Pandoc warnings.
   - Rewrites `\\includegraphics{figures/...}` references where appropriate to prefer PNG filenames.
2. `_latex_to_html()` calls Pandoc (via `pypandoc` when available, or subprocess fallback) with `--mathml` and `--resource-path=static` so Pandoc can resolve included resources.
3. After Pandoc returns HTML, `_rewrite_image_paths()` post-processes the HTML to convert image `src` values like `figures/foo.png` into `/static/figures/foo.png`. It also contains fallback logic to map `.pdf`/`.jpg` references to `.png` if the PNG exists.

Rationale: The LaTeX source code that stores the problems is meant to render inside a LaTeX document, but it does not render well inside an HTML website. Therefore, the workaround was to convert the LaTeX to HTML first with the third-party pandoc package, and then render that HTML directly. Along the way, fixes were implemented to render the images and custom commands that had been defined in the LaTeX document.

## Database schema (summary)

- `problems` table: stores `id`, `year`, `problem` (problem number), `problem` text, `answer` text, other metadata.
- `topics` table: list of topics/categories.
- `problem_topics` table: many-to-many relationship connecting problems to topics.
- `problem_attempts` table: tracks user attempts for problems.
- `users` (in `users.db`): standard users table used for authentication.

## Import script and data flow

- The import script reads CSV rows and inserts problems and related topics into `problems.db`.
- This is designed so that it is easy in the future to update the csv file with more problems that can get inserted into the website pipeline.
- When migrating `problem_attempts`, the script maps legacy columns to the current schema and attempts to associate each attempt with the canonical `problems.id`. If mapping fails, attempts are logged and skipped or assigned to a fallback topic such as `Any`.

## Styling decisions

- Building off the official Stat110 logo, styling is stored in static/styles.css. Everything is themed in blue and includes the logo in static/stat110-logo.png.

## Security & operational notes

- Passwords: Ensure password hashing (the app should use `werkzeug.security` or `flask-bcrypt`).

## Known limitations and future work

- Pandoc dependency: currently the website depends on the user installing pandoc. Ideally in the future this would already be completed, but currently it is kept in the website to preserve the flexibility of being able to add more problems.
- Image handling: Current heuristics assume PNGs exist for images referenced in LaTeX. There were only three images so it wasn't too hard, but in the future may need a more official pipeline.
