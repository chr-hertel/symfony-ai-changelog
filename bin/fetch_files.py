"""Fetch changed-file patches for PRs whose description has no code block."""
import json, glob, os, re, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, '..', 'cache')
todo = []
for f in glob.glob(os.path.join(CACHE, 'pr', '*.json')):
    pr = json.load(open(f))
    out = os.path.join(CACHE, 'files', f"{pr['number']}.json")
    if '```' not in (pr['body'] or '') and not os.path.exists(out):
        todo.append((pr['number'], out))
def run(item):
    n, out = item
    try:
        data = subprocess.check_output(['gh', 'api', '--paginate', f'repos/symfony/ai/pulls/{n}/files?per_page=100',
            '--jq', '[.[] | {filename, status, patch}]'], text=True)
        files = [x for chunk in data.split('\n') if chunk.strip() for x in json.loads(chunk)]
        json.dump(files, open(out, 'w'))
    except subprocess.CalledProcessError as e:
        print('fail', n, file=sys.stderr)
with ThreadPoolExecutor(8) as ex:
    list(ex.map(run, todo))
print(len(todo), file=sys.stderr)
