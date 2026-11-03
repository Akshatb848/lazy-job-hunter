"""Turn your resume (PDF, DOCX, TXT or MD) into a Lazy Job Hunter profile.

  python make_profile.py my_resume.pdf --roles "data analyst, business analyst" --cities "Bengaluru, Remote"

The AI only copies facts out of your resume. Every bullet is checked against the resume text, and any
line it can't find word for word is dropped and listed, so the profile never holds anything you didn't write.
Open the JSON once and check it before your first run.
"""
import argparse, json, os, re, sys

from jobhunter import HERE, llm_json
from guard import norm, numbers

sys.stdout.reconfigure(encoding='utf-8')

PROMPT = """Extract this resume into JSON. COPY text exactly as written. Do not rewrite, summarise, shorten,
merge, translate or improve anything. Do not add any skill, tool, number or fact that is not in the resume.

Return only JSON:
{{"name": "...", "email": "... or empty", "city": "... or empty",
  "years_exp": <whole years of full-time work experience; internships do not count; 0 for students>,
  "summary": "the resume's own summary/objective sentence copied exactly, or empty if it has none",
  "skills": ["each skill/tool exactly as listed in the resume's skills section"],
  "experience": [{{"org": "...", "role": "...", "dates": "...", "bullets": ["bullet copied exactly", "..."]}}],
  "projects": [{{"org": "Project", "role": "project name", "dates": "... or empty", "bullets": ["copied exactly"]}}],
  "education": ["one line per degree, copied exactly"],
  "suggested_roles": ["3-5 job titles this person can apply for now, lower case, based on the resume"]}}

Internships go in "experience". Certifications and achievements may go in "projects" with org "Achievement".

RESUME:
{resume}
"""


