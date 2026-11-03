"""Save your Anthropic API key from the clipboard as a Windows user variable. Never prints the key.

Copy the key in console.anthropic.com (Settings > API Keys), then run:
  python save_anthropic_key.py
It checks the key works and that the account can run a request (has credits) before saving.
"""
import re, subprocess, sys, winreg

sys.stdout.reconfigure(encoding='utf-8')
KEY_RE = r'sk-ant-[A-Za-z0-9_\-]{20,}'
key = subprocess.run(['powershell', '-NoProfile', '-Command', 'Get-Clipboard'], capture_output=True, text=True).stdout.strip()
if not re.fullmatch(KEY_RE, key) or len(key) < 80:  # < 80 chars = the shortened preview, not the real key
    import getpass
    print('No Anthropic key found on the clipboard (copying inside some browser panes never reaches Windows).')
    key = getpass.getpass('Paste the key here and press Enter (right-click pastes; nothing is shown): ').strip()
    if not re.fullmatch(KEY_RE, key) or len(key) < 80:
        hint = (' That looks like the shortened preview from the keys list. The full key (~100 characters) is shown only once,'
                ' in the pop-up right after "Create Key"; create a new key and copy it from that pop-up.') if len(key) < 80 else ''
        sys.exit(f'That is not a full Anthropic API key (got {len(key)} characters).{hint} Nothing was saved.')

import anthropic
client = anthropic.Anthropic(api_key=key, max_retries=1, timeout=60.0)
try:
    # test on the model the job hunter actually uses, so promotional credits limited to some models are caught here
    client.messages.create(model='claude-opus-5-5', max_tokens=256, output_config={'effort': 'low'},
                           messages=[{'role': 'user', 'content': 'Reply OK'}])
    status = 'works, and the account has credits'
except anthropic.AuthenticationError:
    sys.exit('Anthropic rejected this key. Copy it again from console.anthropic.com.')
except anthropic.BadRequestError as e:
    if re.search(r'credit balance|billing|purchase credits', str(e), re.I):
        status = 'is valid but the account has NO credits yet; the job hunter will use NVIDIA until you add credits'
    else:
        status = 'is valid (test request returned: %s)' % str(e)[:80]
with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Environment', 0, winreg.KEY_SET_VALUE) as k:
    winreg.SetValueEx(k, 'ANTHROPIC_API_KEY', 0, winreg.REG_SZ, key)
subprocess.run(['powershell', '-NoProfile', '-Command', 'Set-Clipboard -Value " "'])
print(f'Saved as ANTHROPIC_API_KEY (clipboard cleared). The key {status}.')
