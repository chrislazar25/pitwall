# Race layout

Source: Chris's Phase 5 specification supplied in chat on 16 November 2026.

## Step A decision gate

Build a separate `race` layout with two equally weighted blocks. The top block
shows the native `racetrack` mod. The bottom shows `{ "agent": "focused" }`.
The existing `pitwall` mod floats at the right edge with `peek: 52`.
Preserve the existing layouts and key bindings.

The prototype has `demo: true`. One car advances 0.02 laps every two seconds.
Native transitions interpolate its left and top coordinates. Its position is
measured by length along an ordered centerline with at least 24 points, starting
at the finish line. Scale the 1000 by 500 drawing to the block's measured size.
The invented circuit has rounded corners, a finish on the top straight, a pit
lane with six boxes inside the bottom straight, and a garage on the left.

Run the native check, switch to `race`, and save `shot-phase5-proto.png`.
Chris then watches the car and chooses between the circuit and a straight
speedway with left-to-right lanes. The suggested default is the circuit.
Stop until he answers. The prototype is disposable.

Chris also requested distinct agent car designs. Claude uses an orange and
cream livery. Codex uses blue. Driver colors in the live view follow Step B.

## Step B after acceptance

- Add optional `pit lap start --agent NAME`. Persist `agent` in the start event
  and `laps.running`. Update the shared Laps rule to pass it.
- Add `config.json` drivers mapping Pit agent names to Herdr `program.key`,
  color, and tyre. Initial entries are `claude` (soft, `#e8743b`), `codex`
  (medium, `#3b82f6`), and `glm-flash` (hard, `#22c55e`). Observe program keys
  instead of inferring them from the harness names.
- Project `drivers` from config and `laps.pace_hours` from the shipping baseline,
  defaulting to 4 until ten laps have shipped.
- Project `laps.last` with title, agent, hours, shipped_at, and rating. Rating is
  `best` at or below every earlier shipped lap, `good` below pace, otherwise `slow`.
- Add nullable `open_asks[].lap`.
- Project `pit_stops.fastest_today_minutes` and `last_minutes` from asks answered
  today in local time.
- Project each `scores_trend` as `best`, `up`, `down`, `flat`, or null. `best`
  means equal to the historical maximum with at least two dated lines. Otherwise
  compare with the previous dated line. Null scores or no previous line yield null.
- Add unit tests for every new projection.

## Step C live view

Read and watch `state.json` as the tower does. Move cars once per minute.
One car represents each running lap. The title labels it; the driver colors it.
Its clock fraction is hours since start divided by pace hours. Keep circling
after one lap and show yellow `+1`, `+2`, and so on. Position is elapsed time,
not progress.

Link to the first Herdr agent whose `program.key` matches the driver program
and whose `space_name` matches the lap project. Fall back to the first program
match. With no match, clicks do nothing. Clicking a linked car or garage icon
calls `agent.focus` and changes the onboard terminal.

| State | Condition | Drawing |
| --- | --- | --- |
| On track | Running lap without an associated open ask | Clock position |
| In pit | Open ask has lap ID, or same agent and project | Pulsing pit box and minutes waiting |
| Finished | Shipped within ten minutes | Finish line and hours; rating color |
| Garage | Herdr agent has no running lap | Small icon in agent status color |

The tyre dot is soft red `#ef4444` for flagship, medium yellow `#eab308`
for mid, and hard white `#f5f5f5` for cheap models. Fixed result colors are
best purple `#a855f7`, good green `#22c55e`, and slow yellow `#eab308`.
Use `theme()` for other colors except driver liveries.

The top flag bar is 28 px and shows the day's fastest pit stop. Choose the
first matching flag: yellow for any ask over 30 minutes; red if no Herdr agent
is working; chequered for a shipment in the last ten minutes; green otherwise.

Compare open ask IDs with the preceding load. Play `playSound("blocked")`
once on a new ID. Set the Dock badge to the open ask count, clearing with null
at zero. Skip both effects when `checking()` is true.

Give the tower a fixed width of 380 when `placement()` is non-null. SECTORS
bars use purple for best, green for up, and yellow for down.
Animate natively. No kart-to-rocket evolution and no ghost car.

## Final done-check

- Unit tests end in OK. Both native mods pass `herdr-app check`.
- Capture a real running lap on track in `shot-phase5-track.png`.
- Open a real ask and capture `shot-phase5-pit.png`. Chris confirms the sound
  and Dock badge 1.
- Answer the ask and capture `shot-phase5-out.png`. The car returns to the
  track and the badge clears.
- Chris clicks a car and confirms its live terminal appears onboard.
- Chris presses ctrl-shift-l and confirms his usual layout is unchanged.
  Herdr status has no errors.
- Stop. The build is complete.
