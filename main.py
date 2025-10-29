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

# init bedrock client
bedrock = boto3.client(
    service_name = 'bedrock-runtime',
    region_name=os.getenv('AWS_DEFAULT_REGION', 'us-east-1')
)

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

async def get_match_history(puuid, region="americas", count=100, start_time=None):
    '''Get recent match IDS for a player'''
    api_key = os.getenv('RIOT_API_KEY')
    url = f"https://{region}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids"
    headers = {"X-Riot-Token": api_key}
    params = {"start": 0, "count": count}
    
    # Add startTime filter for 2025 matches only
    if start_time:
        params["startTime"] = start_time
    
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
        # print(f"Cached: {match_id}")

    return match_data

# statistics helper functs
def is_from_2025(match_data):
    try:
        game_start = match_data['info']['gameStartTimestamp']
        game_date = datetime.fromtimestamp(game_start/1000)
        return game_date.year == 2025
    except:
        return False
    
def extract_player_stats(match_data, puuid):
    '''extract stats for specific player from match data'''
    try:
        participants = match_data['info']['participants']

        # find the player in match
        player_data = None
        for participant in participants:
            if participant['puuid'] == puuid:
                player_data = participant
                break
        
        if not player_data:
            return None
        
        return {
            'champion': player_data['championName'],
            'role': player_data['teamPosition'],
            'kills': player_data['kills'],
            'deaths': player_data['deaths'],
            'assists': player_data['assists'],
            'win': player_data['win'],
            'gameDuration': match_data['info']['gameDuration'],
            'gameDate': datetime.fromtimestamp(match_data['info']['gameStartTimestamp'] / 1000)
        }
    except Exception as e:
        print(f"Error extracting player stats: {e}")
        return None
    
def calculate_aggregate_stats(all_stats):
    '''calc aggr stats from all matches'''
    if not all_stats:
        return None
    
    total_games = len(all_stats)
    wins = sum(1 for s in all_stats if s['win'])
    losses = total_games - wins
    win_rate = (wins / total_games * 100) if total_games > 0 else 0

    # champ stats
    champion_games = {}
    champion_wins = {}
    for stat in all_stats:
        champ = stat['champion']
        champion_games[champ] = champion_games.get(champ, 0) + 1
        if stat['win']: 
            champion_wins[champ] = champion_wins.get(champ, 0) + 1
    
    # sort champs by games played
    top_champions = sorted(champion_games.items(), key=lambda x: x[1], reverse=True)[:5]

    # role stats
    role_games = {}
    for stat in all_stats:
        role = stat['role'] if stat['role'] else 'UNKNOWN'
        role_games[role] = role_games.get(role, 0) + 1 
    
    most_played_role = max(role_games.items(), key=lambda x: x[1]) if role_games else ('UNKNOWN', 0)

    # KDA stats
    total_kills = sum(s['kills'] for s in all_stats)
    total_deaths = sum(s['deaths'] for s in all_stats)
    total_assists = sum(s['assists'] for s in all_stats)
    avg_kda = ((total_kills + total_assists) / total_deaths) if total_deaths > 0 else total_kills + total_assists

    return {
        'total_games': total_games,
        'wins': wins,
        'losses': losses,
        'win_rate': win_rate,
        'top_champions': top_champions,
        'most_played_role': most_played_role,
        'avg_kda': avg_kda,
        'total_kills': total_kills,
        'total_deaths': total_deaths,
        'total_assists': total_assists
    }

