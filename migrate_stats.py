import sqlite3
import json

DB_PATH = "data/scrims.db"

def migrate():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Alle Scrims holen, die schon Ergebnisse haben
    cur.execute("""
        SELECT m.id AS scrim_id, m.opponent, m.team_points, m.opponent_points, s.team, s.user_id
        FROM scrim_meta m
        JOIN scrim s ON m.id = s.id
        WHERE m.team_points IS NOT NULL AND m.opponent_points IS NOT NULL
    """)
    rows = cur.fetchall()

    inserted = 0
    for row in rows:
        scrim_id = row["scrim_id"]
        team = row["team"]
        uid = row["user_id"]

        points_for = row["team_points"]
        points_against = row["opponent_points"]

        # Win = 1 wenn Punkte_for > Punkte_against
        win = 1 if points_for > points_against else 0

        cur.execute("""
            INSERT INTO scrim_stats (scrim_id, user_id, team, points_for, points_against, win)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (scrim_id, uid, team, points_for, points_against, win))
        inserted += 1

    conn.commit()
    conn.close()
    print(f"✅ Migration abgeschlossen. {inserted} Stats-Einträge erstellt.")

if __name__ == "__main__":
    migrate()
