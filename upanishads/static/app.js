const state = {
  data: null,
  workIndex: 0,
  sectionIndex: 0,
  flat: []
};

const els = {
  work: document.getElementById("workSelect"),
  section: document.getElementById("sectionSelect"),
  search: document.getElementById("searchInput"),
  list: document.getElementById("sectionList"),
  workCount: document.getElementById("workCount"),
  sectionCount: document.getElementById("sectionCount"),
  eyebrow: document.getElementById("readerEyebrow"),
  title: document.getElementById("readerTitle"),
  meta: document.getElementById("readerMeta"),
  meaning: document.getElementById("meaningText"),
  translator: document.getElementById("translatorText"),
  ref: document.getElementById("referenceChip"),
  sourceLine: document.getElementById("sourceLine"),
  context: document.getElementById("studyContext"),
  text: document.getElementById("passageText"),
  original: document.getElementById("originalPanel"),
  note: document.getElementById("sourceNote"),
  prev: document.getElementById("prevBtn"),
  next: document.getElementById("nextBtn"),
  random: document.getElementById("randomBtn"),
  share: document.getElementById("shareBtn"),
  panel: document.getElementById("navigationPanel"),
  backdrop: document.getElementById("panelBackdrop"),
  topBrowse: document.getElementById("topBrowseBtn"),
  closeBrowse: document.getElementById("closeBrowseBtn"),
  mobilePrev: document.getElementById("mobilePrevBtn"),
  mobileNext: document.getElementById("mobileNextBtn"),
  mobileRandom: document.getElementById("mobileRandomBtn"),
  mobileBrowse: document.getElementById("mobileBrowseBtn")
};

function getCurrent() {
  const work = state.data.works[state.workIndex];
  const section = work.sections[state.sectionIndex];
  return { work, section };
}

function flatten() {
  state.flat = [];
  state.data.works.forEach((work, workIndex) => {
    work.sections.forEach((section, sectionIndex) => {
      state.flat.push({ workIndex, sectionIndex, work, section });
    });
  });
}

function currentFlatIndex() {
  return state.flat.findIndex((item) =>
    item.workIndex === state.workIndex &&
    item.sectionIndex === state.sectionIndex
  );
}

function updateBrowseState(open) {
  document.body.classList.toggle("nav-open", open);
  [els.topBrowse, els.mobileBrowse].forEach((button) => {
    if (button) button.setAttribute("aria-expanded", open ? "true" : "false");
  });
}

function openBrowse() {
  updateBrowseState(true);
  requestAnimationFrame(() => els.search.focus({ preventScroll: true }));
}

function closeBrowse() {
  updateBrowseState(false);
}

function scrollToReaderTop() {
  requestAnimationFrame(() => {
    document.querySelector(".reader").scrollIntoView({ block: "start" });
  });
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(value, max));
}

function setLocation(workIndex, sectionIndex, options = {}) {
  state.workIndex = clamp(workIndex, 0, state.data.works.length - 1);
  state.sectionIndex = clamp(sectionIndex, 0, state.data.works[state.workIndex].sections.length - 1);
  render();
  if (options.closeBrowse !== false) closeBrowse();
  if (options.scroll !== false) scrollToReaderTop();
}

function populateSelect(select, items, selectedIndex, labeler) {
  select.innerHTML = "";
  items.forEach((item, index) => {
    const option = document.createElement("option");
    option.value = String(index);
    option.textContent = labeler(item, index);
    option.selected = index === selectedIndex;
    select.append(option);
  });
}

function renderSelectors() {
  const { work } = getCurrent();
  populateSelect(els.work, state.data.works, state.workIndex, (item) => item.title);
  populateSelect(els.section, work.sections, state.sectionIndex, (item) => item.reference);
}

