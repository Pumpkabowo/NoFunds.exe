import requests
import discord
from datetime import datetime

def get_free_games(_=None):
    promo_url = "https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions?locale=en-US&country=US&allowCountries=US"
    games = []
    try:
        promo_res = requests.get(promo_url)
        if promo_res.status_code == 200:
            data = promo_res.json()
            elements = data['data']['Catalog']['searchStore']['elements']
            for game in elements:
                title = game['title']
                product_slug = game.get('productSlug', '')
                promotions = game.get('promotions', {})
                if not promotions or not promotions.get('promotionalOffers'):
                    continue

                offer = promotions['promotionalOffers'][0]['promotionalOffers'][0]
                if offer['discountSetting']['discountPercentage'] != 0:
                    continue

                start = offer['startDate']
                end = offer['endDate']
                thumbnail = game['keyImages'][0]['url']
                url = f"https://store.epicgames.com/en-US/p/{product_slug}"

                # Genre parsing from filtered category paths
                categories = game.get("categories", [])
                valid_genres = []
                for cat in categories:
                    path = cat["path"]
                    if "games/" in path and not any(skip in path for skip in ["vaulted", "free", "edition", "bundle"]):
                        valid_genres.append(path.split("/")[-1].replace("-", " ").title())
                genre = ", ".join(valid_genres) if valid_genres else "Unknown"

                # Fetch original price via GraphQL
                price_api = "https://store.epicgames.com/graphql"
                headers = {"Content-Type": "application/json"}
                payload = {
                    "query": "query productPrices($locale: String!, $country: String!, $slug: String!) {\
                                Catalog {\
                                    catalogOffer(slug: $slug, locale: $locale, country: $country) {\
                                        price { totalPrice { fmtPrice { originalPrice } } }\
                                    }\
                                }\
                            }",
                    "variables": {
                        "locale": "en-US",
                        "country": "US",
                        "slug": product_slug
                    }
                }

                original_price = "Unavailable"
                try:
                    price_res = requests.post(price_api, json=payload, headers=headers)
                    if price_res.status_code == 200:
                        price_data = price_res.json()
                        original_price = price_data["data"]["Catalog"]["catalogOffer"]["price"]["totalPrice"]["fmtPrice"]["originalPrice"]
                except Exception as e:
                    print(f"Price fetch error for {title}: {e}")

                games.append({
                    "title": title,
                    "url": url,
                    "start_date": start,
                    "end_date": end,
                    "thumbnail": thumbnail,
                    "description": game.get('description', 'No description available.'),
                    "original_price": original_price,
                    "genre": genre
                })
    except Exception as e:
        print(f"Epic free games fetch error: {e}")
    return games

def get_steam_sales(api_key):
    url = f"https://api.isthereanydeal.com/v01/deals/list/?key={api_key}&limit=5&store=steam"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            return response.json().get("data", {}).get("list", [])
    except Exception as e:
        print(f"Steam sale fetch error: {e}")
    return []

def create_embed(game, is_sale=False):
    embed = discord.Embed(color=0xFF80CC)

    if is_sale:
        title = game.get('title', 'Game')
        old_price = f"${game.get('price_old', '?')}"
        new_price = f"${game.get('price_new', '?')}"
        description = game.get('description', 'No description available.')
        genre = game.get("tags", ["Unknown"])[0] if isinstance(game.get("tags"), list) else "Unknown"
        platform = "Steam"

        embed.description = (
            f"__**🔥 STEAM SALE!**__\n\n"
            f"**{title}**\n"
            f"~~{old_price}~~ → **{new_price}**\n"
            f"{description}"
        )
        embed.add_field(name="🎮 Genre", value=genre, inline=True)
        embed.add_field(name="💻 Platform", value=platform, inline=True)
        embed.add_field(name="🕓 Ends", value="Check store for details", inline=False)
        embed.add_field(name="🔗 Link", value=game.get("url", "N/A"), inline=False)
        embed.set_thumbnail(url=game.get("image", ""))

    else:
        title = game.get("title", "Game")
        old_price = game.get("original_price", "Unavailable")
        new_price = "$0.00"
        description = game.get("description", "No description available.")
        genre = game.get("genre", "Unknown")
        platform = "Epic Games"

        embed.description = (
            f"__**🎉 EPIC FREE GAME**__\n\n"
            f"**{title}**\n"
            f"~~{old_price}~~ → **{new_price}**\n"
            f"{description}"
        )
        embed.add_field(name="🎮 Genre", value=genre, inline=True)
        embed.add_field(name="💻 Platform", value=platform, inline=True)
        embed.add_field(name="🕓 Ends", value=format_date(game.get('end_date')), inline=False)
        embed.add_field(name="🔗 Link", value=game.get("url", "N/A"), inline=False)
        embed.set_thumbnail(url=game.get("thumbnail", ""))

    return embed

def format_date(iso_str):
    try:
        dt = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
        return dt.strftime('%b %d, %Y at %I:%M %p UTC')
    except:
        return "Unknown"


