# Agent-Assisted Development

## Purpose and authority

Balance the efficiency of agentic coding with the developer's understanding and ownership of the codebase. Keep changes understandable, reviewable, and easy to edit by hand.

This file provides development guidance, not a security boundary or permission system. The developer may override its defaults at any time, subject to the harness's higher-priority instructions and actual tool permissions. For example, if the agent recommends splitting a feature into several plans and the developer requests one plan, follow the developer's direction.

Read `README.md` first for project context. The sections above **Project-specific guidance** are intended to be reusable across projects and harnesses.

## Working modes

Use **Default mode** unless the developer selects **Learning mode** or **Direct mode**. Keep the selected mode for the current task unless the developer changes it. If a harness lacks a dedicated planning or chat mode, follow the same workflow through ordinary conversation and Markdown files.

Read-only investigation and discussion may happen before implementation approval. Approval to discuss or revise a plan does not by itself authorize implementation. Approval to implement does not authorize a commit, push, or pull request.

### Default mode

1. **Understand the request.** Establish the intended outcome and acceptance criteria. Inspect the relevant code and project instructions before proposing changes.
2. **Write a plan.** Save the proposed plan under `docs/plans/` and add it to that directory's `README.md`. Use the harness's planning mode when available.
3. **Discuss and refine.** Resolve questions with the developer. If the change is too large to review effectively, suggest independently reviewable plans and explain their boundaries. The developer decides whether to split it.
4. **Wait for implementation approval.** Once the developer approves implementation, carry out the agreed plan and validation. Leave the changes uncommitted.
5. **Support review.** Explain the result and help the developer inspect it. Apply requested edits and record amendments when required by the plan rules below.
6. **Commit only when requested.** Commit after the developer explicitly authorizes a commit. Report any remaining validation gaps before doing so.

A direct request to implement an already-discussed plan counts as implementation approval. Interpret approval in context; ask only when it is unclear which action is authorized.

### Learning mode

Use this mode for learning unfamiliar tools or technologies through manual coding. Favor the developer's understanding over implementation speed.

1. **Create a learning plan.** Explain the relevant concepts and outline three to five exercises. Each exercise should identify its goal, files involved, manual coding work, and a way to check the result. Apply the same task-splitting guidance as in Default mode.
2. **Discuss and refine.** Agree on the exercises and how much scaffolding the agent should provide.
3. **Prepare only the approved scaffolding.** After approval, create any planned starter files and clearly marked exercise sections. Some exercises may require no file changes by the agent.
4. **Let the developer implement and test.** Provide hints, explanations, or complete answers according to the developer's request. Do not complete later exercises unasked.
5. **Review each exercise.** Give concrete feedback, explain corrections, make agreed edits, and complete planned follow-up work such as test coverage when testing was not part of the exercise.
6. **Follow the same commit rules as Default mode.** Keep work uncommitted until the developer explicitly requests a commit.

### Direct mode

Use this mode for work that does not need a plan record: fine-tuning and small changes too minor for a plan amendment, or chat-centered exploration of ideas, APIs, and designs.

1. **Work from the conversation.** Treat the developer's request in chat as the scope and approval for that change. Do not create or update a plan file.
2. **Keep changes small and visible.** Make one focused change at a time and briefly say what changed, so the developer can follow along in `git diff`.
3. **Explore freely, decide deliberately.** Investigation, experiments, and prototypes are welcome. Point out when an exploration produces a durable decision worth recording here or in a plan.
4. **Escalate when the work grows.** If a change touches the agreed scope or design of an existing plan, or grows beyond a small, easily reviewed change, suggest switching to Default or Learning mode and writing a plan or amendment. The developer decides.
5. **Follow the same commit rules as Default mode.** Keep work uncommitted until the developer explicitly requests a commit.

## Plan records

Save both implementation and learning plans as Markdown files in `docs/plans/`. Use descriptive names, such as `001-playlist-sorter-ui.md`. Create the directory and its index when the first plan is needed.

Each plan should include:

