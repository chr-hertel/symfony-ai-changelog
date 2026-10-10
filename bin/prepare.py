"""Write compact per-batch inputs for curating summaries and snippets."""
import json, os, re, glob, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
data = json.load(open(os.path.join(ROOT, 'site', 'data.json')))
curated_path = os.path.join(ROOT, 'curated.json')
curated = json.load(open(curated_path)) if os.path.exists(curated_path) else {}
todo = [e for e in data['features'] if str(e['number']) not in curated]
os.makedirs(os.path.join(ROOT, 'work'), exist_ok=True)
def patch_digest(n):
    p = os.path.join(ROOT, 'cache', 'files', f'{n}.json')
    if os.path.exists(p):
        files = json.load(open(p))
    else:
        out = subprocess.check_output(['gh', 'api', '--paginate', f'repos/symfony/ai/pulls/{n}/files?per_page=100', '--jq', '[.[] | {filename, status, patch}]'], text=True)
        files = [x for c in out.split('\n') if c.strip() for x in json.loads(c)]
        json.dump(files, open(p, 'w'))
    def prio(f):
        n = f['filename']
        if 'CHANGELOG' in n: return 0
        if n.startswith('docs/') or n.endswith('README.md'): return 1
        if n.startswith('examples/'): return 2
        if '/Tests/' in n or '/tests/' in n: return 5
        if n.endswith('.php'): return 3
        return 4
    parts, budget = [], 7000
    for f in sorted(files, key=prio):
        added = '\n'.join(l[1:] for l in (f.get('patch') or '').splitlines() if l.startswith('+') and not l.startswith('+++'))
        if not added.strip() or prio(f) == 5: continue
        chunk = f"### {f['filename']} ({f['status']})\n{added[:2500]}\n"
        if len(chunk) > budget: chunk = chunk[:budget]
        parts.append(chunk); budget -= len(chunk)
        if budget <= 200: break
    return ''.join(parts) + ('\n(other files: ' + ', '.join(f['filename'] for f in files[:40]) + ')')
size = 70
batches = [todo[i:i+size] for i in range(0, len(todo), size)]
for bi, batch in enumerate(batches):
    with open(os.path.join(ROOT, 'work', f'batch{bi}.md'), 'w') as fh:
        for e in batch:
            pr = json.load(open(os.path.join(ROOT, 'cache', 'pr', f"{e['number']}.json")))
            body = re.sub(r'^\|.*\n', '', pr.get('body') or '', flags=re.M)
            body = re.sub(r'<!--.*?-->', '', body, flags=re.S).strip()[:3000]
            fh.write(f"\n\n======== PR #{e['number']} ========\nTitle: {e['title']}\nComponents: {', '.join(e['components'])} | Bridges: {', '.join(e['bridges']) or '-'}\n--- Description ---\n{body}\n--- Added lines ---\n{patch_digest(e['number'])}\n")
print(len(todo), len(batches))
