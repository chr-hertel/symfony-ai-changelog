"""Turn cached git + GitHub data into site/data.json for the feature timeline."""
import glob, html, json, os, re, shutil, sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, '..', 'cache')
SITE = os.path.join(HERE, '..', 'site')
OUT = os.path.join(SITE, 'data.json')
TEMPLATE = os.path.join(HERE, '..', 'template', 'index.html')
REPO_DIR = sys.argv[1] if len(sys.argv) > 1 else None

COMPONENTS = ['Platform', 'Agent', 'Store', 'Chat', 'AI Bundle', 'MCP Bundle', 'Mate', 'Demo', 'Examples', 'Website', 'MCP SDK']
ALIASES = {'aibundle': 'AI Bundle', 'ai bundle': 'AI Bundle', 'ai-bundle': 'AI Bundle', 'mcpbundle': 'MCP Bundle',
           'mcp bundle': 'MCP Bundle', 'mcp-bundle': 'MCP Bundle', 'mcp sdk': 'MCP SDK', 'docs': 'Docs', 'documentation': 'Docs'}
BRIDGE_HOME = {'openrouter': 'Platform', 'openai': 'Platform', 'ai/ml api': 'Platform', 'elasticsearch': 'Store'}
MAX_LINES = 22


def norm_component(name):
    low = name.strip().lower()
    if low in ALIASES:
        return ALIASES[low]
    for c in COMPONENTS:
        if c.lower() == low:
            return c
    return None


def parse_subject(subject):
    tags = re.findall(r'\[([^\]]+)\]', re.match(r'^((?:\s*\[[^\]]+\])*)', subject).group(1))
    title = re.sub(r'^(\s*\[[^\]]+\])*\s*', '', subject).strip()
    title = re.sub(r'\s*\(#\d+\)$', '', title)
    title = title[:1].upper() + title[1:]
    components, bridges = [], []
    for t in tags:
        c = norm_component(t)
        if c:
            components.append(c)
        else:
            bridges.append(t.strip())
            home = BRIDGE_HOME.get(t.strip().lower())
            if home and not components:
                components.append(home)
    return title, components, bridges


def clean_md(text):
    text = re.sub(r'<!--.*?-->', '', text, flags=re.S)
    text = re.sub(r'!\[[^\]]*\]\([^)]*\)', '', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    return re.sub(r'\s+', ' ', text).strip()


def shorten(text, limit=300):
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind('. '), cut.rfind('! '), cut.rfind('? '))
    if end > 80:
        return cut[:end + 1]
    return cut[:cut.rfind(' ')].rstrip(',;:') + ' …'


SKIP_PARA = re.compile(r'^(\||#|>|🤖|-{3,}|fix(es)? #|closes? #|replaces? #|supersedes|follow[- ]up|related|depends on|requires #|based on|cc @|todo|\* \[)', re.I)


def summary_from_body(body):
    body = re.sub(r'```.*?```', '\n\n', body or '', flags=re.S)
    for para in re.split(r'\n\s*\n', body):
        p = para.strip()
        if not p or SKIP_PARA.match(p):
            continue
        lines = [l for l in p.splitlines() if not re.match(r'^\s*\|', l)]
        if not lines:
            continue
        if all(re.match(r'^\s*[-*] ', l) for l in lines) and len(lines) > 1:
            text = '; '.join(clean_md(re.sub(r'^\s*[-*] ', '', l)) for l in lines[:3])
        else:
            text = clean_md(' '.join(lines))
        text = re.sub(r'^(this pr|this pull request|this change)\s+', '', text, flags=re.I)
        text = text[:1].upper() + text[1:]
        if len(text) >= 40:
            return shorten(text)
    return None


def trim_code(code):
    lines = code.rstrip().splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    if lines and lines[0].strip() == '<?php':
        lines.pop(0)
        while lines and not lines[0].strip():
            lines.pop(0)
    indent = min((len(l) - len(l.lstrip()) for l in lines if l.strip()), default=0)
    lines = [l[indent:] for l in lines]
    if len(lines) > MAX_LINES:
        lines = lines[:MAX_LINES] + ['// …']
    return '\n'.join(lines)


