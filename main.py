import discord
from discord.ext import commands
import requests
import boto3
import os
from dotenv import load_dotenv
import asyncio

load_dotenv()

bot = commands.Bot(command_prefix='!', intents=discord.Intents.all())

# league API functions
async def get_summoner_by_riot_id(game_name, tag_line="NA1", region="americas"):
    '''Get summoner info by Riot ID'''
    api_key = os.getenv('RIOT_API_KEY')
    url = f"https://{region}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
    headers = {"X-Riot-Token": api_key}

    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    else: return None

async def get_summoner_by_puuid(puuid, region="na1"):
    '''Get summoner details (including level) by PUUID'''
    api_key = os.getenv('RIOT_API_KEY')
    url = f"https://{region}.api.riotgames.com/lol/summoner/v4/summoners/by-puuid/{puuid}"
    headers = {"X-Riot-Token": api_key}
    
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        return response.json()
    else: return None

async def get_match_history(puuid, region="americas", count= 20):
    '''Get recent match IDS for a player'''
    api_key = os.getenv('RIOT_API_KEY')
    url = f"https://{region}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids"
    headers = {"X-Riot-Token": api_key}
    params = {"start": 0, "count": count}

    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        return response.json()
    else: return None

async def get_match_details(match_id, region="americas"):
    '''Get detailed match information'''
    api_key = os.getenv('RIOT_API_KEY')
    url = f"https://{region}.api.riotgames.com/lol/match/v5/matches/{match_id}"
    headers = {"X-Riot-Token": api_key}

    response =  requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    else: return None

@bot.command()
async def wrapped(ctx, *, summoner_input):
    # handle both formats: "blaberfish2" or "blaberfish2#NA1"
    if "#" in summoner_input:
        game_name, tag_line = summoner_input.split("#", 1)
    else:
        game_name = summoner_input
        tag_line = "NA1" # default tag
    
    await ctx.send(f"Fetching League data for {game_name}#{tag_line}...")

    # get account info using riot id
    account = await get_summoner_by_riot_id(game_name, tag_line)
    if not account:
        await ctx.send(f"Summoner '{game_name}#{tag_line}' not found!")
        return
    
    # get summoner details using PUUID
    summoner = await get_summoner_by_puuid(account['puuid'])
    if not summoner:
        await ctx.send(f"Could not fetch summoner details!")
        return

    await ctx.send(f"Found player: {account['gameName']}#{account['tagLine']} (Level {summoner['summonerLevel']})")

    # get recent match history
    match_ids = await get_match_history(account['puuid'], count = 5)
    if not match_ids:
        await ctx.send("Could not fetch match history!")
        return
    
    await ctx.send(f"Analyzing {len(match_ids)} recent matches...")

    match_details = await get_match_details(match_ids[0])
    if match_details:
        game_duration = match_details['info']['gameDuration'] // 60
        await ctx.send(f"Most recent match: {game_duration} minute game")
    
    await ctx.send("League Wrapped analysis coming soon!")

@bot.event
async def on_ready():
    print(f'Bot logged in as {bot.user}')


if __name__ == "__main__":
    bot.run(os.getenv('DISCORD_TOKEN'))