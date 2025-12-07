import os
import re
import subprocess
from typing import Optional

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session, jsonify
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd, process_holdings

# Optional: use pypandoc if available; otherwise fall back to calling pandoc binary
try:
    import pypandoc  # type: ignore
except Exception:
    pypandoc = None

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///users.db")
problems_db = SQL("sqlite:///problems.db")

# Path to your macros file (adjust if needed)
MACROS_PATH = os.path.join(os.path.dirname(__file__), "static", "macros.tex")
_LATEX_MACROS_CACHE: str | None = None

def _get_latex_macros() -> str:
    """Load LaTeX macro definitions from static/macros.tex, cached in memory."""
    global _LATEX_MACROS_CACHE
    if _LATEX_MACROS_CACHE is not None:
        return _LATEX_MACROS_CACHE

    try:
        with open(MACROS_PATH, "r", encoding="utf-8") as f:
            _LATEX_MACROS_CACHE = f.read()
    except OSError:
        # If the file is missing, just use an empty string so things still render.
        _LATEX_MACROS_CACHE = ""
    return _LATEX_MACROS_CACHE


def _rewrite_image_paths(html: str) -> str:
    """Rewrite image src attributes from Pandoc output to point to Flask static files.

    Assumes you've put PNGs in static/figures with the same base names as the
    LaTeX figures.
    """
    if not html:
        return html

    def repl(match):
        prefix, src, quote = match.group(1), match.group(2), match.group(3)
        src_norm = src.lstrip("./")  # remove leading ./ but KEEP no leading /

        # Case 1: src="figures/chain15.pdf" or "figures/chain15.jpg" or "figures/chain15.png"
        if src_norm.startswith("figures/"):
            rel = src_norm[len("figures/"):]  # "chain15.pdf"
            base, ext = os.path.splitext(rel)
            # Always point to PNG under /static/figures/
            return f'{prefix}/static/figures/{base}.png{quote}'

        # Case 2: src="static/figures/chain15.png" (missing leading slash)
        if src_norm.startswith("static/figures/"):
            return f'{prefix}/static/{src_norm[len("static/") :]}{quote}'

        # Otherwise, leave it alone
        return f"{prefix}{src}{quote}"

    pattern = re.compile(r'(<img\b[^>]*\bsrc=["\'])([^"\']+)(["\'])', flags=re.IGNORECASE)
    return pattern.sub(repl, html)


def _clean_latex_text(text: str) -> str:
    """Return a copy of LaTeX text with leading TeX comment markers removed per-line.

    This keeps the original DB content intact but ensures the HTML view shows the
    commented-out lines (our importer may have prefixed lines with '%').
    """
    if text is None:
        return text
    
    # Remove full-line comments
    cleaned = re.sub(r'(?m)^[ \t]*%.*(?:\n|$)', '', text)

    # Replace \textnormal{...} with \mathrm{...} so Pandoc's math parser understands it
    cleaned = re.sub(r'\\textnormal\{([^}]*)\}', r'\\mathrm{\1}', cleaned)

    # Remove leading \noin or \noindent at the very start (plus any following whitespace)
    cleaned = re.sub(r'^\s*\\noin\b\s*', '', cleaned)
    cleaned = re.sub(r'^\s*\\noindent\b\s*', '', cleaned)

    # Pandoc's LaTeX math parser does not support the low-level primitive
    # \displaylimits (used to alter operator limit placement). Replace it
    # with \limits (or remove) so Pandoc can parse limits like \lim_{n\to\infty}.
    cleaned = re.sub(r'\\displaylimits', r'\\limits', cleaned)

    # Rewrite \includegraphics paths from .pdf/.jpg/.jpeg to .png
    cleaned = re.sub(
        r'(\\includegraphics(?:\[[^\]]*\])?\{)figures/([^}]+?)(?:\.pdf|\.jpg|\.jpeg)(\})',
        r'\1figures/\2.png\3',
        cleaned,
    )

    return cleaned


