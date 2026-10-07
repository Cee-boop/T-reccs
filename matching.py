from db_helpers import *
from collections import Counter


def find_book_in_db(title: str, author: str = None, conn=None):
    exact_query = '''
        SELECT editions.id AS edition_id, editions.title, works.id AS work_id, works.work_author_ids
        FROM editions
        JOIN works ON editions.edition_work_ids = works.id
        WHERE LOWER(editions.title) = LOWER(?)
    '''
    results = pd.read_sql(exact_query, conn, params=[title])

    if results.empty:
        substring_query = '''
            SELECT editions.id AS edition_id, editions.title, works.id AS work_id, works.work_author_ids
            FROM editions
            JOIN works ON editions.edition_work_ids = works.id
            WHERE LOWER(editions.title) LIKE LOWER(?)
        '''
        results = pd.read_sql(substring_query, conn, params=[f'%{title}%'])

    if results.empty:
        return None

    if author:
        matches = []
        for _, row in results.iterrows():
            author_ids = row['work_author_ids'].split(',')
            names = get_author_names(author_ids, conn)
            if any(author.lower() in name.lower() for name in names.values()):
                matches.append(row)
        if matches:
            return matches[0]
        return None

    # no author specified, pick the work_id with the most editions (most "canonical")
    work_counts = Counter(results['work_id'])
    most_common_work_id = work_counts.most_common(1)[0][0]
    return results[results['work_id'] == most_common_work_id].iloc[0]


def parse_title(user_input: str):
    if ' by ' in user_input.lower():
        idx = user_input.lower().rfind(' by ')
        title = re.sub(r'\s+', ' ', user_input[:idx].strip())
        author = user_input[idx + 4:].strip()
        return title, author

    return user_input.strip(), None