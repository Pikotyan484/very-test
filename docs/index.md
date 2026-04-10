# AutoPedia

<section class="ap-hero">
  <div class="ap-hero__copy">
    <p class="ap-eyebrow">Continuous AI Research Wiki</p>
    <h1>AutoPedia</h1>
    <p class="ap-lead">AI picks the next topic, performs large-scale multi-turn web research, produces a long-form report, and turns that evidence into a GitHub Pages wiki.</p>
    <div class="ap-hero__actions">
      <a class="md-button md-button--primary" href="wiki/">Wiki Index</a>
      <a class="md-button" href="#request-topic">トピックを依頼</a>
      <a class="md-button" href="https://github.com">GitHub</a>
    </div>
  </div>
  <div class="ap-metrics">
    <div><span>0</span><small>pages</small></div>
    <div><span>0</span><small>sources</small></div>
    <div><span>--</span><small>latest run</small></div>
  </div>
</section>

## Latest Pages

<section class="ap-card-grid">
<article class="ap-card ap-card--empty"><p>No pages yet. Trigger the first AutoPedia cycle to generate one.</p></article>
</section>

## Request a Topic

> Request buttons become active after `AUTOPEDIA_GITHUB_REPOSITORY` is configured or the site is built on GitHub Actions.

## Pipeline

1. The planner chooses a topic that is not already covered.
2. The research engine runs multi-turn online search and bulk page retrieval.
3. A 2000+ line evidence report is written under the reports directory.
4. The writer converts distilled evidence into a Markdown wiki page.
5. Users can request new topics or page refreshes through GitHub Issue links and Actions processes them automatically.
6. GitHub Actions commits the result, deploys GitHub Pages, and can immediately queue the next cycle.

## Notes

- Accuracy still depends on the configured model and search provider quality.
- The default search path is keyless and free: DDGS, with optional self-hosted SearXNG for more control.
- The site intentionally keeps reports in the repository so the generation trail stays auditable.
