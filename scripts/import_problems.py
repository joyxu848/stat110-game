
"""
Rebuild `problems.db` schema and import problems from CSV.

Behavior:
- Drops and recreates `topics` and `problems` tables.
- Prompts whether to delete existing `problem_attempts` data or migrate it into the new schema.
- Imports problems from `static/cs50_problems.csv` into the new `problems` table and creates topics.

NOTE: Back up `problems.db` before running.
"""

import csv
import os
import sqlite3
import sys

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DB_PATH = os.path.join(BASE, 'problems.db')
CSV_PATH = os.path.join(BASE, 'static', 'cs50_problems.csv')

if not os.path.exists(DB_PATH):
    print(f"Database not found at {DB_PATH}")
    sys.exit(1)

print(f"Using DB: {DB_PATH}")
print(f"CSV: {CSV_PATH}")

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# Helper to read CSV headers/preview for debugging
def preview_csv(path, n=3):
    if not os.path.exists(path):
        print('CSV file not found; skipping preview.')
        return
    with open(path, newline='') as f:
        reader = csv.reader(f)
        rows = [r for i, r in enumerate(reader) if i < n+1]
        if rows:
            print('\nCSV preview:')
            for r in rows:
                print('  ', r)


try:
    # Make a safe snapshot of existing problems & attempts
    cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = {r[0] for r in cur.fetchall()}

    orig_problems = {}
    if 'problems' in tables:
        # Determine whether the old `problems` table had a `topic` column.
        cur.execute("PRAGMA table_info(problems);")
        cols = [r[1] for r in cur.fetchall()]
        if 'topic' in cols:
            cur.execute('SELECT id, problem, answer, topic FROM problems;')
            for id_, problem, answer, topic in cur.fetchall():
                orig_problems[id_] = {'problem': problem, 'answer': answer, 'topic': topic}
        else:
            # older schema: no `topic` column
            cur.execute('SELECT id, problem, answer FROM problems;')
            for id_, problem, answer in cur.fetchall():
                orig_problems[id_] = {'problem': problem, 'answer': answer, 'topic': None}
    else:
        print('No existing `problems` table found.')

    orig_attempts = []
    if 'problem_attempts' in tables:
            # Inspect existing problem_attempts schema and load rows robustly.
            cur.execute("PRAGMA table_info(problem_attempts);")
            pa_cols = [r[1] for r in cur.fetchall()]
            if pa_cols:
                cur.execute('SELECT * FROM problem_attempts;')
                rows = cur.fetchall()
                for row in rows:
                    rowdict = dict(zip(pa_cols, row))
                    aid = rowdict.get('id')
                    user_id = rowdict.get('user_id')
                    problem_id = rowdict.get('problem_id')
                    # older schemas might store a topic name in `topic` or a topic id in `topic_id`
                    old_topic = rowdict.get('topic') if 'topic' in pa_cols else rowdict.get('topic_id') if 'topic_id' in pa_cols else None
                    correct = rowdict.get('correct')
                    attempted_at = rowdict.get('attempted_at')
                    orig_attempts.append((aid, user_id, problem_id, old_topic, correct, attempted_at))
            print(f'Found {len(orig_attempts)} existing attempts (will handle based on your choice).')
    else:
        print('No existing `problem_attempts` table found.')

    # Preview CSV to help user if nothing is importing
    preview_csv(CSV_PATH)

    # Ask user whether to delete problem_attempts data or migrate it
    choice = None
    while choice not in ('y', 'n'):
        choice = input('\nDelete all existing `problem_attempts` data and start fresh? (y/n): ').strip().lower()

    delete_attempts = (choice == 'y')

    print('\nProceeding: will drop & recreate `topics` and `problems` tables.')
    if delete_attempts:
        print('You chose to remove existing problem_attempts data (will create an empty table).')
    else:
        print('You chose to migrate existing problem_attempts records where possible.')

    # Turn off FK checks while rebuilding
    cur.execute('PRAGMA foreign_keys=OFF;')

    # Drop tables if they exist
    cur.execute('DROP TABLE IF EXISTS problem_attempts;')
    cur.execute('DROP TABLE IF EXISTS problems;')
    cur.execute('DROP TABLE IF EXISTS topics;')
    cur.execute('DROP TABLE IF EXISTS problem_topics;')

    # Recreate topics and problems (many-to-many via problem_topics)
    cur.execute('''
    CREATE TABLE topics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL
    );
    ''')

    # problems will store Year, Problem (title), Text (full prompt), and optional answer
    cur.execute('''
    CREATE TABLE problems (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        year TEXT,
        problem TEXT NOT NULL,
        text TEXT NOT NULL,
        answer TEXT
    );
    ''')

    # junction table for many-to-many relationship between problems and topics
    cur.execute('''
    CREATE TABLE problem_topics (
        problem_id INTEGER NOT NULL,
        topic_id INTEGER NOT NULL,
        PRIMARY KEY (problem_id, topic_id),
        FOREIGN KEY(problem_id) REFERENCES problems(id) ON DELETE CASCADE,
        FOREIGN KEY(topic_id) REFERENCES topics(id) ON DELETE CASCADE
    );
    ''')

    # Import CSV rows into new tables
    imported = 0
    if os.path.exists(CSV_PATH):
        with open(CSV_PATH, newline='') as f:
            reader = csv.reader(f)
            try:
                headers = next(reader)
            except StopIteration:
                headers = []

            # Normalize header names
            headers_norm = [h.strip() for h in headers]

            # Find core columns: Year, Problem, Text (case-insensitive)
            col_map = {name.lower(): i for i, name in enumerate(headers_norm)}
            year_idx = col_map.get('year')
            problem_idx = col_map.get('problem')
            text_idx = col_map.get('text')

            if problem_idx is None or text_idx is None:
                print('CSV must include at least "Problem" and "Text" columns. Found headers:', headers_norm)
            else:
                # Topic flag columns are any columns after the 'Text' column in the CSV
                topic_columns = []
                if text_idx is not None:
                    for i in range(text_idx + 1, len(headers_norm)):
                        topic_name = headers_norm[i]
                        if topic_name:
                            topic_columns.append((i, topic_name))

                # Insert topics for all topic columns so we have ids
                for _, tname in topic_columns:
                    cur.execute('INSERT OR IGNORE INTO topics (name) VALUES (?)', (tname,))

                # Build mapping of topic header index -> topic_id
                topic_index_to_id = {}
                for idx, tname in topic_columns:
                    cur.execute('SELECT id FROM topics WHERE name = ?', (tname,))
                    row = cur.fetchone()
                    if row:
                        topic_index_to_id[idx] = row[0]

                # Process rows
                for row in reader:
                    # protect against short rows
                    if len(row) <= max(problem_idx, text_idx):
                        continue
                    year_val = row[year_idx].strip() if year_idx is not None and year_idx < len(row) else None
                    problem_val = row[problem_idx].strip()
                    text_val = row[text_idx].strip()
                    # answer may not exist in this CSV; leave NULL
                    if not problem_val or not text_val:
                        continue
                    cur.execute('INSERT INTO problems (year, problem, text, answer) VALUES (?,?,?,?)', (year_val, problem_val, text_val, None))
                    pid = cur.lastrowid
                    # For each topic flag column, if flagged (1/true), create relation
                    for idx, tid in topic_index_to_id.items():
                        if idx < len(row):
                            val = row[idx].strip().lower()
                            if val in ('1', 'true', 'yes', 'y'):
                                cur.execute('INSERT OR IGNORE INTO problem_topics (problem_id, topic_id) VALUES (?,?)', (pid, tid))
                    imported += 1
        print(f'Imported {imported} problems from CSV.')
    else:
        print('CSV file not found; no problems imported.')

    # Recreate problem_attempts table (empty or migrated)
    cur.execute('''
    CREATE TABLE problem_attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        problem_id INTEGER NOT NULL,
        topic_id INTEGER NOT NULL,
        correct INTEGER NOT NULL,
        attempted_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(problem_id) REFERENCES problems(id),
        FOREIGN KEY(topic_id) REFERENCES topics(id)
    );
    ''')

    # If migrating attempts, insert preserved rows mapping to new problem ids by problem text where possible
    migrated = 0
    skipped = 0
    if not delete_attempts and orig_attempts:
        for aid, user_id, old_problem_id, old_topic_text, correct, attempted_at in orig_attempts:
            # Try to get problem text from orig_problems mapping
            problem_text = None
            if old_problem_id in orig_problems:
                problem_text = orig_problems[old_problem_id]['problem']
            # If problem_text available, find new problem id by text
            new_pid = None
            if problem_text:
                cur.execute('SELECT id FROM problems WHERE problem = ? LIMIT 1', (problem_text,))
                r = cur.fetchone()
                if r:
                    new_pid = r[0]
                    # find a topic_id for this problem from the problem_topics junction table
                    cur.execute('SELECT topic_id FROM problem_topics WHERE problem_id = ? LIMIT 1', (new_pid,))
                    trow = cur.fetchone()
                    new_tid = trow[0] if trow else None
                else:
                    new_pid = None
            # If we couldn't map by problem text, try to map by topic text (best-effort) -> insert with problem_id=0 skipped
            if new_pid is None:
                skipped += 1
                continue
            # Determine topic_id: prefer problem's topic_id; fall back to attempting to map from old topic text/id
            topic_id = new_tid
            if topic_id is None:
                # Try to use old_topic_text if present (could be a topic name or id)
                if old_topic_text:
                    try:
                        # if it's numeric, treat as id
                        maybe_id = int(old_topic_text)
                        cur.execute('SELECT id FROM topics WHERE id = ? LIMIT 1', (maybe_id,))
                        if cur.fetchone():
                            topic_id = maybe_id
                    except Exception:
                        # treat as topic name
                        cur.execute('SELECT id FROM topics WHERE name = ? LIMIT 1', (old_topic_text,))
                        r = cur.fetchone()
                        if r:
                            topic_id = r[0]
                # final fallback: ensure 'Any' topic exists and use it
                if topic_id is None:
                    cur.execute('INSERT OR IGNORE INTO topics (name) VALUES (?)', ('Any',))
                    cur.execute('SELECT id FROM topics WHERE name = ? LIMIT 1', ('Any',))
                    topic_id = cur.fetchone()[0]
            # Insert preserving id if possible
            cur.execute('INSERT INTO problem_attempts (user_id, problem_id, topic_id, correct, attempted_at) VALUES (?,?,?,?,?)',
                        (user_id, new_pid, topic_id, correct, attempted_at))
            migrated += 1

    print(f'Migrated {migrated} attempts; skipped {skipped} attempts that could not be mapped.')

    # Update sqlite_sequence
    for tbl in ('topics', 'problems', 'problem_attempts'):
        cur.execute(f'SELECT MAX(id) FROM {tbl}')
        m = cur.fetchone()[0] or 0
        cur.execute('INSERT OR REPLACE INTO sqlite_sequence(name, seq) VALUES (?, ?)', (tbl, m))

    conn.commit()
    cur.execute('PRAGMA foreign_keys=ON;')
    conn.commit()
    print('\nRebuild + import complete.')

except Exception as e:
    conn.rollback()
    print('Error during rebuild/import:', e)
    raise

finally:
    conn.close()

