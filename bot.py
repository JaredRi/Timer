import discord
from discord.ext import commands
import asyncio
import re
import datetime
import time 
from typing import Optional # Import Optional type hint
import os # <-- Added for environment variable access
import requests # <-- Added for .dog and .cat commands

# Set up the bot with necessary intents and command prefix
# CHANGE: command_prefix is now a list, allowing both ".shield " and "." to be recognized.
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=['.shield ', '.'], intents=intents)

# Dictionary to store active timers: {user_id: {"task": task_object, ...} or {custom_name: {"task": task_object, ...}}
active_timers = {}

def parse_time(time_input):
    """Converts a string like '1d 2h 30m' or '1h1m' into seconds."""
    seconds = 0
    matches = re.findall(r'(\d+)\s*([dhm])', time_input.lower())
    if not matches:
        return None

    for value, unit in matches:
        value = int(value)
        if unit == 'd':
            seconds += value * 86400
        elif unit == 'h':
            seconds += value * 3600
        elif unit == 'm':
            seconds += value * 60
    return seconds

async def run_timer(target_key, total_seconds, original_duration_str, author_id, channel_id, is_custom_name):
    """The main timer logic with 1 hour and 15 minute conditional warnings."""
    timer_start_time = time.time()
    warning_sent_1hr = False
    warning_sent_15min = False
    
    channel = bot.get_channel(channel_id)
    if not channel:
        print(f"Error: Channel with ID {channel_id} not found.")
        return

    author = bot.get_user(author_id)
    if not author:
        author_mention = ""
    else:
        author_mention = author.mention

    target_mention_str = ""
    if is_custom_name:
        target_mention_str = target_key.split(':')[1]  # Get the custom name part
    else:
        target_user = bot.get_user(target_key)
        target_mention_str = target_user.mention if target_user else "the target"

    try:
        while time.time() - timer_start_time < total_seconds:
            
            # Check for 1 hour warning
            if total_seconds > 3600 and not warning_sent_1hr and (total_seconds - (time.time() - timer_start_time)) <= 3600:
                await channel.send(
                    f"**⏳ 1-Hour Warning!** The shield for {target_mention_str} (set by {author_mention}) will expire in **1 hour**."
                )
                warning_sent_1hr = True

            # Check for 15 minute warning
            if total_seconds > 900 and not warning_sent_15min and (total_seconds - (time.time() - timer_start_time)) <= 900:
                await channel.send(
                    f"**🔥 15-Minute Warning!** The shield for {target_mention_str} (set by {author_mention}) will expire in **15 minutes**. Get ready!"
                )
                warning_sent_15min = True

            await asyncio.sleep(60) # Sleep for 60 seconds
        
        # Timer completion
        await channel.send(
            f"**🛡️ SHIELD DOWN!** The **{original_duration_str}** shield for {target_mention_str} (set by {author_mention}) has expired! Attack now!"
        )

    except asyncio.CancelledError:
        # Task was cancelled (by the .break command)
        pass 
    finally:
        # Clean up the active timer dictionary
        if target_key in active_timers:
            del active_timers[target_key]


# --- Bot Commands ---

