# Blankebot

Discord bot for detecting changes to the CLHS Staff Directory page. (https://www.creanlutheran.org/about/directory)

# Features

- Automatically downloads the site (both pages of constituents) on a delay
- Bypasses the site's built in Cloudflare anti-bot measures
- Compares the downloaded file with the file it downloaded last time
- Pings my Discord if it detects a change, reports the lines that were added or removed from the HTML
- Automatically reports any errors to the Discord
- Built in /status command which reports bot uptime, when it last checked and when it will check next, and the current page HTML's hash
