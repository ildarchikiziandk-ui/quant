import sqlite3
conn = sqlite3.connect('quant.db')
try:
    conn.execute('DROP TABLE IF EXISTS notifications')
    conn.execute('''CREATE TABLE notifications (
        id INTEGER PRIMARY KEY,
        user_id INTEGER REFERENCES users(id),
        from_user_id INTEGER REFERENCES users(id),
        type VARCHAR,
        post_id INTEGER REFERENCES posts(id),
        is_read BOOLEAN DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    print('notifications пересоздана')
except Exception as e:
    print(f'Ошибка: {e}')
conn.commit()
conn.close()
print('OK')