function renderList() {
  const { work } = getCurrent();
  const query = els.search.value.trim().toLowerCase();
  const sections = query
    ? state.flat.filter(({ section, work }) => {
        const relevance = section.relevance ? `${section.relevance.label} ${(section.relevance.tags || []).join(" ")}` : "";
        const original = section.original ? `${section.original.sanskrit || ""} ${section.original.transliteration || ""}` : "";
        const haystack = `${work.title} ${work.veda} ${section.reference} ${section.text} ${section.keyIdea} ${relevance} ${original}`.toLowerCase();
        return haystack.includes(query);
      }).slice(0, 100)
    : work.sections.map((section, sectionIndex) => ({ workIndex: state.workIndex, sectionIndex, work, section }));

  els.list.innerHTML = "";
  if (!sections.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = "No sections found.";
    els.list.append(empty);
    return;
  }

  sections.forEach((item) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "section-link";
    if (item.workIndex === state.workIndex && item.sectionIndex === state.sectionIndex) {
      button.classList.add("active");
    }

    const title = document.createElement("strong");
    title.textContent = item.section.reference;

    const preview = document.createElement("span");
    preview.textContent = item.section.keyIdea || item.section.text.slice(0, 96);

    button.append(title, preview);
    button.addEventListener("click", () => setLocation(item.workIndex, item.sectionIndex, { closeBrowse: true }));
    els.list.append(button);
  });
}

function matchCase(original, replacement) {
  if (original === original.toUpperCase()) return replacement.toUpperCase();
  if (original[0] === original[0].toUpperCase()) return replacement[0].toUpperCase() + replacement.slice(1);
  return replacement;
}

function replaceWord(text, source, replacement) {
  return text.replace(new RegExp(`\\b${source}\\b`, "gi"), (match) => matchCase(match, replacement));
}

function plainMeaning(text) {
  const replacements = [
    ["hath", "has"],
    ["hast", "have"],
    ["thou", "you"],
    ["thee", "you"],
    ["thy", "your"],
    ["thine", "yours"],
    ["ye", "you"],
    ["art", "are"],
    ["dost", "do"],
    ["doth", "does"],
    ["didst", "did"],
    ["wast", "were"],
    ["wert", "were"],
    ["shalt", "shall"],
    ["wilt", "will"],
    ["unto", "to"],
    ["hither", "here"],
    ["thither", "there"],
    ["whence", "from where"],
    ["wherein", "in which"],
    ["whereby", "by which"],
    ["therein", "in it"],
    ["thereof", "of it"],
    ["thereby", "by that"],
    ["thus", "in this way"]
  ];
  return replacements
    .reduce((value, [source, replacement]) => replaceWord(value, source, replacement), text)
    .replace(/\s+/g, " ")
    .trim();
}

function splitVerse(paragraph) {
  const numbered = paragraph.match(/^(\d+)\.\s+([\s\S]+)$/);
  if (numbered) return { marker: `${numbered[1]}.`, body: numbered[2] };
  return { marker: "", body: paragraph };
}

function renderVerse(paragraph) {
  const verse = splitVerse(paragraph);
  const block = document.createElement("section");
  block.className = "verse-block";

  const marker = document.createElement("div");
  marker.className = "verse-number";
  marker.textContent = verse.marker || " ";

  const body = document.createElement("div");
  body.className = "verse-body";

  const translationLabel = document.createElement("div");
  translationLabel.className = "verse-label";
  translationLabel.textContent = "Translation";

  const translation = document.createElement("p");
  translation.className = "verse-translation";
  translation.textContent = verse.body;

  const meaningLabel = document.createElement("div");
  meaningLabel.className = "verse-label meaning-label";
  meaningLabel.textContent = "Plain meaning";

  const meaning = document.createElement("p");
  meaning.className = "verse-meaning";
  meaning.textContent = plainMeaning(verse.body);

  body.append(translationLabel, translation, meaningLabel, meaning);
  block.append(marker, body);
  return block;
}

