"""Guardrail: the tailored resume may only reword and reorder what is already in the resume.

It blocks three kinds of invention and logs every block:
  1. a skill in the skills list that the person does not have
  2. a tool/skill name in a bullet, headline or referral DM that appears nowhere in the resume
  3. a number in a bullet that is not in that bullet's original text (e.g. 40,000 -> 60,000)
A blocked bullet falls back to its original wording, so nothing invented ever reaches the PDF.
"""
import re

# Tool and skill names the model is most likely to slip in. JD skills and "missing" skills are added per job.
LEXICON = """
aws, azure, gcp, google cloud, kubernetes, k8s, docker, terraform, ansible, jenkins, github actions, ci/cd, linux, bash,
java, spring boot, kotlin, scala, golang, rust, c++, c#, .net, python, django, flask, fastapi, node.js, nodejs,
typescript, javascript, react, next.js, angular, vue, redux, graphql, grpc, microservice, kafka, rabbitmq, redis, memcached,
postgresql, postgres, mysql, mongodb, cassandra, dynamodb, elasticsearch, snowflake, bigquery, redshift, databricks, spark, hadoop,
airflow, dbt, etl, pandas, numpy, scikit-learn, sklearn, tensorflow, pytorch, keras, llm, machine learning, deep learning, nlp,
tableau, power bi, looker, metabase, excel, vba, sas, spss, statistics, a/b testing, amplitude, mixpanel, google analytics, ga4,
figma, jira, confluence, salesforce, hubspot, zoho, sap, meta ads, google ads, seo, sem, email marketing, marketing automation,
canva, photoshop, copywriting, market research, crm, braze, clevertap, moengage, webengage, shopify, tally,
prometheus, grafana, datadog, splunk, new relic, azure functions, aws lambda, serverless, ec2, s3, selenium, cypress, jest,
distributed system, system design, event-driven, cloud-native, high-throughput, low-latency, scalability, sdlc, agile, scrum,
devops, mlops, data pipeline, data warehouse, team lead, mentoring, stakeholder management, p&l
""".replace('\n', ' ').split(',')
LEXICON = sorted({t.strip() for t in LEXICON if t.strip()}, key=len, reverse=True)  # whole phrases only
LEX_SET = set()
STOP = {'r', 'go', 'spring', 'express', 'segment', 'rest', 'sql'}  # too generic alone; checked only via JD/profile terms


def norm(s):
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9+#./\- ]', ' ', str(s).lower())).strip()


def has_term(text_norm, term):
    t = norm(term)
    if not t:
        return False
    t = re.escape(t[:-1]) + '(?:s|es)?' if t.endswith('s') and len(t) > 3 else re.escape(t) + '(?:s|es)?'  # plural or singular
    return re.search(r'(?<![a-z0-9])' + t + r'(?![a-z0-9])', text_norm) is not None


def numbers(s):
    out = set()
    for n, k in re.findall(r'(\d[\d,\.]*)\s?([kK](?![a-zA-Z]))?', str(s)):
        n = n.replace(',', '').rstrip('.')
        if n:
            if k:  # "40K" means 40000
                try:
                    n = str(int(float(n) * 1000))
                except ValueError:
                    pass
            out.add(n)
    return out


def tool_like(term):
    """Only real tool/skill names count as inventions, not soft phrases like 'campaign operations'."""
    t = str(term).strip()
    if norm(t) in LEX_SET:
        return True
    if len(t.split()) > 2:
        return False
    return bool(re.search(r'[A-Z]{2,}|[a-z][A-Z]|[0-9.+#/]', t)) or (t[:1].isupper() and len(t.split()) == 1)


