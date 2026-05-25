const state = {
  sources: [],
  outputDir: "",
  custodians: [
    { display_name: "Executive sponsor", email: "", aliases: "" },
    { display_name: "Complainant", email: "", aliases: "" },
  ],
  keywords: [
    {
      name: "harassment and retaliation",
      terms: "harass\nhostile work environment\nretaliation\ncomplaint\ninappropriate",
    },
    {
      name: "sexual misconduct",
      terms: "sexual\nunwanted\ntouch\nquid pro quo\nadvances\nconsent",
    },
    {
      name: "executive concealment",
      terms: "off the record\nsettlement\nNDA\ndo not forward\ndelete this\nconfidential",
    },
  ],
  plan: null,
  run: null,
};

const views = {
  matter: document.querySelector("#matter-view"),
  plan: document.querySelector("#plan-view"),
  review: document.querySelector("#review-view"),
  exports: document.querySelector("#exports-view"),
};

const titles = {
  matter: "Build the matter file",
  plan: "Approve the search plan",
  review: "Review evidence hits",
  exports: "Manage export artifacts",
};

document.querySelectorAll(".nav-item").forEach((button) => {
  button.addEventListener("click", () => activateView(button.dataset.view));
});

document.querySelector("#add-custodian").addEventListener("click", () => {
  state.custodians.push({ display_name: "", email: "", aliases: "" });
  renderCustodians();
});

document.querySelector("#add-keyword").addEventListener("click", () => {
  state.keywords.push({ name: "new keyword set", terms: "" });
  renderKeywords();
});

document.querySelector("#select-sources").addEventListener("click", async () => {
  const files = await window.opensore.selectSources();
  state.sources = unique([...state.sources, ...files]);
  renderSources();
});

document.querySelector("#select-output").addEventListener("click", async () => {
  const folder = await window.opensore.selectOutput();
  if (folder) {
    state.outputDir = folder;
    renderOutput();
  }
});

document.querySelector("#plan-button").addEventListener("click", async () => {
  await planDiscovery();
});

document.querySelector("#run-button").addEventListener("click", async () => {
  await runDiscovery();
});

function activateView(name) {
  for (const [viewName, element] of Object.entries(views)) {
    element.classList.toggle("active", viewName === name);
  }
  document.querySelectorAll(".nav-item").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === name);
  });
  document.querySelector("#page-title").textContent = titles[name];
}

function renderCustodians() {
  const list = document.querySelector("#custodian-list");
  list.innerHTML = "";
  state.custodians.forEach((custodian, index) => {
    const row = document.createElement("div");
    row.className = "row-card";
    row.innerHTML = `
      <label>Name<input value="${escapeHtml(custodian.display_name)}" data-field="display_name" /></label>
      <label>Email<input value="${escapeHtml(custodian.email)}" data-field="email" /></label>
      <button class="remove" title="Remove custodian">x</button>
    `;
    row.querySelectorAll("input").forEach((input) => {
      input.addEventListener("input", () => {
        state.custodians[index][input.dataset.field] = input.value;
      });
    });
    row.querySelector(".remove").addEventListener("click", () => {
      state.custodians.splice(index, 1);
      renderCustodians();
    });
    list.appendChild(row);
  });
}

function renderKeywords() {
  const list = document.querySelector("#keyword-list");
  list.innerHTML = "";
  state.keywords.forEach((keyword, index) => {
    const row = document.createElement("div");
    row.className = "row-card keyword-card";
    row.innerHTML = `
      <label>Name<input value="${escapeHtml(keyword.name)}" data-field="name" /></label>
      <label>Terms<textarea data-field="terms">${escapeHtml(keyword.terms)}</textarea></label>
      <button class="remove" title="Remove keyword set">x</button>
    `;
    row.querySelectorAll("input, textarea").forEach((input) => {
      input.addEventListener("input", () => {
        state.keywords[index][input.dataset.field] = input.value;
      });
    });
    row.querySelector(".remove").addEventListener("click", () => {
      state.keywords.splice(index, 1);
      renderKeywords();
    });
    list.appendChild(row);
  });
}

