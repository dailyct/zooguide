CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    remaining_time INTEGER NOT NULL DEFAULT 60,
    current_location TEXT NOT NULL DEFAULT 'entrance',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_interests (
    user_id TEXT NOT NULL,
    interest TEXT NOT NULL,
    weight REAL NOT NULL,
    PRIMARY KEY (user_id, interest),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS user_visits (
    user_id TEXT NOT NULL,
    animal_id TEXT NOT NULL,
    visited_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, animal_id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    animal_id TEXT,
    action TEXT NOT NULL,
    detail TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_chat_user ON chat_messages(user_id, id);
CREATE INDEX IF NOT EXISTS idx_interactions_user ON interactions(user_id, id);
