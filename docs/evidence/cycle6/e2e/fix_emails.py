import sqlite3

c = sqlite3.connect(r"C:\Users\dario\.venvs\e2e\run\darioos.db")
c.execute("update users set email='admin@example.com' where email='admin@e2e.local'")
c.execute("update users set email='user@example.com' where email='user@e2e.local'")
c.commit()
print(c.execute("select email, role from users").fetchall())
