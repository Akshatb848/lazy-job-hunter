# Lazy Job Hunter: setup guide

Every morning before 8 AM, your Telegram gets:
- the top 3 **new** jobs in India that fit your resume, each with a match score and the reasons
- what you're **missing** for each job (flagged, never added to your resume)
- a resume PDF tailored to each job, using **only facts already in your resume**
- a referral message draft you can send to someone at that company

It never applies for you. You read the 3 jobs and apply yourself.

**Time to set up:** about 20 minutes, once.
**Cost:** free with the NVIDIA key and a free Telegram bot. With a Claude key it uses a little of your Anthropic credit each morning, and falls back to NVIDIA when that runs out.

---

## What you need
- A Windows laptop (Mac/Linux works too; only step 7 is Windows-only)
- Python 3.10 or newer: [python.org/downloads](https://www.python.org/downloads/). When installing, tick **"Add Python to PATH"**.
- Google Chrome or Microsoft Edge (for the resume PDFs)
- Your resume as a PDF or DOCX (a text PDF, not a scanned photo)
- Telegram on your phone

## 1. Download and install
Download the ZIP: [github.com/Akshatb848/lazy-job-hunter/archive/refs/heads/main.zip](https://github.com/Akshatb848/lazy-job-hunter/archive/refs/heads/main.zip) (or **Code → Download ZIP** on the repo page).
Unzip the folder anywhere, for example `D:\jobhunter`. Open PowerShell in that folder and run:
```
pip install -r requirements.txt
```

## 2. Add an AI key
The tool tries **Claude (Anthropic)** first and switches to **NVIDIA Nemotron** automatically if there's no Claude key, no credits left, or Claude is down. You need at least one.

**Claude (best quality, paid per use):** create a key at [console.anthropic.com](https://console.anthropic.com) (Settings → API Keys) and add a few dollars of credit. A daily run uses roughly 25–30 short AI calls. Copy the key, then run:
```
python save_anthropic_key.py
```
It saves the key from your clipboard, tells you whether the account has credits, and clears the clipboard.
**NVIDIA (free backup):** sign in at [build.nvidia.com](https://build.nvidia.com), open any model, click **Get API Key**, and copy it:
```
setx NVIDIA_API_KEY "paste-your-key-here"
```
Close PowerShell and open it again so the keys are picked up. Never paste a key into chats or screenshots.

## 3. Make your Telegram bot
1. In Telegram, open **@BotFather** (blue tick) → send `/newbot` → give it a name → give it a username ending in `bot`.
2. Tap the token BotFather sends you (it copies), then run:
   ```
   python save_token.py
   ```
   It saves the token from your clipboard and clears the clipboard. Never post this token anywhere.
3. Open your new bot in Telegram and press **Start**.
4. Run `python telegram_setup.py`. It prints your chat ID. Save it:
   ```
   setx TELEGRAM_CHAT_ID "your-chat-id"
   ```
5. Run `python telegram_setup.py` again. You should get "Lazy Job Hunter is connected" in Telegram.

## 4. Turn your resume into a profile
```
python make_profile.py "C:\path\to\your_resume.pdf" --roles "data analyst, business analyst" --cities "Bengaluru, Pune, Remote"
```
- `--roles`: the job titles you want (leave it out and it suggests some from your resume).
- `--cities`: where you'd work.

It copies your resume word for word. Any line it can't find exactly in your resume is dropped and listed. Open the file it saves in `profiles\` and check it once.

## 5. First run
```
python jobhunter.py --profile profiles\yourname.json
```
It takes 2–4 minutes. The first run looks at every open India job on the boards; after that, each run only shows jobs posted since the last one.

## 6. Check before you apply
- Open the tailored PDF. Lines it reworded are in your words, just reordered and sharpened. If anything reads wrong, fix it before sending.
- The `*_review.pdf` in the `runs\` folder shows exactly what changed (yellow) and what's missing for the job.

## 7. Every morning at 7:50 AM
Add your profile path to `daily_profiles.txt` (one line), then run once:
```
powershell -ExecutionPolicy Bypass -File install_schedule.ps1
```
Your laptop needs to be on or asleep (not shut down) at 7:50. If it was off, it runs as soon as you start it.
To stop it: `Unregister-ScheduledTask -TaskName LazyJobHunter-Daily -Confirm:$false`

---

## Honest limits
- **Where jobs come from:** 34 company career boards that publish jobs openly (Greenhouse, Lever, Ashby): Stripe, Databricks, MongoDB, Okta, Zscaler, Paytm, CRED, Groww, Meesho, Atlan, Rubrik and more. It does **not** read LinkedIn or Naukri.
- **Freshers:** these boards have fewer fresher roles. Some mornings you may get "no strong matches"; it says so instead of padding the list.
- **Scores are a guide**, not a promise. In our test, an independent check agreed with the top 3 for a 2-year backend developer, but not every profile and day will be that clean.
- **No interviews are promised.** It saves you the 2 hours of searching; the applying is still yours.

## If something breaks
| Message | Fix |
|---|---|
| `TELEGRAM_BOT_TOKEN is not set` | Redo step 3.2, then reopen PowerShell |
| `Telegram rejected the token` | Copy the token again from BotFather (`/mybots` → your bot → API Token) |
| `Could not read enough text from the resume` | Export your resume again as a text PDF or DOCX |
| `Couldn't score today's jobs: ...` | Both AI services failed (no Claude credits and NVIDIA busy or rate-limited); it tries again tomorrow. `runs\<latest>\run.json` → `llm_calls` shows which AI answered and why Claude was skipped |
| PDFs come as `.html` | Install Chrome or Edge |
