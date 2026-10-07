import re
import string
import random
import sqlite3
import pandas as pd


TITLE_DECORATORS = [
    lambda t: f"⟪ {t} ⟫",
    lambda t: f"『 {t} 』",
]


def setup_synopsis_cache(conn):
    conn.execute('''
        CREATE TABLE IF NOT EXISTS synopsis_cache (
            cache_key TEXT PRIMARY KEY,
            synopsis TEXT,
            url TEXT,
            source TEXT
        )
    ''')
    conn.commit()


def decorate_title(title: str) -> str:
    decorator = random.choice(TITLE_DECORATORS)
    return decorator(title)


def format_title(title: str) -> str:
    link_title = string.capwords(title).split()

    minor_words = {'and', 'of', 'the', 'in', 'on', 'a', 'an', 'by'}
    for i, word in enumerate(link_title):
        if word in minor_words:
            link_title[i] = word.lower()

    return " ".join(link_title)


def format_genre_list() -> str:
    return "`Art` • `Adventure` • `Biography` • `Business` • `Comic` • `Drama` • `Dystopian` • `Education` • `Fantasy` • `Health` • `History` • `Horror` • `Humor` • `Memoir` • `Mystery` • `Nature` • `Philosophy` • `Poetry` • `Politics` • `Psychology` • `Religion` • `Romance` • `Science` • `Science Fiction` • `Self-Help` • `Thriller` • `Travel` • `War` • `Western`"


def format_author(author: str) -> str:
    return re.sub(r'\s+', ' ', author).title()


def get_isbn_for_work(work_id: str, conn):
    result = pd.read_sql(
        "SELECT isbn FROM editions WHERE edition_work_ids = ? AND isbn IS NOT NULL",
        conn, params=(work_id,)
    )
    if result.empty:
        return None

    isbn_10s = result[result['isbn'].str.len() == 10]
    if not isbn_10s.empty:
        return isbn_10s.iloc[0]['isbn']
    return result.iloc[0]['isbn']


def get_connection(db_path: str='./datasets/books.db'):
    return sqlite3.connect(db_path, check_same_thread=False)


def get_cover_for_work(work_id: str, conn):
    result = pd.read_sql(
        "SELECT cover FROM works WHERE id = ?",
        conn, params=(work_id,)
    )
    if result.empty or pd.isna(result.iloc[0]['cover']):
        return None
    return int(result.iloc[0]['cover'])


def get_author_names(author_ids: list, conn) -> dict:
    placeholders = ",".join("?" * len(author_ids))
    query = f"SELECT id, author_name FROM authors WHERE id IN ({placeholders})"
    result = pd.read_sql(query, conn, params=author_ids)
    return dict(zip(result['id'], result['author_name']))