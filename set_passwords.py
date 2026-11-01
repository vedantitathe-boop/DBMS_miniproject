from werkzeug.security import generate_password_hash
from db import get_db

conn = get_db()
cur = conn.cursor()
cur.execute('UPDATE Users SET password_hash = %s',
            (generate_password_hash('Test@123'),))
conn.commit()
print(cur.rowcount, 'users updated')
conn.close()