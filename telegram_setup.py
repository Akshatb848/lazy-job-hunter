"""Telegram setup check for Lazy Job Hunter. Never prints the bot token.

1. Set TELEGRAM_BOT_TOKEN (from @BotFather) as a user environment variable.
2. Send any message (e.g. "hi") to your bot in Telegram.
3. Run: python telegram_setup.py
   It shows the bot's name and the chat ID of whoever messaged it.
4. Set TELEGRAM_CHAT_ID to your chat ID, then run this again: it sends a test message.
"""
import json, sys, urllib.request

from jobhunter import env

sys.stdout.reconfigure(encoding='utf-8')


def call(token, method, data=None):
    url = f'https://api.telegram.org/bot{token}/{method}'
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return json.loads(e.read() or b'{}') or {'ok': False, 'description': str(e.code)}


token = env('TELEGRAM_BOT_TOKEN')
if not token:
    sys.exit('TELEGRAM_BOT_TOKEN is not set yet (step 1).')

me = call(token, 'getMe')
if not me.get('ok'):
    sys.exit(f"Telegram rejected the token: {me.get('description')}. Copy it again from @BotFather.")
print(f"Bot OK: @{me['result']['username']}")

chat = env('TELEGRAM_CHAT_ID')
if chat:
    r = call(token, 'sendMessage', {'chat_id': chat, 'text': 'Lazy Job Hunter is connected. Your top 3 jobs will arrive here.'})
    print('Test message sent. Check Telegram.' if r.get('ok') else f"Send failed: {r.get('description')}")
    sys.exit(0 if r.get('ok') else 1)

ups = call(token, 'getUpdates').get('result', [])
chats = {}
for u in ups:
    m = u.get('message') or u.get('edited_message') or {}
    c = m.get('chat')
    if c:
        chats[c['id']] = c.get('first_name') or c.get('title') or c.get('username') or c.get('type')
if not chats:
    print(f"No messages yet. Open Telegram, find @{me['result']['username']}, press Start or send 'hi', then run this again.")
else:
    for cid, name in chats.items():
        print(f'Chat ID for {name}: {cid}')
    print('Set TELEGRAM_CHAT_ID to that number, then run this again to send a test message.')
