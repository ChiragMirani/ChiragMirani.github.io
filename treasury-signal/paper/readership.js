// One canonical paper path, including visits from links with campaign parameters.
const paperPath = "/treasury-signal/paper";
const analyticsSite = "https://mirani-treasury-paper.goatcounter.com";

if (location.hostname === "chiragmirani.github.io") {
    const tracker = document.createElement("script");
    tracker.async = true;
    tracker.src = "https://gc.zgo.at/count.js";
    tracker.dataset.goatcounter = analyticsSite + "/count";
    tracker.dataset.goatcounterSettings = JSON.stringify({ path: paperPath });
    document.head.append(tracker);
}

async function displayPaperVisits() {
    const counter = document.getElementById("paper-readership");
    const url = analyticsSite + "/counter/" + encodeURIComponent(paperPath) + ".json";
    try {
        const response = await fetch(url, { credentials: "omit", referrerPolicy: "no-referrer" });
        if (!response.ok) return;
        const { count } = await response.json();
        if (!/^\d[\d,.\s]*$/.test(String(count))) return;
        counter.querySelector("strong").textContent = String(count);
        counter.hidden = false;
    } catch {
        // Leave the paper available if the counter is blocked or offline.
    }
}

displayPaperVisits();
