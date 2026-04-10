function initPage() {
  const targets = document.querySelectorAll(".ap-card, .ap-hero, .ap-meta-card, .ap-reference-card, .md-typeset h2, .md-typeset table, .md-typeset .admonition");
  if (targets.length && "IntersectionObserver" in window) {
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
  }
  initializeTranslationShells();
  initializeRequestForms();
}

// MkDocs Material navigation.instant uses document$ observable instead of DOMContentLoaded
if (typeof document$ !== "undefined") {
  document$.subscribe(initPage);
} else {
  document.addEventListener("DOMContentLoaded", initPage);
}

function initializeTranslationShells() {
  const shells = document.querySelectorAll("[data-ap-translation-shell]");
  if (!shells.length) {
    return;
  }

  shells.forEach((shell) => {
    const buttons = [...shell.querySelectorAll("[data-ap-language-button]")];
    const views = [...shell.querySelectorAll("[data-ap-language-view]")];
    if (!buttons.length || !views.length) {
      return;
    }

    // Default to the first button (site language = ja). No localStorage persistence
    // so the site language is always shown first on every page load.
    const defaultLanguage = buttons[0].getAttribute("data-ap-language-button");

    const applyLanguage = (languageCode) => {
      buttons.forEach((button) => {
        const isActive = button.getAttribute("data-ap-language-button") === languageCode;
        button.classList.toggle("is-active", isActive);
        button.setAttribute("aria-pressed", isActive ? "true" : "false");
      });

      views.forEach((view) => {
        const isActive = view.getAttribute("data-ap-language-view") === languageCode;
        view.classList.toggle("is-active", isActive);
        view.hidden = !isActive;
      });
    };

    buttons.forEach((button) => {
      button.addEventListener("click", () => {
        const languageCode = button.getAttribute("data-ap-language-button");
        if (languageCode) {
          applyLanguage(languageCode);
        }
      });
    });

    if (defaultLanguage) {
      applyLanguage(defaultLanguage);
    }
  });
}

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
