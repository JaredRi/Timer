import discord
from discord.ext import commands
import asyncio
import re
import datetime
import time 
import os
from typing import Optional # Import Optional type hint

# Set up the bot with necessary intents and command prefix
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='.shield ', intents=intents)

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
    timer_data = active_timers.get(target_key)
    if not timer_data: return

    channel = bot.get_channel(channel_id)
    author_mention = f"<@{author_id}>"
    target_mention_str = timer_data.get('target_mention_str', 'A timer target') # Fallback if error

    warning_1hr_time = 60 * 60
    warning_15min_time = 15 * 60
    time_until_next_event = total_seconds

    try:
        # 1 Hour Warning
        if total_seconds > (warning_1hr_time + warning_15min_time):
            await asyncio.sleep(total_seconds - warning_1hr_time)
            if target_key in active_timers:
                await channel.send(
                    f"⏰ **1 hour remaining** for the shield for {target_mention_str} (set by {author_mention} for {original_duration_str})."
                )
                time_until_next_event = warning_1hr_time

        # 15 Minute Warning
        if time_until_next_event > warning_15min_time:
            await asyncio.sleep(time_until_next_event - warning_15min_time)
            if target_key in active_timers:
                await channel.send(
                    f"⏰ **15 minutes remaining** for the shield for {target_mention_str} (set by {author_mention} for {original_duration_str})."
                )
                time_until_next_event = warning_15min_time
            else:
                return

        # Final Reminder
        await asyncio.sleep(time_until_next_event)

        if target_key in active_timers:
            await channel.send(
                f"⏰ **Reminder finished!** The shield for {target_mention_str} (set by {author_mention}) is now over."
            )
            del active_timers[target_key]

    except asyncio.CancelledError:
        pass


@bot.command(name='set')
async def set_timer(ctx, time_input: str, *, target: Optional[str] = None):
    """Starts or overwrites a timer. Use: .shield set <time> [@user or Custom Name]"""
    seconds = parse_time(time_input)

    if seconds is None or seconds <= 0:
        await ctx.channel.send("Please provide a valid time format (e.g., `1d 2h 30m`).")
        return

    is_custom_name = False
    target_key = None
    target_mention_str = None

    if target is None:
        # Default to the command author
        target_key = ctx.author.id
        target_mention_str = ctx.author.mention
    else:
        # Check if the input is a user mention or nickname mention
        if ctx.message.mentions:
            mentioned_user = ctx.message.mentions[0]
            target_key = mentioned_user.id
            target_mention_str = mentioned_user.mention
        else:
            # It's a custom name
            is_custom_name = True
            target_key = f"custom:{target.lower()}" # Prefix to avoid ID collisions
            target_mention_str = f"**{target}**"

    # Cancel any existing timer for this key/ID
    if target_key in active_timers:
        active_timers[target_key]['task'].cancel()
        await ctx.channel.send(f"⏰ {ctx.author.mention}, the previous shield timer for {target_mention_str} was overwritten.")

    # Store necessary data in the dictionary
    task = asyncio.create_task(run_timer(target_key, seconds, time_input, ctx.author.id, ctx.channel.id, is_custom_name))
    active_timers[target_key] = {
        "task": task,
        "channel_id": ctx.channel.id,
        "author_id": ctx.author.id,
        "original_duration_str": time_input,
        "target_mention_str": target_mention_str,
    }

    # Confirmation Message
    future_time = datetime.datetime.now() + datetime.timedelta(seconds=seconds)
    timestamp = int(time.mktime(future_time.timetuple()))
    
    confirmation_message = (
        f"⏰ {ctx.author.mention} set a shield timer for {target_mention_str} for **{time_input}**."
        f"\nIt will be completed at: <t:{timestamp}:F>."
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
        await ctx.channel.send(f"{ctx.author.mention}, I couldn't find an active shield timer for {target_mention_str}.")


@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name} (ID: {bot.user.id})')


# --- START OF MODIFIED/ADDED SECTION ---
# Get the token from the environment variable (securely)
TOKEN = os.getenv("DISCORD_TOKEN") 

if not TOKEN:
    print("--------------------------------------------------------------------------------")
    print("ERROR: The DISCORD_TOKEN environment variable is not set.")
    print("Please set it in your environment (for local use) or in Railway's Variables tab.")
    print("--------------------------------------------------------------------------------")
else:
    try:
        bot.run(TOKEN)
    except discord.errors.LoginFailure:
        print("ERROR: Failed to log in. Check if your DISCORD_TOKEN is correct and has the 'Bot' scope.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
# --- END OF MODIFIED/ADDED SECTION ---