function renderSources() {
  const list = document.querySelector("#source-files");
  list.innerHTML = "";
  if (state.sources.length === 0) {
    list.innerHTML = '<div class="file-item"><span>No source exports selected</span></div>';
    return;
  }
  state.sources.forEach((file, index) => {
    const item = document.createElement("div");
    item.className = "file-item";
    item.innerHTML = `<span>${escapeHtml(file)}</span><button class="remove">x</button>`;
    item.querySelector(".remove").addEventListener("click", () => {
      state.sources.splice(index, 1);
      renderSources();
    });
    list.appendChild(item);
  });
}

function renderOutput() {
  document.querySelector("#output-path").textContent =
    state.outputDir || "No output folder selected";
  renderArtifacts();
}

async function planDiscovery() {
  try {
    setBusy(true, "Planning...");
    state.plan = await window.opensore.planDiscovery(buildRequest());
    renderPlan();
    activateView("plan");
    toast("Discovery plan generated.");
  } catch (error) {
    toast(error.message || String(error));
  } finally {
    setBusy(false);
  }
}

async function runDiscovery() {
  try {
    if (state.sources.length === 0) {
      toast("Add at least one CSV, JSON, JSONL, or NDJSON export first.");
      return;
    }
    if (!state.outputDir) {
      const folder = await window.opensore.selectOutput();
      if (!folder) {
        return;
      }
      state.outputDir = folder;
      renderOutput();
    }

    setBusy(true, "Running...");
    state.run = await window.opensore.runDiscovery({
      request: buildRequest("local_csv"),
      sources: state.sources,
      outputDir: state.outputDir,
    });
    renderRun();
    activateView("review");
    toast(`Discovery complete. ${state.run.manifest.row_count} matched rows.`);
  } catch (error) {
    toast(error.message || String(error));
  } finally {
    setBusy(false);
  }
}

function buildRequest(exportTarget = "local_csv") {
  const custodians = state.custodians
    .map((custodian) => ({
      display_name: custodian.display_name.trim(),
      email: custodian.email.trim(),
      aliases: lines(custodian.aliases),
    }))
    .filter((custodian) => custodian.display_name || custodian.email || custodian.aliases.length);

  return {
    title: document.querySelector("#title").value,
    matter_type: document.querySelector("#matter-type").value,
    date_start: document.querySelector("#date-start").value || null,
    date_end: document.querySelector("#date-end").value || null,
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
    custodians,
    sources: [{ kind: "custom_csv", label: "Local export", scopes: ["read_export"] }],
    keyword_sets: state.keywords
      .map((keyword) => ({
        name: keyword.name.trim(),
        terms: lines(keyword.terms),
        category: "investigation",
      }))
      .filter((keyword) => keyword.name && keyword.terms.length),
    export_target: exportTarget,
    store_evidence_locally: false,
  };
}

function renderPlan() {
  const plan = state.plan;
  document.querySelector("#plan-meta").textContent = `${plan.queries.length} query units`;
  document.querySelector("#plan-metrics").innerHTML = metricMarkup([
    ["Sources", plan.source_count],
    ["Custodians", plan.custodian_count],
    ["Keywords", plan.keyword_count],
    ["CSV fields", plan.csv_columns.length],
  ]);
  const rows = plan.queries
    .slice(0, 250)
    .map(
      (query) => `
        <tr>
          <td>${escapeHtml(query.source)}</td>
          <td>${escapeHtml(query.custodian || "All custodians")}</td>
          <td>${escapeHtml(query.keyword_set)}</td>
          <td class="query-text">${escapeHtml(query.query_text)}</td>
        </tr>
      `,
    )
    .join("");
  document.querySelector("#query-table").innerHTML =
    rows || '<tr><td colspan="4">No queries generated</td></tr>';
}