def _latex_to_html(text: str | None) -> str | None:
    """Convert LaTeX snippet to HTML using pypandoc or pandoc binary.

    - Prepends macros from static/macros.tex so commands like \\Pois are known.
    - Enables the latex_macros extension in Pandoc.
    - Uses MathML output so math renders without MathJax.

    Returns None if input is None. On error, falls back to returning
    the original text wrapped in <pre> to avoid losing content.
    """
    if text is None:
        return None

    cleaned = _clean_latex_text(text)
    macros = _get_latex_macros()

    # Feed macros + body into Pandoc so it sees the \\newcommand definitions
    full_input = (macros + "\n" + cleaned) if macros else cleaned

    # Try pypandoc first
    try:
        if pypandoc is not None:
            html = pypandoc.convert_text(
                full_input,
                to="html",
                format="latex+latex_macros",
                extra_args=["--mathml", "--resource-path=static"],  # make math render without MathJax
            )
            # rewrite image paths so they point at Flask's /static/ location
            return _rewrite_image_paths(html)
    except Exception:
        pass

    # Fall back to calling pandoc binary if available
    try:
        proc = subprocess.run(
            [
                "pandoc",
                "-f",
                "latex+latex_macros",  # understand \newcommand definitions
                "-t",
                "html",
                "--mathml",            # emit MathML for equations
                "--resource-path=static",
            ],
            input=full_input,
            text=True,
            capture_output=True,
            check=True,
        )
        html = proc.stdout
        return _rewrite_image_paths(html)
    except Exception:
        # As a final fallback, return plain text inside <pre>
        print("exception in _latex_to_html, falling back to <pre>")
        safe_text = (
            "<pre>"
            + cleaned.replace("&", "&amp;")
                     .replace("<", "&lt;")
                     .replace(">", "&gt;")
            + "</pre>"
        )
        return safe_text


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/break")
@login_required
def game_menu():
    """Show the menu to choose a game"""
    return render_template("game_select.html")

@app.route("/blotchville")
@login_required
def blotchville():
    """Play the Bus Game"""
    leaders = db.execute("""
        SELECT users.username, leaderboard.score, leaderboard.timestamp
        FROM leaderboard
        JOIN users ON users.id = leaderboard.user_id
        ORDER BY score DESC
        LIMIT 10
    """)
    # Ensure your template is named blotchville.html
    return render_template("blotchville.html", leaders=leaders)