LANG_RANK = {'php': 0, 'yaml': 1, 'yml': 1, 'twig': 2, 'bash': 3, 'shell': 3, 'sh': 3, 'console': 3, 'terminal': 3, 'json': 4, 'xml': 4, '': 5}


def lang_of(raw):
    raw = (raw or '').strip().lower()
    return {'yml': 'yaml', 'shell': 'bash', 'sh': 'bash', 'console': 'bash', 'terminal': 'bash', 'html+twig': 'twig', 'diff': 'diff'}.get(raw, raw)


def snippet_from_body(body):
    blocks = []
    for m in re.finditer(r'```([\w+-]*)[^\n]*\n(.*?)```', body or '', flags=re.S):
        lang = lang_of(m.group(1))
        code = m.group(2)
        if not code.strip() or lang in ('diff', 'text', 'log') or 'Fatal error' in code or 'Stack trace' in code:
            continue
        if lang == '' and re.search(r'\$\w+|->|::|use [A-Z]', code):
            lang = 'php'
        blocks.append((LANG_RANK.get(lang, 6), len(blocks), lang or 'text', code))
    if not blocks:
        return None
    rank, _, lang, code = sorted(blocks)[0]
    return {'lang': lang, 'code': trim_code(code), 'source': 'pr'}


def added_lines(patch):
    return [l[1:] for l in (patch or '').splitlines() if l.startswith('+') and not l.startswith('+++')]


def rst_blocks(lines):
    blocks, i = [], 0
    while i < len(lines):
        m = re.match(r'^(\s*)\.\. code-block::\s*(\S+)', lines[i])
        if m:
            base = len(m.group(1))
            j, body = i + 1, []
            while j < len(lines) and (not lines[j].strip() or len(lines[j]) - len(lines[j].lstrip()) > base):
                body.append(lines[j])
                j += 1
            if any(l.strip() for l in body):
                blocks.append((lang_of(m.group(2)), '\n'.join(body)))
            i = j
        else:
            i += 1
    return blocks


def snippet_from_files(files):
    candidates = []
    for f in files:
        name, added = f['filename'], added_lines(f.get('patch'))
        if not added:
            continue
        if name.startswith('docs/') and name.endswith('.rst'):
            for lang, code in rst_blocks(added):
                candidates.append((0, LANG_RANK.get(lang, 6), lang, code, 'docs'))
        elif name.endswith('README.md'):
            for m in re.finditer(r'```([\w+-]*)\n(.*?)```', '\n'.join(added), flags=re.S):
                lang = lang_of(m.group(1))
                candidates.append((1, LANG_RANK.get(lang, 6), lang or 'text', m.group(2), 'readme'))
        elif name.startswith('examples/') and name.endswith('.php') and f['status'] == 'added':
            code = '\n'.join(added)
            code = re.sub(r'^.*?\n(?=\$|use )', '', code, count=1, flags=re.S) if '<?php' in code else code
            body = [l for l in code.splitlines() if not re.match(r'^(use |require|/\*|\s\*|declare|namespace)', l)]
            start = next((k for k, l in enumerate(body) if l.startswith('$')), 0)
            candidates.append((2, 0, 'php', '\n'.join(body[start:]), 'example'))
    candidates = [c for c in candidates if c[3].strip() and c[2] not in ('diff', 'text')]
    if not candidates:
        return None
    _, _, lang, code, source = sorted(candidates, key=lambda c: (c[0], c[1]))[0]
    return {'lang': lang, 'code': trim_code(code), 'source': source}


def changelog_entry(files):
    for f in files:
        if f['filename'].endswith('CHANGELOG.md'):
            for l in added_lines(f.get('patch')):
                m = re.match(r'^\s*\*\s+(.+)', l)
                if m and len(m.group(1)) > 15:
                    return shorten(clean_md(m.group(1).replace('`', '')))
    return None


