import discord
from discord.ext import commands
import requests
import boto3
from boto3.dynamodb.conditions import Key
import os
from dotenv import load_dotenv
import json
from datetime import datetime
import asyncio

load_dotenv()

bot = commands.Bot(command_prefix='!', intents=discord.Intents.all())

# initialize DynamoDB
dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_DEFAULT_REGION', 'us-east-1'))
matches_table = dynamodb.Table('rift-rewind-matches')
players_table = dynamodb.Table('rift-rewind-players')

print("Initializing bot with DynamoDb connection")

# league API functions
async def get_summoner_by_riot_id(game_name, tag_line="NA1", region="americas"):
    '''Get summoner info by Riot ID'''
    api_key = os.getenv('RIOT_API_KEY')
    url = f"https://{region}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
    headers = {"X-Riot-Token": api_key}

    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    else: 
        print(f"Riot ID lookup failed: {response.status_code}")
        return None

async def get_summoner_by_puuid(puuid, region="na1"):
    '''Get summoner details (including level) by PUUID'''
    api_key = os.getenv('RIOT_API_KEY')
    url = f"https://{region}.api.riotgames.com/lol/summoner/v4/summoners/by-puuid/{puuid}"
    headers = {"X-Riot-Token": api_key}
    
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        return response.json()
    else: 
        print(f"Summoner lookup failed: {response.status_code}")
        return None

async def get_match_history(puuid, region="americas", count= 20):
    '''Get recent match IDS for a player'''
    api_key = os.getenv('RIOT_API_KEY')
    url = f"https://{region}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids"
    headers = {"X-Riot-Token": api_key}
    params = {"start": 0, "count": count}

    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        return response.json()
    else: 
        print(f"Match history failed: {response.status_code}")
        return None

async def get_match_details(match_id, region="americas"):
    '''Get detailed match information'''
    api_key = os.getenv('RIOT_API_KEY')
    url = f"https://{region}.api.riotgames.com/lol/match/v5/matches/{match_id}"
    headers = {"X-Riot-Token": api_key}

    response =  requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    else: 
        print(f"Match details failed for {match_id}: {response.status_code}")
        return None

# dynamoDB cache functions
async def store_match_data(match_id, puuid, match_data):
    '''store match data in dynamodb'''
    try:
        matches_table.put_item(
            Item={
                'match_id': match_id,
                'puuid': puuid,
                'data': json.dumps(match_data),
                'timestamp': int(datetime.now().timestamp())
            }
        )
        return True
    except Exception as e:
        print(f"Error storinig match {match_id}: {e}")
        return False
    
async def get_cached_match(match_id, puuid):
    '''retrieve cached match from dynamoDB'''
    try:
        response = matches_table.get_item(
            Key = {'match_id': match_id, 'puuid': puuid}
        )
        if 'Item' in response:
            return json.loads(response['Item']['data'])
        return None
    except Exception as e:
        print(f"Error retrieving cached match {match_id}: {e}")
        return None

async def get_match_details_cached(match_id, puuid, region='americas'):
    '''get match details with caching'''
    # try cache first
    cached = await get_cached_match(match_id, puuid)
    if cached:
        # print(f"Cache hit: {match_id}")
        return cached
    
    # not in cache - fetch from API
    # print(f"API fetch: {match_id}")
    match_data = await get_match_details(match_id, region)

    if match_data:
        # store in cache for next time
        await store_match_data(match_id, puuid, match_data)
        print(f"Cached: {match_id}")

    return match_data

@bot.command()
async def test_aws(ctx):
    '''test aws dynamodb connection'''
    try:
        # check both tables
        matches_status = matches_table.table_status
        players_status = players_table.table_status

        embed = discord.Embed(
            title="AWS Connection Test",
            description="DynamoDB tables are connected!",
            color=discord.Color.green()
        )
        embed.add_field(name="Matches Table", value=f"Status: {matches_status}", inline=False)
        embed.add_field(name="Players Table", value=f"Status: {players_status}", inline=False)

        await ctx.send(embed=embed)

    except Exception as e:
        await ctx.send(f"AWS connection failed:\n```{e}```")

@bot.command()
async def wrapped(ctx, *, summoner_input):
    # handle both formats: "blaberfish2" or "blaberfish2#NA1"
    if "#" in summoner_input:
        game_name, tag_line = summoner_input.split("#", 1)
    else:
        game_name = summoner_input
        tag_line = "NA1" # default tag
    
    await ctx.send(f"🔍 Fetching League data for **{game_name}#{tag_line}**...")

    # get account info using riot id
    account = await get_summoner_by_riot_id(game_name, tag_line)
    if not account:
        await ctx.send(f"❌ Summoner **{game_name}#{tag_line}** not found!")
        return
    
    # get summoner details using PUUID
    summoner = await get_summoner_by_puuid(account['puuid'])
    if not summoner:
        await ctx.send(f"❌ Could not fetch summoner details!")
        return

    await ctx.send(f"✅ Found: **{account['gameName']}#{account['tagLine']}** (Level {summoner['summonerLevel']})")

    # get recent match history
    match_ids = await get_match_history(account['puuid'], count = 100)
    if not match_ids:
        await ctx.send("❌ Could not fetch match history!")
        return
    
    await ctx.send(f"📊 Analyzing **{len(match_ids)}** recent matches...")

    # process matches
    processed = 0
    cache_hits = 0
    api_calls = 0

    for i, match_id in enumerate(match_ids):
        # progress updates
        if (i+1) % 5 == 0:
            await ctx.send(f"⏳ Progress: {i + 1}/{len(match_ids)} matches processed...")
        
        # check if cached first
        is_cached = await get_cached_match(match_id, account['puuid']) is not None

        # get match data(from cache or API)
        match_data = await get_match_details_cached(match_id, account['puuid'])

        if match_data:
            processed += 1
            if is_cached:
                cache_hits += 1
            else:
                api_calls += 1
        
        # small delay to respect rate limits
        await asyncio.sleep(0.5)

    # results summary
    embed = discord.Embed(
        title="Analysis Complete!",
        description=f"Successfully processed {processed} matches",
        color = discord.Color.blue()
    )
    embed.add_field(name="From cache", value=cache_hits, inline=True)
    embed.add_field(name="API calls", value=api_calls, inline=True)
    embed.add_field(name="Total", value=processed, inline=True)
    embed.set_footer(text="AI-Powered insights coming soon!!")

    await ctx.send(embed=embed)

@bot.event
async def on_ready():
    print(f'Bot logged in as {bot.user}')
    print(f"Connected to DynamoDB:")
    print(f'    - Table: {matches_table.table_name} ({matches_table.table_status})')
    print(f'    - Table: {players_table.table_name} ({players_table.table_status})')
    print(f'Bot is ready!')


if __name__ == "__main__":
    bot.run(os.getenv('DISCORD_TOKEN'))