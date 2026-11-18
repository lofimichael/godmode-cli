# Independent first-use review — installed Godmode CLI

> Archived review record from 2026-11-17. Personal checkout paths are generalized. Referenced PTY captures, binaries and temporary fixtures remain session evidence and are not included here. Findings and scores describe the reviewed build, not the current candidate.

Date: 2026-11-17. Verdict: **6/10 for first-use navigation.** The credential-saving mechanics and file previews are strong. The tool makes a new user discover the setup sequence and define completion for themselves.

## Method and limits

I inspected the installed executable `~/.godmode/bin/godmode` through normal help and an 80×24 PTY, using a fresh temporary HOME/GODMODE_HOME and synthetic GitHub token. Initial impressions were frozen in `01-first-impressions.md` before source, test, or capture-helper inspection. No prior design report or review was read, no target score was supplied, and no product files were changed. Only after the independent journey did I inspect capture-helper implementations to reproduce screenshots. The screenshots are explicitly reproductions of observed states, not recordings of the initial actions.

No real credential files were opened, no actual credentials were printed, and no provider API, login, install, release, payment, or publication action was performed. I did not launch a coding agent or prove it obeyed the instructions. The agent connection evidence is instruction placement and Doctor detection only.

## Task results and cost

| Task | Observed result | Cost / qualification |
| --- | --- | --- |
| Discover what the tool does | Complete. The first line of `godmode help` explains local business/profile and credential storage. | `help` speaks to an agent; `--help` later supplied the useful human command map. |
| Save one provider with fake data | Complete. GitHub form masked input, previewed GH_TOKEN, and returned with “1 key stored” and a saved message. | 11 discrete key/paste actions after initial launch, including a four-action detour through default-selected Active setup. A direct route would have needed seven. No provider validity was checked or implied by this test. |
| Decide what else is required | Complete after exploration. Doctor says business fields are optional and warns that agent instructions are missing. Profile editor also says optional. | Required consulting Doctor/FAQ and opening Business → Edit profile. The home menu's bare “0 fields” does not convey optional status. |
| Connect chosen agent to disposable project | Assisted/partial. With a project AGENTS.md but no global agent directory, Agents found nothing. Manually appending `agents --print` placed a note in that project, but Doctor still warned. Creating a synthetic global `.codex/AGENTS.md` fixture exposed a precise append preview; append preserved the existing sentence and Doctor reported one file. | Project instruction placement worked through a manual shell step. Automatic path is global, not a chosen project. A real agent was not launched. No in-product method to select a project was encountered. |
| Determine what to do next | Incomplete in the UI; inferable from the agent guide. | After global append, `godmode agents` exited with no success summary or next action. Returning home showed 1 key / 1 note / 0 fields with Active setup selected again. “Give your agent a task in your project” and how to confirm the note is loaded were not stated in the screens encountered. |

## Observed findings

### 1. The home menu emphasizes switching before starting

On first run, two full-screen intro pages precede the menu. Then the selected row is Active setup, annotated “Switch business / keys”. The header says “Business: Automatic · Keys: default”. Following the selected row leads through Active setup → Key environment → a default environment; no change is needed for the one-provider case. “Automatic” is only explained after entering Business details. Providers and Agents are the useful first-run actions, but neither is selected or connected into a sequence.

The intro clearly states the account consequences, and the brand voice is distinctive. The weakness is not the profanity itself: after the warning, “Put your agent to fucking work” and YOUR KEYS → YOUR AGENT → YOUR APP still leave the concrete first two actions unstated. The phrasing “You set the limits” does not identify any actual limit-setting action in this experience.

### 2. Human and agent help have an undisclosed fork

`godmode help` opens with a clear purpose but soon says “Ask the user to run godmode in a terminal.” It lists machine state and agent safety/credential operations rather than the human menu. Its final scope instruction introduces `active --command` without explaining the business/environment axes.

`godmode --help` clearly separates “For you”, “For agents”, “Files”, and options. This is substantially better for the stated task, but a first-time person who naturally types `help` does not learn to use `--help`. `agents --help` exposes only `agents [--print]` and an example ending in `pbcopy`; it supplies no project placement example.

### 3. Saving credentials is smooth, but has no transition to agent setup

Providers gives plain-English capability descriptions. The GitHub form shows the actual destination and planned GH_TOKEN addition. Secret entry is masked, and the list says “saved”. The helpful agent guide explicitly says stored is not verified, and FAQ says Doctor does not verify provider access.

After saving, however, the user remains in the provider list. Nothing says “Next: add the note to your agent” or whether one provider is enough. The feedback distinguishes storage from access in docs, but not next to the success state itself.

