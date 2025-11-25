import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd, process_holdings

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")
problems_db = SQL("sqlite:///problems.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/break")
@login_required
def study_break():
    return render_template("break.html")

@app.route("/")
@login_required
def index():
    return(apology("TODO"))

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
            db.execute("INSERT INTO users (username, hash) VALUES(?,?)",
                       username, generate_password_hash(password))
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
        return render_template("account_settings.html")

@app.route("/study", methods=["GET", "POST"])
@login_required
def study():
    user_id = session["user_id"]

    # For the topic dropdown
    topics = problems_db.execute(
        "SELECT DISTINCT topic FROM problems ORDER BY topic"
    )

    if request.method == "POST":
        action = request.form.get("action")          # "reveal", "right", "wrong"
        problem_id = request.form.get("problem_id")
        selected_topic = request.form.get("topic") or "Any"

        if not problem_id:
            return redirect("/study")

        rows = problems_db.execute(
            "SELECT id, problem, answer, topic FROM problems WHERE id = ?",
            problem_id,
        )
        if len(rows) != 1:
            return redirect("/study")

        problem_row = rows[0]

        if action == "reveal":
            # Show the same problem, now with the answer visible
            return render_template(
                "study.html",
                topics=topics,
                selected_topic=selected_topic,
                problem=problem_row,
                show_answer=True,
                feedback=None,
            )

        elif action in ("right", "wrong"):
            correct = 1 if action == "right" else 0

            problems_db.execute(
                "INSERT INTO problem_attempts (user_id, problem_id, topic, correct) "
                "VALUES (?, ?, ?, ?)",
                user_id,
                problem_row["id"],
                problem_row["topic"],
                correct,
            )

            # After logging, get a new random problem (same topic filter)
            if selected_topic == "Any":
                probs = problems_db.execute(
                    "SELECT id, problem, answer, topic FROM problems ORDER BY RANDOM() LIMIT 1"
                )
            else:
                probs = problems_db.execute(
                    "SELECT id, problem, answer, topic FROM problems "
                    "WHERE topic = ? ORDER BY RANDOM() LIMIT 1",
                    selected_topic,
                )

            new_problem = probs[0] if probs else None

            return render_template(
                "study.html",
                topics=topics,
                selected_topic=selected_topic,
                problem=new_problem,
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
            "SELECT id, problem, answer, topic FROM problems WHERE id = ?",
            problem_id,
        )
        if rows:
            problem_row = rows[0]
            # Ensure dropdown matches this problem’s topic
            selected_topic = problem_row["topic"]
    else:
        if selected_topic == "Any":
            probs = problems_db.execute(
                "SELECT id, problem, answer, topic FROM problems ORDER BY RANDOM() LIMIT 1"
            )
        else:
            probs = problems_db.execute(
                "SELECT id, problem, answer, topic FROM problems "
                "WHERE topic = ? ORDER BY RANDOM() LIMIT 1",
                selected_topic,
            )
        problem_row = probs[0] if probs else None

    return render_template(
        "study.html",
        topics=topics,
        selected_topic=selected_topic,
        problem=problem_row,
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
            topic,
            SUM(CASE WHEN correct = 1 THEN 1 ELSE 0 END) AS correct_count,
            SUM(CASE WHEN correct = 0 THEN 1 ELSE 0 END) AS wrong_count,
            COUNT(*) AS total
        FROM problem_attempts
        WHERE user_id = ?
        GROUP BY topic
        ORDER BY topic;
        """,
        user_id,
    )

    # Problems user has gotten wrong at least once
    wrong_problems = problems_db.execute(
        """
        SELECT
            p.id,
            p.problem,
            p.answer,
            p.topic,
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

    return render_template("progress.html", stats=stats, wrong_problems=wrong_problems)


