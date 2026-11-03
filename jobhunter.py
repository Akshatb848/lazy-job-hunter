"""Lazy Job Hunter: every morning, find new India jobs for you, score them against your resume,
send the top 3 to Telegram with a resume tailored ONLY from your real facts, plus a referral DM draft.

Job data: public job-board APIs only (Greenhouse, Lever, Ashby). No LinkedIn/Naukri scraping. It never applies for you.

Env (secrets by name only, never in files):
  ANTHROPIC_API_KEY  primary AI (Claude, model claude-opus-5-5; override with ANTHROPIC_MODEL). Used when set and the
                     account has credits; on no key / no credits / errors it falls back to NVIDIA automatically.
  NVIDIA_API_KEY (or LLM_API_KEY)  backup AI: NVIDIA Nemotron via its OpenAI-compatible API
  LLM_BASE_URL   default https://integrate.api.nvidia.com/v1
  LLM_MODEL      default nvidia/nemotron-3-ultra-550b-a55b
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID   optional; without them the run is a dry run (messages saved to the run folder)

Usage:
  python jobhunter.py --profile profiles/rohan_sde2.json                 # full run, dry run unless Telegram env is set
  python jobhunter.py --profile ... --candidates-only                     # stop after filtering (for blind labelling)
  python jobhunter.py --profile ... --from-candidates runs/<dir>/candidates.json
"""
import argparse, concurrent.futures as cf, datetime as dt, html, json, os, re, subprocess, sys, time, urllib.request, uuid

from guard import Guard

HERE = os.path.dirname(os.path.abspath(__file__))


def env(name):
    """Read an env var; on Windows also check the user's saved variables, so a value set with setx
    works without restarting the program that launches this script."""
    v = os.environ.get(name)
    if v or os.name != 'nt':
        return v
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Environment') as k:
            return str(winreg.QueryValueEx(k, name)[0]).strip() or None
    except OSError:
        return None


IST =dt.timezone(dt.timedelta(hours=5, minutes=30))
LLM_BASE = (env('LLM_BASE_URL') or 'https://integrate.api.nvidia.com/v1').rstrip('/')
LLM_KEY = env('LLM_API_KEY') or env('NVIDIA_API_KEY')
LLM_MODEL = env('LLM_MODEL') or 'nvidia/nemotron-3-ultra-550b-a55b'
INDIA = re.compile(r'india|bengaluru|bangalore|mumbai|pune|hyderabad|gurgaon|gurugram|noida|delhi|chennai|ahmedabad|kolkata|jaipur', re.I)
SENIOR = re.compile(r'\b(senior|sr\.?|staff|principal|lead|manager|director|head|vp|avp|vice president|architect|iii|iv|gm|dgm|am/m|sde ?3|engineer 3)\b', re.I)
EXP = re.compile(r'(\d+)\s*(?:\+|-|to)?\s*\d*\s*(?:yrs|years)', re.I)  # "Experience : 5-7 yrs" in a title
WEAK = 40  # top score below this = tell the user these are weak matches
UA = {'User-Agent': 'lazy-job-hunter/1.0 (public job board API)'}


# ---------- http ----------
def http_json(url, data=None, headers=None, timeout=40, retries=2):
    for i in range(retries + 1):
        try:
            body = json.dumps(data).encode() if data is not None else None
            h = dict(UA, **(headers or {}))
            if body:
                h['Content-Type'] = 'application/json'
            with urllib.request.urlopen(urllib.request.Request(url, data=body, headers=h), timeout=timeout) as r:
                return json.load(r)
        except Exception as e:
            if i == retries:
                raise
            time.sleep(2 * (i + 1))


def strip_html(s):
    s = html.unescape(html.unescape(str(s or '')))
    s = re.sub(r'<(br|/p|/li|/h\d)[^>]*>', '\n', s, flags=re.I)
    s = re.sub(r'<[^>]+>', ' ', s)
    return re.sub(r'[ \t]+', ' ', re.sub(r'\n\s*\n+', '\n', s)).strip()


