# AI Tools Hub — Telegram Mini App Storefront

A gorgeous mobile-first storefront for the AI Tools Hub bot, as a Telegram Mini App (WebApp).
Single self-contained `index.html` — no backend, no API keys, no external API calls.
(The only external script is Telegram's official WebApp SDK, required for Mini App
integration; the app works fine in a normal browser without it.)

## Files

- `build.py` — reads `../data/tools.yaml`, applies the free-sample rule
  (first 3 tools per category are open; the rest are locked with **name + URL
  stripped at build time**), and generates `index.html` with the data embedded as JSON.
- `index.html` — generated output. Do not edit by hand; rebuild instead.

## Rebuild

```bash
cd ~/workspace/telegram-ai-hub/miniapp
python3 build.py
```

`build.py` asserts at the end that **no locked tool name or URL** appears in the
generated HTML (anti-Google rule). Rebuild after every 9 PM digest adds new tools,
or automate it.

## Host free on GitHub Pages

1. Create a new **public** GitHub repo, e.g. `ai-tools-hub-miniapp`.
2. Push the `miniapp/` contents (at minimum `index.html`):
   ```bash
   cd ~/workspace/telegram-ai-hub/miniapp
   git init && git add index.html README.md build.py
   git commit -m "AI Tools Hub mini app"
   git branch -M main
   git remote add origin https://github.com/<YOU>/ai-tools-hub-miniapp.git
   git push -u origin main
   ```
3. On GitHub: **Settings → Pages → Deploy from branch → `main` / `/ (root)` → Save.**
4. After ~1 minute the app is live at:
   `https://<YOU>.github.io/ai-tools-hub-miniapp/`

## Wire it to the bot

1. Save the Pages URL in the store config:
   ```bash
   python3 -c "
   import json
   p = '../data/store_config.json'
   c = json.load(open(p)); c['miniapp_url'] = 'https://<YOU>.github.io/ai-tools-hub-miniapp/'
   json.dump(c, open(p, 'w')); print('saved')
   "
   ```
2. In BotFather: open `@wahidaihunter_bot` → **Bot Settings → Menu Button →
   Configure menu button** → set the URL to the Pages URL (button text e.g. "🏪 Open Store").
   Every bot user then gets a persistent **🏪 Open Store** button that launches
   this Mini App.

## Notes

- Locked cards show "🔒 Premium Tool" + teaser only, with an **Unlock in Bot**
  button deep-linking to `https://t.me/wahidaihunter_bot`. Names/URLs of locked
  tools never reach the browser.
- Trial offers are public promos — names and links are shown, same as the bot.
- Dark charcoal + neon teal (`#00C9A7`) brand theme, mobile-first responsive grid.
