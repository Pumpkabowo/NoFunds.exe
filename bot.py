import discord
from discord.ext import commands, tasks
from discord import app_commands
from discord.ui import View, Button
import aiohttp
import asyncio
import json
import os
from datetime import datetime
from game_fetcher import get_free_games, get_steam_sales, create_embed

DISCORD_TOKEN = "YOUR-DISCORD-TOKEN"
STEAM_API_KEY = "YOUR-STEAM-API-KEY"

FREE_GAMES_CHANNEL_ID = 12345678910111213
FORTNITE_CHANNEL_ID = 12345678910111213


intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

last_fortnite_post = None
auto_post_ready = False
last_shop_data = None  # Cache for Fortnite shop items

async def get_steam_free_games():
    url = "https://www.cheapshark.com/api/1.0/deals?storeID=1&upperPrice=0.00"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                print(f"Failed to fetch Steam free games: {resp.status}")
                return []
            data = await resp.json()
    free_games = []
    for deal in data:
        free_games.append({
            "title": deal.get("title"),
            "dealID": deal.get("dealID"),
            "normalPrice": deal.get("normalPrice"),
            "salePrice": deal.get("salePrice"),
            "thumb": deal.get("thumb"),
            "steamAppID": deal.get("steamAppID"),
            "dealRating": deal.get("dealRating"),
        })
    return free_games

def get_current_and_next_steam_sale_embeds():
    try:
        with open("steam_sales.json", "r") as f:
            events = json.load(f)
    except Exception as e:
        print(f"Error loading steam_sales.json: {e}")
        return None, None

    today = datetime.utcnow().date()
    current_event = None
    next_event = None

    upcoming_events = []

    for event in events:
        start = datetime.strptime(event["start"], "%Y-%m-%d").date()
        end = datetime.strptime(event["end"], "%Y-%m-%d").date()

        if start <= today <= end:
            current_event = event
        elif start > today:
            upcoming_events.append(event)

    upcoming_events.sort(key=lambda e: datetime.strptime(e["start"], "%Y-%m-%d").date())

    if upcoming_events:
        next_event = upcoming_events[0]

    current_embed = None
    if current_event:
        current_embed = discord.Embed(
            title=f"🎮 Current Steam Sale:",
            description=f"{current_event['name']}\n\n{current_event.get('description', 'No description available.')}",
            color=0x1b2838
        )
        end = datetime.strptime(current_event["end"], "%Y-%m-%d").date()
        current_embed.add_field(name="⏳ Ends", value=end.strftime("%B %d, %Y"), inline=False)
        current_embed.add_field(name="🔗 Visit Event", value=current_event.get("link", "https://store.steampowered.com/"), inline=False)
        current_embed.set_image(url=current_event.get("image", ""))
        if next_event:
            next_start = datetime.strptime(next_event["start"], "%Y-%m-%d").date()
            current_embed.set_footer(text=f"Next sale: {next_event['name']} starts on {next_start.strftime('%B %d, %Y')}")
        else:
            current_embed.set_footer(text="No upcoming sales scheduled.")
    return current_embed, next_event

@tasks.loop(hours=6)
async def auto_post_free_games_once():
    free_games_channel = bot.get_channel(FREE_GAMES_CHANNEL_ID)

    try:
        new_games = get_free_games(STEAM_API_KEY)
        steam_free_games = await get_steam_free_games()
    except Exception as e:
        print(f"Error fetching free games: {e}")
        return

    last_games_file = "last_free_games.json"

    if os.path.exists(last_games_file):
        with open(last_games_file, "r") as f:
            last_games = json.load(f)
    else:
        last_games = []

    # Combine titles from both sources for comparison
    new_game_titles = [game.get("title", "") for game in new_games] + [game.get("title", "") for game in steam_free_games]
    last_game_titles = [game.get("title", "") for game in last_games]

    if new_game_titles != last_game_titles:
        print("New free games detected! Posting...")

        # Post Epic free games
        for game in new_games:
            embed = create_embed(game, is_sale=False)
            await free_games_channel.send(embed=embed)
            await asyncio.sleep(1)

        # Post Steam free games
        for game in steam_free_games:
            embed = discord.Embed(
                title=f"STEAM FREE GAME: {game['title']}",
                url=f"https://store.steampowered.com/app/{game['steamAppID']}" if game.get("steamAppID") else None,
                color=0x1b2838
            )
            embed.set_thumbnail(url=game.get("thumb", ""))
            embed.add_field(name="Original Price", value=f"${game.get('normalPrice', 'N/A')}", inline=True)
            embed.add_field(name="Current Price", value=f"${game.get('salePrice', '0.00')} (Free!)", inline=True)
            embed.add_field(name="Deal Rating", value=game.get("dealRating", "N/A"), inline=True)
            embed.set_footer(text="Source: CheapShark")
            await free_games_channel.send(embed=embed)
            await asyncio.sleep(1)

        with open(last_games_file, "w") as f:
            # Save combined list for next comparison
            combined_games = new_games + steam_free_games
            json.dump(combined_games, f)
    else:
        print("No new free games to post.")