# ---------- job sources ----------
def fetch_source(src):
    t, tok, co = src['type'], src['token'], src['company']
    jobs = []
    if t == 'greenhouse':
        for j in http_json(f'https://boards-api.greenhouse.io/v1/boards/{tok}/jobs').get('jobs', []):
            jobs.append({'id': f'gh:{tok}:{j["id"]}', 'company': co, 'title': j.get('title', ''),
                         'location': (j.get('location') or {}).get('name', ''), 'url': j.get('absolute_url', ''),
                         'updated': j.get('updated_at') or j.get('first_published') or '', 'desc': None,
                         'detail_url': f'https://boards-api.greenhouse.io/v1/boards/{tok}/jobs/{j["id"]}'})
    elif t == 'lever':
        for j in http_json(f'https://api.lever.co/v0/postings/{tok}?mode=json'):
            c = j.get('categories') or {}
            lists = '\n'.join(l.get('text', '') + '\n' + strip_html(l.get('content', '')) for l in j.get('lists', []))
            jobs.append({'id': f'lv:{tok}:{j["id"]}', 'company': co, 'title': j.get('text', ''),
                         'location': ' / '.join(filter(None, [c.get('location', '')] + (c.get('allLocations') or []))),
                         'url': j.get('hostedUrl', ''),
                         'updated': dt.datetime.fromtimestamp(j.get('createdAt', 0) / 1000, IST).isoformat() if j.get('createdAt') else '',
                         'desc': (j.get('descriptionPlain') or '') + '\n' + lists})
    elif t == 'ashby':
        for j in http_json(f'https://api.ashbyhq.com/posting-api/job-board/{tok}').get('jobs', []):
            locs = [j.get('location') or ''] + [x.get('location', '') for x in (j.get('secondaryLocations') or [])]
            jobs.append({'id': f'as:{tok}:{j.get("id")}', 'company': co, 'title': j.get('title', ''),
                         'location': ' / '.join(filter(None, locs)), 'url': j.get('jobUrl', ''),
                         'updated': j.get('publishedAt', ''), 'desc': j.get('descriptionPlain') or strip_html(j.get('descriptionHtml', ''))})
    return jobs


def fetch_all(sources):
    out, errors = [], []
    with cf.ThreadPoolExecutor(8) as ex:
        futs = {ex.submit(fetch_source, s): s for s in sources}
        for f in cf.as_completed(futs):
            try:
                out += f.result()
            except Exception as e:
                errors.append({'source': futs[f]['token'], 'error': str(e)[:200]})
    return out, errors


def job_desc(job):
    if job.get('desc') is None and job.get('detail_url'):
        try:
            job['desc'] = strip_html(http_json(job['detail_url']).get('content', ''))
        except Exception:
            job['desc'] = ''
    return (job.get('desc') or '')[:6000]


def prefilter(jobs, prof, cap):
    roles = [r.lower() for r in prof['target_roles']]
    locs = [l.lower() for l in prof['locations']]
    junior = prof.get('years_exp', 0) < 5
    keep = []
    for j in jobs:
        title, loc = j['title'].lower(), j['location']
        if not INDIA.search(loc):  # remote roles count only when they say India
            continue
        if not any(r in title for r in roles):
            continue
        if junior and SENIOR.search(j['title']):
            continue
        m = EXP.search(j['title'])  # e.g. "Experience : 5-7 yrs" in the title
        if m and int(m.group(1)) > prof.get('years_exp', 0) + 2:
            continue
        if prof.get('years_exp', 0) >= 1 and re.search(r'\bintern', title):
            continue
        j['loc_match'] = any(l in loc.lower() for l in locs)
        keep.append(j)
    keep.sort(key=lambda j: (not j['loc_match'], ''.join(reversed(j.get('updated') or ''))), reverse=False)
    keep.sort(key=lambda j: j.get('updated') or '', reverse=True)
    keep.sort(key=lambda j: not j['loc_match'])
    return keep[:cap]


# ---------- LLM ----------
# Order: Anthropic (if ANTHROPIC_API_KEY is set and the account has credits) -> NVIDIA Nemotron (backup).
# A credit, auth or permission error turns Anthropic off for the rest of the run; a refusal, rate limit
# or outage falls back to NVIDIA for that one call only.
ANTHROPIC_MODEL = env('ANTHROPIC_MODEL') or 'claude-opus-5-5'
USAGE = {'anthropic': 0, 'nvidia': 0, 'anthropic_errors': []}
_anthropic = {'client': None, 'off': None}


