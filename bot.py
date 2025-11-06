import discord
from discord.ext import commands
import asyncio
import re
import datetime
import time
import os  # <-- Make sure this is imported
import requests  # <-- Make sure this is imported
from typing import Optional

# Set up the bot with necessary intents and multiple command prefixes
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=['.shield ', '.'], intents=intents) # <-- Multi-prefix

# Disable the default help command to use our custom one
bot.remove_command('help')

# Dictionary to store active timers
# Format: {target_key: {"task": task_object, "duration": original_duration_str, "completion_timestamp": int, ...}}
active_timers = {}

def parse_time(time_input):
    """Converts a string like '1d 2h 30m' or '1h1m' into seconds."""
    seconds = 0
    # Updated regex to be more flexible, e.g., '1h30m'
    matches = re.findall(r'(\d+)\s*([dhm])', time_input.lower())
    if not matches and time_input.isdigit(): # Allow just seconds
        return int(time_input)
    
    for value, unit in matches:
        value = int(value)
        if unit == 'd':
            seconds += value * 86400
        elif unit == 'h':
            seconds += value * 3600
        elif unit == 'm':
            seconds += value * 60
            
    return seconds if seconds > 0 else None

async def run_timer(target_key, total_seconds, original_duration_str, author_id, channel_id, is_custom_name):
    """The main timer logic with 1 hour and 15 minute conditional warnings."""
    timer_data = active_timers.get(target_key)
    if not timer_data: return

    channel = bot.get_channel(channel_id)
    if not channel: # Channel might be deleted or bot lost access
        if target_key in active_timers:
            del active_timers[target_key]
        return

    author_mention = f"<@{author_id}>"
    target_mention_str = timer_data.get('target_mention_str', 'A timer target') # Fallback if error

    warning_1hr_time = 3600  # 60 * 60
    warning_15min_time = 900 # 15 * 60
    
    try:
        current_sleep = total_seconds

        # 1 Hour Warning
        if current_sleep > warning_1hr_time:
            await asyncio.sleep(current_sleep - warning_1hr_time)
            # Check if timer still exists before sending
            if target_key not in active_timers:
                return
            await channel.send(
                f"⏰ **1 hour remaining** for the shield for {target_mention_str} (set by {author_mention} for {original_duration_str})."
            )
            current_sleep = warning_1hr_time # Time remaining is now 1hr

        # 15 Minute Warning
        if current_sleep > warning_15min_time:
            await asyncio.sleep(current_sleep - warning_15min_time)
            if target_key not in active_timers:
                return
            await channel.send(
                f"⏰ **15 minutes remaining** for the shield for {target_mention_str} (set by {author_mention} for {original_duration_str})."
            )
            current_sleep = warning_15min_time # Time remaining is now 15m
        
        # Final Reminder
        await asyncio.sleep(current_sleep)

        if target_key in active_timers:
            await channel.send(
                f"⏰ **Reminder finished!** The shield for {target_mention_str} (set by {author_mention}) is now over."
            )
            del active_timers[target_key]

    except asyncio.CancelledError:
        # This is expected when a timer is manually broken
        pass
    except Exception as e:
        print(f"Error in run_timer: {e}")
        if channel:
            await channel.send(f"An error occurred with a timer for {target_mention_str}. It has been removed.")
        if target_key in active_timers:
            del active_timers[target_key]


