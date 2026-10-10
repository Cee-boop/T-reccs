import re
import string
import random
import sqlite3
import logging
import pandas as pd
from collections import deque
from typing import Callable


Pool = list[tuple[str, int]]
Pools = dict[str, Pool]
Recent = dict[str, deque[str]]


TITLE_DECORATORS: list[Callable[[str], str]] = [lambda t: f"⟪ {t} ⟫", lambda t: f"『 {t} 』",]
POOL_SIZE = 300
RECENT_SIZE = 30      # per-genre memory of recent picks
WEIGHT_POWER = 0.6    # 0 = uniform, 1 = strongly favors the most-published


def build_genre_pools(conn: sqlite3.Connection, genres: list[str]) -> Pools:
    pools: Pools = {}
    for genre in genres:
        rows = conn.execute('''
            SELECT g.work_id, w.title, e.edition_count
            FROM work_genres g
            JOIN works w ON w.id = g.work_id
            JOIN work_edition_counts e ON e.work_id = g.work_id
            WHERE g.genre = ?
            ORDER BY e.edition_count DESC
            LIMIT ?
        ''', (genre, POOL_SIZE * 2)).fetchall()

        seen: set[str] = set()
        pool: Pool = []
        for work_id, title, count in rows:
            key = title.strip().lower()
            if key in seen:
                continue
            seen.add(key)
            pool.append((work_id, count))
            if len(pool) == POOL_SIZE:
                break
        pools[genre] = pool
        if pool:
            logging.info(f'{genre}: pool {len(pool)}, cutoff {pool[-1][1]} editions')
        else:
            logging.warning(f'{genre}: empty pool')

    return pools


def make_recent(genres: list[str]) -> Recent:
    return {g: deque(maxlen=RECENT_SIZE) for g in genres}


def pick_work_id(genre: str, pools: Pools, recent: Recent) -> str:
    candidates = [p for p in pools[genre] if p[0] not in recent[genre]]
    if not candidates:
        raise ValueError(f'no candidates left for {genre}')
    ids, counts = zip(*candidates)
    work_id = random.choices(ids, weights=[c ** WEIGHT_POWER for c in counts], k=1)[0]
    recent[genre].append(work_id)
    return work_id


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
    return "`Art` • `Adventure` • `Biography` • `Classics` • `Comic` • `Dystopian` • `Fantasy` • `History` • `Horror` • `Humor` • `Mystery` • `Nature` • `Philosophy` • `Poetry` • `Politics` • `Religion` • `Romance` • `Science` • `Science Fiction` • `Self-Help` • `Theatre` • `Thriller` • `War` • `Western`"


def format_author(author: str) -> str:
    return re.sub(r'\s+', ' ', author).title()


def get_isbn_for_work(work_id: str, conn: sqlite3.Connection) -> str | None:
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


def get_connection(db_path: str = './datasets/books.db') -> sqlite3.Connection:
    return sqlite3.connect(db_path, check_same_thread=False)


def get_cover_for_work(work_id: str, conn: sqlite3.Connection) -> int | None:
    result = pd.read_sql(
        "SELECT cover FROM works WHERE id = ?",
        conn, params=(work_id,)
    )
    if result.empty or pd.isna(result.iloc[0]['cover']):
        return None

    return int(result.iloc[0]['cover'])


def get_author_names(author_ids: list[str], conn: sqlite3.Connection) -> dict[str, str]:
    placeholders = ",".join("?" * len(author_ids))
    query = f"SELECT id, author_name FROM authors WHERE id IN ({placeholders})"
    result = pd.read_sql(query, conn, params=author_ids)
    return dict(zip(result['id'], result['author_name']))