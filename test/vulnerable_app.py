"""
Test file with intentional SECURITY vulnerabilities.
Used for testing GitMind's security analysis agent.

Vulnerabilities:
  - SQL Injection (user input concatenated into SQL query)
  - Hardcoded API secret
  - Cross-Site Scripting (XSS) via unsanitized user input in HTML
"""

import sqlite3

def login(username, password):
    """Authenticate user — VULNERABLE to SQL injection."""
    conn = sqlite3.connect("users.db")
    query = f"SELECT * FROM users WHERE username='{username}' AND password='{password}'"
    result = conn.execute(query)
    return result.fetchone()


API_KEY = "sk-1234567890abcdef" 


def render_page(user_input):
    """Render a page — VULNERABLE to XSS."""
    return f"<html><body>Welcome {user_input}</body></html>"


def get_user_data(user_id):
    """Fetch user data — VULNERABLE to SQL injection."""
    conn = sqlite3.connect("users.db")
    query = "SELECT * FROM users WHERE id=" + str(user_id)
    return conn.execute(query).fetchone()