class Guard:
    def __init__(self, profile, extra_terms=(), job_title=''):
        self.p = profile
        self.allow_numbers = numbers(job_title)  # e.g. "O365" in the role name may appear in the DM
        parts = [profile.get('summary', ''), ' '.join(profile.get('skills', [])), ' '.join(profile.get('education', []))]
        self.bullets = {}
        for sec in ('experience', 'projects'):
            for item in profile.get(sec, []):
                parts += [item.get('org', ''), item.get('role', ''), item.get('dates', '')]
                for b in item.get('bullets', []):
                    self.bullets[b['id']] = b['text']
                    parts.append(b['text'])
        self.resume_norm = norm(' '.join(parts))
        # numbers the person can truthfully use outside a bullet: anything in the resume, its years, and years of experience
        years = set()
        for y in numbers(' '.join(parts)):
            if len(y) == 4 and y.startswith('20'):
                years.add(y[2:])  # "2025" may be written as "'25"
        self.resume_numbers = numbers(' '.join(parts)) | years | {str(profile.get('years_exp', 0))}
        self.skill_map = {norm(s): s for s in profile.get('skills', [])}
        terms = [t for t in LEXICON if t not in STOP] + [t for t in extra_terms if t and tool_like(t)]
        self.terms = sorted({norm(t) for t in terms if norm(t)}, key=len, reverse=True)
        self.violations = []

    def _invented_terms(self, text):
        tn = norm(text)
        bad = []
        for t in self.terms:
            if has_term(tn, t) and not has_term(self.resume_norm, t):
                # skip if it is only part of a longer term already flagged or present
                if not any(t != b and t in b for b in bad):
                    bad.append(t)
        return bad

    def check_text(self, where, text, allowed_numbers):
        bad_terms = self._invented_terms(text)
        bad_nums = sorted(numbers(text) - allowed_numbers)
        for t in bad_terms:
            self.violations.append({'where': where, 'kind': 'invented_term', 'detail': t})
        for n in bad_nums:
            self.violations.append({'where': where, 'kind': 'invented_number', 'detail': n})
        return not bad_terms and not bad_nums

    def clean(self, tailored):
        """Return a safe copy of the model's tailored resume plus the list of blocked inventions."""
        self.violations = []
        out = {'headline': '', 'skills': [], 'bullets': [], 'referral_dm': ''}
        # skills: exact subset of the person's own skills
        for s in tailored.get('skills', []) or []:
            k = norm(s)
            if k in self.skill_map:
                if self.skill_map[k] not in out['skills']:
                    out['skills'].append(self.skill_map[k])
            else:
                self.violations.append({'where': 'skills', 'kind': 'invented_skill', 'detail': str(s)})
        for s in self.p.get('skills', []):  # never drop a real skill, just put unranked ones last
            if s not in out['skills']:
                out['skills'].append(s)
        # bullets: every original bullet exactly once, each checked against its own source
        seen = set()
        for b in tailored.get('bullets', []) or []:
            src = str(b.get('src', ''))
            if src not in self.bullets or src in seen:
                if src not in self.bullets:
                    self.violations.append({'where': 'bullets', 'kind': 'unknown_source', 'detail': src})
                continue
            seen.add(src)
            text = str(b.get('text', '')).strip() or self.bullets[src]
            ok = self.check_text('bullet ' + src, text, numbers(self.bullets[src]))
            out['bullets'].append({'src': src, 'text': text if ok else self.bullets[src],
                                   'changed': ok and norm(text) != norm(self.bullets[src]), 'reverted': not ok})
        for src, text in self.bullets.items():
            if src not in seen:
                out['bullets'].append({'src': src, 'text': text, 'changed': False, 'reverted': False})
        h = str(tailored.get('headline', '')).strip()
        out['headline'] = h if h and self.check_text('headline', h, self.resume_numbers) else self.p.get('summary', '')
        # referral DM: drop only the sentences that invent something, keep the rest
        dm = str(tailored.get('referral_dm', '')).strip()
        keep = [s for s in re.split(r'(?<=[.!?])\s+', dm) if s and self.check_text('referral_dm', s, self.resume_numbers | self.allow_numbers)]
        out['referral_dm'] = ' '.join(keep) if len(keep) >= 2 else ''
        return out, list(self.violations)


LEX_SET.update(norm(t) for t in LEXICON)
