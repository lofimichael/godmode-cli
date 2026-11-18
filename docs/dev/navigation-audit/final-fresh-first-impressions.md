# Frozen first impressions — help only

Recorded before interacting with the UI or reading implementation/design/audit material.

- `--help` immediately tells me what the tool does and gives a usable three-step route: add provider keys, connect my existing coding agent, then work in my project.
- I understand that saving a key does not verify provider access and that business details are optional.
- The distinction between key environments and business profiles is understandable but adds vocabulary. I expect Switch setup to show the exact pair before it changes anything.
- The agent connection promise sounds like an instruction-file append, not an account login. I will look for a target selection and preview before it edits files.
- Keyboard navigation, action search, filtering, settings and plain mode are discoverable from help. I have not yet exercised them.

Binary SHA-256: `2f2a154eede10971a3e6bfe605a776d1e489e9e7027af299b900f93a11f93348`

Tooling-only files read: `scripts/record-v019.py`, `scripts/record-native.py`, `tests/pty_support.py`. No implementation source, design documents or previous audit results read. The initial noninteractive `--help` invocation inherited the ordinary shell environment; all subsequent invocations use a temporary HOME and explicitly isolated agent homes. No ordinary Godmode storage was opened by the auditor.

## Frozen first-use UI impressions

- Two introduction cards use deliberately profane language. The first communicates agency and consequence clearly; the second conveys the keys → agent → app flow. They do not yet tell me a practical task, but the immediately following home screen does.
- The 80×24 home screen is calm and legible, with Provider keys selected and a direct “Add a provider key, then connect your agent.” next step. Business details and Music are clearly optional.
- “Business: Automatic · Environment: default” is prominent. Automatic is less immediately concrete than an actual business name, but help explained it.
- I can see Settings, Help, Switch setup and Exit together. Initial orientation feels strong. I have not completed any task yet and am withholding an overall navigation rating.
