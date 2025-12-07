#!/usr/bin/env python3
"""
Comment out any lines containing \includegraphics inside the `text` column
of the `problems` table in `problems.db`.

This script will:
 - create a timestamped backup of `problems.db` as `problems.db.bak-YYYYMMDD-HHMMSS`
 - for each row in `problems`, prefix any line containing "\\includegraphics" with "%"
   unless that line is already commented.
 - write updated `text` values back to the DB and report a summary.

Run from the repo root:
    python3 scripts/comment_graphics_in_db.py

Make sure to stop your Flask server while running this (to avoid concurrent writes).
"""

import os
import re
import shutil
import sqlite3
import sys
from datetime import datetime

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DB_PATH = os.path.join(BASE, 'problems.db')

if not os.path.exists(DB_PATH):
    print(f"Database not found at {DB_PATH}")
    sys.exit(1)

# Backup
bak_name = f"problems.db.bak-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
bak_path = os.path.join(BASE, bak_name)
shutil.copy2(DB_PATH, bak_path)
print(f"Backup created: {bak_path}")

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# Match a variety of graphics / file-inclusion commands
cmd_patterns = [
    r"\\includegraphics",   # \includegraphics
    r"\\includegraphics\*",# \includegraphics*
    r"\\includepdf",       # \includepdf
    r"\\input\s*\{",      # \input{...
    r"\\include\s*\{",    # \include{...
    r"\\pgfimage",         # \pgfimage
    r"\\graphicspath",      # \graphicspath
    r"\\DeclareGraphicsExtensions", # \DeclareGraphicsExtensions
    r"\\begin\s*\{figure\}", # \begin{figure}
    r"\\end\s*\{figure\}", # \begin{figure}
    r"\\centering",           # \centering inside figure
    r"\\caption\s*\{"       # \caption{...}
]

# Also match common image/pdf file extensions when they appear in a line
# (no leading backslash; we want to catch
# things like "{figures/chain15.pdf}" or simply ".pdf" inside a line)
ext_pattern = r"\.(?:pdf|png|jpe?g|eps|svg)\b"

# Combine command patterns and extension pattern
pattern = re.compile("(?:" + "|".join(cmd_patterns + [ext_pattern]) + ")", re.IGNORECASE)
changed = []
try:
    cur.execute('SELECT id, text FROM problems')
    rows = cur.fetchall()
    print(f"Scanned {len(rows)} problem rows.")

    for pid, text in rows:
        if not text:
            continue
        # Split into lines, preserve endings
        lines = text.splitlines(True)
        modified = False
        for i, line in enumerate(lines):
            if pattern.search(line):
                # If line is already commented (leading whitespace then %), skip
                if re.match(r"^\s*%", line):
                    continue
                # Otherwise prefix with % but preserve leading indentation
                lines[i] = re.sub(r'^(\s*)', r'\1%', line)
                modified = True
        if modified:
            new_text = ''.join(lines)
            cur.execute('UPDATE problems SET text = ? WHERE id = ?', (new_text, pid))
            changed.append(pid)

    conn.commit()
    print(f"Updated {len(changed)} problems: {changed}")
    print("Done.")

except Exception as e:
    conn.rollback()
    print('Error:', e)
    raise
finally:
    conn.close()
