import discord
from discord import Intents, app_commands
import os
import difflib
import asyncio
from pathlib import Path
import hashlib
import re
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from datetime import datetime, timedelta
import time

# Blankebot by NorthernChicken: https://github.com/NorthernChicken/blankebot
# Uses Playwright to download HTML of pages 1 and 2, combines them, and checks for changes.
# If changes are detected, it pings on Discord. Errors are sent to Discord.
# Added /status command to show bot stats.

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)
bot = app_commands.CommandTree(client)

url = "https://www.creanlutheran.org/about/directory"

BASE_DIR = Path(__file__).parent
PAGE1_PATH = BASE_DIR / "page1.html"
PAGE2_PATH = BASE_DIR / "page2.html"
DIFF_PATH = BASE_DIR / "differences.txt"

delay = 5

# Stats tracking
start_time = time.time()
last_check_time = None
total_checks = 0
changes_detected = 0
last_error = None
last_check_success = True
current_page_hash = None

def get_uptime():
    uptime_seconds = int(time.time() - start_time)
    days, remainder = divmod(uptime_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{days}d {hours}h {minutes}m {seconds}s"

async def send_error_to_discord(error_message):
    global last_error
    last_error = error_message
    try:
        channel = client.get_channel(1365847730034970656)
        if not channel:
            print("Error: Text channel not found for sending error.")
            return
        await channel.send(f"⚠️ Error in blankebot: {error_message}")
        print("Error sent to Discord.")
    except discord.errors.HTTPException as e:
        print(f"Discord API error while sending error: {e}")
    except Exception as e:
        print(f"Error sending error to Discord: {e}")

# Normalize HTML and remove anti-bot scripts and other things
def normalize_html(html):
    soup = BeautifulSoup(html, 'html.parser')
    constituents = soup.find_all('div', class_='fsConstituentItem')
    print(f"Found {len(constituents)} constituents in HTML")
    if not constituents:
        error_message = "No constituents found in HTML."
        print(f"Warning: {error_message}")
        asyncio.create_task(send_error_to_discord(error_message))
        return ""
    seen_ids = set()
    unique_constituents = []
    for c in constituents:
        link = c.find('a', class_='fsConstituentProfileLink')
        if link and 'data-constituent-id' in link.attrs:
            cid = link['data-constituent-id']
            if cid not in seen_ids:
                seen_ids.add(cid)
                unique_constituents.append(c)
    print(f"After deduplication: {len(unique_constituents)} unique constituents")
    html = '\n'.join(str(c) for c in unique_constituents)
    html = html.replace('\r\n', '\n').replace('\r', '\n')
    html = re.sub(r'<!--[\s\S]*?-->', '', html)
    html = re.sub(r'nonce="[a-zA-Z0-9_-]+"', 'nonce=""', html)
    html = re.sub(
        r'<script>\(function\(\)\{function c\(\)\{var b=a\.contentDocument.*?</script>',
        '',
        html,
        flags=re.DOTALL
    )
    html = re.sub(
        r'window\.__CF\$cv\$params=\{r:.*?}',
        'window.__CF$cv$params={}',
        html
    )
    return html.strip()

async def download_page1():
    global last_check_time, total_checks, last_check_success, current_page_hash
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                viewport={"width": 1280, "height": 720}
            )
            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_selector('div.fsElementPagination', timeout=10000)
            pagination = await page.query_selector('div.fsElementPagination')
            if pagination:
                pagination_html = await page.evaluate('(element) => element.outerHTML', pagination)
                print(f"Pagination HTML: {pagination_html[:500]}...")
            else:
                error_message = "Pagination div not found."
                print(f"Warning: {error_message}")
                await send_error_to_discord(error_message)
            html1 = normalize_html(await page.content())
            print(f"Downloaded page1 (page 1): {len(html1)} chars, {html1[:100]}...")
            if not html1:
                error_message = "No constituents found on page 1."
                print(f"Error: {error_message}")
                await send_error_to_discord(error_message)
                with open(PAGE1_PATH, "w", encoding="utf-8", newline='\n') as page1:
                    page1.write(html1)
                await browser.close()
                return

            selectors = [
                'a.fsNextPageLink',
                'a.fsPageLink[data-page="2"]',
                'a.fsPaginationLabel[data-page="2"]',
                'a[data-page="2"]',
                'li.fsPageItem a[data-page="2"]'
            ]
            html2 = ""
            for selector in selectors:
                try:
                    print(f"Trying selector: {selector}")
                    await page.click(selector, timeout=15000)
                    await page.wait_for_selector('div.fsConstituentItem', timeout=10000)
                    await asyncio.sleep(3)
                    html2 = normalize_html(await page.content())
                    print(f"Downloaded page1 (page 2): {len(html2)} chars, {html2[:100]}...")
                    if html2:
                        break
                except Exception as e:
                    error_message = f"Failed to click selector {selector}: {str(e)}"
                    print(f"Error with selector {selector}: {e}")
                    await send_error_to_discord(error_message)
                    continue

            if not html2:
                error_message = "Failed to load page 2 with any selector."
                print(f"Error: {error_message}")
                await send_error_to_discord(error_message)
                with open(PAGE1_PATH, "w", encoding="utf-8", newline='\n') as page1:
                    page1.write(html1)
                await browser.close()
                return

            combined_html = html1 + '\n' + html2
            current_page_hash = hashlib.md5(combined_html.encode('utf-8')).hexdigest()
            print(f"Combined page1 hash: {current_page_hash}")
            print(f"Combined page1 preview: {combined_html[:100]}...")
            print(f"Combined page1 length: {len(combined_html)} chars")

            with open(PAGE1_PATH, "w", encoding="utf-8", newline='\n') as page1:
                page1.write(combined_html)
            file_size = PAGE1_PATH.stat().st_size
            print(f"Page1 file size: {file_size} bytes")
            await browser.close()
        last_check_time = datetime.utcnow()
        total_checks += 1
        last_check_success = True
    except Exception as e:
        last_check_success = False
        error_message = f"Error downloading page1: {str(e)}"
        print(f"Error downloading page1: {e}")
        await send_error_to_discord(error_message)

