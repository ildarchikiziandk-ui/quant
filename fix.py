import sqlite3
conn = sqlite3.connect('quant.db')
try:
    conn.execute('ALTER TABLE users ADD COLUMN is_moderator BOOLEAN DEFAULT 0')
    print('is_moderator добавлена')
except: print('уже есть')
conn.commit()
conn.close()
print('OK')