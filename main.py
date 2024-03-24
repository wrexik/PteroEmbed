import asyncio
import discord
from discord.ext import commands
import requests
import os
import configparser
from datetime import datetime

config = configparser.ConfigParser()

# Ensure config file exists
if not os.path.exists('config.ini'):
    config['Discord'] = {
        'token': 'your_dc_bot_token',
        'channel_id': 'your_discord_channel_for_status_information',
        'alert_channel_id': 'your_alert_channel'
    }
    config['Pterodactyl'] = {
        'api_url': 'your_panel_url',
        'api_key': 'your_pterodactyl_user_api_key',
        'server_ids': 'your_server_ids_separated_by_coma'
    }
    config['Settings'] = {
        'refresh_interval': '300 #default is 300 seconds (five minutes)',
        'note': 'Please delete all #comments before continuing :)'
    }
    with open('config.ini', 'w') as configfile:
        config.write(configfile)
else:
    config.read('config.ini')

TOKEN = config['Discord']['token']
DISCORD_CHANNEL_ID = int(config['Discord']['channel_id'])
ALERT_CHANNEL_ID = int(config['Discord']['alert_channel_id'])  # Get alert channel ID from config

PTERODACTYL_API_URL = config['Pterodactyl']['api_url']
PTERODACTYL_API_KEY = config['Pterodactyl']['api_key']
SERVER_IDS = config['Pterodactyl']['server_ids'].split(',')  # Split comma-separated server IDs

refresh_interval = config['Settings']['refresh_interval']

intents = discord.Intents.default()
intents.typing = False
intents.presences = False
intents.members = False

bot = commands.Bot(command_prefix='/', intents=intents)


async def fetch_server_stats(server_id):
    url = f"{PTERODACTYL_API_URL}/api/client/servers/{server_id}/resources"
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {PTERODACTYL_API_KEY}'
    }
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            print(f"Successfully fetched data for server ID: {server_id}")
            return response.json()['attributes']  # Returns attributes of the server stats
        else:
            print(f"Failed to fetch data for server ID: {server_id}. Status code: {response.status_code}")
            return None
    except Exception as e:
        print(f"Error fetching data for server ID: {server_id}. Exception: {e}")
        return None


async def fetch_server_info(server_id):
    url = f"{PTERODACTYL_API_URL}/api/client/servers/{server_id}"
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {PTERODACTYL_API_KEY}'
    }
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            print(f"Successfully fetched info for server ID: {server_id}")
            attributes = response.json().get('attributes')
            if attributes:
                return attributes.get('name')  # Returns server name
            else:
                print(f"Attributes not found for server ID: {server_id}")
                return None
        else:
            print(f"Failed to fetch info for server ID: {server_id}. Status code: {response.status_code}")
            return None
    except Exception as e:
        print(f"Error fetching info for server ID: {server_id}. Exception: {e}")
        return None


async def update_status():
    await asyncio.sleep(5)  # Initial sleep to ensure bot is ready

    channel = bot.get_channel(DISCORD_CHANNEL_ID)
    alert_channel = bot.get_channel(ALERT_CHANNEL_ID)  # Get the alert channel

    previous_messages = load_previous_messages()
    servers_down = {}  # Change to store downtime start time
    counter = 0

    while True:
        try:
            for server_id in SERVER_IDS:
                server_stats = await fetch_server_stats(server_id)
                server_name = await fetch_server_info(server_id)

                if server_stats and server_name:
                    online_status = "🟢 Online" if server_stats['current_state'] == "running" else "🔴 Offline"
                    color = 0x00ff00 if server_stats['current_state'] == "running" else 0xff0000
                    cpu_usage = server_stats['resources']['cpu_absolute']
                    ram_usage = round(server_stats['resources']['memory_bytes'] / (1024 * 1024),
                                      2)  # Round to 2 decimal places and convert to MB
                    disk_usage = round(server_stats['resources']['disk_bytes'] / (1024 * 1024),
                                       2)  # Round to 2 decimal places and convert to MB

                    embed_description = f"Server: {server_name}\nStatus: {online_status}\nDisk Usage: {disk_usage} MB\nCPU Usage: {cpu_usage}%\nRAM Usage: {ram_usage} MB\nCredits: Made with love by Wrexik"

                    if server_stats['current_state'] != "running":
                        if server_id not in servers_down:
                            async with channel.typing():  # Indicate bot typing
                                servers_down[server_id] = datetime.now()  # Record downtime start time
                                alert_delay = int(refresh_interval) * 5
                                info = f"Server {server_name} down! Another alert in {alert_delay} seconds!"
                                log = f"[{datetime.now()}]: {info}"
                                add_to_log(log)
                                await alert_channel.send(log)  # Send alert message to the alert channel

                    if server_id in previous_messages:  # Edit existing message if present
                        message_id = previous_messages[server_id]
                        async with channel.typing():  # Indicate bot typing
                            message = await channel.fetch_message(message_id)
                            embed = discord.Embed(title='Server Status', description=embed_description, color=color)
                            await message.edit(embed=embed)
                    else:  # Send new message if not present
                        async with channel.typing():  # Indicate bot typing
                            embed = discord.Embed(title='Server Status', description=embed_description, color=color)
                            message = await channel.send(embed=embed)
                            previous_messages[server_id] = message.id
                            save_previous_messages(previous_messages)
                else:
                    print(f"No data fetched for server ID: {server_id}")

            counter += 1
            if counter >= 5:
                servers_down.clear()
                counter = 0

        except Exception as e:
            print(f'Error updating status: {e}')

        await asyncio.sleep(int(refresh_interval))


def load_previous_messages():
    previous_messages = {}
    if os.path.exists("message_ids.txt"):
        with open("message_ids.txt", 'r') as file:
            lines = file.readlines()
            for line in lines:
                server_id, message_id = line.strip().split(',')
                previous_messages[server_id] = int(message_id)
    return previous_messages


def save_previous_messages(previous_messages):
    with open("message_ids.txt", 'w') as file:
        for server_id, message_id in previous_messages.items():
            file.write(f"{server_id},{message_id}\n")

def add_to_log(text):
    # Get the current date
    current_date = datetime.now().strftime("%Y-%m-%d")
    
    # Construct the log file name
    log_file_name = f"log_{current_date}.txt"
    
    # Check if the log file exists, create it if not
    if not os.path.exists(log_file_name):
        print(f"Creating log file: {log_file_name}")
        with open(log_file_name, "w") as log_file:
            log_file.write(f"{datetime.now()} - Log file created\n")
    
    # Append the log message to the file
    with open(log_file_name, "a") as log_file:
        log_file.write(f"{text}\n")
        log_file.flush()  # Ensure immediate write to file
        print(f"Added to log: {text}")


@bot.event
async def on_ready():
    print(f'We have logged in as {bot.user}')
    asyncio.create_task(update_status())

bot.run(TOKEN)