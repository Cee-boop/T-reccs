import os
import discord
from matching import *
from dotenv import load_dotenv
from discord.ext import commands
from isbnlib import isbn_from_words

import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('book_rec_bot')

load_dotenv()
CONN = get_connection()

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)


@bot.event
async def on_ready():
    logger.info(f'Logged in as {bot.user}')
    await bot.change_presence(
        activity=discord.Activity(type=discord.ActivityType.playing, name="!rechelp | 🦖")
    )


@bot.event
async def on_command_error(ctx, error):
    logger.error(f'Error in command {ctx.command}: {error}', exc_info=True)
    await ctx.send("Something went wrong — try again?")


def create_goodreads_url(title: str, author=None) -> str | None:
    query = f"{title} by {author}" if author else title
    isbn = isbn_from_words(query)
    return f"https://www.goodreads.com/book/isbn/{isbn}" if isbn else None


def build_book_embed(title: str, author: str = None, goodreads_url: str = None, cover_id: int = None) -> discord.Embed:
    embed = discord.Embed(
        title=decorate_title(title),
        color=discord.Color.blurple()
    )

    if author is not None:
        embed.set_author(name=f"by️ {author}")

    if cover_id:
        embed.set_thumbnail(url=f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg")

    embed.add_field(
        name="🔗 Book info:",
        value=f"[View book synopsis on Goodreads]({goodreads_url})" if goodreads_url else "Not available",
        inline=True
    )

    return embed


@bot.command(name='rechelp')
async def rechelp(ctx):
    embed = discord.Embed(
        title="📖 How to use !rec",
        description="Get a book's info and a link to its Goodreads page.",
        color=discord.Color.blurple()
    )
    embed.add_field(
        name="Commands:",
        value=(
        "`!rec {title}`\n`!rec {title} by {author}`\n\n"
        "*Adding the author increases accuracy when recc'ing a title shared by multiple books.*"
        ),
        inline=False
    )
    embed.add_field(
        name="Examples:",
        value="`!rec Dune`\n`!rec Dune by Frank Herbert`",
        inline=False
    )
    embed.add_field(
        name="Tips:",
        value=(
            "• When including an author always separate the author's name with `by` -> e.g. `!rec Dune by Frank Herbert`, not `!rec Dune Frank Herbert`.\n"
            "• Double-check the spelling.\n"
            "• Niche book titles may not include an embedded book cover.\n"
        ),
        inline=False
    )

    await ctx.send(embed=embed)


ALL_GENRES = ['Fantasy', 'Science Fiction', 'Horror', 'Western', 'Thriller', 'Mystery',
              'Romance', 'Adventure', 'Humor', 'War', 'Poetry', 'Drama', 'Comic',
              'History', 'Memoir', 'Biography', 'Religion', 'Philosophy',
              'Science', 'Politics', 'Psychology', 'Self-Help', 'Memoir', 'Travel',
              'Art', 'Business', 'Education', 'Health', 'Nature', 'Dystopian']


@bot.command(name='random')
async def get_random_book(ctx, *, genre: str = None):
    logger.info(f'{ctx.author}: !random {genre or ""}')

    if genre is None:
        embed = discord.Embed(
            title="‼️ Genre required",
            description="Please specify a genre like this: `!random fantasy`",
            color=discord.Color.red()
        )
        embed.add_field(name="Available genres:", value=format_genre_list(), inline=False)
        await ctx.send(embed=embed)
        return

    matched_genre = next((g for g in ALL_GENRES if g.lower() == genre.lower()), None)
    if matched_genre is None:
        embed = discord.Embed(
            title="❓ Unknown genre",
            description=f"`{genre}` isn't a genre I recognize.",
            color=discord.Color.red()
        )
        embed.add_field(name="Available genres:", value=format_genre_list(), inline=False)
        await ctx.send(embed=embed)
        return

    genres_to_use = [matched_genre]

    placeholders = ",".join("?" * len(genres_to_use))
    min_editions = 100
    query = f'''
        SELECT works.* FROM works
        JOIN work_genres ON works.id = work_genres.work_id
        JOIN work_edition_counts ON works.id = work_edition_counts.work_id
        WHERE work_genres.genre IN ({placeholders})
        AND work_edition_counts.edition_count >= ?
        ORDER BY RANDOM() LIMIT 1
    '''
    params = genres_to_use + [min_editions]
    book_info = pd.read_sql(query, CONN, params=params).iloc[0]

    first_author_id = book_info['work_author_ids'].split(',')[0]
    book_author = get_author_names([first_author_id], CONN).get(first_author_id, "Unknown author")
    cover_id = get_cover_for_work(book_info['id'], CONN)
    formatted_title = format_title(book_info['title'])
    formatted_author = format_author(book_author)

    goodreads_url = create_goodreads_url(formatted_title, formatted_author)

    embed = build_book_embed(formatted_title, formatted_author, goodreads_url, cover_id)
    await ctx.send(embed=embed)


@bot.command(name='rec')
async def rec(ctx, *, user_input: str):
    logger.info(f'{ctx.author}: !rec {user_input}')

    title, author = parse_title(user_input)
    formatted_title = format_title(title)
    formatted_author = format_author(author) if author is not None else author

    book_info = find_book_in_db(formatted_title, formatted_author, CONN)

    goodreads_url = create_goodreads_url(formatted_title, formatted_author)

    if book_info is None:
        if goodreads_url is None:
            logger.warning(f'No match found for: {user_input!r}')
            await ctx.send("Book not in database — check spelling?")
            return

        embed = build_book_embed(formatted_title, formatted_author, goodreads_url)
        await ctx.send(embed=embed)
        return

    work_id = book_info['work_id']
    cover_id = get_cover_for_work(work_id, CONN)

    embed = build_book_embed(formatted_title, formatted_author, goodreads_url, cover_id)
    await ctx.send(embed=embed)


bot.run(os.getenv('DISCORD_TOKEN'))