import sqlite3
conn = sqlite3.connect('quant.db')
conn.execute('ALTER TABLE users ADD COLUMN name VARCHAR DEFAULT ""')
conn.commit()
conn.close()
print('OK')