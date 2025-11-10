# Rift Rewind - League of Legends AI Year-in-Review

AI-powered Discord bot that analyzes League of Legends players' 2025 season performance and provides personalized coaching insights.

## Features
- 📊 Season statistics (win rate, top champions, KDA)
- 🤖 AI-powered coaching analysis using AWS Bedrock
- ⚡ Fast caching with AWS DynamoDB
- 🎮 Easy Discord integration

## Tech Stack
- **Discord.py** - Bot framework
- **Riot Games API** - Match data
- **AWS Bedrock (Claude 3 Haiku)** - AI insights
- **AWS DynamoDB** - Match caching
- **Python 3.11+**

## Setup Instructions

### Prerequisites
- Python 3.11+
- Discord Bot Token
- Riot Games API Key
- AWS Account with Bedrock & DynamoDB access

### Installation
```bash
# Clone repository
git clone https://github.com/mel418/league-wrapped.git
cd league-wrapped

# Install dependencies
pip install discord.py boto3 requests python-dotenv

# Configure environment variables
cp .env.example .env
# Edit .env with your credentials

# Run bot
python main.py
```

### Environment Variables
```env
DISCORD_TOKEN=your_discord_token
RIOT_API_KEY=your_riot_api_key
AWS_ACCESS_KEY_ID=your_aws_key
AWS_SECRET_ACCESS_KEY=your_aws_secret
AWS_DEFAULT_REGION=us-east-1
```

## Usage
In Discord, type:
```
!wrapped blaberfish2#NA1
```

The bot will:
1. Fetch all 2025 matches from Riot API
2. Cache data in DynamoDB for fast repeat lookups
3. Calculate season statistics
4. Generate personalized AI insights using AWS Bedrock
5. Display results in formatted Discord embed

## AWS Services Used
- **Amazon Bedrock (Claude 3 Haiku)**: Generates personalized coaching insights
- **Amazon DynamoDB**: Caches match data to reduce API calls
- **CloudWatch**: Logging (implicit)

## Testing Instructions for Judges
1. Invite bot to Discord server
2. Run: `!wrapped <any-league-username>#<tag>`
3. Bot will analyze their 2025 season and show AI insights
4. Run command again - should be instant (cached)

## License
MIT License - See LICENSE file

## Hackathon
Built for Riot Games Hackathon: Rift Rewind 2025