def title_key(subject):
    return re.sub(r'[^a-z0-9]', '', re.sub(r'^(\s*\[[^\]]+\])*', '', subject).lower())


def main():
    git = json.load(open(os.path.join(CACHE, 'git.json')))
    curated = {}
    curated_path = os.path.join(HERE, '..', 'curated.json')
    if os.path.exists(curated_path):
        curated = json.load(open(curated_path))
    releases = sorted(({'tag': r['tag'], 'date': r['date']} for r in git['releases']), key=lambda r: r['date'])
    entries = []
    subjects = {}
    for f in git['features']:
        subjects[title_key(f['subject'])] = subjects.get(title_key(f['subject']), 0) + 1
    for f in git['features']:
        path = os.path.join(CACHE, 'pr', f"{f['number']}.json")
        pr = json.load(open(path)) if os.path.exists(path) else {}
        if subjects[title_key(f['subject'])] > 1 and title_key(pr.get('title', '')) != title_key(f['subject']):
            continue
        files_path = os.path.join(CACHE, 'files', f"{f['number']}.json")
        files = json.load(open(files_path)) if os.path.exists(files_path) else []
        title, components, bridges = parse_subject(f['subject'])
        for label in (l['name'] for l in pr.get('labels', {}).get('nodes', [])):
            c = norm_component(label)
            if c and c not in components:
                components.append(c)
        if not components:
            components = ['Other']
        body = pr.get('body') or ''
        snippet = snippet_from_body(body) or snippet_from_files(files)
        summary = summary_from_body(body) or changelog_entry(files)
        override = curated.get(str(f['number']))
        if override:
            summary = override.get('summary') or summary
            if 'snippet' in override:
                snippet = override['snippet'] and {'lang': override['snippet']['lang'], 'code': trim_code(override['snippet']['code']), 'source': 'curated'}
        release = next((r['tag'] for r in releases if r['date'] >= f['date']), None)
        entries.append({
            'number': f['number'], 'title': title, 'date': f['date'], 'components': components, 'bridges': bridges,
            'authors': f['authors'], 'url': pr.get('url') or f"https://github.com/symfony/ai/pull/{f['number']}",
            'summary': summary, 'snippet': snippet, 'release': release,
        })
    entries.sort(key=lambda e: e['date'], reverse=True)
    counts = {}
    for e in entries:
        for c in e['components']:
            counts[c] = counts.get(c, 0) + 1
    data = {
        'generatedAt': datetime.now().astimezone().isoformat(timespec='seconds'),
        'components': sorted(counts.items(), key=lambda kv: -kv[1]),
        'releases': [{**r, 'features': sum(1 for e in entries if e['release'] == r['tag'])} for r in reversed(releases)],
        'features': entries,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(data, open(OUT, 'w'), separators=(',', ':'))
    with_snip = sum(1 for e in entries if e['snippet'])
    with_sum = sum(1 for e in entries if e['summary'])
    print(f'{len(entries)} features, {with_snip} snippets, {with_sum} summaries, {os.path.getsize(OUT)} bytes', file=sys.stderr)

    if REPO_DIR:
        assemble(data)


def svg(path):
    return re.sub(r'\s+', ' ', open(path).read()).strip()


def assemble(data):
    site_assets = os.path.join(REPO_DIR, 'ai.symfony.com', 'assets')
    icons = os.path.join(site_assets, 'icons')
    page = open(TEMPLATE).read()
    replacements = {
        '%LOGO%': svg(os.path.join(REPO_DIR, 'ai.symfony.com', 'templates', '_symfony-ai-logo.svg')),
        '%ICON_GITHUB%': svg(os.path.join(icons, 'simple-icons', 'github.svg')),
        '%ICON_AUTO%': svg(os.path.join(icons, 'tabler', 'contrast-filled.svg')),
        '%ICON_LIGHT%': svg(os.path.join(icons, 'tabler', 'sun-filled.svg')),
        '%ICON_DARK%': svg(os.path.join(icons, 'tabler', 'moon.svg')),
        '%ICON_ARROW%': svg(os.path.join(icons, 'tabler', 'arrow-up-right.svg')).replace("'", '"'),
    }
    for key, value in replacements.items():
        page = page.replace(key, value)
    open(os.path.join(SITE, 'index.html'), 'w').write(page)
    os.makedirs(os.path.join(SITE, 'fonts'), exist_ok=True)
    for font in ('ubuntu-sans-variable-latin.woff2', 'JetBrainsMono-Regular.woff2', 'UbuntuSans-LICENCE.txt', 'JetBrainsMono-OFL.txt'):
        shutil.copy(os.path.join(site_assets, 'fonts', font), os.path.join(SITE, 'fonts', font))
    shutil.copy(os.path.join(site_assets, 'images', 'favicons', 'favicon.svg'), os.path.join(SITE, 'favicon.svg'))
    write_feed(data)
    base = 'https://symfony-ai.space.fast/'
    open(os.path.join(SITE, 'robots.txt'), 'w').write('User-agent: *\nAllow: /\n\nSitemap: ' + base + 'sitemap.xml\n')
    open(os.path.join(SITE, 'sitemap.xml'), 'w').write(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        '<url><loc>' + base + '</loc><lastmod>' + data['generatedAt'][:10] + '</lastmod></url></urlset>\n')
    not_found = re.sub(r'<main.*?</main>', '<main class="container" style="padding-block:96px"><h1 class="ff-title">Page not found</h1>'
                       '<p>This address does not exist. <a href="/" style="color:var(--sf-ai-link-color)">Go to the feature timeline</a>.</p></main>', page, flags=re.S)
    not_found = re.sub(r'<section class="hero.*?</section>', '', not_found, flags=re.S)
    not_found = re.sub(r'<script>\n\(function \(\) \{\n    \'use strict\'.*?</script>', '', not_found, flags=re.S)
    not_found = not_found.replace('<title>Symfony AI Feature Timeline</title>', '<title>Page not found · Symfony AI Feature Timeline</title>')
    not_found = not_found.replace('<link rel="canonical" href="https://symfony-ai.space.fast/">', '<meta name="robots" content="noindex">')
    open(os.path.join(SITE, '404.html'), 'w').write(not_found)


def write_feed(data):
    e = html.escape
    entries = []
    for f in data['features'][:60]:
        content = '<p>' + e(f['summary'] or '') + '</p>'
        if f['snippet']:
            content += '<pre><code>' + e(f['snippet']['code']) + '</code></pre>'
        content += '<p><a href="' + e(f['url']) + '">#' + str(f['number']) + '</a>' + (' by ' + e(f['authors']) if f['authors'] else '') + '</p>'
        entries.append(
            '<entry><id>' + e(f['url']) + '</id><title>' + e('[' + ', '.join(f['components']) + '] ' + f['title']) + '</title>'
            '<updated>' + f['date'] + '</updated><link href="' + e(f['url']) + '"/>'
            + ''.join('<category term="' + e(c) + '"/>' for c in f['components'])
            + '<content type="html">' + e(content) + '</content></entry>'
        )
    updated = data['features'][0]['date'] if data['features'] else data['generatedAt']
    feed = ('<?xml version="1.0" encoding="utf-8"?>\n<feed xmlns="http://www.w3.org/2005/Atom">'
            '<title>Symfony AI features</title><subtitle>Every feature merged into Symfony AI, newest first.</subtitle>'
            '<id>urn:symfony-ai:feature-timeline</id><updated>' + updated + '</updated>'
            '<link href="https://github.com/symfony/ai"/><author><name>Symfony AI contributors</name></author>'
            + ''.join(entries) + '</feed>\n')
    open(os.path.join(SITE, 'feed.xml'), 'w').write(feed)


main()
