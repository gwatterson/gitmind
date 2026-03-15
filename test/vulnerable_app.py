import sqlite3

def login(username, password):
    conn = sqlite3.connect("users.db")
    query = f"SELECT * FROM users WHERE username='{username}' AND password='{password}'"
    result = conn.execute(query)
    return result.fetchone()


API_KEY = "sk-1234567890abcdef" 


def render_page(user_input):
    return f"<html><body>Welcome {user_input}</body></html>"


def get_user_data(user_id):
    conn = sqlite3.connect("users.db")
    query = "SELECT * FROM users WHERE id=" + str(user_id)
    return conn.execute(query).fetchone()