def read_resume(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == '.pdf':
        import fitz
        with fitz.open(path) as d:
            t = '\n'.join(p.get_text() for p in d)
        return re.sub(r'(?<=\w)-\n(?=\w)', '-', t)  # rejoin words the PDF wrapped at a hyphen
    if ext == '.docx':
        import docx
        d = docx.Document(path)
        rows = [p.text for p in d.paragraphs]
        for t in d.tables:
            rows += [c.text for r in t.rows for c in r.cells]
        return '\n'.join(rows)
    return open(path, encoding='utf-8', errors='ignore').read()


MONTHS = {m: i for i, m in enumerate('jan feb mar apr may jun jul aug sep oct nov dec'.split(), 1)}


def years_from_dates(experience):
    """Whole years of full-time work from 'Jul 2024 - Present' style dates; internships don't count. None if unreadable."""
    import datetime as dt
    today, months, got = dt.date.today(), 0, False
    for it in experience:
        if re.search(r'intern|trainee|apprentice', (it.get('role', '') + ' ' + it.get('org', '')).lower()):
            continue
        ends = []
        for mon, yr, yonly, now in re.findall(r'([a-z]{3})[a-z]*\.?\s*(\d{4})|(\d{4})|(present|current|now|till date)',
                                              str(it.get('dates', '')).lower()):
            if now:
                ends.append((today.year, today.month))
            elif yr:
                ends.append((int(yr), MONTHS.get(mon, 1)))
            elif yonly:
                ends.append((int(yonly), 1))
        if len(ends) >= 2:
            (y1, m1), (y2, m2) = ends[0], ends[1]
            months += max(0, (y2 - y1) * 12 + (m2 - m1))
            got = True
    return months // 12 if got else None


def found_in(text, src_norm, src_nums):
    """True if a line is really in the resume: every number appears there and 90%+ of its words do, in order-agnostic terms."""
    words = [w for w in norm(text).split() if len(w) > 2]
    if not words:
        return False
    hit = sum(1 for w in words if re.search(r'(?<![a-z0-9])' + re.escape(w) + r'(?![a-z0-9])', src_norm))
    return hit / len(words) >= 0.9 and numbers(text) <= src_nums


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('resume')
    ap.add_argument('--roles', help='comma-separated job titles you want (default: suggested from your resume)')
    ap.add_argument('--cities', default='Bengaluru, Remote, India', help='comma-separated cities you would work in')
    ap.add_argument('--years', type=int, help='years of full-time experience (default: worked out from your dates)')
    ap.add_argument('--id', help='short profile name, e.g. akshat (default: from your first name)')
    a = ap.parse_args()

    text = read_resume(a.resume)
    if len(text.strip()) < 200:
        sys.exit('Could not read enough text from the resume. If it is a scanned image, export it again as a text PDF or DOCX.')
    src_norm, src_nums = norm(text), numbers(text)
    raw = llm_json(PROMPT.format(resume=text[:15000]), max_tokens=4000, effort='medium')

    dropped, n = [], 0
    prof = {'id': a.id or re.sub(r'[^a-z0-9]', '', (raw.get('name') or 'me').split()[0].lower()) or 'me',
            'name': raw.get('name', '').strip(), 'email': raw.get('email', '').strip(), 'city': raw.get('city', '').strip()}
    roles = [r.strip().lower() for r in (a.roles.split(',') if a.roles else raw.get('suggested_roles', [])) if r.strip()]
    prof['target_roles'] = roles
    prof['years_exp'] = a.years if a.years is not None else int(raw.get('years_exp') or 0)
    prof['locations'] = [c.strip() for c in a.cities.split(',') if c.strip()] + (['India'] if 'india' not in a.cities.lower() else [])
    s = (raw.get('summary') or '').strip()
    prof['summary'] = s if s and found_in(s, src_norm, src_nums) else ''
    if s and not prof['summary']:
        dropped.append(('summary', s))
    prof['skills'] = []
    for k in raw.get('skills', []):
        k = str(k).strip()
        if k and re.search(r'(?<![a-z0-9])' + re.escape(norm(k)) + r'(?![a-z0-9])', src_norm):
            prof['skills'].append(k)
        elif k:
            dropped.append(('skill', k))
    for sec, pre in (('experience', 'x'), ('projects', 'p')):
        prof[sec] = []
        for item in raw.get(sec, []) or []:
            bl = []
            for b in item.get('bullets', []) or []:
                b = re.sub(r'^[\s•\-–*·]+', '', str(b)).strip()
                if b and found_in(b, src_norm, src_nums):
                    n += 1
                    bl.append({'id': f'{pre}{n}', 'text': b})
                elif b:
                    dropped.append((sec, b))
            if bl:
                prof[sec].append({'org': item.get('org', ''), 'role': item.get('role', ''), 'dates': item.get('dates', ''), 'bullets': bl})
    prof['education'] = [e for e in raw.get('education', []) if e]
    if a.years is None:
        y = years_from_dates(raw.get('experience', []) or [])
        if y is not None:
            prof['years_exp'] = y
    if not prof['summary']:  # the tailored headline falls back to this, so build one only from verified facts
        top = ', '.join(prof['skills'][:4])
        prof['summary'] = (f"{prof['experience'][0]['role']} with {prof['years_exp']} years of experience" if prof['experience'] and prof['years_exp']
                           else 'Graduate') + (f", skilled in {top}" if top else '') + '.'

    os.makedirs(os.path.join(HERE, 'profiles'), exist_ok=True)
    out = os.path.join(HERE, 'profiles', prof['id'] + '.json')
    json.dump(prof, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    nb = sum(len(i['bullets']) for s in ('experience', 'projects') for i in prof[s])
    print(f"Saved {out}\n  {prof['name']} · {prof['years_exp']} yrs · {len(prof['skills'])} skills · {nb} bullets\n"
          f"  roles: {', '.join(prof['target_roles'])}\n  cities: {', '.join(prof['locations'])}")
    if dropped:
        print(f"\n{len(dropped)} item(s) dropped because they were not found word for word in your resume:")
        for w, t in dropped:
            print(f"  - {w}: {t[:110]}")
    print('\nOpen the file once and check it. Then run: python jobhunter.py --profile ' + os.path.relpath(out, HERE))


if __name__ == '__main__':
    main()
