"""Fetch merged feature PRs of symfony/ai (from git history) plus their GitHub data into cache/."""
import json, os, re, subprocess, sys

REPO_DIR = sys.argv[1]
HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, '..', 'cache')
os.makedirs(os.path.join(CACHE, 'pr'), exist_ok=True)
os.makedirs(os.path.join(CACHE, 'files'), exist_ok=True)


def git(*args):
    return subprocess.check_output(['git', '-C', REPO_DIR, *args], text=True)


def gh(*args, input=None):
    return subprocess.check_output(['gh', *args], text=True, input=input)


features = []
for line in git('log', 'upstream/main', '--format=%H%x1f%cI%x1f%s', '--grep=^feature #').splitlines():
    sha, date, subject = line.split('\x1f')
    m = re.match(r'^feature #(\d+) (.*?)(?: \(([^()]+)\))?$', subject)
    if not m:
        continue
    features.append({'number': int(m.group(1)), 'sha': sha, 'date': date, 'subject': m.group(2), 'authors': m.group(3)})

releases = []
for line in git('for-each-ref', '--format=%(refname:short)\x1f%(creatordate:iso-strict)\x1f%(objectname)', 'refs/tags/v0.*').splitlines():
    tag, date, sha = line.split('\x1f')
    releases.append({'tag': tag, 'date': date})

missing = [f['number'] for f in features if not os.path.exists(os.path.join(CACHE, 'pr', f"{f['number']}.json"))]
print(f'{len(features)} features, {len(missing)} to fetch', file=sys.stderr)
for i in range(0, len(missing), 40):
    chunk = missing[i:i + 40]
    fields = ' '.join(
        f'p{n}: pullRequest(number: {n}) {{ number title body url mergedAt author {{ login }} labels(first: 20) {{ nodes {{ name }} }} }}'
        for n in chunk
    )
    query = f'query {{ repository(owner: "symfony", name: "ai") {{ {fields} }} }}'
    data = json.loads(gh('api', 'graphql', '-f', f'query={query}'))
    for key, pr in data['data']['repository'].items():
        if pr:
            with open(os.path.join(CACHE, 'pr', f"{pr['number']}.json"), 'w') as fh:
                json.dump(pr, fh)
    print(f'  fetched {i + len(chunk)}/{len(missing)}', file=sys.stderr)

with open(os.path.join(CACHE, 'git.json'), 'w') as fh:
    json.dump({'features': features, 'releases': releases}, fh)
