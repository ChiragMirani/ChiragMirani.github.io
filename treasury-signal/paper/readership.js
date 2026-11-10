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

async function displayVisits(elementId, path) {
    const counter = document.getElementById(elementId);
    if (!counter) return;

    const url = analyticsSite + "/counter/" + encodeURIComponent(path) + ".json";
    const options = { credentials: "omit", referrerPolicy: "no-referrer" };
    try {
        let response = await fetch(url, options);
        if (response.status === 404) {
            // GoatCounter can cache a new path's initial 404 for four hours.
            const minute = Math.floor(Date.now() / 60000);
            response = await fetch(url + "?retry=" + minute, options);
        }
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

displayVisits("tool-visits", toolPath);
displayVisits("paper-readership", paperPath);