def anthropic_client():
    if _anthropic['off']:
        return None
    if _anthropic['client']:
        return _anthropic['client']
    key = env('ANTHROPIC_API_KEY')
    if not key:
        _anthropic['off'] = 'no ANTHROPIC_API_KEY'
        return None
    try:
        import anthropic
        _anthropic['client'] = anthropic.Anthropic(api_key=key, max_retries=2, timeout=180.0)
    except ImportError:
        _anthropic['off'] = 'anthropic package not installed'
    return _anthropic['client']


def anthropic_json(prompt, effort):
    import anthropic
    c = anthropic_client()
    try:
        r = c.beta.messages.create(
            model=ANTHROPIC_MODEL, max_tokens=16000,
            output_config={'effort': effort},
            betas=['server-side-fallback-2026-07-01'],
            extra_body={'fallbacks': 'default'},  # if a safety classifier declines, Anthropic retries on its recommended model
            messages=[{'role': 'user', 'content': prompt}])
    except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as e:
        _anthropic['off'] = f'{type(e).__name__}: {str(e)[:120]}'
        raise
    except anthropic.BadRequestError as e:
        if re.search(r'credit balance|billing|purchase credits', str(e), re.I):
            _anthropic['off'] = 'no Anthropic credits'
        raise
    if r.stop_reason == 'refusal':
        raise RuntimeError('anthropic refusal: %s' % getattr(r.stop_details, 'category', None))
    txt = ''.join(b.text for b in r.content if b.type == 'text')
    return json.loads(re.search(r'\{[\s\S]*\}', txt).group(0))


def llm_json(prompt, max_tokens=1500, effort='low'):
    if anthropic_client():
        try:
            out = anthropic_json(prompt, effort)
            USAGE['anthropic'] += 1
            return out
        except Exception as e:
            if len(USAGE['anthropic_errors']) < 5:
                USAGE['anthropic_errors'].append(f'{type(e).__name__}: {str(e)[:150]}')
    out = nvidia_json(prompt, max_tokens)
    USAGE['nvidia'] += 1
    return out


def nvidia_json(prompt, max_tokens=1500):
    body = {'model': LLM_MODEL, 'temperature': 0, 'max_tokens': max_tokens,
            'messages': [{'role': 'user', 'content': prompt}]}
    if 'nvidia.com' in LLM_BASE:
        body['chat_template_kwargs'] = {'enable_thinking': False}
    last = None
    for i in range(6):
        try:
            r = http_json(LLM_BASE + '/chat/completions', body, {'Authorization': 'Bearer ' + LLM_KEY}, timeout=120, retries=1)
            txt = r['choices'][0]['message'].get('content') or ''
            return json.loads(re.search(r'\{[\s\S]*\}', txt).group(0))
        except Exception as e:
            last = e
            # free tiers allow only a few calls a minute: wait longer after a 429
            busy = re.search(r'HTTP Error (429|5\d\d)|timed out', str(e))  # rate limit or service outage: wait longer
            time.sleep(min(60, 12 * (i + 1)) if busy else 2)
            if not busy and i >= 2:
                break
    raise RuntimeError('LLM failed: %s' % last)


def resume_text(prof):
    lines = ['Summary: ' + prof.get('summary', ''), 'Years of experience: %s' % prof.get('years_exp', 0),
             'Skills: ' + ', '.join(prof['skills'])]
    for sec in ('experience', 'projects'):
        for it in prof.get(sec, []):
            lines.append(f"{it['role']} at {it['org']} ({it['dates']}):")
            lines += [f"  [{b['id']}] {b['text']}" for b in it['bullets']]
    lines += ['Education: ' + '; '.join(prof.get('education', []))]
    return '\n'.join(lines)


SCORE_PROMPT = """You screen jobs for one candidate. Be strict and honest.

CANDIDATE RESUME
{resume}
Target roles: {roles}. Preferred locations: {locs}.

JOB
{title} at {company}, {location}
{desc}

Return ONLY JSON:
{{"score": <0-100 fit for THIS candidate today>, "level_fit": "ok"|"too_senior"|"too_junior",
 "reasons": [3 short lines, each naming a specific fact from the resume that matches the job],
 "missing": [short skill or requirement names (max 4 words each) the job asks for that the resume does NOT show, max 5],
 "jd_skills": [up to 15 tools/skills the job names]}}
Rules: if the job needs clearly more experience than the candidate has, level_fit "too_senior" and score <= 40.
Never claim the candidate has something the resume does not show."""

