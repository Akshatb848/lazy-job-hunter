# Lazy Job Hunter: setup guide

About **20 minutes, once**. After that, every morning before 8 AM, Telegram gets the new jobs that fit you (up to 3). Some mornings there are none.

**You need:** a laptop (Windows 10/11 is easiest, Mac notes at the end) · Telegram on your phone · your resume as a PDF or Word file (a text PDF, not a scanned photo) · Google Chrome or Microsoft Edge.

Copy each command exactly. Lines in grey boxes are typed into PowerShell and run with **Enter**.

---

## Step 1. Install Python (5 min, skip if you have it)
1. Go to [python.org/downloads](https://www.python.org/downloads/) and install the latest Python 3.
2. On the first install screen, **tick "Add python.exe to PATH"**, then click Install.

## Step 2. Download Lazy Job Hunter (2 min)
1. Download **[the ZIP](https://github.com/Akshatb848/lazy-job-hunter/archive/refs/heads/main.zip)** and unzip it, for example to `Documents\lazy-job-hunter-main`.
2. Open that folder, click the address bar at the top, type `powershell` and press Enter. A blue/black PowerShell window opens **in that folder**.
3. Install the parts it needs:
   ```
   python -m pip install -r requirements.txt
   ```
   If it says `python` is not found, use `py` instead of `python` in every command of this guide.
4. Quick check (should end with `0 failed`):
   ```
   python test_guard.py
   ```

## Step 3. Get a free AI key (3 min)
The tool uses **Claude** if you add a Claude key, otherwise **NVIDIA** (free). You need at least one.

**NVIDIA (free):**
1. Sign in at [build.nvidia.com](https://build.nvidia.com), open any model, click **Get API Key**, and copy the key.
2. Save it (replace the text in quotes with your key):
   ```
   setx NVIDIA_API_KEY "paste-your-key-here"
   ```

**Claude (optional, better tailoring, paid per use):** create a key at [console.anthropic.com](https://console.anthropic.com) → API Keys, add a few dollars of credit, copy the key, then run `python save_anthropic_key.py`. It saves the key from your clipboard, checks it, and clears the clipboard. When the credit runs out, the tool switches to NVIDIA by itself.

Never paste a key into a chat, a comment or a screenshot.

## Step 4. Make your Telegram bot (4 min)
1. In Telegram, search **@BotFather** (blue tick) → tap Start → send `/newbot` → type any name → type a username ending in `bot` (for example `rahul_jobs_bot`).
2. BotFather sends a long token. Tap it to copy, then run:
   ```
   python save_token.py
   ```
3. In Telegram, open your new bot and press **Start** (or send "hi").
4. Run:
   ```
   python telegram_setup.py
   ```
   It finds your chat, saves it, and sends **"✅ Lazy Job Hunter is connected"** to your Telegram.

## Step 5. Turn your resume into a profile (2 min)
```
python make_profile.py "C:\Users\YOU\Downloads\your_resume.pdf" --roles "data analyst, business analyst" --cities "Bengaluru, Pune, Remote"
```
- Tip: drag your resume file into the PowerShell window to paste its full path.
- `--roles`: the job titles you want. Leave it out and it suggests roles from your resume.
- `--cities`: where you'd work.

It copies your resume word for word; any line it can't find exactly in your resume is dropped and listed. It prints the file it saved, like `profiles\rahul.json`. Open it once in Notepad and check it.

Want to try it before using your own resume? Use the fictional one: `python make_profile.py examples\sample_resume_fictional.pdf`

## Step 6. Your first run (3 min)
```
python jobhunter.py --profile profiles\rahul.json
```
(use the file name from step 5). The first run checks every open India job on the boards (about 10,000), picks up to 3 that fit, tailors a resume for each and sends everything to Telegram. **Your first matches are in your Telegram.** 🎉

From the next morning it looks only at jobs posted since the last run, so most days bring 0 or 1 match.

Before you apply: open the tailored PDF and read it. The reworded lines use only your facts, but you're the one sending it.

## Step 7. Every morning at 7:50 AM (1 min)
1. Open `daily_profiles.txt` in Notepad, replace the example line with your profile path (for example `profiles/rahul.json`) and save.
2. Run once:
   ```
   powershell -ExecutionPolicy Bypass -File install_schedule.ps1
   ```
Your laptop must be on or asleep (not shut down) at 7:50. If it was off, the run happens as soon as you start it.
To stop it any time: `Unregister-ScheduledTask -TaskName LazyJobHunter-Daily -Confirm:$false`

---

## ✅ Done? Tell me
DM **"DONE"** to **[@the_lazy_automator](https://www.instagram.com/the_lazy_automator/)** on Instagram with a screenshot of your first Telegram message, and star ⭐ the repo. It tells me the guide works, and I'll keep improving it.

## If something breaks
| You see | Fix |
|---|---|
| `python is not recognized` | Use `py` instead of `python`, or reinstall Python with "Add python.exe to PATH" ticked |
| `No AI key found` | Redo step 3, then open a new PowerShell window in the folder |
| `TELEGRAM_BOT_TOKEN is not set` | Redo step 4.2 (copy the token again first) |
| `Telegram rejected the token` | In BotFather: `/mybots` → your bot → API Token → copy, then `python save_token.py` |
| `No messages yet` | Open your bot in Telegram, press Start, then run `python telegram_setup.py` again |
| `Could not read enough text from the resume` | Export your resume again as a text PDF or Word file |
| `Profile not found` | Use the exact file name that step 5 printed |
| `Couldn't score today's jobs` | The AI service was busy or out of credit. It tries again tomorrow |
| `No strong matches today` | Normal on some days, especially for fresher roles. Add more `--roles` in step 5 |
| Resumes come as `.html` files | Install Google Chrome or Microsoft Edge |

Still stuck? Open an [issue](https://github.com/Akshatb848/lazy-job-hunter/issues/new) with the exact error (never your keys), or DM on Instagram.

## Mac
Steps 1 to 6 work the same in Terminal, with `python3` instead of `python` and `/` instead of `\` in paths. The key helpers (`save_token.py`, `save_anthropic_key.py`) are Windows-only, so on a Mac add your keys to `~/.zshrc` instead, then open a new Terminal:
```
export NVIDIA_API_KEY="your-key"
export TELEGRAM_BOT_TOKEN="token-from-botfather"
export TELEGRAM_CHAT_ID="number-printed-by-telegram_setup.py"
```
For the daily run, add this line with `crontab -e`:
```
50 7 * * * cd /path/to/lazy-job-hunter-main && python3 jobhunter.py --profile profiles/rahul.json
```

## Honest limits
- Jobs come from 83 free public company career boards (Greenhouse, Lever, Ashby, SmartRecruiters). It does not scrape LinkedIn or Naukri. They post about 20 new India jobs a day in total, so expect 0 to 3 matches a morning. Best for tech and software roles.
- Fresher roles are thinner on these boards; on a weak day it says so instead of padding the list.
- Scores are a guide, not a promise. No interviews are promised. Applying is still yours.
