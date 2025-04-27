import discord
from discord import Intents
import os
import httpx
import difflib
import asyncio
from pathlib import Path
import hashlib
import re

# Blankebot by NorthernChicken: https://github.com/NorthernChicken/blankebot
# Downloads the HTML of the provided URL every day and sees if anything changes.
# If it does, it pings me on Discord.

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)
url = "https://www.creanlutheran.org/about/directory"

BASE_DIR = Path(__file__).parent
PAGE1_PATH = BASE_DIR / "page1.html"
PAGE2_PATH = BASE_DIR / "page2.html"
DIFF_PATH = BASE_DIR / "differences.txt"

delay = 5

# Normalize HTML and remove anti-bot scripts and other things
def normalize_html(html):
    html = html.replace('\r\n', '\n').replace('\r', '\n')
    html = re.sub(r'<!--[\s\S]*?-->', '', html)
    html = re.sub(
        r'<script>\(function\(\)\{function c\(\)\{var b=a\.contentDocument.*?</script>',
        '',
        html,
        flags=re.DOTALL
    )
    html = re.sub(r'nonce="[a-zA-Z0-9_-]+"', 'nonce=""', html)
    html = re.sub(
        r'window\.__CF\$cv\$params=\{r:.*?}',
        'window.__CF$cv$params={}',
        html
    )

    return html.strip()

async def download_page1():
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            response.raise_for_status()
            html = normalize_html(response.text)
            html_hash = hashlib.md5(html.encode('utf-8')).hexdigest()
            print(f"Downloaded page1: {response.status_code}, Hash: {html_hash}")
            with open(PAGE1_PATH, "w", encoding="utf-8", newline='\n') as page1:
                page1.write(html)
            file_size = PAGE1_PATH.stat().st_size
            print(f"Page1 file size: {file_size} bytes")
    except Exception as e:
        print(f"Error downloading page1: {e}")

async def download_page2():
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            response.raise_for_status()
            html = normalize_html(response.text)
            html_hash = hashlib.md5(html.encode('utf-8')).hexdigest()
            print(f"Downloaded page2: {response.status_code}, Hash: {html_hash}")
            with open(PAGE2_PATH, "w", encoding="utf-8", newline='\n') as page2:
                page2.write(html)
            file_size = PAGE2_PATH.stat().st_size
            print(f"Page2 file size: {file_size} bytes")
    except Exception as e:
        print(f"Error downloading page2: {e}")

def compare_pages(file1_path, file2_path, output_file):
    if not (file1_path.exists() and file2_path.exists()):
        print("Error: HTML files not found.")
        return False

    with open(file1_path, 'r', encoding='utf-8') as f1:
        file1_content = f1.read()
    with open(file2_path, 'r', encoding='utf-8') as f2:
        file2_content = f2.read()

    file1_hash = hashlib.md5(file1_content.encode('utf-8')).hexdigest()
    file2_hash = hashlib.md5(file2_content.encode('utf-8')).hexdigest()
    print(f"Page1 hash: {file1_hash}")
    print(f"Page2 hash: {file2_hash}")

    if file1_hash == file2_hash:
        print("Files are identical (same hash).")
        return True

    print(f"Page1 content length: {len(file1_content)} characters")
    print(f"Page2 content length: {len(file2_content)} characters")

    if not file1_content or not file2_content:
        print("Error: One or both files are empty.")
        return False

    file1_lines = file1_content.splitlines()
    file2_lines = file2_content.splitlines()

    differ = difflib.Differ()
    diff = list(differ.compare(file1_lines, file2_lines))

    # I was getting some fale-positives because of whitespace-only differences
    significant_diff = [line for line in diff if line.startswith(('- ', '+ ')) and line[2:].strip()]

    if not significant_diff:
        print("Files are identical (no significant changes).")
        return True

    print(f"Found {len(significant_diff)} significant differences.")
    print("Sample differences (first 5 lines):")
    for line in significant_diff[:5]:
        print(line)

    with open(output_file, 'w', encoding='utf-8', newline='\n') as f:
        f.write(f"Comparing {file1_path} and {file2_path}\n")
        f.write("Differences (lines starting with '-' are from page1, '+' from page2):\n\n")
        for line in significant_diff:
            f.write(line + '\n')

    print(f"Differences saved to {output_file}")
    return False

async def notify_on_change(changes):
    try:
        channel = client.get_channel(1365847730034970656)
        if not channel:
            print("Error: Text channel not found.")
            return

        await channel.send("@everyone A change was detected in the directory!")

        MAX_LENGTH = 1900
        print(f"Total changes length: {len(changes)} characters")
        if len(changes) <= MAX_LENGTH:
            await channel.send(f"```diff\n{changes}\n```")
        else:
            with open(DIFF_PATH, 'rb') as f:
                discord_file = discord.File(f, filename="differences.txt")
                await channel.send("Differences too long to display. Uploading file...", file=discord_file)

        print("Change detected! Pinging Discord...")
    except discord.errors.HTTPException as e:
        print(f"Discord API error: {e}")
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

        # Cycle pages
        if PAGE2_PATH.exists():
            if PAGE1_PATH.exists():
                PAGE1_PATH.unlink()
            PAGE2_PATH.rename(PAGE1_PATH)
            print("Moved page2 to page1 for next cycle")

@client.event
async def on_ready():
    print(f'Logged in as {client.user}')
    client.loop.create_task(main())

client.run("tokentokentoken")