TAILOR_PROMPT = """Tailor this resume for the job below.

RESUME (bullet ids in brackets)
{resume}

JOB: {title} at {company}
{desc}

Return ONLY JSON:
{{"headline": "one line, max 20 words, using only facts from the resume",
 "skills": [the candidate's skills reordered by relevance; copy each EXACTLY from the resume skills list, add nothing],
 "bullets": [{{"src": "<bullet id>", "text": "<same fact, reworded to echo the job's language>"}} ... every bullet id exactly once, most relevant first],
 "referral_dm": "max 450 chars, to an employee at {company} addressed as [Name], asking for a referral for this role, citing 1-2 true facts from the resume"}}
HARD RULES: Do not add any tool, skill, technology, employer, number or achievement that is not in the resume.
Keep every number exactly as written. Reword and reorder only. Gaps stay gaps.
Do not add framing the resume does not state (e.g. 'distributed systems', 'microservices', 'at scale', 'high-throughput', 'led', 'architected'). No filler like 'applying engineering principles'."""


def score_job(job, prof):
    s = llm_json(SCORE_PROMPT.format(resume=resume_text(prof), roles=', '.join(prof['target_roles']),
                                     locs=', '.join(prof['locations']), title=job['title'], company=job['company'],
                                     location=job['location'], desc=job_desc(job) or '(no description)'), 900)
    try:
        sc = int(float(s.get('score', 0)))
    except Exception:
        sc = 0
    if s.get('level_fit') == 'too_senior':
        sc = min(sc, 40)
    return {'id': job['id'], 'score': max(0, min(100, sc)), 'level_fit': s.get('level_fit'),
            'reasons': [str(x) for x in (s.get('reasons') or [])][:3], 'missing': [str(x) for x in (s.get('missing') or [])][:5],
            'jd_skills': [str(x) for x in (s.get('jd_skills') or [])][:15]}


def tailor(job, prof, sc):
    raw = llm_json(TAILOR_PROMPT.format(resume=resume_text(prof), title=job['title'], company=job['company'],
                                        desc=job_desc(job)), 2500, effort='medium')
    g = Guard(prof, extra_terms=sc['jd_skills'] + sc['missing'], job_title=job['title'])
    clean, violations = g.clean(raw)
    return raw, clean, violations


# ---------- resume PDF ----------
CSS = """body{font-family:Calibri,Arial,sans-serif;font-size:10.5pt;color:#111;margin:28px 34px}h1{font-size:18pt;margin:0}
.c{color:#444;margin:2px 0 8px}h2{font-size:11pt;border-bottom:1px solid #999;margin:12px 0 4px;text-transform:uppercase}
ul{margin:2px 0 6px 18px;padding:0}li{margin:2px 0}.chg{background:#fff3a3}.miss{border:1.5px solid #e09b00;background:#fff7e6;
padding:6px 9px;margin:8px 0;font-size:9.5pt}.role{font-weight:bold}.d{color:#555;float:right}.tag{font-size:8.5pt;color:#7a5c00}"""