async def generate_ai_insights(stats, game_name, tag_line):
    '''generate ai insights using aws bedrock'''

    prompt = f"""You are an expert League of Legends coach analyzing a player's 2025 season performance. 
    
Player: {game_name}#{tag_line}

Season Statistics:
- Total Games: {stats['total_games']}
- Record: {stats['wins']}W - {stats['losses']}L ({stats['win_rate']:.1f}% win rate)
- Top 3 Champions: {', '.join([f"{champ} ({games} games)" for champ, games in stats['top_champions'][:3]])}
- Main Role: {stats['most_played_role'][0]}
- Average KDA: {stats['avg_kda']:.2f} ({stats['total_kills']}K / {stats['total_deaths']}D / {stats['total_assists']}A)

Based on this data, provide:
1. A brief personality assessment of their playstyle (2-3 sentences)
2. Their biggest strength (1 sentence)
3. One specific area for improvement with actionable advice (2-3 sentences)
4. One surprising or interesting insight from their stats (1-2 sentences)

Keep your response conversational, encouraging, and under 200 words total."""
    
    conversation = [
        {
            "role": "user",
            "content": [{"text": prompt}]
        }
    ]

    try:
        response = bedrock.converse(
            modelId='anthropic.claude-3-haiku-20240307-v1:0',
            messages=conversation,
            inferenceConfig={
                "maxTokens": 500,
                "temperature": 0.7, # a bit creative but not too random
                "topP": 0.9
            }
        )

        # extract response
        ai_insights = response["output"]["message"]["content"][0]["text"]
        return ai_insights
    
    except Exception as e:
        print(f"Error generating AI insights: {e}")
        return "Unable to generate AI insights at this time."

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
    '''league wrapped for player'''

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

    # get match history from 2025 only
    start_of_2025 = int(datetime(2025, 1, 1).timestamp())
    match_ids = await get_match_history(account['puuid'], count=100, start_time=start_of_2025)
    
    if not match_ids:
        await ctx.send("❌ Could not fetch match history!")
        return
    
    if len(match_ids) == 0:
        await ctx.send("❌ No matches found from 2025!")
        return
    
    await ctx.send(f"📊 Found **{len(match_ids)}** matches from 2025. Analyzing...")

    # process matches
    processed = 0
    cache_hits = 0
    api_calls = 0
    all_player_stats = []

    for i, match_id in enumerate(match_ids):
        # progress updates every 10 matches
        '''if (i+1) % 10 == 0:
            await ctx.send(f"⏳ Progress: {i + 1}/{len(match_ids)} matches processed...")'''
        
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
            
            # Extract player stats
            player_stats = extract_player_stats(match_data, account['puuid'])
            if player_stats:
                all_player_stats.append(player_stats)
        
        # small delay to respect rate limits
        if not is_cached:
            await asyncio.sleep(1.2)
        else:
            await asyncio.sleep(0.1)
    
    # calc aggr stats
    stats = calculate_aggregate_stats(all_player_stats)

    if not stats:
        await ctx.send("❌ No valid match data found!")
        return
    
    # generate ai insights
    await ctx.send("Generating AI-powered insights...")
    ai_insights = await generate_ai_insights(stats, account['gameName'], account["tagLine"])

    # Create detailed results embed
    embed = discord.Embed(
        title=f"🎮 League Wrapped 2025",
        description=f"**{account['gameName']}#{account['tagLine']}** - Year to Date",
        color=discord.Color.gold()
    )
    
    # Overview
    embed.add_field(
        name="📊 Overview",
        value=f"**{stats['total_games']}** games played in 2025\n"
              f"**{stats['wins']}W - {stats['losses']}L** ({stats['win_rate']:.1f}% win rate)",
        inline=False
    )
    
    # Top Champions
    champ_text = "\n".join([
        f"**{i+1}.** {champ} - {games} games ({games/stats['total_games']*100:.1f}%)"
        for i, (champ, games) in enumerate(stats['top_champions'][:3])
    ])
    embed.add_field(
        name="🏆 Top Champions",
        value=champ_text or "No data",
        inline=False
    )
    
    # Role & KDA
    embed.add_field(
        name="⚔️ Main Role",
        value=f"**{stats['most_played_role'][0]}**\n{stats['most_played_role'][1]} games",
        inline=True
    )
    
    embed.add_field(
        name="📈 Average KDA",
        value=f"**{stats['avg_kda']:.2f}**\n"
              f"{stats['total_kills']}K / {stats['total_deaths']}D / {stats['total_assists']}A",
        inline=True
    )

    # Cache stats (footer)
    embed.set_footer(
        text=f"💾 {cache_hits} cached | 🌐 {api_calls} API calls | 📅 {len(match_ids)} total matches"
    )
    
    await ctx.send(embed=embed)
    
    ai_message = f"## AI Coach Analysis\n\n{ai_insights}"
    await ctx.send(ai_message)

@bot.event
async def on_ready():
    print(f'Bot logged in as {bot.user}')
    print(f"Connected to DynamoDB:")
    print(f'    - Table: {matches_table.table_name} ({matches_table.table_status})')
    print(f'    - Table: {players_table.table_name} ({players_table.table_status})')
    print(f'Bot is ready!')


if __name__ == "__main__":
    bot.run(os.getenv('DISCORD_TOKEN'))