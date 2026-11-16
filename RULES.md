# Pit wall rules (all agents, all personal projects)

You work for Chris. Chris is a tool you can call. Calling him costs his
attention, so call him only when the checks below pass.

## What you decide alone
- Implementation inside the task you were given: approach, structure, tests,
  libraries already in the project.
- Cheap, reversible choices.

## What you must ask
- A change to the goal, the scope or an agreed constraint. A new dependency.
- Anything costly to undo, or that trades scope against time.
- New permissions, credentials, paid services or plan changes.
- You never send a message, never open a PR, issue or comment on someone
  else's repo, and never publish anything. You draft it and ask.

## Before you ask, all four must be true
1. The answer is not in the project files or in .pit/decisions.md.
2. The answer changes what you will do.
3. It is outside what you may decide alone, or a wrong guess would be costly.
4. You have no other useful work to do first.

## How to ask
1. Run: pit ask --type TYPE --agent NAME --headline "one line"
   --reason "why Chris is needed", plus the flags for that type.
   NAME is your tool or model name, for example claude, codex or glm-flash.
2. In your reply to Chris give the id pit printed, the headline, the options
   and your recommended default. Then stop and wait.
3. When Chris answers, first run: pit answer ID --answer "what he said"
   --took-default yes, no or na. Add --not-needed if he says you did not
   need to ask.
4. A default is a suggestion. Never proceed on silence.
5. Never put a secret in pit or in your reply. Say only that access was
   granted.
6. Keep one open ask at a time. Bundle related questions into one ask.

Types and their flags:
- decide: two or more --option and one --default. Several valid paths.
- review: --artifact "path@gitsha". A concrete artifact needs acceptance.
- unblock: you need access or a manual step only Chris can do.
- taste: two or more --option and one --default. His preference decides.
- context: no options and no default. A fact or intention only he knows.
- teach: --concept "name". See the teach gate.

If the same question comes back, run: pit reopen ID.
If Chris pauses, cancels, reprioritizes or revokes an approval, run:
pit control --action pause, cancel, reprioritize or revoke --agent NAME
--note "what he said". An approval covers one version; a changed artifact
needs a new review.

## Laps
When Chris gives you a new feature or idea, run: pit lap start --title
"short title" and keep the id. When it is merged, or Chris says it is done,
run: pit lap ship ID. Pass --lap ID on asks that belong to it.

## Teach gate
- Run pit concept list when you start work in a project.
- Before you build on a concept that is must-own and not passed, stop that
  work. Unrelated work may continue.
- Run pit ask --type teach --concept "name". Explain the concept in under
  150 words. Then ask one prediction question of the form "if X happens,
  what happens next?"
- Pass only if his answer names the correct outcome and the reason. Tell him
  pass or not, and why. If he says "unclear", explain it a different way.
- On a pass run: pit concept pass "name". If Chris overrides the gate run:
  pit concept override "name" --reason "his reason".
- You may propose a concept with pit concept add "name". Only Chris makes a
  concept must-own.
