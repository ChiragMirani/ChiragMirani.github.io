const paperPath = "/treasury-signal/paper";
const toolPath = "/treasury-signal";
const analyticsSite = "https://mirani-treasury-paper.goatcounter.com";
const visitPath = document.currentScript.dataset.visitPath || paperPath;

if (location.hostname === "chiragmirani.github.io") {
    const tracker = document.createElement("script");
    tracker.async = true;
    tracker.src = "https://gc.zgo.at/count.js";
    tracker.dataset.goatcounter = analyticsSite + "/count";
    tracker.dataset.goatcounterSettings = JSON.stringify({ path: visitPath });
    document.head.append(tracker);
}

async function displayVisits(elementId, path, startDate) {
    const counter = document.getElementById(elementId);
    if (!counter) return;

    const url = new URL(analyticsSite + "/counter/" + encodeURIComponent(path) + ".json");
    if (startDate) url.searchParams.set("start", startDate);
    const options = { credentials: "omit", referrerPolicy: "no-referrer" };
    try {
        const response = await fetch(url, options);
        if (!response.ok) return;
        const { count } = await response.json();
        if (!/^\d[\d,.\s]*$/.test(String(count))) return;
        counter.querySelector("strong").textContent = String(count);
        counter.hidden = false;
        counter.closest("#visit-counts")?.removeAttribute("hidden");
    } catch {
        // A blocked counter leaves the signal and preprint usable.
    }
}

displayVisits("tool-visits", toolPath, "2026-11-10");
displayVisits("paper-readership", paperPath);