@bot.command(name='set')
async def set_timer(ctx, time_input: str, *, target: Optional[str] = None):
    """Starts or overwrites a timer. Use: .shield set <time> [@user or Custom Name]"""
    seconds = parse_time(time_input)

    if seconds is None or seconds <= 0:
        await ctx.channel.send("Please provide a valid time format (e.g., `1d 2h 30m`, `10h`, `45m`).")
        return

    is_custom_name = False
    target_key = None
    target_mention_str = None

    if target is None:
        # Default to the command author
        target_key = ctx.author.id
        target_mention_str = ctx.author.mention
    else:
        # Check if the input is a user mention
        if ctx.message.mentions:
            mentioned_user = ctx.message.mentions[0]
            target_key = mentioned_user.id
            target_mention_str = mentioned_user.mention
        else:
            # It's a custom name
            is_custom_name = True
            target_key = f"custom:{ctx.guild.id}:{target.lower()}" # Prefix to avoid ID collisions, scoped to guild
            target_mention_str = f"**{target}**"

    # Cancel any existing timer for this key/ID
    if target_key in active_timers:
        active_timers[target_key]['task'].cancel()
        await ctx.channel.send(f"⏰ {ctx.author.mention}, the previous shield timer for {target_mention_str} was overwritten.")

    # Calculate completion time
    future_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=seconds)
    timestamp = int(future_time.timestamp())

    # Store necessary data in the dictionary
    task = asyncio.create_task(run_timer(target_key, seconds, time_input, ctx.author.id, ctx.channel.id, is_custom_name))
    
    active_timers[target_key] = {
        "task": task,
        "duration": time_input,
        "completion_timestamp": timestamp,
        "author_id": ctx.author.id,
        "target_mention_str": target_mention_str,
        "is_custom_name": is_custom_name
    }

    # Confirmation Message
    confirmation_message = (
        f"⏰ {ctx.author.mention} set a shield timer for {target_mention_str} for **{time_input}**."
        f"\nIt will be completed at: <t:{timestamp}:F> (which is <t:{timestamp}:R>)."
    )
    await ctx.channel.send(confirmation_message)


@bot.command(name='break')
async def break_timer(ctx, *, target: Optional[str] = None):
    """Stops the active timer for yourself, a mentioned user, or a custom name."""
    
    target_key = None
    target_mention_str = None

    if target is None:
        # Default to the author's own timer
        target_key = ctx.author.id
        target_mention_str = ctx.author.mention
    else:
        # Check for mention first
        if ctx.message.mentions:
            mentioned_user = ctx.message.mentions[0]
            target_key = mentioned_user.id
            target_mention_str = mentioned_user.mention
        else:
            # It's likely a custom name
            target_key = f"custom:{ctx.guild.id}:{target.lower()}"
            target_mention_str = f"**{target}**"


    if target_key in active_timers:
        active_timers[target_key]['task'].cancel()
        del active_timers[target_key]
        # Confirmation that it stopped
        await ctx.channel.send(f"✅ {ctx.author.mention} cancelled the shield timer for {target_mention_str}.")
    else:
        await ctx.channel.send(f"{ctx.author.mention}, I couldn't find an active shield timer for {target_mention_str}.")

@bot.command(name='timers')
async def list_timers(ctx):
    """Lists all active timers set in this guild."""
    if not active_timers:
        await ctx.channel.send("There are no active timers right now.")
        return

    response_lines = ["**Current Active Timers:**"]
    
    # Filter timers for the current guild if they are custom-named
    guild_timers = 0
    for key, data in active_timers.items():
        # Check if it's a user ID (int) or a custom name for this guild
        if isinstance(key, int) or (isinstance(key, str) and key.startswith(f"custom:{ctx.guild.id}")):
            guild_timers += 1
            timestamp = data['completion_timestamp']
            target_str = data['target_mention_str']
            
            # Format the line
            line = f"- {target_str} (Set for {data['duration']}) finishes <t:{timestamp}:R>."
            response_lines.append(line)

    if guild_timers == 0:
        await ctx.channel.send("There are no active timers for this server.")
        return

    await ctx.channel.send("\n".join(response_lines))

# --- Animal Commands ---

@bot.command(name='dog')
async def dog(ctx):
    """Fetches a random dog picture."""
    try:
        response = requests.get('https://dog.ceo/api/breeds/image/random')
        response.raise_for_status() # Raise an error for bad responses (4xx or 5xx)
        data = response.json()
        
        if data.get('status') == 'success':
            await ctx.channel.send(data['message'])
        else:
            await ctx.channel.send("Sorry, I couldn't fetch a dog picture right now.")
    except requests.exceptions.RequestException as e:
        print(f"Error fetching dog pic: {e}")
        await ctx.channel.send("Sorry, the dog API seems to be down.")

