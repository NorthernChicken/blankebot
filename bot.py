import discord
from discord import Intents
import os
import httpx
import difflib
import asyncio
from pathlib import Path

# Blankebot by NorthernChicken: https://github.com/NorthernChicken/blankebot
# Downloads the HTML of the provided URL every day and sees if anything changes.
# If it does, it pings me on Discord.

intents = discord.Intents.default()
intents.members = True
intents.guilds = True
client = discord.Client(intents=intents)

url = "https://www.creanlutheran.org/about/directory"

BASE_DIR = Path(__file__).parent
PAGE1_PATH = BASE_DIR / "page1.html"
PAGE2_PATH = BASE_DIR / "page2.html"
DIFF_PATH = BASE_DIR / "differences.txt"

# Time between webpage checks in seconds
delay = (5)

async def download_page1():
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            response.raise_for_status()
            print(f"Downloaded page1: {response.status_code}")
            with open(PAGE1_PATH, "w", encoding="utf-8") as page1:
                page1.write(response.text)
    except Exception as e:
        print(f"Error downloading page1: {e}")

async def download_page2():
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            response.raise_for_status()
            print(f"Downloaded page2: {response.status_code}")
            with open(PAGE2_PATH, "w", encoding="utf-8") as page2:
                page2.write(response.text)
    except Exception as e:
        print(f"Error downloading page2: {e}")

def compare_pages(file1_path, file2_path, output_file):
    if not (file1_path.exists() and file2_path.exists()):
        print("Error: HTML files not found.")
        return False

    with open(file1_path, 'r', encoding='utf-8') as f1, \
         open(file2_path, 'r', encoding='utf-8') as f2:
        file1_lines = f1.readlines()
        file2_lines = f2.readlines()

    differ = difflib.Differ()
    diff = list(differ.compare(file1_lines, file2_lines))

    if not any(line.startswith(('- ', '+ ')) for line in diff):
        print("Files are identical.")
        return True

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(f"Comparing {file1_path} and {file2_path}\n")
        f.write("Differences (lines starting with '-' are from page1, '+' from page2):\n\n")
        for line in diff:
            if line.startswith(('- ', '+ ')):
                f.write(line)

    print(f"Differences saved to {output_file}")
    return False

async def notify_on_change(changes):
    try:
        channel = client.get_channel(1365847730034970656)
        if channel:
            await channel.send("@everyone A change was detected in the directory!")
            await channel.send(f"```diff\n{changes}\n```")
            print("Change detected! Pinging Discord...")
        else:
            print("Error: Text channel not found.")
    except Exception as e:
        print(f"Error notifying on change: {e}")

async def main():
    await download_page1()
    while True:
        await asyncio.sleep(delay)

        await download_page2()
        no_changes = compare_pages(PAGE1_PATH, PAGE2_PATH, DIFF_PATH)
        print(f"No changes: {no_changes}")

        if not no_changes:
            with open(DIFF_PATH, 'r', encoding='utf-8') as diff:
                changes = diff.read()
            await notify_on_change(changes)
        # Move page2 to page1 for the next cycle
        if PAGE2_PATH.exists():
            PAGE2_PATH.rename(PAGE1_PATH)


@client.event
async def on_ready():
    print(f'Logged in as {client.user}')
    client.loop.create_task(main())

# Replace 'YOUR_TOKEN' with your actual bot token
client.run("")
