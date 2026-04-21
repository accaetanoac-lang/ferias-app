from database import get_conn, init_db

init_db()

conn = get_conn()
c = conn.cursor()

c.execute("SELECT * FROM colaboradores")
print(c.fetchall())

conn.close()