async def download_page2():
    global last_check_time, total_checks, last_check_success, current_page_hash
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                viewport={"width": 1280, "height": 720}
            )
            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_selector('div.fsElementPagination', timeout=10000)
            pagination = await page.query_selector('div.fsElementPagination')
            if pagination:
                pagination_html = await page.evaluate('(element) => element.outerHTML', pagination)
                print(f"Pagination HTML: {pagination_html[:500]}...")
            else:
                error_message = "Pagination div not found."
                print(f"Warning: {error_message}")
                await send_error_to_discord(error_message)
            html1 = normalize_html(await page.content())
            print(f"Downloaded page2 (page 1): {len(html1)} chars, {html1[:100]}...")
            if not html1:
                error_message = "No constituents found on page 1."
                print(f"Error: {error_message}")
                await send_error_to_discord(error_message)
                with open(PAGE2_PATH, "w", encoding="utf-8", newline='\n') as page2:
                    page2.write(html1)
                await browser.close()
                return

            selectors = [
                'a.fsNextPageLink',
                'a.fsPageLink[data-page="2"]',
                'a.fsPaginationLabel[data-page="2"]',
                'a[data-page="2"]',
                'li.fsPageItem a[data-page="2"]'
            ]
            html2 = ""
            for selector in selectors:
                try:
                    print(f"Trying selector: {selector}")
                    await page.click(selector, timeout=15000)
                    await page.wait_for_selector('div.fsConstituentItem', timeout=10000)
                    await asyncio.sleep(3)
                    html2 = normalize_html(await page.content())
                    print(f"Downloaded page2 (page 2): {len(html2)} chars, {html2[:100]}...")
                    if html2:
                        break
                except Exception as e:
                    error_message = f"Failed to click selector {selector}: {str(e)}"
                    print(f"Error with selector {selector}: {e}")
                    await send_error_to_discord(error_message)
                    continue

            if not html2:
                error_message = "Failed to load page 2 with any selector."
                print(f"Error: {error_message}")
                await send_error_to_discord(error_message)
                with open(PAGE2_PATH, "w", encoding="utf-8", newline='\n') as page2:
                    page2.write(html1)
                await browser.close()
                return

            combined_html = html1 + '\n' + html2
            current_page_hash = hashlib.md5(combined_html.encode('utf-8')).hexdigest()
            print(f"Combined page2 hash: {current_page_hash}")
            print(f"Combined page2 preview: {combined_html[:100]}...")
            print(f"Combined page2 length: {len(combined_html)} chars")

            with open(PAGE2_PATH, "w", encoding="utf-8", newline='\n') as page2:
                page2.write(combined_html)
            file_size = PAGE2_PATH.stat().st_size
            print(f"Page2 file size: {file_size} bytes")
            await browser.close()
        last_check_time = datetime.utcnow()
        total_checks += 1
        last_check_success = True
    except Exception as e:
        last_check_success = False
        error_message = f"Error downloading page2: {str(e)}"
        print(f"Error downloading page2: {e}")
        await send_error_to_discord(error_message)

