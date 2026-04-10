# AutoPedia

AutoPedia is a GitHub Pages-ready autonomous wiki generator. One cycle does the following:

1. AI selects the next topic to cover.
2. A multi-turn web research pass collects large batches of search results and fetches source pages.
3. A detailed report with at least 2000 lines is written under the reports directory.
4. The report is distilled into a Markdown wiki page under docs/wiki.
5. Users can request a brand new topic or ask an existing page to update/expand from the published site.
6. GitHub Actions commits the result, deploys the site, and can immediately queue the next cycle.

If AutoPedia cannot fetch enough grounded references, it refuses to publish the wiki page and leaves the report behind for inspection.

## What Is Included

- A Python pipeline for planning, searching, fetching, synthesizing, and writing pages.
- A GitHub Actions workflow that continuously self-dispatches after each automatic generation cycle.
- A GitHub Actions workflow that processes GitHub Issue-based page update and new-topic requests.
- A GitHub Pages deployment workflow using MkDocs Material.
- A white-first modern UI with dark mode and a generated landing page.

## 24/7 Continuous Mode

GitHub Actions cannot keep one single process alive forever, but AutoPedia is configured to behave like a practical nonstop loop on GitHub-hosted runners:

1. One cycle finishes.
2. The workflow immediately dispatches the next cycle.
3. A `*/5` cron trigger restarts the chain if a dispatch is dropped or a run fails unexpectedly.
4. Every successful content commit triggers the GitHub Pages deployment workflow automatically.

This is the GitHub Actions-compatible way to run AutoPedia continuously without self-hosted infrastructure.

## Recommended Production Setup

For higher-quality research results, configure:

- An OpenAI-compatible model via `AUTOPEDIA_API_KEY`, `AUTOPEDIA_BASE_URL`, and `AUTOPEDIA_MODEL`
- `AUTOPEDIA_GITHUB_REPOSITORY=owner/repo` so request buttons on the site can open GitHub Issues correctly
- A stronger model than the sample `llama-3` if you want better synthesis quality

Do not hardcode API keys into the repository. Put them in GitHub Secrets.

The default search stack is keyless and free: `ddgs`. You can optionally point AutoPedia at a self-hosted `SearXNG` instance via `AUTOPEDIA_SEARXNG_URL` if you want more control without adding API keys.

## Local Usage

```bash
python -m pip install -e .
python -m autopedia rebuild-site
python -m autopedia run-cycle
```

If no API key is configured, AutoPedia falls back to demo mode for the LLM layer. Web search and fetching still use the live network.

To run a requested topic manually from the terminal:

```bash
python -m autopedia --request-mode new-topic --topic-title "Closed-loop geothermal systems" --request-notes "Focus on deployment economics and drilling constraints" run-cycle
```

## GitHub Secrets

Create these repository secrets:

- `AUTOPEDIA_API_KEY`
- `AUTOPEDIA_BASE_URL`
- `AUTOPEDIA_MODEL`
- `AUTOPEDIA_WORKFLOW_TOKEN` (optional, but useful if your repository blocks self-dispatch with the default token)

Optional repository variables:

- `AUTOPEDIA_CONTINUOUS_LOOP=true`
- `AUTOPEDIA_GITHUB_REPOSITORY=owner/repo`
- `AUTOPEDIA_RESEARCH_TURNS=3`
- `AUTOPEDIA_MIN_PAGES_PER_TURN=100`
- `AUTOPEDIA_MAX_PAGES_PER_TURN=160`
- `AUTOPEDIA_SEARCH_RESULTS_PER_QUERY=24`
- `AUTOPEDIA_REPORT_MIN_LINES=2000`
- `AUTOPEDIA_MIN_REFERENCE_COUNT=8`

There is no longer a built-in cap on automatic consecutive cycles.

## User Request Flow

Published pages now include a `このWikiページを更新または拡張して` button.

The flow is:

1. A user clicks the page button or submits the topic request form on the home page.
2. The site opens a prefilled GitHub Issue request.
3. The user submits the Issue.
4. The `AutoPedia Request Issues` workflow parses the Issue and runs a full multi-turn deep-research refresh or new-page generation.
5. The workflow commits the updated page, comments on the Issue, and closes it on success.

GitHub Pages is static, so it cannot create Issues or dispatch workflows directly without GitHub authentication. The implemented Issue-driven flow is the practical GitHub-native way to keep the site static while still making requests one-click from the UI.

## Enable GitHub Pages

1. Push this repository to GitHub.
2. Open Settings -> Pages.
3. Set Source to `GitHub Actions`.
4. Run the `AutoPedia Cycle` workflow manually once.

After the first successful run, AutoPedia keeps chaining the next automatic cycle on GitHub Actions, and every successful content commit triggers `Deploy GitHub Pages` automatically.

## Project Structure

```text
.
|- .github/workflows/
|- autopedia/
|- data/site-state.json
|- docs/
|  |- index.md
|  |- wiki/
|  |- stylesheets/extra.css
|  |- javascripts/extra.js
|- reports/
|- mkdocs.yml
|- pyproject.toml
```

## Tuning For More Aggressive Research

If you want closer to 500 fetched pages per turn, increase:

- `AUTOPEDIA_MAX_PAGES_PER_TURN`
- `AUTOPEDIA_SEARCH_RESULTS_PER_QUERY`
- `AUTOPEDIA_FETCH_WORKERS`

Keep in mind that aggressive settings increase runtime, network failures, and the chance of hitting search-provider rate limits.