@tasks.loop(hours=6)
async def auto_post_steam_sales_once():
    free_games_channel = bot.get_channel(FREE_GAMES_CHANNEL_ID)

    try:
        sales = get_steam_sales(STEAM_API_KEY)
    except Exception as e:
        print(f"Error fetching Steam sales: {e}")
        return

    last_sale_file = "last_steam_sale.json"

    if os.path.exists(last_sale_file):
        with open(last_sale_file, "r") as f:
            last_sale = json.load(f)
    else:
        last_sale = None

    today = datetime.utcnow().date()
    current_sale = None
    for sale in sales:
        start = datetime.strptime(sale["start"], "%Y-%m-%d").date()
        end = datetime.strptime(sale["end"], "%Y-%m-%d").date()
        if start <= today <= end:
            current_sale = sale
            break

    if current_sale:
        if not last_sale or last_sale.get("name") != current_sale.get("name"):
            print(f"New Steam sale detected: {current_sale.get('name')} - Posting!")
            embed = create_embed(current_sale, is_sale=True)
            await free_games_channel.send(embed=embed)
            with open(last_sale_file, "w") as f:
                json.dump(current_sale, f)
        else:
            print("Steam sale unchanged; no post.")
    else:
        print("No active Steam sale currently.")

@tree.command(name="freegames", description="Show current free Epic and Steam games")
async def freegames(interaction: discord.Interaction):
    print("Received /freegames command")
    await interaction.response.defer()
    try:
        epic_games = get_free_games(STEAM_API_KEY)
        steam_games = await get_steam_free_games()
    except Exception as e:
        print(f"Error fetching free games: {e}")
        await interaction.followup.send("⚠️ Something went wrong fetching free games.")
        return

    if not epic_games and not steam_games:
        await interaction.followup.send("No free games available right now.")
        return

    # Post Epic free games
    for game in epic_games:
        embed = create_embed(game, is_sale=False)
        await interaction.followup.send(embed=embed)
        await asyncio.sleep(1)

    # Post Steam free games
    for game in steam_games:
        embed = discord.Embed(
            title=f"STEAM FREE GAME: {game['title']}",
            url=f"https://store.steampowered.com/app/{game['steamAppID']}" if game.get("steamAppID") else None,
            color=0x1b2838
        )
        embed.set_thumbnail(url=game.get("thumb", ""))
        embed.add_field(name="Original Price", value=f"${game.get('normalPrice', 'N/A')}", inline=True)
        embed.add_field(name="Current Price", value=f"${game.get('salePrice', '0.00')} (Free!)", inline=True)
        embed.add_field(name="Deal Rating", value=game.get("dealRating", "N/A"), inline=True)
        embed.set_footer(text="Source: CheapShark")
        await interaction.followup.send(embed=embed)
        await asyncio.sleep(1)

@tree.command(name="gamesale", description="Show current Steam sales")
async def gamesale(interaction: discord.Interaction):
    print("Received /gamesale command")
    try:
        await interaction.response.defer()
        sales = get_steam_sales(STEAM_API_KEY)
        if not sales:
            await interaction.followup.send(content="No Steam sales found right now.")
            return
        for sale in sales:
            embed = create_embed(sale, is_sale=True)
            await interaction.followup.send(embed=embed)
    except Exception as e:
        print(f"/gamesale error: {e}")
        await interaction.followup.send("⚠️ Something went wrong fetching Steam sales.")