@bot.command(name='cat')
async def cat(ctx):
    """Fetches a random cat picture."""
    try:
        response = requests.get('https.api.thecatapi.com/v1/images/search')
        response.raise_for_status()
        data = response.json()
        
        if data and data[0].get('url'):
            await ctx.channel.send(data[0]['url'])
        else:
            await ctx.channel.send("Sorry, I couldn't fetch a cat picture right now.")
    except requests.exceptions.RequestException as e:
        print(f"Error fetching cat pic: {e}")
        await ctx.channel.send("Sorry, the cat API seems to be down.")

@bot.command(name='raccoon')
async def raccoon(ctx):
    """Fetches a random raccoon picture."""
    try:
        # Using a more general-purpose random image API that has raccoons
        response = requests.get('https://some-random-api.com/animal/raccoon')
        response.raise_for_status()
        data = response.json()
        
        if data and data.get('image'):
            await ctx.channel.send(data['image'])
        else:
            await ctx.channel.send("Sorry, I couldn't fetch a raccoon picture right now.")
    except requests.exceptions.RequestException as e:
        print(f"Error fetching raccoon pic: {e}")
        await ctx.channel.send("Sorry, the raccoon API seems to be down.")

# --- NEW HELP COMMAND ---

@bot.command(name='help')
async def help(ctx):
    """Displays this help message."""
    
    # Create the embed object
    embed = discord.Embed(
        title="Bot Help & Command List",
        description="This bot responds to two prefixes: `.shield ` and `.`",
        color=discord.Color.blue()
    )
    
    # Add Timer Commands field
    embed.add_field(
        name="🛡️ Timer Commands (Prefix: `.shield ` or `.`)",
        value=(
            "**`.shield set <time> [target]`**\n"
            "Sets a shield timer. *Target* can be a `@User` or a custom name (like `My Castle`). If no target, defaults to you.\n"
            "*Example:* `.shield set 8h @MyFriend`\n"
            "*Example:* `.set 3d Main Base`\n\n"
            
            "**`.shield break [target]`**\n"
            "Cancels an active timer for you, a `@User`, or a custom name.\n"
            "*Example:* `.break @MyFriend`\n\n"
            
            "**`.shield timers`**\n"
            "Lists all active timers running on this server.\n"
            "*Example:* `.timers`"
        ),
        inline=False
    )
    
    # Add Fun Commands field
    embed.add_field(
        name="🐼 Fun Commands (Prefix: `.`)",
        value=(
            "**`.dog`**: Fetches a random dog picture.\n"
            "**`.cat`**: Fetches a random cat picture.\n"
            "**`.raccoon`**: Fetches a random raccoon picture.\n"
        ),
        inline=False
    )
    
    # Add Help Command field
    embed.add_field(
        name="❓ Help",
        value="**`.help`**: Shows this help message.",
        inline=False
    )
    
    embed.set_footer(text="Time format: 1d = 1 day, 1h = 1 hour, 1m = 1 minute")
    
    # Send the embed
    await ctx.channel.send(embed=embed)


# --- Bot Events ---

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name} (ID: {bot.user.id})')
    print('Bot is ready and running.')

# Securely get the token and run the bot
TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    print("CRITICAL: DISCORD_TOKEN environment variable not set.")
    print("Please set the DISCORD_TOKEN in your Railway project variables.")
else:
    try:
        bot.run(TOKEN)
    except discord.errors.LoginFailure:
        print("CRITICAL: Improper token passed.")
        print("Please ensure your DISCORD_TOKEN is correct in Railway.")
    except Exception as e:
        print(f"CRITICAL: An error occurred while running the bot: {e}")