function renderContext(section) {
  els.context.innerHTML = "";

  const ideaLabel = document.createElement("div");
  ideaLabel.className = "context-label";
  ideaLabel.textContent = "Key idea";

  const idea = document.createElement("strong");
  idea.textContent = section.keyIdea;

  const relevanceLabel = document.createElement("div");
  relevanceLabel.className = "context-label context-label-spaced";
  relevanceLabel.textContent = "Relevant use";

  const relevance = document.createElement("p");
  relevance.className = "context-title";
  relevance.textContent = section.relevance.label;

  const note = document.createElement("p");
  note.textContent = section.relevance.note;

  const tags = document.createElement("div");
  tags.className = "context-tags";
  (section.relevance.tags || []).forEach((tag) => {
    const chip = document.createElement("span");
    chip.textContent = tag;
    tags.append(chip);
  });

  els.context.append(ideaLabel, idea, relevanceLabel, relevance, note, tags);
}

function originalBlock(title, text, className) {
  const section = document.createElement("section");
  section.className = `original-section ${className}`;

  const heading = document.createElement("h3");
  heading.textContent = title;

  const pre = document.createElement("pre");
  pre.className = "original-text";
  pre.textContent = text;

  section.append(heading, pre);
  return section;
}

function renderOriginal(section) {
  const original = section.original;
  els.original.innerHTML = "";
  if (!original) {
    els.original.hidden = true;
    return;
  }
  els.original.hidden = false;

  const label = document.createElement("div");
  label.className = "context-label";
  label.textContent = "Original text";
  els.original.append(label);

  if (original.status !== "available") {
    const unavailable = document.createElement("p");
    unavailable.className = "original-unavailable";
    unavailable.textContent = original.note || "Original Sanskrit and transliteration are not attached for this section yet.";
    els.original.append(unavailable);
    return;
  }

  const grid = document.createElement("div");
  grid.className = "original-grid";
  grid.append(
    originalBlock("Sanskrit", original.sanskrit, "sanskrit-block"),
    originalBlock("Transliteration", original.transliteration, "transliteration-block")
  );
  els.original.append(grid);

  const source = document.createElement("p");
  source.className = "original-source";
  source.textContent = `${original.note} Source: `;
  const link = document.createElement("a");
  link.href = original.sourceUrl;
  link.rel = "noopener noreferrer";
  link.textContent = original.sourceTitle;
  source.append(link, ".");
  els.original.append(source);
}

function renderPassage() {
  const { work, section } = getCurrent();
  document.title = `${section.reference} · The Upanishads`;
  els.workCount.textContent = state.data.works.length.toLocaleString();
  els.sectionCount.textContent = state.flat.length.toLocaleString();
  els.eyebrow.textContent = `${work.title} · ${work.veda}`;
  els.title.textContent = section.reference;
  els.meta.textContent = work.description;
  els.meaning.textContent = work.meaning;
  els.translator.textContent = `${work.translator} · ${work.year}`;
  els.ref.textContent = section.reference;
  els.sourceLine.textContent = `English translation · ${work.translator}, ${work.year}`;

  renderContext(section);
  renderOriginal(section);

  els.text.innerHTML = "";
  section.text.split(/\n{2,}/).forEach((paragraph) => {
    if (paragraph.trim()) els.text.append(renderVerse(paragraph.trim()));
  });

  els.note.innerHTML = `Plain meanings are modernized readings from the public-domain English translation. Source: <a href="${section.sourceUrl}" rel="noopener noreferrer">${work.sourceTitle}</a>.`;

  history.replaceState(null, "", `#${work.id}/${section.id}`);
  localStorage.setItem("upanishads:last", JSON.stringify({
    workIndex: state.workIndex,
    sectionIndex: state.sectionIndex
  }));
  updateNavigationState();
}

function render() {
  renderSelectors();
  renderList();
  renderPassage();
}

function navigate(delta) {
  const index = currentFlatIndex();
  const next = state.flat[index + delta];
  if (next) setLocation(next.workIndex, next.sectionIndex);
}