function renderRun() {
  const manifest = state.run.manifest;
  document.querySelector("#posture").textContent = "Evidence ready";
  document.querySelector("#run-summary").textContent =
    `${manifest.row_count} rows, ${manifest.unique_hash_count} unique records`;
  document.querySelector("#evidence-meta").textContent = `${manifest.row_count} matched rows`;
  document.querySelector("#review-metrics").innerHTML = metricMarkup([
    ["Rows", manifest.row_count],
    ["Unique", manifest.unique_hash_count],
    ["Queries", manifest.query_count],
    ["Sources", manifest.source_files.length],
  ]);
  renderReviewInsights(state.run.review);
  document.querySelector("#evidence-table").innerHTML = state.run.evidence
    .slice(0, 500)
    .map(
      (row) => `
        <tr>
          <td>${escapeHtml(row.custodian)}</td>
          <td>${escapeHtml(row.timestamp)}</td>
          <td>${escapeHtml(row.matched_keyword_set)}<br><strong>${escapeHtml(row.matched_keyword)}</strong></td>
          <td>${escapeHtml((state.run.review.suggested_tags[row.hash] || []).join(", "))}</td>
          <td class="excerpt">${escapeHtml(row.context_excerpt)}</td>
        </tr>
      `,
    )
    .join("");
  renderArtifacts();
}

function renderReviewInsights(review) {
  const facetList = document.querySelector("#facet-list");
  const facetFields = ["source", "custodian", "matched_keyword_set", "matched_keyword"];
  facetList.innerHTML = facetFields
    .map((field) => {
      const values = (review.facets[field] || [])
        .slice(0, 5)
        .map((item) => `<span>${escapeHtml(item.value)} <strong>${item.count}</strong></span>`)
        .join("");
      return `<div class="facet-row"><strong>${escapeHtml(field)}</strong><div>${values || "<span>none</span>"}</div></div>`;
    })
    .join("");

  document.querySelector("#open-questions").innerHTML = review.open_questions
    .map((question) => `<li>${escapeHtml(question)}</li>`)
    .join("");
  document.querySelector("#report-preview").textContent = review.report_markdown;
}

function renderArtifacts() {
  const list = document.querySelector("#artifact-list");
  if (!state.run) {
    list.innerHTML = '<div class="artifact-item"><span>Run discovery to create artifacts</span></div>';
    return;
  }
  const manifest = state.run.manifest;
  const artifacts = [
    ["Evidence CSV", manifest.evidence_file],
    ["Hit report CSV", manifest.hit_report_file],
    ["Manifest JSON", manifest.manifest_file],
    ["Review JSON", state.run.reviewJsonFile],
    ["Report draft", state.run.reportFile],
  ];
  list.innerHTML = "";
  artifacts.forEach(([label, file]) => {
    const item = document.createElement("div");
    item.className = "artifact-item";
    item.innerHTML = `<span><strong>${escapeHtml(label)}</strong><br>${escapeHtml(file)}</span><button class="button secondary">Open</button>`;
    item.querySelector("button").addEventListener("click", () => window.opensore.openPath(file));
    list.appendChild(item);
  });
}

function setBusy(isBusy, label = "") {
  const runButton = document.querySelector("#run-button");
  const planButton = document.querySelector("#plan-button");
  runButton.disabled = isBusy;
  planButton.disabled = isBusy;
  if (isBusy) {
    runButton.textContent = label;
  } else {
    runButton.textContent = "Run discovery";
    planButton.textContent = "Plan";
  }
}

function metricMarkup(items) {
  return items
    .map(([label, value]) => `<div class="metric"><strong>${value}</strong><span>${label}</span></div>`)
    .join("");
}

function lines(value) {
  return value
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
}

function unique(values) {
  return [...new Set(values)];
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

let toastTimer;
function toast(message) {
  const element = document.querySelector("#toast");
  element.textContent = message;
  element.classList.add("visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => element.classList.remove("visible"), 4200);
}

renderCustodians();
renderKeywords();
renderSources();
renderOutput();