@bot.command(name='set')
async def set_timer(ctx, duration: str, *, target: Optional[str] = None):
    """
    Sets a shield timer for a specified duration for yourself, a mentioned user, or a custom name.
    Usage: .shield set <duration> [@user | custom name]
    Example: .shield set 2h 30m @UserA
    """
    
    total_seconds = parse_time(duration)
    
    if total_seconds is None or total_seconds <= 0:
        await ctx.channel.send(
            f"{ctx.author.mention}, please provide a valid duration (e.g., `3d 12h 5m`)."
        )
        return

    if total_seconds > 604800: # Max 7 days
        await ctx.channel.send(
            f"{ctx.author.mention}, the maximum duration for a shield timer is 7 days."
        )
        return
    
    target_key = None
    target_mention_str = None
    is_custom_name = False

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
            # It's a custom name
            target_key = f"custom:{target.lower()}"
            target_mention_str = f"**{target}**"
            is_custom_name = True

    # If a timer is already active, cancel the old one before starting the new one
    if target_key in active_timers:
        active_timers[target_key]['task'].cancel()
        del active_timers[target_key]

    # Calculate completion time
    completion_time = datetime.datetime.now() + datetime.timedelta(seconds=total_seconds)
    timestamp = int(completion_time.timestamp())

    # Start the timer task
    timer_task = bot.loop.create_task(
        run_timer(target_key, total_seconds, duration, ctx.author.id, ctx.channel.id, is_custom_name)
    )
    
    # Store the task object
    active_timers[target_key] = {
        'task': timer_task,
        'channel_id': ctx.channel.id,
        'author_id': ctx.author.id,
        'target_mention_str': target_mention_str
    }

    # Confirmation message
    confirmation_message = (
        f"**✅ Shield Timer Set!**\n"
        f"A **{duration}** shield has been set for {target_mention_str} by {ctx.author.mention}.\n"
        f"It will be completed at: <t:{timestamp}:F>."
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
            target_key = f"custom:{target.lower()}"
            target_mention_str = f"**{target}**"


    if target_key in active_timers:
        active_timers[target_key]['task'].cancel()
        del active_timers[target_key]
        # Confirmation that it stopped
        await ctx.channel.send(f"✅ {ctx.author.mention} cancelled the shield timer for {target_mention_str}.")
    else:
        await ctx.channel.send(f"{ctx.author.mention}, there is no active shield timer for {target_mention_str}.")

@bot.command(name='check')
async def check_timer(ctx, *, target: Optional[str] = None):
    """Checks the status of the active timer for yourself, a mentioned user, or a custom name."""
    
    target_key = None
    target_mention_str = None
    
    if target is None:
        target_key = ctx.author.id
        target_mention_str = ctx.author.mention
    else:
        if ctx.message.mentions:
            mentioned_user = ctx.message.mentions[0]
            target_key = mentioned_user.id
            target_mention_str = mentioned_user.mention
        else:
            target_key = f"custom:{target.lower()}"
            target_mention_str = f"**{target}**"

    if target_key in active_timers:
        # The stored task object doesn't directly give the remaining time, 
        # but the logic in run_timer only sends the final message after the full duration.
        # For simplicity, we can only confirm it's active.
        await ctx.channel.send(f"**🟢 Active!** The shield timer for {target_mention_str} is currently active and counting down.")
    else:
        await ctx.channel.send(f"**🔴 Inactive.** There is no active shield timer for {target_mention_str}.")

@bot.command(name='dog')
async def dog_pic(ctx):
    """Pulls a random dog image from the Dog API."""
    try:
        response = requests.get('https://dog.ceo/api/breeds/image/random')
        response.raise_for_status() # Raise an exception for bad status codes
        data = response.json()
        
        if data['status'] == 'success':
            image_url = data['message']
            await ctx.channel.send(f"A random dog picture for you, {ctx.author.mention}! 🐶\n{image_url}")
        else:
            await ctx.channel.send("Sorry, I couldn't fetch a dog picture right now.")
    except requests.exceptions.RequestException as e:
        print(f"Error fetching dog picture: {e}")
        await ctx.channel.send("Sorry, I had trouble connecting to the image service.")


@bot.command(name='cat')
async def cat_pic(ctx):
    """Pulls a random cat image from the Cat API."""
    try:
        # Note: TheCatAPI returns an array of objects
        response = requests.get('https://api.thecatapi.com/v1/images/search')
        response.raise_for_status() # Raise an exception for bad status codes
        data = response.json()
        
        if data and isinstance(data, list) and 'url' in data[0]:
            image_url = data[0]['url']
            await ctx.channel.send(f"A random cat picture for you, {ctx.author.mention}! 🐱\n{image_url}")
        else:
            await ctx.channel.send("Sorry, I couldn't fetch a cat picture right now.")
    except requests.exceptions.RequestException as e:
        print(f"Error fetching cat picture: {e}")
        await ctx.channel.send("Sorry, I had trouble connecting to the image service.")


@bot.event
async def on_ready():
    print(f'Bot is ready and logged in as {bot.user}')

# Safely get the token from the environment variable
TOKEN = os.getenv("DISCORD_TOKEN")
if TOKEN is None:
    print("FATAL ERROR: DISCORD_TOKEN environment variable not set.")
else:
    bot.run(TOKEN)
