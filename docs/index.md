# AutoPedia

<section class="ap-hero">
  <div class="ap-hero__copy">
    <p class="ap-eyebrow">Continuous AI Research Wiki</p>
    <h1>AutoPedia</h1>
    <p class="ap-lead">AI picks the next topic, performs large-scale multi-turn web research, produces a long-form report, and turns that evidence into a GitHub Pages wiki.</p>
    <div class="ap-hero__actions">
      <a class="md-button md-button--primary" href="wiki/">Wiki Index</a>
      <a class="md-button" href="#request-topic">トピックを依頼</a>
      <a class="md-button" href="https://github.com/Pikotyan484/very-test">GitHub</a>
    </div>
  </div>
  <div class="ap-metrics">
    <div><span>2</span><small>pages</small></div>
    <div><span>139</span><small>sources</small></div>
    <div><span>2026-04-10</span><small>latest run</small></div>
  </div>
</section>

## Latest Pages

<section class="ap-card-grid">
<article class="ap-card">
  <span class="ap-card__kicker">2026-04-10</span>
  <h3><a href="wiki/mrna-vaccine-manufacturing.md">mRNA vaccine manufacturing</a></h3>
  <p>mRNA vaccine manufacturing is selected because it has active scientific, industrial, and policy developments that reward a high-evidence synthesis.</p>
  <div class="ap-card__meta">20 sources</div>
  <div class="ap-card__actions"><a href="https://github.com/Pikotyan484/very-test/issues/new?title=%5BExpand+Page%5D+mRNA+vaccine+manufacturing&body=%23%23+Request+Type%0Aexpand-page%0A%0A%23%23+Topic+Title%0AmRNA+vaccine+manufacturing%0A%0A%23%23+Topic+Slug%0Amrna-vaccine-manufacturing%0A%0A%23%23+Request+Notes%0APlease+update+this+page+and+expand+missing+sections+with+newer+evidence.%0A%0A%23%23+Existing+Page%0Adocs%2Fwiki%2Fmrna-vaccine-manufacturing.md%0A&labels=autopedia-request%2Cexpand-page" target="_blank" rel="noopener">更新または拡張</a></div>
</article>
<article class="ap-card">
  <span class="ap-card__kicker">2026-04-10</span>
  <h3><a href="wiki/quantum-error-correction.md">Quantum error correction</a></h3>
  <p>Quantum error correction is selected because it has active scientific, industrial, and policy developments that reward a high-evidence synthesis.</p>
  <div class="ap-card__meta">119 sources</div>
  <div class="ap-card__actions"><a href="https://github.com/Pikotyan484/very-test/issues/new?title=%5BExpand+Page%5D+Quantum+error+correction&body=%23%23+Request+Type%0Aexpand-page%0A%0A%23%23+Topic+Title%0AQuantum+error+correction%0A%0A%23%23+Topic+Slug%0Aquantum-error-correction%0A%0A%23%23+Request+Notes%0APlease+update+this+page+and+expand+missing+sections+with+newer+evidence.%0A%0A%23%23+Existing+Page%0Adocs%2Fwiki%2Fquantum-error-correction.md%0A&labels=autopedia-request%2Cexpand-page" target="_blank" rel="noopener">更新または拡張</a></div>
</article>
</section>

<section id="request-topic" class="ap-request-panel">
  <div class="ap-request-panel__copy">
    <p class="ap-eyebrow">User Requests</p>
    <h2>希望のトピックをAIに依頼</h2>
    <p>ここで話題名と要望を書いて送ると、GitHub Issue が作成され、その Issue をトリガーに GitHub Actions が全自動で long deep research と wiki 生成を実行します。</p>
  </div>
  <form class="ap-request-form" data-autopedia-request-form data-issues-url="https://github.com/Pikotyan484/very-test/issues/new">
    <label><span>Topic Title</span><input type="text" name="topic_title" placeholder="Example: Solid-state batteries" required></label>
    <label><span>What should be covered?</span><textarea name="request_notes" rows="5" placeholder="Example: Focus on commercialization, safety constraints, and latest performance benchmarks."></textarea></label>
    <button class="md-button md-button--primary" type="submit">新しいWikiを依頼する</button>
  </form>
</section>

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