def render_html(prof, clean, job, sc, review):
    e = html.escape
    order = [b['src'] for b in clean['bullets']]
    by = {b['src']: b for b in clean['bullets']}
    h = [f"<html><head><meta charset='utf-8'><style>{CSS}</style></head><body>",
         f"<h1>{e(prof['name'])}</h1><div class='c'>{e(prof['email'])} · {e(prof['city'])}</div>",
         f"<div>{e(clean['headline'])}</div>"]
    if review:
        h.append(f"<div class='miss'><b>For {e(job['title'])} at {e(job['company'])}</b> · match {sc['score']}%<br>"
                 f"<b>Missing for this job (NOT added to your resume):</b> {e(', '.join(sc['missing']) or 'nothing major')}<br>"
                 f"<span class='tag'>Yellow lines were reworded for this job using only your own facts.</span></div>")
    h.append(f"<h2>Skills</h2><div>{e(' · '.join(clean['skills']))}</div>")
    for sec, title in (('experience', 'Experience'), ('projects', 'Projects')):
        items = prof.get(sec, [])
        if not items:
            continue
        h.append(f'<h2>{title}</h2>')
        for it in items:
            ids = [b['id'] for b in it['bullets']]
            ids.sort(key=lambda i: order.index(i) if i in order else 99)
            h.append(f"<div><span class='role'>{e(it['role'])}</span>, {e(it['org'])}<span class='d'>{e(it['dates'])}</span></div><ul>")
            for i in ids:
                b = by[i]
                cls = " class='chg'" if review and b['changed'] else ''
                h.append(f"<li{cls}>{e(b['text'])}</li>")
            h.append('</ul>')
    h.append('<h2>Education</h2>' + ''.join(f'<div>{e(x)}</div>' for x in prof.get('education', [])))
    return ''.join(h) + '</body></html>'


def chrome():
    for p in [os.environ.get('CHROME_PATH', ''), r'C:\Program Files\Google\Chrome\Application\chrome.exe',
              r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
              os.path.expandvars(r'%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe'),
              r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe', r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
              '/usr/bin/google-chrome', '/usr/bin/chromium-browser',
              '/usr/bin/chromium']:
        if p and os.path.exists(p):
            return p
    return None


def to_pdf(html_text, path):
    hp = path[:-4] + '.html'
    open(hp, 'w', encoding='utf-8').write(html_text)
    c = chrome()
    if not c:
        return hp
    subprocess.run([c, '--headless=new', '--disable-gpu', '--no-pdf-header-footer', f'--print-to-pdf={os.path.abspath(path)}',
                    'file:///' + os.path.abspath(hp).replace('\\', '/')], capture_output=True, timeout=90)
    return path if os.path.exists(path) else hp


