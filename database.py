import random
import sqlite3
from contextlib import contextmanager

DB_PATH = 'words.db'

DEFAULT_WORDS = [
    'tova', 'pech', 'temir yol', 'ustoz', 'non pishirgich', 'aytmoq', 'ketmoq',
    'qolmoq', 'bormoq', 'romashka', 'gul', 'choynak', 'piyola', 'kalay', 'noq',
    'ha', 'hop', 'yoq', 'mayli', 'olma', 'nok', 'apelsin', 'malina', 'banan',
    'top', 'issiq', 'sovuq', 'kir', 'toza', 'shirin', 'achiq'
]

DEFAULT_CATEGORIES = [
    'Taom', 'Meva', 'Tabiat', 'So‘zlar', 'Harakat', 'His-tuyg‘u', 'Ustoz', 'Uy', 'Ichimlik'
]


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS words (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            word TEXT,
            added_by INTEGER,
            category TEXT
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE
        )''')
        c.execute("SELECT COUNT(*) FROM categories")
        if c.fetchone()[0] == 0:
            for cat in DEFAULT_CATEGORIES:
                c.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (cat,))


def get_categories():
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT name FROM categories ORDER BY id")
        rows = [r[0] for r in c.fetchall()]
    return rows or DEFAULT_CATEGORIES.copy()


def add_category(name):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (name,))
        return c.rowcount > 0


def add_word(chat_id, word, added_by, category):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            "INSERT INTO words (chat_id, word, added_by, category) VALUES (?, ?, ?, ?)",
            (chat_id, word, added_by, category)
        )
        return c.lastrowid


def list_words(chat_id):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT id, category, word, added_by FROM words WHERE chat_id = ?", (chat_id,))
        return c.fetchall()


def remove_word(chat_id, word_id):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM words WHERE id = ? AND chat_id = ?", (word_id, chat_id))
        return c.rowcount


def _words_pool(chat_id, category=None):
    """Returns (pool, source_label). Prefers custom words for the exact category,
    then any custom words for the chat, then falls back to the default word bank."""
    with get_conn() as conn:
        c = conn.cursor()
        if category:
            c.execute("SELECT word FROM words WHERE chat_id = ? AND category = ?", (chat_id, category))
            rows = [r[0] for r in c.fetchall()]
            if rows:
                return rows, f"Toifadan ({category})"
        c.execute("SELECT word FROM words WHERE chat_id = ?", (chat_id,))
        rows = [r[0] for r in c.fetchall()]
    if rows:
        return rows, "Saqlangan so‘zlardan"
    return DEFAULT_WORDS, "Standart so‘zlardan"


def pick_random_word(chat_id, category, used_words):
    """Picks a random word not yet used this game. If the pool is exhausted,
    it resets (clears used_words) so words start repeating again instead of erroring out."""
    pool, source = _words_pool(chat_id, category)
    available = [w for w in pool if w not in used_words]
    if not available:
        used_words.clear()
        available = pool
    word = random.choice(available)
    used_words.add(word)
    return word, source