- **Purpose and mode:** the problem, desired outcome, and selected working mode.
- **Scope:** what is included and any relevant exclusions.
- **Approach:** the proposed design, files or modules affected, and meaningful tradeoffs.
- **Steps:** reviewable implementation steps or learning exercises.
- **Acceptance criteria:** observable conditions that establish completion.
- **Validation:** tests and manual checks, including any checks requiring a running iTunes instance or external services.
- **Open questions:** unresolved decisions that affect implementation.
- **Amendments:** changes recorded after implementation begins.

Track each plan's purpose, mode, and status in `docs/plans/README.md`, with a link to the plan. Use these statuses consistently:

`Draft` → `Approved` → `In progress` → `Ready for review` → `Complete`

Use `Paused` or `Superseded` when appropriate. A plan becomes **Complete** when its acceptance criteria are met and the developer accepts the result. Record commit status separately; completion does not imply a commit.

Before implementation begins, revise the plan in place. After implementation begins, preserve the approved scope and approach and append dated amendments at the end, including changes agreed in chat. Status fields and progress checkboxes may still be updated in place.

Each amendment should record what changed, why it changed, and any effect on acceptance criteria or validation. Minor implementation details that do not change the agreed approach or scope need not become amendments.

Record requested edits as amendments where applicable. If a discovery materially changes the agreed scope or design, propose the amendment and obtain direction before implementing the affected work. Recording an amendment does not itself grant approval.

## Git and pull requests

- Keep implementation changes unstaged and uncommitted for review unless the developer requests otherwise. This preserves the usefulness of `git diff`.
- Inspect the existing working tree before editing. Preserve unrelated developer changes and existing staged work.
- Do not commit without explicit commit authorization. A request to implement or continue a plan is not commit authorization.
- If the developer moves to a new plan while the previous plan's changes remain uncommitted, remind them once. Continue if they choose to defer the commit.
- Stage only the intended changes when preparing an authorized commit. Do not include unrelated files.
- Branches, pushes, and pull requests are developer-controlled; perform them only when requested. Pull requests are optional for this single-developer workflow.
- Agent-assisted pull request review may be introduced as the project matures, at the developer's direction.

## Readability and maintainability

Optimize for a developer who needs to understand, debug, and change the code manually.

- **Prefer explicit code.** Use clear names, straightforward control flow, and simple interfaces. Favor a longer, understandable implementation over a compact but obscure one.
- **Reuse existing behavior.** Inspect existing implementations before adding another. Extract shared behavior when the abstraction is clear; avoid speculative generalization or coupling unrelated code merely to remove similar-looking lines.
- **Keep modules cohesive.** Group related responsibilities. Aim for files of roughly 250 lines when practical, but split by responsibility rather than line count alone.
- **Keep changes focused.** Avoid unrelated refactoring, formatting churn, and new dependencies unless needed for the approved work. Explain significant additions.
- **Support top-to-bottom reading.** Prefer high-level entry points before their helpers when language constraints allow. Follow an established local convention when it improves consistency.
- **Document intent and contracts.** Explain non-obvious decisions, constraints, side effects, and public interfaces. Omit comments that merely repeat the code. Make TODOs specific enough to act on.
- **Use type annotations** or the language's equivalent where supported. Prefer explicit types at module boundaries and public interfaces.
- **Keep documentation accurate.** Update affected usage instructions and examples as part of the change. Distinguish proposed behavior from implemented behavior.

Language-specific conventions and test tools belong in the project-specific section below.

## Validation and review handoff

Run checks appropriate to the affected behavior. Use meaningful automated tests for new behavior and regressions, and manual checks when automated checks cannot establish the result. Do not claim a check passed unless it actually ran successfully.

Before handing work back for review, provide a concise summary of:

- What changed and how it meets the acceptance criteria.
- The main files or entry points to read, and any significant design decisions.
- Checks run and their results, plus checks that were skipped or could not run.
- Remaining limitations, missing tests, and any manual review steps.

Keep the explanation proportional to the change. Offer enough context for the developer to understand and edit the result without narrating every line.

Before an authorized commit, call out missing tests, unmet project coverage targets, and unresolved failures. Ask for direction if they prevent the agreed acceptance criteria from being met. Otherwise, report the limitation and follow the developer's direction.

## Scope and stopping conditions

