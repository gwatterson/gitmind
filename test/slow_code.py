"""
Test file with intentional PERFORMANCE issues.
Used for testing GitMind's performance analysis agent.

Issues:
  - N+1 query pattern (DB queries inside a loop)
  - String concatenation in a loop (instead of list join)
  - Unnecessary repeated computation
"""

import time


def get_user_orders(db, user_ids):
    """Fetch orders for users — N+1 QUERY anti-pattern."""
    orders = []
    for uid in user_ids:
        user = db.query(f"SELECT * FROM users WHERE id = {uid}")
        user_orders = db.query(f"SELECT * FROM orders WHERE user_id = {uid}")
        orders.append({"user": user, "orders": user_orders})
    return orders


def build_report(items):
    """Build report — STRING CONCATENATION IN LOOP anti-pattern."""
    report = ""
    for item in items:
        report += f"Item: {item['name']}, Price: {item['price']}\n"
    return report


def find_duplicates(items):
    """Find duplicates — UNNECESSARY REPEATED COMPUTATION."""
    duplicates = []
    for i in range(len(items)):
        for j in range(len(items)):
            if i != j and items[i] == items[j]:
                if items[i] not in duplicates:
                    duplicates.append(items[i])
    return duplicates


def process_batch(records):
    """Process records — SYNCHRONOUS I/O IN LOOP."""
    results = []
    for record in records:
        time.sleep(0.1)  # Simulates blocking I/O
        results.append({"id": record["id"], "processed": True})
    return results
