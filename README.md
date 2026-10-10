# Symfony AI Feature Timeline

A static page listing every feature merged into [symfony/ai](https://github.com/symfony/ai), newest first, with a
short description, a code sample, component tags and release markers. Published at https://symfony-ai.space.fast/.

## Requirements

- Python 3
- `gh`, authenticated with GitHub
- A checkout of symfony/ai with an `upstream` remote pointing at `symfony/ai` (the build also reads the logo, icons
  and fonts from its `ai.symfony.com/` directory)

## Build

```bash
REPO=~/Projects/SymfonyAI/repo

git -C $REPO fetch upstream --tags
python3 bin/fetch.py $REPO          # feature merges + release tags from git, PR data from GitHub into cache/
python3 bin/fetch_files.py          # PR diffs for PRs without code in their description
python3 bin/build.py $REPO          # writes site/
```

`fetch.py` only fetches PRs that are not in `cache/` yet.

## Summaries and snippets

`build.py` takes each feature's summary and snippet from `curated.json` (keyed by PR number). Features missing there
fall back to text extracted automatically: the first paragraph of the PR description and its first code block, or a
code block added to the docs, a README or an example.

To write entries for new features, run `python3 bin/prepare.py`. It writes the missing features with their
description and added lines to `work/batch*.md`; add the resulting entries to `curated.json`:

```json
{"2640": {"summary": "One or two sentences.", "snippet": {"lang": "php", "code": "..."}}}
```

Use `"snippet": null` for features without user-facing usage.

## Publish

```bash
npx -y spacefast publish site --space spc_b2204060218e487ab86fdbae9c339899 --json
```
