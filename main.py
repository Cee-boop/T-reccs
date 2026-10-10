import os
import discord
from matching import *
from db_helpers import *
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


ALL_GENRES = [
    'Fantasy', 'Classics', 'Science Fiction', 'Horror', 'Western', 'Thriller', 'Mystery',
    'Romance', 'Adventure', 'Humor', 'War', 'Poetry', 'Theatre', 'Comic',
    'History', 'Biography', 'Religion', 'Philosophy',
    'Science', 'Politics', 'Self-Help', 'Art', 'Nature', 'Dystopian'
]

CONN = get_connection()
GENRE_POOLS = build_genre_pools(CONN, ALL_GENRES)
RECENT = make_recent(ALL_GENRES)

load_dotenv()

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
    error = getattr(error, 'original', error)   # unwrap CommandInvokeError

    if isinstance(error, commands.CommandNotFound):
        return   # ignore unknown commands, e.g. other bots' prefixes

    logger.error(f'Error in command {ctx.command}: {error!r}', exc_info=(type(error), error, error.__traceback__))

    if isinstance(error, discord.Forbidden):
        msg = ("I'm missing a permission in this channel (probably **Embed Links**). "
               "Ask a server admin to enable it for my role.")
    elif isinstance(error, commands.CommandOnCooldown):
        msg = f"Slow down. Try again in {error.retry_after:.0f}s."
    else:
        msg = "Invalid input — try again?"

    try:
        await ctx.send(msg)
    except discord.Forbidden:
        try:
            await ctx.author.send(f"I can't reply in #{ctx.channel} on {ctx.guild}. "
                                  "Please ask an admin to give me Send Messages and Embed Links.")
        except discord.Forbidden:
            pass


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
        title="📖 ⭐︎ 🎲 How to use `!rec` and `!random`",
        description="Get the link to a specific book's Goodreads page, or I can suggest a random book from a selected genre!",
        color=discord.Color.blurple()
    )
    embed.add_field(
        name="Commands:",
        value=(
            "`!rec {title}`\n`!rec {title} by {author}`\n`!random {genre}`\n\n"
            "*Adding the author increases accuracy when recc'ing a title shared by multiple books.*"
        ),
        inline=False
    )
    embed.add_field(
        name="Examples:",
        value="`!rec I Married a Lizardman`\n`!rec I Married a Lizardman by Regine Abel`\n`!random fantasy`",
        inline=False
    )
    embed.add_field(
        name="Tips:",
        value=(
            "• When including an author always separate the author's name with `by` -> e.g. `!rec It by Stephen King`, not `!rec It Stephen King`.\n"
            "• Double-check the spelling.\n"
            "• Niche book titles may not include an embedded book cover.\n"
            "• `!random` needs a genre. Use `!random` on its own to see the list of genres.\n"
            "• `!random` leans toward well-known books but smaller genres may show lesser-known ones.\n"
            "• `!random` isn't 100% accurate so expect some false positives within each genre."
        ),
        inline=False
    )

    await ctx.send(embed=embed)


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

    try:
        work_id = pick_work_id(matched_genre, GENRE_POOLS, RECENT)
    except (KeyError, ValueError):   # empty pool, or genre missing from GENRE_POOLS
        work_id = None

    result = None
    if work_id is not None:
        result = pd.read_sql('SELECT * FROM works WHERE id = ?', CONN, params=(work_id,))

    if result is None or result.empty:
        embed = discord.Embed(
            title="📭 No results",
            description=f"No books found for `{matched_genre}` right now.",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        return

    book_info = result.iloc[0]

    first_author_id = book_info['work_author_ids'].split(',')[0]
    book_author = get_author_names([first_author_id], CONN).get(first_author_id, "Unknown author")
    cover_id = get_cover_for_work(book_info['id'], CONN)
    formatted_title = format_title(book_info['title'])
    formatted_author = format_author(book_author)

    goodreads_url = create_goodreads_url(formatted_title, formatted_author)

    embed = build_book_embed(formatted_title, formatted_author, goodreads_url, cover_id)
    await ctx.send(embed=embed)


@bot.command(name='rec')
@commands.cooldown(1, 3, commands.BucketType.user)
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