@app.route("/")
def index():
    """Public landing page for guests; dashboard for logged-in users"""
    # If user is logged in, show dashboard with large links
    if session.get("user_id"):
        return render_template("dashboard.html")

    # Otherwise, show the public homepage
    return render_template("index.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        username = request.form.get("username")
        if not username:
            return apology("Must enter a username")
        password = request.form.get("password")
        if not password:
            return apology("Must enter a password")
        confirmation = request.form.get("confirmation")
        if not confirmation:
            return apology("Must reenter password")
        if confirmation != password:
            return apology("Password does not match")

        try:
            new_user_id = db.execute("INSERT INTO users (username, hash) VALUES(?,?)",
                       username, generate_password_hash(password))
            
            # Log the user in automatically
            session["user_id"] = new_user_id

            return redirect("/")
        except ValueError:
            return apology("Username taken")
    else:
        return render_template("register.html")


@app.route("/account_settings", methods=["GET", "POST"])
@login_required
def account_settings():
    user_id = session["user_id"]
    if request.method == "POST":

        current_password = request.form.get("current_password")
        new_password = request.form.get("new_password")
        confirmation = request.form.get("confirmation")

        if not current_password or not new_password or not confirmation:
            return apology("All fields required")
        if new_password != confirmation:
            return apology("New password does not match confirmation")

        check_password = db.execute("SELECT hash FROM users WHERE id = ?", user_id)
        if not check_password:
            return apology("Current password not found")
        if not check_password_hash(check_password[0]["hash"], current_password):
            return apology("Current password is incorrect")
        if check_password_hash(check_password[0]["hash"], new_password):
            return apology("New password must be different")

        # reset password using hash function
        db.execute("UPDATE users SET hash = ? WHERE id = ?",
                   generate_password_hash(new_password), user_id)

        return redirect("/")

    else:
        # Show the account settings form with current username
        user_row = db.execute("SELECT username FROM users WHERE id = ?", user_id)
        username = user_row[0]["username"] if user_row else ""
        return render_template("account_settings.html", username=username)

@app.route("/study", methods=["GET", "POST"])
@login_required
def study():
    user_id = session["user_id"]

    # For the topic dropdown: topics table now stores available topics
    topics = problems_db.execute(
        "SELECT id, name FROM topics ORDER BY name"
    )

    if request.method == "POST":

        action = request.form.get("action")          # "reveal", "right", "wrong"
        problem_id = request.form.get("problem_id")
        selected_topic = request.form.get("topic") or "Any"

        if not problem_id:
            return redirect("/study")

        # Fetch the problem row
        rows = problems_db.execute(
            "SELECT id, year, problem, text, answer FROM problems WHERE id = ?",
            problem_id,
        )
        if len(rows) != 1:
            return redirect("/study")

        problem_row = rows[0]

        # Get topic names for this problem
        problem_topic_rows = problems_db.execute(
            "SELECT t.name FROM topics t JOIN problem_topics pt ON t.id = pt.topic_id WHERE pt.problem_id = ? ORDER BY t.name",
            problem_row["id"],
        )
        problem_topics = [r["name"] for r in problem_topic_rows]

        if action == "reveal":
            # Show the same problem, now with the answer visible
            # prepare cleaned fields for rendering
            problem_row['html_text'] = _latex_to_html(problem_row.get('text'))
            problem_row['html_answer'] = _latex_to_html(problem_row.get('answer'))
            return render_template(
                "study.html",
                topics=topics,
                selected_topic=selected_topic,
                problem=problem_row,
                problem_topics=problem_topics,
                show_answer=True,
                feedback=None,
            )

        elif action in ("right", "wrong"):
            correct = 1 if action == "right" else 0

            # Determine topic_id to log: prefer selected_topic if provided, else fallback to one of the problem's topics, else create/use 'Any'
            if selected_topic != "Any":
                tid_rows = problems_db.execute("SELECT id FROM topics WHERE name = ?", selected_topic)
                topic_id = tid_rows[0]["id"] if tid_rows else None
            else:
                # try to find a topic for this problem
                tid_rows = problems_db.execute("SELECT topic_id FROM problem_topics WHERE problem_id = ? LIMIT 1", problem_row["id"])
                if tid_rows:
                    topic_id = tid_rows[0]["topic_id"]
                else:
                    # ensure 'Any' topic exists
                    problems_db.execute("INSERT OR IGNORE INTO topics (name) VALUES (?)", "Any")
                    tid_rows = problems_db.execute("SELECT id FROM topics WHERE name = ?", "Any")
                    topic_id = tid_rows[0]["id"]

            problems_db.execute(
                "INSERT INTO problem_attempts (user_id, problem_id, topic_id, correct) VALUES (?, ?, ?, ?)",
                user_id,
                problem_row["id"],
                topic_id,
                correct,
            )

            # After logging, get a new random problem (same topic filter)
            if selected_topic == "Any":
                probs = problems_db.execute(
                    "SELECT id, year, problem, text, answer FROM problems ORDER BY RANDOM() LIMIT 1"
                )
            else:
                probs = problems_db.execute(
                    "SELECT p.id, p.year, p.problem, p.text, p.answer FROM problems p "
                    "JOIN problem_topics pt ON p.id = pt.problem_id "
                    "JOIN topics t ON pt.topic_id = t.id "
                    "WHERE t.name = ? ORDER BY RANDOM() LIMIT 1",
                    selected_topic,
                )

            new_problem = probs[0] if probs else None

            new_problem_topics = []
            if new_problem:
                pt_rows = problems_db.execute(
                    "SELECT t.name FROM topics t JOIN problem_topics pt ON t.id = pt.topic_id WHERE pt.problem_id = ? ORDER BY t.name",
                    new_problem["id"],
                )
                new_problem_topics = [r["name"] for r in pt_rows]
            if new_problem:
                new_problem['html_text'] = _latex_to_html(new_problem.get('text'))
                new_problem['html_answer'] = _latex_to_html(new_problem.get('answer'))

            return render_template(
                "study.html",
                topics=topics,
                selected_topic=selected_topic,
                problem=new_problem,
                problem_topics=new_problem_topics,
                show_answer=False,
                feedback="Nice, logged! Here's a new problem." if new_problem else "No more problems found for this topic.",
            )

        # Fallback
        return redirect("/study")

    # GET: either random problem or a specific one (for review)
    selected_topic = request.args.get("topic") or "Any"
    problem_id = request.args.get("problem_id")

    problem_row = None

    if problem_id:
        rows = problems_db.execute(
            "SELECT id, year, problem, text, answer FROM problems WHERE id = ?",
            problem_id,
        )
        if rows:
            problem_row = rows[0]
            # Ensure dropdown matches this problem’s first topic if available
            pt_rows = problems_db.execute(
                "SELECT t.name FROM topics t JOIN problem_topics pt ON t.id = pt.topic_id WHERE pt.problem_id = ? ORDER BY t.name LIMIT 1",
                problem_row["id"],
            )
            if pt_rows:
                selected_topic = pt_rows[0]["name"]
    else:
        if selected_topic == "Any":
            probs = problems_db.execute(
                "SELECT id, year, problem, text, answer FROM problems ORDER BY RANDOM() LIMIT 1"
            )
        else:
            probs = problems_db.execute(
                "SELECT p.id, p.year, p.problem, p.text, p.answer FROM problems p "
                "JOIN problem_topics pt ON p.id = pt.problem_id "
                "JOIN topics t ON pt.topic_id = t.id "
                "WHERE t.name = ? ORDER BY RANDOM() LIMIT 1",
                selected_topic,
            )
        problem_row = probs[0] if probs else None

    # If we have a problem, fetch its topic names
    problem_topics = []
    if problem_row:
        pt_rows = problems_db.execute(
            "SELECT t.name FROM topics t JOIN problem_topics pt ON t.id = pt.topic_id WHERE pt.problem_id = ? ORDER BY t.name",
            problem_row["id"],
        )
        problem_topics = [r["name"] for r in pt_rows]
    if problem_row:
        problem_row['html_text'] = _latex_to_html(problem_row.get('text'))
        problem_row['html_answer'] = _latex_to_html(problem_row.get('answer'))

    return render_template(
        "study.html",
        topics=topics,
        selected_topic=selected_topic,
        problem=problem_row,
        problem_topics=problem_topics,
        show_answer=False,
        feedback=None,
    )

@app.route("/progress")
@login_required
def progress():
    user_id = session["user_id"]

    # Per-topic stats
    stats = problems_db.execute(
        """
        SELECT
            t.name AS topic,
            SUM(CASE WHEN a.correct = 1 THEN 1 ELSE 0 END) AS correct_count,
            SUM(CASE WHEN a.correct = 0 THEN 1 ELSE 0 END) AS wrong_count,
            COUNT(*) AS total
        FROM problem_attempts a
        JOIN topics t ON a.topic_id = t.id
        WHERE a.user_id = ?
        GROUP BY t.name
        ORDER BY t.name;
        """,
        user_id,
    )

    # Problems user has gotten wrong at least once
    wrong_problems = problems_db.execute(
        """
        SELECT
            p.id,
            p.year,
            p.problem,
            p.answer,
            MAX(a.attempted_at) AS last_attempt
        FROM problem_attempts a
        JOIN problems p ON a.problem_id = p.id
        WHERE a.user_id = ? AND a.correct = 0
        GROUP BY p.id
        ORDER BY last_attempt DESC
        LIMIT 50;
        """,
        user_id,
    )

    # For each wrong problem, fetch all topic names it is linked to so the UI can show them
    for p in wrong_problems:
        pt_rows = problems_db.execute(
            "SELECT t.name FROM topics t JOIN problem_topics pt ON t.id = pt.topic_id WHERE pt.problem_id = ? ORDER BY t.name",
            p["id"],
        )
        p["topics"] = [r["name"] for r in pt_rows]

    return render_template("progress.html", stats=stats, wrong_problems=wrong_problems)

@app.route("/prue_frida")
@login_required
def prue_frida():
   return render_template("prue_frida.html")

@app.route("/submit_score", methods=["POST"])
@login_required
def submit_score():
    data = request.get_json()
    score = data.get("score")
    
    if score is not None:
        # Save score to users.db
        db.execute("INSERT INTO leaderboard (user_id, score) VALUES (?, ?)", 
                   session["user_id"], score)
        return jsonify({"success": True})
    
    return jsonify({"success": False}), 400


@app.route("/monty_hall")
@login_required
def monty_hall():
    """Play the Monty Hall Game"""
    user_id = session["user_id"]

    # Calculate stats for the user
    # 1. Stats for SWITCHING
    switch_attempts = db.execute("SELECT COUNT(*) as n FROM monty_stats WHERE user_id = ? AND switched = 1", user_id)[0]["n"]
    switch_wins = db.execute("SELECT COUNT(*) as n FROM monty_stats WHERE user_id = ? AND switched = 1 AND won = 1", user_id)[0]["n"]
    
    # 2. Stats for STAYING
    stay_attempts = db.execute("SELECT COUNT(*) as n FROM monty_stats WHERE user_id = ? AND switched = 0", user_id)[0]["n"]
    stay_wins = db.execute("SELECT COUNT(*) as n FROM monty_stats WHERE user_id = ? AND switched = 0 AND won = 1", user_id)[0]["n"]

    stats = {
        "switch_attempts": switch_attempts,
        "switch_wins": switch_wins,
        "stay_attempts": stay_attempts,
        "stay_wins": stay_wins
    }

    return render_template("monty_hall.html", stats=stats)

@app.route("/monty_save", methods=["POST"])
@login_required
def monty_save():
    """Save the result of a Monty Hall game"""
    data = request.get_json()
    switched = 1 if data.get("switched") else 0
    won = 1 if data.get("won") else 0
    
    db.execute("INSERT INTO monty_stats (user_id, switched, won) VALUES (?, ?, ?)",
               session["user_id"], switched, won)
    
    return jsonify({"success": True})