def compare_pages(file1_path, file2_path, output_file):
    global changes_detected
    if not (file1_path.exists() and file2_path.exists()):
        error_message = "HTML files not found for comparison."
        print(f"Error: {error_message}")
        asyncio.create_task(send_error_to_discord(error_message))
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
        error_message = "One or both HTML files are empty."
        print(f"Error: {error_message}")
        asyncio.create_task(send_error_to_discord(error_message))
        return False

    file1_lines = file1_content.splitlines()
    file2_lines = file2_content.splitlines()

    print("Page1 first 5 lines:", file1_lines[:5])
    print("Page2 first 5 lines:", file2_lines[:5])

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
    changes_detected += 1
    return False

async def notify_on_change(changes):
    try:
        channel = client.get_channel(1365847730034970656)
        if not channel:
            error_message = "Text channel not found for notification."
            print(f"Error: {error_message}")
            await send_error_to_discord(error_message)
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
        error_message = f"Discord API error during notification: {str(e)}"
        print(f"Discord API error: {e}")
        await send_error_to_discord(error_message)
    except Exception as e:
        error_message = f"Error notifying on change: {str(e)}"
        print(f"Error notifying on change: {e}")
        await send_error_to_discord(error_message)

async def main():
    while True:
        await download_page1()
        while True:
            await asyncio.sleep(delay)
            await download_page2()
            no_changes = compare_pages(PAGE1_PATH, PAGE2_PATH, DIFF_PATH)
            print(f"No changes: {no_changes}")

            if not no_changes and DIFF_PATH.exists():
                with open(DIFF_PATH, 'r', encoding='utf-8') as diff:
                    changes = diff.read()
                await notify_on_change(changes)

            if PAGE2_PATH.exists():
                if PAGE1_PATH.exists():
                    PAGE1_PATH.unlink()
                PAGE2_PATH.rename(PAGE1_PATH)
                print("Moved page2 to page1 for next cycle")

@client.event
async def on_ready():
    print(f'Logged in as {client.user}')
    try:
        synced = await bot.sync(guild=None)
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Error syncing commands: {e}")
    client.loop.create_task(main())

@bot.command(name="status", description="Get the current status and stats of the bot.")
async def status(interaction: discord.Interaction):
    await interaction.response.defer()  # Defer response since this might take a moment
    embed = discord.Embed(title="📊 Blankebot Status", color=discord.Color.blue())

    # Uptime
    embed.add_field(name="Uptime", value=get_uptime(), inline=False)

    # Last Check Time
    if last_check_time:
        last_check_str = last_check_time.strftime("%Y-%m-%d %H:%M:%S UTC")
        time_since_last = (datetime.utcnow() - last_check_time).total_seconds()
        time_since_str = f"{int(time_since_last // 3600)}h {int((time_since_last % 3600) // 60)}m {int(time_since_last % 60)}s ago"
        embed.add_field(name="Last Check", value=f"{last_check_str} ({time_since_str})", inline=False)
    else:
        embed.add_field(name="Last Check", value="Not yet checked", inline=False)

    # Next Check Time
    if last_check_time:
        next_check = last_check_time + timedelta(seconds=delay)
        if datetime.utcnow() < next_check:
            next_check_str = next_check.strftime("%Y-%m-%d %H:%M:%S UTC")
            time_until_next = (next_check - datetime.utcnow()).total_seconds()
            time_until_str = f"in {int(time_until_next // 60)}m {int(time_until_next % 60)}s"
            embed.add_field(name="Next Check", value=f"{next_check_str} ({time_until_str})", inline=False)
        else:
            embed.add_field(name="Next Check", value="Checking now...", inline=False)
    else:
        embed.add_field(name="Next Check", value="Soon...", inline=False)

    # Total Checks
    embed.add_field(name="Total Checks", value=str(total_checks), inline=True)

    # Changes Detected
    embed.add_field(name="Changes Detected", value=str(changes_detected), inline=True)

    # Current Page Hash
    if current_page_hash:
        embed.add_field(name="Current Page Hash", value=current_page_hash[:10] + "...", inline=True)
    else:
        embed.add_field(name="Current Page Hash", value="N/A", inline=True)

    # Last Check Status
    if last_check_time:
        status_str = "Success" if last_check_success else "Failed"
        embed.add_field(name="Last Check Status", value=status_str, inline=True)

    # Last Error
    if last_error:
        embed.add_field(name="Last Error", value=last_error[:100] + "..." if len(last_error) > 100 else last_error, inline=False)
    else:
        embed.add_field(name="Last Error", value="None", inline=False)

    embed.set_footer(text=f"Bot started at {datetime.utcfromtimestamp(start_time).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    await interaction.followup.send(embed=embed)

client.run("tokentokentoken")
