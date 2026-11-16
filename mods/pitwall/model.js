const sectors = [
  ["SPEED", "speed"],
  ["ASKS", "ask_quality"],
  ["SHIP", "shipping"],
  ["OWN", "ownership"],
];

const record = (value) => value !== null && typeof value === "object" && !Array.isArray(value);
const numberOrNull = (value, max = Infinity) => value === null ||
  (typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= max);
const date = (value) => typeof value === "string" && Number.isFinite(Date.parse(value));

/**
 * Return a Tower from snapshot text, ordered Herdr grid agents, and epoch milliseconds.
 * Tower.data is "ready" or "no-data". Only unavailable data has a null openCount.
 * Grid agents have key, programName, spaceName, and status. Elapsed values are numeric.
 */
export function tower(snapshotText, gridAgents, nowMs) {
  const grid = gridAgents.map((agent, index) => ({ ...agent, position: index + 1 }));
  const unavailable = {
    data: "no-data",
    openCount: null,
    grid,
    asks: [],
    sectors: sectors.map(([label]) => ({ label, value: null })),
    laps: [],
    lastHours: null,
    bestHours: null,
  };
  let snapshot;
  try {
    snapshot = typeof snapshotText === "string" ? JSON.parse(snapshotText) : null;
  } catch {
    return unavailable;
  }
  if (!record(snapshot) || !Array.isArray(snapshot.open_asks) || !record(snapshot.laps) ||
      !Array.isArray(snapshot.laps.running) || !record(snapshot.scores) ||
      !numberOrNull(snapshot.laps.last_hours) || !numberOrNull(snapshot.laps.best_hours) ||
      !sectors.every(([, field]) => numberOrNull(snapshot.scores[field], 100)) ||
      !snapshot.open_asks.every((ask) => record(ask) &&
        ["id", "type", "headline", "project", "agent"].every((field) => typeof ask[field] === "string") &&
        date(ask.asked_at)) ||
      !snapshot.laps.running.every((lap) => record(lap) &&
        typeof lap.lap === "string" && typeof lap.title === "string" && date(lap.started_at))) {
    return unavailable;
  }
  return {
    data: "ready",
    openCount: snapshot.open_asks.length,
    grid,
    asks: snapshot.open_asks.map((ask) => {
      const elapsed = Math.max(0, nowMs - Date.parse(ask.asked_at));
      return {
        key: ask.id,
        type: ask.type,
        headline: ask.headline,
        project: ask.project,
        agent: ask.agent,
        waitingMinutes: Math.floor(elapsed / 60000),
        overdue: elapsed > 30 * 60000,
      };
    }),
    sectors: sectors.map(([label, field]) => ({ label, value: snapshot.scores[field] })),
    laps: snapshot.laps.running.map((lap) => ({
      key: lap.lap,
      title: lap.title,
      elapsedHours: Math.max(0, nowMs - Date.parse(lap.started_at)) / 3600000,
    })),
    lastHours: snapshot.laps.last_hours,
    bestHours: snapshot.laps.best_hours,
  };
}
