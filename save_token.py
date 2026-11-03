"""Save the Telegram bot token from your clipboard as a Windows user variable. Never prints it.

Copy the token in Telegram (BotFather > your bot > API Token > tap to copy), then run:
  python save_token.py
"""
import json, re, subprocess, sys, urllib.request, winreg

sys.stdout.reconfigure(encoding='utf-8')
tok = subprocess.run(['powershell', '-NoProfile', '-Command', 'Get-Clipboard'], capture_output=True, text=True).stdout.strip()
if not re.fullmatch(r'\d{6,12}:[A-Za-z0-9_-]{30,}', tok):
    sys.exit('The clipboard does not hold a bot token. Copy it from BotFather and run this again.')
try:
    with urllib.request.urlopen(f'https://api.telegram.org/bot{tok}/getMe', timeout=30) as r:
        me = json.load(r)['result']
except Exception:
    sys.exit('Telegram rejected this token. Copy it again from BotFather.')
with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Environment', 0, winreg.KEY_SET_VALUE) as k:
    winreg.SetValueEx(k, 'TELEGRAM_BOT_TOKEN', 0, winreg.REG_SZ, tok)
subprocess.run(['powershell', '-NoProfile', '-Command', 'Set-Clipboard -Value " "'])  # clear the token from the clipboard
print(f"Saved. Token for @{me['username']} is stored as TELEGRAM_BOT_TOKEN (clipboard cleared).")
