import sqlite3
import os
import json

DB_PATH = "./data/scrims.db"


def get_db():
    os.makedirs("./data", exist_ok=True)
    return sqlite3.connect(DB_PATH)


def init_db():
    with get_db() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS signups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team TEXT,
                hour INTEGER,
                role TEXT,
                user_ids TEXT
            )
        """)
        c.execute(""" 
            CREATE TABLE IF NOT EXISTS teams (
                name TEXT PRIMARY KEY
            )
        """)
        c.commit()


def can(team, hour, user_id, role):
    with get_db() as db:
        c = db.cursor()

        # Ensure both roles exist
        for r in ["main", "sub"]:
            c.execute(
                "SELECT id FROM signups WHERE team = ? AND hour = ? AND role = ?",
                (team, hour, r),
            )
            if not c.fetchone():
                c.execute(
                    "INSERT INTO signups (team, hour, role, user_ids) VALUES (?, ?, ?, ?)",
                    (team, hour, r, json.dumps([])),
                )

        # Remove user from the other role if present
        opposite_role = "sub" if role == "main" else "main"
        c.execute(
            "SELECT id, user_ids FROM signups WHERE team = ? AND hour = ? AND role = ?",
            (team, hour, opposite_role),
        )
        row = c.fetchone()
        if row:
            opp_signup_id, opp_user_ids_json = row
            opp_user_ids = json.loads(opp_user_ids_json)
            if user_id in opp_user_ids:
                opp_user_ids.remove(user_id)
                if opp_user_ids:
                    c.execute(
                        "UPDATE signups SET user_ids = ? WHERE id = ?",
                        (json.dumps(opp_user_ids), opp_signup_id),
                    )
                else:
                    c.execute("DELETE FROM signups WHERE id = ?", (opp_signup_id,))

        # Add user to the selected role if not already present
        c.execute(
            "SELECT id, user_ids FROM signups WHERE team = ? AND hour = ? AND role = ?",
            (team, hour, role),
        )
        row = c.fetchone()
        if row:
            signup_id, user_ids_json = row
            user_ids = json.loads(user_ids_json)

            if user_id not in user_ids:
                user_ids.append(user_id)
                c.execute(
                    "UPDATE signups SET user_ids = ? WHERE id = ?",
                    (json.dumps(user_ids), signup_id),
                )

        # Cleanup: remove any empty signups at this hour
        c.execute("SELECT id, user_ids FROM signups WHERE hour = ?", (hour,))
        for s_id, s_user_json in c.fetchall():
            s_users = json.loads(s_user_json)
            if not s_users:
                c.execute("DELETE FROM signups WHERE id = ?", (s_id,))

        db.commit()


def drop(team, hour, user_id):
    with get_db() as db:
        c = db.cursor()

        roles = ["main", "sub"]
        updated = False

        for role in roles:
            c.execute(
                "SELECT id, user_ids FROM signups WHERE team = ? AND hour = ? AND role = ?",
                (team, hour, role),
            )
            row = c.fetchone()

            if row:
                signup_id, user_ids_json = row
                user_ids = json.loads(user_ids_json)

                if user_id in user_ids:
                    user_ids.remove(user_id)
                    updated = True
                    if user_ids:
                        c.execute(
                            "UPDATE signups SET user_ids = ? WHERE id = ?",
                            (json.dumps(user_ids), signup_id),
                        )
                    else:
                        c.execute("DELETE FROM signups WHERE id = ?", (signup_id,))

        if not updated:
            raise ValueError("You are not signed up for this scrim.")

        db.commit()


def get_list():
    with get_db() as db:
        c = db.cursor()
        c.execute("SELECT * FROM signups")
        rows = c.fetchall()

        if not rows:
            return []

        return [
            {
                "team": row[1],
                "hour": row[2],
                "role": row[3],
                "user_ids": json.loads(row[4]),
            }
            for row in rows
        ]


def dropall(user_id):
    with get_db() as db:
        c = db.cursor()

        c.execute("SELECT id, team, hour, role, user_ids FROM signups")
        rows = c.fetchall()

        affected = set()

        for signup_id, team, hour, role, user_ids_json in rows:
            user_ids = json.loads(user_ids_json)

            if user_id in user_ids:
                user_ids.remove(user_id)
                affected.add((team, hour))

                if len(user_ids) == 0:
                    c.execute("DELETE FROM signups WHERE id = ?", (signup_id,))
                else:
                    c.execute(
                        "UPDATE signups SET user_ids = ? WHERE id = ?",
                        (json.dumps(user_ids), signup_id),
                    )

        for team, hour in affected:
            c.execute(
                "SELECT role, user_ids FROM signups WHERE team = ? AND hour = ?",
                (team, hour),
            )
            role_rows = c.fetchall()

            completely_empty = True
            for role, user_ids_json in role_rows:
                user_ids = json.loads(user_ids_json)
                if user_ids:
                    completely_empty = False
                    break

            if completely_empty:
                c.execute(
                    "DELETE FROM signups WHERE team = ? AND hour = ?",
                    (team, hour),
                )

        db.commit()


def reset():
    with get_db() as db:
        db.execute("DELETE FROM signups")
        db.commit()