# ---------- Telegram ----------
def tg(method, fields=None, file_path=None):
    token, chat = env('TELEGRAM_BOT_TOKEN'), env('TELEGRAM_CHAT_ID')
    url = f'https://api.telegram.org/bot{token}/{method}'
    fields = dict(fields or {}, chat_id=chat)
    if not file_path:
        return http_json(url, fields, timeout=40)
    b = uuid.uuid4().hex
    parts = []
    for k, v in fields.items():
        parts.append(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    fn = os.path.basename(file_path)
    parts.append(f'--{b}\r\nContent-Disposition: form-data; name="document"; filename="{fn}"\r\n'
                 f'Content-Type: application/pdf\r\n\r\n'.encode() + open(file_path, 'rb').read() + b'\r\n')
    parts.append(f'--{b}--\r\n'.encode())
    req = urllib.request.Request(url, data=b''.join(parts), headers=dict(UA, **{'Content-Type': f'multipart/form-data; boundary={b}'}))
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


# ---------- main ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--profile', required=True)
    ap.add_argument('--top', type=int, default=3)
    ap.add_argument('--max-candidates', type=int, default=25)
    ap.add_argument('--candidates-only', action='store_true')
    ap.add_argument('--from-candidates')
    ap.add_argument('--label', default='')
    ap.add_argument('--dry-run', action='store_true', help='do everything but send nothing to Telegram')
    ap.add_argument('--baseline', action='store_true', help='mark every current India job as seen and stop (no AI, no message)')
    a = ap.parse_args()
    t0 = time.time()
    prof = json.load(open(a.profile, encoding='utf-8'))
    stamp = dt.datetime.now(IST).strftime('%Y%m%d-%H%M%S')
    rd = os.path.join(HERE, 'runs', f'{stamp}_{prof["id"]}{("_" + a.label) if a.label else ""}')
    os.makedirs(rd, exist_ok=True)
    log = {'profile': prof['id'], 'started': dt.datetime.now(IST).isoformat(), 'model_primary': ANTHROPIC_MODEL if anthropic_client() else None, 'model_backup': LLM_MODEL, 'llm_base': LLM_BASE}
    seen_path = os.path.join(HERE, 'state', f'seen_{prof["id"]}.json')
    seen = json.load(open(seen_path)) if os.path.exists(seen_path) else {}

    new = []
    if a.from_candidates:
        cands = json.load(open(a.from_candidates, encoding='utf-8'))['candidates'][:a.max_candidates]
        log.update(jobs_checked=None, india_new=None, source_errors=[])
    else:
        sources = json.load(open(os.path.join(HERE, 'sources.json')))
        say(f'Checking {len(sources)} company job boards...')
        jobs, errors = fetch_all(sources)
        india_jobs = [j for j in jobs if INDIA.search(j['location'])]
        new = [j for j in india_jobs if j['id'] not in seen]
        if a.baseline:
            for j in india_jobs:
                seen.setdefault(j['id'], log['started'])
            os.makedirs(os.path.dirname(seen_path), exist_ok=True)
            json.dump(seen, open(seen_path, 'w'), indent=0)
            print(f"[{prof['id']}] baseline: {len(india_jobs)} India jobs marked seen ({len(jobs)} checked); next run sends only new posts")
            return
        cands = prefilter(new, prof, a.max_candidates)
        log.update(sources=len(sources), jobs_checked=len(jobs), india_jobs=len(india_jobs), india_new=len(new),
                   first_run=not seen, source_errors=errors)
        json.dump({'profile': prof['id'], 'created': log['started'],
                   'candidates': [dict(j, desc=j.get('desc')) for j in cands]},
                  open(os.path.join(rd, 'candidates.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    log['candidates'] = len(cands)
    say(f"{log.get('jobs_checked') or len(cands):,} jobs checked, {log.get('india_new') or len(cands):,} new in India, {len(cands)} fit your roles")
    if a.candidates_only:
        json.dump(log, open(os.path.join(rd, 'run.json'), 'w', encoding='utf-8'), indent=1)
        print('candidates saved to', rd)
        return

    if cands:
        say(f'Matching {len(cands)} jobs against your resume...')
    workers = int(env('LLM_WORKERS') or 5)
    with cf.ThreadPoolExecutor(workers) as ex:
        scores = list(ex.map(lambda j: _safe(score_job, j, prof), cands))
    by_id = {j['id']: j for j in cands}
    scored = sorted([s for s in scores if s and 'error' not in s], key=lambda s: -s['score'])
    log['score_errors'] = [s for s in scores if s and 'error' in s]
    json.dump(scored, open(os.path.join(rd, 'scores.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    top = []
    for s in scored[:a.top]:
        job = by_id[s['id']]
        say(f"Tailoring resume #{len(top)+1}: {job['title']} at {job['company']} ({s['score']}% match)")
        try:
            raw, clean, viol = tailor(job, prof, s)
        except Exception as e:  # AI busy: still send the job, with the original resume and a note
            say(f"Tailoring failed ({str(e)[:80]}); sending the original resume for this job")
            raw, (clean, viol) = None, Guard(prof).clean({})
            clean['untailored'] = True
        slug = re.sub(r'[^a-z0-9]+', '-', f"{job['company']}-{job['title']}".lower())[:60].strip('-')
        review_pdf = to_pdf(render_html(prof, clean, job, s, True), os.path.join(rd, f'{len(top)+1}_{slug}_review.pdf'))
        clean_pdf = to_pdf(render_html(prof, clean, job, s, False), os.path.join(rd, f'{len(top)+1}_{slug}_resume.pdf'))
        top.append({'job': {k: job[k] for k in ('id', 'company', 'title', 'location', 'url', 'updated')}, 'score': s,
                    'model_output': raw, 'tailored': clean, 'blocked': viol, 'review_pdf': review_pdf, 'resume_pdf': clean_pdf})
    log['llm_calls'] = dict(USAGE, anthropic_off=_anthropic['off'])
    log['blocked_total'] = sum(len(t['blocked']) for t in top)
    log['invented_in_final'] = 0  # guard reverts every blocked item; verified again below
    for t in top:
        g = Guard(prof, extra_terms=t['score']['jd_skills'] + t['score']['missing'], job_title=t['job']['title'])
        _, again = g.clean({'skills': t['tailored']['skills'], 'bullets': t['tailored']['bullets'],
                            'headline': t['tailored']['headline'], 'referral_dm': t['tailored']['referral_dm']})
        log['invented_in_final'] += len(again)

    # messages
    first = prof['name'].split()[0]
    newn = log.get('india_new') if log.get('india_new') is not None else len(cands)
    head = (f"☀️ Good morning {first}! {log.get('jobs_checked') or newn:,} jobs checked, "
            f"{newn:,} new in India{' (first run)' if log.get('first_run') else ' since yesterday'}, {len(cands)} fit your roles.\n")
    if cands and not scored:
        head += ("Couldn't score today's jobs: the AI service returned errors "
                 f"({(log['score_errors'] or [{}])[0].get('error', '')[:80]}). I'll try again tomorrow.")
    elif not top:
        head += "No new jobs match your roles today. Nothing to apply for, so no tailored resumes. I'll check again tomorrow."
    else:
        weak = top[0]['score']['score'] < WEAK
        head += ((f"No strong matches today. These {len(top)} are weak (under {WEAK}%), apply only if they interest you:\n") if weak
                 else f"Top {len(top)} for you:\n") + '\n'.join(
            f"{i+1}. {t['job']['title']} · {t['job']['company']} · {t['score']['score']}% match" for i, t in enumerate(top))
    msgs = [{'text': head}]
    for i, t in enumerate(top):
        s = t['score']
        body = (f"#{i+1} {t['job']['title']}\n{t['job']['company']} · {t['job']['location']} · {s['score']}% match\n\n"
                f"Why you fit:\n" + '\n'.join('• ' + r for r in s['reasons']) +
                f"\n\nMissing (flagged, NOT added): {', '.join(s['missing']) or 'nothing major'}\n"
                f"Apply yourself: {t['job']['url']}")
        msgs.append({'text': body[:4000], 'doc': t['resume_pdf'] if t['resume_pdf'].endswith('.pdf') else None,
                     'doc_caption': (f"Your resume (the AI was busy, so it is NOT tailored for {t['job']['company']} today)"
                                     if t['tailored'].get('untailored') else
                                     f"Resume tailored for {t['job']['company']} (only your real facts)")})
        if t['tailored']['referral_dm']:
            msgs.append({'text': ('Referral DM draft (edit [Name]):\n\n' + t['tailored']['referral_dm'])[:4000]})
    send = bool(env('TELEGRAM_BOT_TOKEN') and env('TELEGRAM_CHAT_ID')) and not a.dry_run
    sent = []
    if send:
        say('Sending your top jobs to Telegram...')
    for m in msgs:
        if send:
            r = tg('sendMessage', {'text': m['text'], 'disable_web_page_preview': 'true'})
            sent.append(r.get('ok'))
            if m.get('doc'):
                r = tg('sendDocument', {'caption': m['doc_caption']}, m['doc'])
                sent.append(r.get('ok'))
    open(os.path.join(rd, 'telegram_preview.txt'), 'w', encoding='utf-8').write(
        '\n\n-----\n\n'.join(m['text'] + (f"\n[PDF: {os.path.basename(m['doc'])}]" if m.get('doc') else '') for m in msgs))
    if send and all(sent):
        for j in (new or cands):  # every new India job is now 'seen', so tomorrow shows only fresh posts
            seen[j['id']] = log['started']
        os.makedirs(os.path.dirname(seen_path), exist_ok=True)
        json.dump(seen, open(seen_path, 'w'), indent=0)
    log.update(top=[{k: t[k] for k in ('job', 'score', 'blocked', 'review_pdf', 'resume_pdf')} for t in top],
               telegram='sent' if send and all(sent) else ('failed' if send else 'dry-run'),
               seconds=round(time.time() - t0, 1))
    json.dump(log, open(os.path.join(rd, 'run.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    json.dump(top, open(os.path.join(rd, 'top.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(head)
    print(f"blocked inventions: {log['blocked_total']}, invented in final: {log['invented_in_final']}, "
          f"telegram: {log['telegram']}, {log['seconds']} s -> {rd}")


def say(msg):
    print(f"[{dt.datetime.now(IST).strftime('%H:%M:%S')}] {msg}", flush=True)


def _safe(fn, *args):
    try:
        return fn(*args)
    except Exception as e:
        return {'id': args[0]['id'], 'error': str(e)[:200]}


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