At 80×24 the GitHub token URL occupies multiple lines and breaks words (`...&w` / `orkflows...`). The actionable setup instructions are just two bullets after this very large link. Footer initially says “Enter open link · Tab details · Esc back” while a token prompt is also visible. Once typing begins, it changes to “Enter save”. This works, but the action of Enter depends on whether input exists and is not explained in place.

### 4. Agent setup works best only when its detection assumptions already hold

Fresh HOME: “No agent folders found. Add this note to your agent's instructions.” The footer offers copy, mark as added, and back. No chooser or destination path is offered. Re-running from a disposable project containing AGENTS.md still shows that state. Manually appending the printed note to the project and pressing `m` exits; Doctor still reports “0 agent files contain Godmode instructions”. Thus the product neither detects nor verifies the path it just invited the user to perform manually.

With an existing global Codex fixture, the preview is excellent: exact logical and resolved file paths, `+10 −0`, the actual marker-delimited addition, and retained existing text. At 80×24 the preview extends into a “Copy for this task” block. After one PageDown, the viewport ends at 27/28 lines. Enter is rejected with “Scroll through the full diff before adding the note.” One Down plus Enter succeeds. A review gate is understandable, but the page contains both the real diff and a separate copyable task note, so “full diff” does not describe all the required scrolling.

The global append directly exits the command. Doctor confirms one detected file; home says one note added. Neither state gives a concrete next action. “Notes added” accurately avoids promising a running agent, but is not very helpful as a setup completion label.

### 5. Optional and maintenance choices receive similar weight

Business details, Doctor, Update, Help / FAQ, Music, and Done sit alongside the main task rows. The business fields' optional nature is invisible on home. Doctor provides the clearest completion checklist, yet it is presented as a general maintenance command. The user must decide whether 0 fields means unfinished setup.

## Inferences, kept separate

- A person with an already installed/detected agent will have a smoother experience than the fresh-home case. The fresh-home test still reveals the unsupported/manual path and the absence of project-specific setup.
- Users are likely to confuse saved keys + added note with verified integration unless completion text states the boundary. This review did not observe a real user making that mistake.
- Starting on Active setup may be appropriate for frequent users managing several businesses, but it creates an unnecessary decision for the initial one-business case.
- The GitHub all-repositories guidance may not match every person's intended scope. This review did not evaluate provider permissions or official GitHub settings; it is a copy/scope question, not a verified permissions defect.

## Highest-impact fixes

1. On an empty install, select Providers and show a compact sequence: “1. Save a provider key. 2. Add the note to your agent. 3. Open your project and give the agent a task.” Keep Active setup as switching/context control. Mark business details optional on home.
2. After saving the first key, offer a visible “Set up an agent” next action. Say “Stored locally; provider access has not been checked.” After adding agent instructions, show the changed file and a literal next action, with restart/new-session advice only where verified for the agent.
3. Make the no-detected-agent path actionable: ask for a project/instruction-file destination or show one exact manual path example. Explain that Doctor checks detected global files and cannot verify arbitrary manual/project placement. Replace silent “mark as added” exit with clear feedback.
4. Put a one-line human redirect at the top of `godmode help` and a short start/use sequence at the top of human help. Add an FAQ entry for “I saved a key—what now?” Keep agent safety detail available without making it the only orientation.
5. Separate the actual append preview from the task-specific copy block; only gate on reviewing the actual changes, or accurately name the whole review. Give the GitHub form a short readable link label with the URL accessible through details.

## Score rationale

**6/10** is a qualitative navigation score, not a user-study statistic. Basic provider entry succeeds, masking is clear, keyboard navigation is consistent, and instruction-file preview/preservation earns trust. Points are lost for initial sequencing, the no-agent/project dead end, split human/agent help, and missing completion/next-step guidance. The underlying task is achievable for a technical user willing to inspect help and edit a file; it is not yet self-guiding from an empty install.

## Evidence

- `01-first-impressions.md`: frozen initial impressions before deeper inspection.
- `02-intro.png` through `11-agents-preview-bottom.png`: 80×24 PTY reproductions and matching `.txt` snapshots.
- `help-agent.txt`, `help-human.txt`, `faq.txt`, `doctor.txt`, `version.txt`: actual isolated command outputs from reproduction.
- `capture_baseline.py`: reproducer; imports only the repository's capture/test harness and uses synthetic values.
- `capture-manifest.json`: exact executable and isolated screenshot HOME.
- `isolated-home.txt`: location of original isolated journey fixture. Its project/global AGENTS.md files demonstrate instruction placement; no credential file needs to be opened.
