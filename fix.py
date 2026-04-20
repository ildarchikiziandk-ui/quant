import sqlite3
conn = sqlite3.connect('quant.db')
try:
    conn.execute('ALTER TABLE users ADD COLUMN is_owner BOOLEAN DEFAULT 0')
    print('is_owner добавлена')
except: print('уже есть')
try:
    conn.execute('ALTER TABLE users ADD COLUMN is_starred BOOLEAN DEFAULT 0')
    print('is_starred добавлена')
except: print('уже есть')
try:
    conn.execute('ALTER TABLE users ADD COLUMN is_verified_badge BOOLEAN DEFAULT 0')
    print('is_verified_badge добавлена')
except: print('уже есть')
try:
    conn.execute('''CREATE TABLE IF NOT EXISTS whales (
        id INTEGER PRIMARY KEY,
        user_id INTEGER REFERENCES users(id),
        post_id INTEGER REFERENCES posts(id)
    )''')
    print('whales создана')
except: print('уже есть')
conn.execute("UPDATE users SET is_owner = 1 WHERE username = 'rubl'")
conn.commit()
conn.close()
print('OK')