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
const nonnegative = (value) => typeof value === "number" && Number.isFinite(value) && value >= 0;
const tokens = (value) => nonnegative(value) && Number.isInteger(value);
const fuelKeys = ["tokens_today", "tokens_7d", "by_tool_7d", "api_value_30d_usd",
  "out_of_pocket_month_usd", "value_ratio"];
const validFuel = (fuel) => record(fuel) && Object.keys(fuel).length === fuelKeys.length &&
  fuelKeys.every((key) => Object.hasOwn(fuel, key)) &&
  tokens(fuel.tokens_today) && tokens(fuel.tokens_7d) &&
  Array.isArray(fuel.by_tool_7d) && fuel.by_tool_7d.every((row) => record(row) &&
    typeof row.tool === "string" && tokens(row.tokens)) &&
  nonnegative(fuel.api_value_30d_usd) && nonnegative(fuel.out_of_pocket_month_usd) &&
  (fuel.value_ratio === null || nonnegative(fuel.value_ratio));
const garageChecks = ["ci", "tests", "readme", "active"];
const validGarage = (garage) => Array.isArray(garage) && garage.every((row) => record(row) &&
  typeof row.project === "string" && garageChecks.every((key) => typeof row[key] === "boolean") &&
  tokens(row.commits_7d));
const coachLine = (value) => typeof value === "string" && value.trim().length > 0 &&
  !/[\r\n\u2028\u2029]/.test(value);
const validRadio = (radio) => record(radio) && typeof radio.date === "string" &&
  /^\d{4}-\d{2}-\d{2}$/.test(radio.date) && date(radio.date) &&
  new Date(radio.date).toISOString().slice(0, 10) === radio.date &&
  coachLine(radio.observation) && coachLine(radio.tweak);
const validScores = (scores) => record(scores) &&
  sectors.every(([, field]) => numberOrNull(scores[field], 100));

/**
 * Return a Tower from snapshot text, ordered Herdr grid agents, and epoch milliseconds.
 * Tower.data is "ready" or "no-data". Only unavailable data has a null openCount.
 * Grid agents have key, programName, spaceName, and status. Elapsed values are numeric.
 * Optional analytics degrade independently. Garage is an array, radio and fuel are nullable.
 */
export function tower(snapshotText, gridAgents, nowMs) {
  const grid = gridAgents.map((agent, index) => ({ ...agent, position: index + 1 }));
  const unavailable = {
    data: "no-data",
    openCount: null,
    grid,
    asks: [],
    sectors: sectors.map(([label]) => ({ label, value: null, trend: null })),
    laps: [],
    lastHours: null,
    bestHours: null,
    fuel: null,
    garage: [],
    radio: null,
  };
  let snapshot;
  try {
    snapshot = typeof snapshotText === "string" ? JSON.parse(snapshotText) : null;
  } catch {
    return unavailable;
  }
  if (!record(snapshot) || !Array.isArray(snapshot.open_asks) || !record(snapshot.laps) ||
      !Array.isArray(snapshot.laps.running) ||
      !numberOrNull(snapshot.laps.last_hours) || !numberOrNull(snapshot.laps.best_hours) ||
      !snapshot.open_asks.every((ask) => record(ask) &&
        ["id", "type", "headline", "project", "agent"].every((field) => typeof ask[field] === "string") &&
        date(ask.asked_at)) ||
      !snapshot.laps.running.every((lap) => record(lap) &&
        typeof lap.lap === "string" && typeof lap.title === "string" && date(lap.started_at))) {
    return unavailable;
  }
  const scores = validScores(snapshot.scores) ? snapshot.scores : null;
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
    sectors: sectors.map(([label, field]) => ({ label, value: scores === null ? null : scores[field],
      trend: ["best", "up", "down", "flat"].includes(snapshot.scores_trend?.[field])
        ? snapshot.scores_trend[field] : null })),
    laps: snapshot.laps.running.map((lap) => ({
      key: lap.lap,
      title: lap.title,
      elapsedHours: Math.max(0, nowMs - Date.parse(lap.started_at)) / 3600000,
    })),
    lastHours: snapshot.laps.last_hours,
    bestHours: snapshot.laps.best_hours,
    fuel: validFuel(snapshot.fuel) ? snapshot.fuel : null,
    garage: validGarage(snapshot.garage) ? snapshot.garage : [],
    radio: validRadio(snapshot.radio) ? snapshot.radio : null,
  };
}

/** Successful reads advance the shared attention claim before native effects run. */
export function attention(previous, snapshotText, { refreshBadge = false } = {}) {
  const ignored = { state: previous, accepted: false, sound: false, writeBadge: false };
  if (tower(snapshotText, [], 0).data !== "ready") return ignored;
  const snapshot = JSON.parse(snapshotText);
  if (!tokens(snapshot.event_count)) return ignored;
  const prior = record(previous) && tokens(previous.eventCount) &&
    Array.isArray(previous.openIds) && previous.openIds.every((id) => typeof id === "string")
    ? previous : null;
  if (prior !== null && snapshot.event_count < prior.eventCount) return ignored;
  if (prior !== null && snapshot.event_count === prior.eventCount) {
    return refreshBadge ? { state: prior, accepted: true, sound: false, writeBadge: true } : ignored;
  }
  const openIds = [...new Set(snapshot.open_asks.map((ask) => ask.id))];
  const badge = openIds.length || null;
  return {
    state: { eventCount: snapshot.event_count, openIds, badge },
    accepted: true,
    sound: prior !== null && openIds.some((id) => !prior.openIds.includes(id)),
    writeBadge: prior === null || badge !== prior.badge,
  };
}
