const record = (value) => value !== null && typeof value === "object" && !Array.isArray(value);
const text = (value) => typeof value === "string";
const date = (value) => text(value) && Number.isFinite(Date.parse(value));
const nonnegative = (value) => typeof value === "number" && Number.isFinite(value) && value >= 0;
const nullableText = (value) => value == null || text(value);
const tyres = { soft: "#ef4444", medium: "#eab308", hard: "#f5f5f5" };
export const RATING_COLORS = { best: "#a855f7", good: "#22c55e", slow: "#eab308" };
export const TYRE_COLORS = tyres;

export function parseSnapshot(snapshotText) {
  let state;
  try { state = JSON.parse(snapshotText); } catch { return null; }
  if (!record(state) || !Array.isArray(state.open_asks) || !record(state.laps) ||
      !Array.isArray(state.laps.running) ||
      !state.open_asks.every((ask) => record(ask) &&
        ["id", "agent", "project", "headline", "type"].every((key) => text(ask[key])) &&
        date(ask.asked_at) && nullableText(ask.lap)) ||
      !state.laps.running.every((lap) => record(lap) && text(lap.lap) && text(lap.title) &&
        date(lap.started_at) && nullableText(lap.agent) && nullableText(lap.project))) return null;
  return state;
}

export function askMatchesLap(ask, lap) {
  return (ask.lap != null && ask.lap === lap.lap) ||
    (lap.agent != null && lap.agent !== "" && ask.agent === lap.agent &&
      lap.project != null && ask.project === lap.project);
}

export function linkAgent(lap, drivers, orderedAgents) {
  if (lap.agent == null) return null;
  const program = drivers?.[lap.agent]?.program;
  if (typeof program !== "string" || program.length === 0) return null;
  return orderedAgents.find((agent) => agent.programKey === program && agent.spaceName === lap.project) ??
    orderedAgents.find((agent) => agent.programKey === program) ?? null;
}

function driverFor(lap, drivers) {
  const driver = lap.agent == null ? null : drivers?.[lap.agent];
  const livery = record(driver) && /^#[0-9a-f]{6}$/i.test(driver.color) ? driver.color : null;
  const tyre = record(driver) && Object.hasOwn(tyres, driver.tyre) ? driver.tyre : null;
  return { driver: lap.agent ?? null, livery, tyre, tyreColor: tyres[tyre] ?? null };
}

function finishedResults(laps, nowMs) {
  const source = Array.isArray(laps.finished) ? laps.finished : laps.last == null ? [] : [laps.last];
  return source.filter((lap) => record(lap) && text(lap.lap) && text(lap.title) &&
    nullableText(lap.agent) && nullableText(lap.project) && date(lap.shipped_at) &&
    nonnegative(lap.hours) && Object.hasOwn(RATING_COLORS, lap.rating) &&
    nowMs - Date.parse(lap.shipped_at) >= 0 && nowMs - Date.parse(lap.shipped_at) <= 600000);
}

/** Cars are track, pit, or finished. Terminal keys remain nullable for legacy laps. */
export function race(snapshotText, orderedAgents, nowMs) {
  const state = parseSnapshot(snapshotText);
  const unavailable = { data: "no-data", flag: null, fastestPitMinutes: null,
    cars: [], garage: orderedAgents, openIds: [] };
  if (state === null || !Number.isFinite(nowMs)) return unavailable;
  const drivers = record(state.drivers) ? state.drivers : {};
  const pace = nonnegative(state.laps.pace_hours) ? state.laps.pace_hours : 4;
  const linked = new Set();
  let pitCount = 0;
  const cars = state.laps.running.map((lap) => {
    const terminal = linkAgent(lap, drivers, orderedAgents)?.key ?? null;
    if (terminal !== null) linked.add(terminal);
    const elapsedHours = Math.max(0, nowMs - Date.parse(lap.started_at)) / 3600000;
    const clockFraction = pace > 0 ? elapsedHours / pace : 0;
    const matches = state.open_asks.filter((ask) => askMatchesLap(ask, lap));
    const base = { key: lap.lap, title: lap.title, terminal, ...driverFor(lap, drivers),
      elapsedHours, completedLaps: Math.floor(clockFraction), fraction: clockFraction % 1 };
    if (!matches.length) return { ...base, mode: "track" };
    const oldest = matches.reduce((a, b) => Date.parse(a.asked_at) <= Date.parse(b.asked_at) ? a : b);
    const slot = pitCount++;
    return { ...base, mode: "pit", bay: slot % 6, stack: Math.floor(slot / 6),
      waitingMinutes: Math.floor(Math.max(0, nowMs - Date.parse(oldest.asked_at)) / 60000) };
  });
  const finished = finishedResults(state.laps, nowMs);
  for (const lap of finished) {
    cars.push({ key: lap.lap, mode: "finished", title: lap.title,
      terminal: linkAgent(lap, drivers, orderedAgents)?.key ?? null, ...driverFor(lap, drivers),
      hours: lap.hours, rating: lap.rating });
  }
  const flag = state.open_asks.some((ask) => nowMs - Date.parse(ask.asked_at) > 1800000) ? "yellow" :
    !orderedAgents.some((agent) => agent.status === "working") ? "red" :
      finished.length > 0 ? "chequered" : "green";
  return { data: "ready", flag,
    fastestPitMinutes: nonnegative(state.pit_stops?.fastest_today_minutes) ? state.pit_stops.fastest_today_minutes : null,
    cars, garage: orderedAgents.filter((agent) => !linked.has(agent.key)),
    openIds: state.open_asks.map((ask) => ask.id) };
}