@tree.command(name="steamsale", description="Show current Steam sale event")
async def steamsale(interaction: discord.Interaction):
    print("Received /steamsale command")
    try:
        await interaction.response.defer()
        current_embed, next_event = get_current_and_next_steam_sale_embeds()
        if current_embed:
            await interaction.followup.send(embed=current_embed)
        else:
            if next_event:
                start = datetime.strptime(next_event["start"], "%Y-%m-%d").date()
                msg = f"No current sale active.\nNext sale: {next_event['name']} starts on {start.strftime('%B %d, %Y')}."
                await interaction.followup.send(msg)
            else:
                await interaction.followup.send("🗓️ No current or upcoming Steam sale event found.")
    except Exception as e:
        print(f"/steamsale error: {e}")
        await interaction.followup.send("⚠️ Something went wrong fetching the Steam sale event.")

class ShopView(View):
    def __init__(self, ctx, items):
        super().__init__(timeout=180)  # 3 minutes timeout
        self.ctx = ctx
        self.items = items
        self.page = 0
        self.max_page = (len(items) - 1) // 5

        self.embed = self.create_embed()

    def create_embed(self):
        embed = discord.Embed(title="Fortnite Item Shop", color=0x0099ff)
        start = self.page * 5
        end = start + 5
        for item in self.items[start:end]:
            name = item.get("name")
            price = item.get("price", "Unknown")
            rarity = item.get("rarity", "Unknown")
            embed.add_field(
                name=f"{name} [{rarity}]",
                value=f"Price: {price} V-Bucks",
                inline=False,
            )
        embed.set_footer(text=f"Page {self.page + 1}/{self.max_page + 1}")
        return embed

    async def update_message(self, interaction):
        self.embed = self.create_embed()
        await interaction.response.edit_message(embed=self.embed, view=self)

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.gray)
    async def previous(self, interaction: discord.Interaction, button: Button):
        if self.page > 0:
            self.page -= 1
            await self.update_message(interaction)
        else:
            await interaction.response.defer()

    @discord.ui.button(label="Next", style=discord.ButtonStyle.gray)
    async def next(self, interaction: discord.Interaction, button: Button):
        if self.page < self.max_page:
            self.page += 1
            await self.update_message(interaction)
        else:
            await interaction.response.defer()

@tree.command(name="fnshop", description="Show current Fortnite item shop")
async def fnshop(interaction: discord.Interaction):
    global last_shop_data

    await interaction.response.defer()
    url = "https://fortnite-api.com/v2/shop"

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                await interaction.followup.send(f"Failed to fetch Fortnite shop data. Status: {resp.status}")
                return
            data = await resp.json()

    featured = data.get("data", {}).get("featured", [])
    daily = data.get("data", {}).get("daily", [])

    items = []
    for section in featured + daily:
        items.extend(section.get("items", []))

    if not items:
        if last_shop_data:
            view = ShopView(interaction, last_shop_data)
            await interaction.followup.send(
                "The Fortnite shop is currently empty. Showing last available items:",
                embed=view.embed, view=view)
        else:
            await interaction.followup.send(
                "The Fortnite shop is empty right now. Please check back after the next reset!")
        return

    last_shop_data = items

    view = ShopView(interaction, items)
    await interaction.followup.send(embed=view.embed, view=view)

@tree.command(name="fndrops", description="Placeholder for Fortnite Twitch Drops")
async def fndrops(interaction: discord.Interaction):
    await interaction.response.send_message("🎁 Fortnite Twitch drops support coming soon!")

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    try:
        synced = await tree.sync()
        print(f"✅ Synced {len(synced)} slash commands.")
    except Exception as e:
        print(f"⚠️ Command sync failed: {e}")
    auto_post_free_games_once.start()
    auto_post_steam_sales_once.start()

bot.run(DISCORD_TOKEN)