- If the intended outcome or completion criteria cannot be inferred from the request or plan, clarify them before implementing.
- Resolve routine implementation details within the approved scope without repeatedly asking for permission.
- If new information materially changes the scope, architecture, dependencies, or expected behavior, pause the affected work, explain the finding, and ask for direction. Continue independent work that remains within scope when useful.
- If a problem cannot be resolved within the agreed scope, explain the blocker and propose a bounded next step. Avoid repeated fixes that expand the task without agreement.
- Stop implementation when the acceptance criteria are met and the planned validation is complete. Report the result and leave further improvements as suggestions.

## Project-specific guidance

Keep `README.md` as the primary project entry point. Record durable agent-relevant facts and conventions here; keep task progress and temporary notes in the relevant plans. Do not store secrets or credentials in either location.

### Context and current state

- **Project:** iTunes Tools, a set of desktop applications for managing an iTunes library on Windows:
  - iTunes playlist manual sorter
  - iTunes metadata verifier
  - iTunes new song importer
  - iTunes to Spotify sync (bidirectional)
- **Current state:** the shared module `src/itunes_tools/common/` exists, with `ItunesClient` (`itunes_client.py`, a lazy wrapper around the `iTunes.Application` COM object), Pydantic models (`models.py`), logging (`logger.py`), and helpers (`utils.py`). The applications themselves, their Qt UIs, and the test suite remain planned.
- **Stack:** Python 3.14, `uv`, Pydantic, PyQt, and `pywin32` (Windows COM) for communication with iTunes.
- **Learning context:** this is a personal, single-developer learning project; the goal is to learn the tools and technologies used. Agent-written project code is kept to a minimum: by default the agent advises, explains, and offers snippets and debugging support. Edit project files when the developer explicitly asks, for that task only. Learning mode is the natural fit for most new work, particularly Qt and COM.
- **Spikes:** `spikes/` is a sandbox where the agent may create, edit, and run experimental scripts without asking. Spike code is throwaway and must not be imported by project code.

### Architecture direction

- Structure the repository to house multiple applications that reuse the common module. Put behavior shared between applications in `itunes_tools.common` rather than duplicating it.
- Keep iTunes COM access behind `ItunesClient`; applications and UIs should not talk to COM directly.
- Keep long-running COM work outside the UI thread.
- Do not rename audio files. iTunes names and files every song itself; when a file does not follow its pattern, warn instead of offering a rename. Ask before proposing any renaming feature.

### Python conventions and testing

- Follow the Zen of Python: longer and simple is better than complex and short; explicit is better than implicit.
- Follow PEP 8 as formatted by PyCharm.
- Use type annotations.
- Use Pydantic for data validation and data models; keep free-form dictionaries to a minimum.
- Use meaningful names, comments, and docstrings without overdoing them. Docstrings use reStructuredText.
- Stick to the organization and conventions of the existing codebase.
- Use `pytest`, with tests under `tests/`. Code should be covered by unit tests and formatted before committing. Tests that need a real iTunes instance carry the `itunes` marker and are excluded by default (run them with `pytest -m itunes`).

The uv environment is in a non-standard location. Always set `UV_PROJECT_ENVIRONMENT=D:\venv\itunes-tools` before running `uv` commands.

Verified commands (from repository root, with the variable above set):

```text
uv sync --locked
uv run python -c "import sys; sys.path.insert(0, 'src'); import itunes_tools.common.itunes_client"
```

`uv run pytest` is configured in `pyproject.toml`, but `tests/` does not exist yet, so pytest currently collects from `spikes/` and fails. Record it as verified once the test suite exists.

### Git and pull requests

- `main` is always releasable; no direct commits to it.
- Work happens on short-lived branches off `main`: `feature/<issue#>-<short-name>` for use cases and enhancements, `bugfix/<issue#>-<short-name>` for bug fixes. A GitHub issue captures the requirements for each.
- Pull requests are optional while the project is young; the developer may merge a branch into `main` directly. As the project matures, pull requests become the usual route into `main` and are used for code review.
- When a pull request is used, keep its title and description short: a concise title and a few bullets on the main change.

### Maintaining this section

Add verified setup instructions, important module entry points, stable interfaces, and durable project decisions as implementation progresses. Link to detailed documentation instead of duplicating it. Remove or revise outdated facts.