function openRandom() {
  if (!state.flat.length) return;
  const current = currentFlatIndex();
  let index = Math.floor(Math.random() * state.flat.length);
  if (state.flat.length > 1) {
    while (index === current) index = Math.floor(Math.random() * state.flat.length);
  }
  const item = state.flat[index];
  setLocation(item.workIndex, item.sectionIndex);
}

function updateNavigationState() {
  const index = currentFlatIndex();
  const atStart = index <= 0;
  const atEnd = index >= state.flat.length - 1;
  [els.prev, els.mobilePrev].forEach((button) => {
    if (button) button.disabled = atStart;
  });
  [els.next, els.mobileNext].forEach((button) => {
    if (button) button.disabled = atEnd;
  });
}

async function shareCurrent() {
  const { section } = getCurrent();
  const url = location.href;
  if (navigator.share) {
    await navigator.share({ title: `The Upanishads · ${section.reference}`, url });
  } else {
    await navigator.clipboard.writeText(url);
    els.share.textContent = "✓";
    setTimeout(() => { els.share.textContent = "↗"; }, 1200);
  }
}

function restoreLocation() {
  const requestedSearch = new URLSearchParams(location.search).get("q");
  if (requestedSearch) els.search.value = requestedSearch;

  const hash = decodeURIComponent(location.hash.replace(/^#/, ""));
  if (hash) {
    const [workId, sectionId] = hash.split("/");
    const workIndex = state.data.works.findIndex((work) => work.id === workId);
    if (workIndex >= 0) {
      const sectionIndex = state.data.works[workIndex].sections.findIndex((section) => section.id === sectionId);
      if (sectionIndex >= 0) {
        setLocation(workIndex, sectionIndex, { scroll: false, closeBrowse: false });
        return;
      }
    }
  }

  try {
    const saved = JSON.parse(localStorage.getItem("upanishads:last") || "{}");
    if (Number.isInteger(saved.workIndex)) {
      setLocation(saved.workIndex, saved.sectionIndex || 0, { scroll: false, closeBrowse: false });
      return;
    }
  } catch (error) {
    localStorage.removeItem("upanishads:last");
  }
  setLocation(0, 0, { scroll: false, closeBrowse: false });
}

els.work.addEventListener("change", () => setLocation(Number(els.work.value), 0));
els.section.addEventListener("change", () => setLocation(state.workIndex, Number(els.section.value)));
els.search.addEventListener("input", renderList);
els.prev.addEventListener("click", () => navigate(-1));
els.next.addEventListener("click", () => navigate(1));
els.random.addEventListener("click", openRandom);
els.share.addEventListener("click", () => shareCurrent().catch(() => {}));
els.topBrowse.addEventListener("click", openBrowse);
els.mobileBrowse.addEventListener("click", openBrowse);
els.closeBrowse.addEventListener("click", closeBrowse);
els.backdrop.addEventListener("click", closeBrowse);
els.mobilePrev.addEventListener("click", () => navigate(-1));
els.mobileNext.addEventListener("click", () => navigate(1));
els.mobileRandom.addEventListener("click", openRandom);

window.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeBrowse();
  if (event.target.matches("input, select, textarea")) return;
  if (event.key === "ArrowLeft") navigate(-1);
  if (event.key === "ArrowRight") navigate(1);
  if (event.key === "Home") setLocation(0, 0);
  if (event.key === "End") {
    const last = state.flat[state.flat.length - 1];
    setLocation(last.workIndex, last.sectionIndex);
  }
});

window.addEventListener("hashchange", () => {
  if (state.data) restoreLocation();
});

fetch("./data.json?v=1", { cache: "no-store" })
  .then((response) => response.json())
  .then((data) => {
    state.data = data;
    flatten();
    restoreLocation();
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("./sw.js?v=1").catch(() => {});
    }
  })
  .catch(() => {
    els.eyebrow.textContent = "Data unavailable";
    els.title.textContent = "The Upanishads";
    els.meta.textContent = "Run the build script to generate docs/data.json.";
    els.text.innerHTML = "<p>The reader is ready, but the Upanishads data file has not been generated yet.</p>";
  });
