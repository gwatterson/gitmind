import sqlite3
import json

conn = sqlite3.connect("reviews.db")
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("SELECT * FROM reviews ORDER BY created_at DESC LIMIT 1")
row = cur.fetchone()
if not row:
    print("No reviews found.")
else:
    r = dict(row)
    print(f"Review ID: {r['id']}")
    print(f"Status: {r['status']}")
    print(f"Verdict: {r['verdict']}")
    
    cur.execute("SELECT * FROM review_events WHERE review_id = ? ORDER BY id ASC", (r["id"],))
    events = cur.fetchall()
    for e in events:
        print(f"[{e['event_type']}] {e['message']}")
        if e['data']:
            try:
                data = json.loads(e['data'])
                if "security_files" in data:
                    print(f"  Assigned Security: {data['security_files']}")
                if "quality_files" in data:
                    print(f"  Assigned Quality: {data['quality_files']}")
                if "performance_files" in data:
                    print(f"  Assigned Performance: {data['performance_files']}")
            except:
                pass
