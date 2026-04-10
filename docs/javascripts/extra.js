document.addEventListener("DOMContentLoaded", () => {
  const targets = document.querySelectorAll(".ap-card, .ap-hero, .md-typeset h2, .md-typeset table, .md-typeset .admonition");
  if (!targets.length || !("IntersectionObserver" in window)) {
    initializeRequestForms();
    return;
  }

  const observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        }
      }
    },
    { threshold: 0.15 }
  );

  targets.forEach((target) => {
    target.classList.add("ap-reveal");
    observer.observe(target);
  });

  initializeRequestForms();
});

function initializeRequestForms() {
  const forms = document.querySelectorAll("[data-autopedia-request-form]");
  if (!forms.length) {
    return;
  }

  forms.forEach((form) => {
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const issuesUrl = form.getAttribute("data-issues-url");
      if (!issuesUrl) {
        return;
      }

      const topicInput = form.querySelector('[name="topic_title"]');
      const notesInput = form.querySelector('[name="request_notes"]');
      const topicTitle = topicInput ? topicInput.value.trim() : "";
      const requestNotes = notesInput ? notesInput.value.trim() : "";
      if (!topicTitle) {
        topicInput?.focus();
        return;
      }

      const topicSlug = slugifyTopic(topicTitle);
      const body = [
        "## Request Type",
        "new-topic",
        "",
        "## Topic Title",
        topicTitle,
        "",
        "## Topic Slug",
        topicSlug,
        "",
        "## Request Notes",
        requestNotes || "Please research and create a new AutoPedia page for this topic.",
        "",
      ].join("\n");

      const url = new URL(issuesUrl);
      url.searchParams.set("title", `[New Topic] ${topicTitle}`);
      url.searchParams.set("labels", "autopedia-request,new-topic");
      url.searchParams.set("body", body);
      window.open(url.toString(), "_blank", "noopener");
    });
  });
}

function slugifyTopic(value) {
  return value
    .normalize("NFKD")
    .replace(/[^\w\s-]/g, "")
    .trim()
    .toLowerCase()
    .replace(/[\s_-]+/g, "-")
    .replace(/^-+|-+$/g, "") || "requested-topic";
}
