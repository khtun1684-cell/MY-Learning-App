import json
import os
import sqlite3
from flask import Flask, render_template, request, redirect

app = Flask(__name__)

BASE_DIR = os.path.dirname(__file__)
DB_FILE = os.path.join(BASE_DIR, "courses.db")
JSON_FILE = os.path.join(BASE_DIR, "courses.json")


def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")  # course削除時にノートも一緒に消す
    return conn


def run_query(sql, params=()):
    """INSERT / UPDATE / DELETE 用"""
    conn = get_db()
    conn.execute(sql, params)
    conn.commit()
    conn.close()


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            notes TEXT NOT NULL DEFAULT '',
            completed INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE
        )
    """)
    conn.commit()

    # courses が空で courses.json があれば、一度だけ取り込む
    count = conn.execute("SELECT COUNT(*) FROM courses").fetchone()[0]
    if count == 0 and os.path.exists(JSON_FILE):
        try:
            with open(JSON_FILE, "r", encoding="utf-8") as file:
                data = json.load(file)
        except json.JSONDecodeError:
            data = []

        for index, item in enumerate(data, start=1):
            if isinstance(item, str):
                conn.execute(
                    "INSERT INTO courses (id, name, notes, completed) VALUES (?, ?, '', 0)",
                    (index, item),
                )
            else:
                conn.execute(
                    "INSERT INTO courses (id, name, notes, completed) VALUES (?, ?, ?, ?)",
                    (
                        item.get("id", index),
                        item.get("name", ""),
                        item.get("notes", ""),
                        1 if item.get("completed") else 0,
                    ),
                )
        conn.commit()

    # 旧形式の「1つだけのノート」を、notes テーブルの最初のノートに移す(一度きり)
    old_rows = conn.execute(
        "SELECT id, notes FROM courses WHERE TRIM(notes) != ''"
    ).fetchall()
    for row in old_rows:
        conn.execute(
            "INSERT INTO notes (course_id, content) VALUES (?, ?)",
            (row["id"], row["notes"]),
        )
        conn.execute("UPDATE courses SET notes = '' WHERE id = ?", (row["id"],))
    conn.commit()

    conn.close()


def load_courses():
    conn = get_db()
    course_rows = conn.execute(
        "SELECT id, name, completed FROM courses ORDER BY id"
    ).fetchall()
    note_rows = conn.execute(
        "SELECT id, course_id, content, created_at FROM notes ORDER BY id"
    ).fetchall()
    conn.close()

    notes_by_course = {}
    for n in note_rows:
        notes_by_course.setdefault(n["course_id"], []).append(
            {"id": n["id"], "content": n["content"], "created_at": n["created_at"]}
        )

    return [
        {
            "id": row["id"],
            "name": row["name"],
            "completed": bool(row["completed"]),
            "notes": notes_by_course.get(row["id"], []),
        }
        for row in course_rows
    ]


def redirect_back():
    current_filter = request.form.get("filter", "all")
    if current_filter not in ("all", "active", "completed"):
        current_filter = "all"
    return redirect(f"/?filter={current_filter}")


@app.route("/")
def home():
    courses = load_courses()
    current_filter = request.args.get("filter", "all")

    total = len(courses)
    done = sum(1 for c in courses if c["completed"])

    if current_filter == "active":
        courses = [c for c in courses if not c["completed"]]
    elif current_filter == "completed":
        courses = [c for c in courses if c["completed"]]
    else:
        current_filter = "all"

    return render_template(
        "index.html",
        courses=courses,
        current_filter=current_filter,
        total=total,
        done=done,
    )


@app.route("/add_course", methods=["POST"])
def add_course():
    name = request.form.get("course_name", "").strip()
    if name:
        run_query("INSERT INTO courses (name) VALUES (?)", (name,))
    return redirect("/")


@app.route("/edit_course/<int:course_id>", methods=["POST"])
def edit_course(course_id):
    new_name = request.form.get("new_name", "").strip()
    if new_name:
        run_query("UPDATE courses SET name = ? WHERE id = ?", (new_name, course_id))
    return redirect_back()


@app.route("/add_note/<int:course_id>", methods=["POST"])
def add_note(course_id):
    content = request.form.get("content", "").strip()
    if content:
        run_query(
            "INSERT INTO notes (course_id, content) "
            "SELECT id, ? FROM courses WHERE id = ?",
            (content, course_id),
        )
    return redirect_back()


@app.route("/delete_note/<int:note_id>", methods=["POST"])
def delete_note(note_id):
    run_query("DELETE FROM notes WHERE id = ?", (note_id,))
    return redirect_back()


@app.route("/toggle_complete/<int:course_id>", methods=["POST"])
def toggle_complete(course_id):
    run_query("UPDATE courses SET completed = 1 - completed WHERE id = ?", (course_id,))
    return redirect_back()


@app.route("/delete_course/<int:course_id>", methods=["POST"])
def delete_course(course_id):
    run_query("DELETE FROM courses WHERE id = ?", (course_id,))
    return redirect_back()


init_db()

if __name__ == "__main__":
    app.run(debug=True)