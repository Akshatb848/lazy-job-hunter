"""Unit tests for guard.py. Run: python test_guard.py"""
import json, os
from guard import Guard

HERE = os.path.dirname(os.path.abspath(__file__))
rohan = json.load(open(os.path.join(HERE, 'profiles', 'rohan_sde2.json'), encoding='utf-8'))
fails = 0


def check(name, cond):
    global fails
    print(('PASS ' if cond else 'FAIL ') + name)
    fails += 0 if cond else 1


g = Guard(rohan, extra_terms=['Kubernetes', 'Kafka', 'GCP'])

# 1. honest reorder + reword passes untouched
out, v = g.clean({'skills': ['Redis', 'Java', 'Spring Boot'], 'bullets': [
    {'src': 'x2', 'text': 'Reduced p95 latency of the payment-status API from 900 ms to 250 ms using Redis caching'},
    {'src': 'x1', 'text': 'Built a Java and Spring Boot refund service handling about 40,000 refunds a day'}],
    'headline': 'Backend engineer, 2 years in Java, Spring Boot and Redis', 'referral_dm': 'Hi [Name], I have 2 years in Java and Redis.'})
check('honest rewrite has no violations', v == [])
check('honest rewrite keeps new wording', out['bullets'][0]['text'].startswith('Reduced p95') and out['bullets'][0]['changed'])
check('all 5 original bullets present once', sorted(b['src'] for b in out['bullets']) == ['p1', 'x1', 'x2', 'x3', 'x4'])
check('skills keep every real skill', set(out['skills']) == set(rohan['skills']))

# 2. Azure -> AWS swap is blocked and reverted
out, v = g.clean({'bullets': [{'src': 'x3', 'text': 'Moved 6 Node.js notification jobs to AWS Lambda, removing 2 always-on servers'}]})
b = [x for x in out['bullets'] if x['src'] == 'x3'][0]
check('AWS invention blocked', any('aws' in x['detail'] for x in v))
check('AWS bullet reverted to original', b['reverted'] and 'Azure Functions' in b['text'])

# 3. invented skill in skills list is dropped
out, v = g.clean({'skills': ['Java', 'Kubernetes', 'Kafka']})
check('invented skills dropped', 'Kubernetes' not in out['skills'] and 'Kafka' not in out['skills'])
check('invented skills logged', sum(1 for x in v if x['kind'] == 'invented_skill') == 2)

# 4. number inflation blocked
out, v = g.clean({'bullets': [{'src': 'x1', 'text': 'Built a refund service in Java and Spring Boot handling 60,000 refunds a day'}]})
check('number inflation blocked', any(x['kind'] == 'invented_number' and x['detail'] == '60000' for x in v))
check('inflated bullet reverted', '40,000' in [x for x in out['bullets'] if x['src'] == 'x1'][0]['text'])

# 5. JD term slipped into headline / DM is blocked
out, v = g.clean({'headline': 'Backend engineer skilled in Kafka and GCP', 'referral_dm': 'Hi [Name], I know Kubernetes well.'})
check('headline invention falls back to summary', out['headline'] == rohan['summary'])
check('DM with only invented sentences removed', out['referral_dm'] == '')

# 6. unknown bullet id ignored
out, v = g.clean({'bullets': [{'src': 'zz', 'text': 'Led a team of 10 engineers'}]})
check('unknown bullet id rejected', any(x['kind'] == 'unknown_source' for x in v) and all(b['src'] != 'zz' for b in out['bullets']))

# 7. soft JD phrases are not inventions; 40K == 40,000; tools from the JD still blocked
g2 = Guard(rohan, extra_terms=['cross-functional collaboration', 'Troubleshooting', 'Kafka'])
out, v = g2.clean({'bullets': [{'src': 'x1', 'text': 'Built a refund service in Java and Spring Boot with cross-functional collaboration, ~40K refunds a day'}]})
check('soft phrase + 40K allowed', v == [] and not out['bullets'][0]['reverted'])
out, v = g2.clean({'referral_dm': 'Hi [Name], I have built Kafka pipelines.'})
check('tool from JD still blocked', any(x['detail'] == 'kafka' for x in v))

# 8. framing + singular forms + generic words
out, v = g2.clean({'bullets': [{'src': 'x2', 'text': 'Reduced p95 latency from 900 ms to 250 ms with Redis caching in a distributed system'},
                               {'src': 'x1', 'text': 'Built a refund microservice in Java and Spring Boot handling about 40,000 refunds a day'}]})
check('distributed system blocked', any(x['detail'] == 'distributed system' for x in v))
check('singular microservice blocked', any(x['detail'] == 'microservice' for x in v))
g3 = Guard(json.load(open(os.path.join(HERE, 'profiles', 'meera_mba_marketing.json'), encoding='utf-8')))
out, v = g3.clean({'headline': 'Marketing associate who runs research-led campaigns on Google Ads and Meta Ads'})
check('generic words like research/marketing not blocked', v == [])

# 9. DM keeps honest sentences and job-title numbers, drops the invented sentence
g4 = Guard(rohan, job_title='Software Engineer - SaaS O365')
out, v = g4.clean({'referral_dm': 'Hi [Name], I am applying for the SaaS O365 role. I built a Java refund service handling 40,000 refunds a day. I also know Kubernetes. Could you refer me?'})
check('DM keeps honest sentences, drops invented one', 'Kubernetes' not in out['referral_dm'] and 'O365' in out['referral_dm'] and 'refer me' in out['referral_dm'])

print('\n%d failed' % fails)
raise SystemExit(1 if fails else 0)
