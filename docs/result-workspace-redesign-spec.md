# Result Workspace Redesign Spec

## Status

Draft v1  
Date: March 19, 2026

## Purpose

Define the next major UI direction for FRED Query.

The current application behaves like a lightweight chat UI with a separate results area. That works for initial questions, but it is a poor fit for multi-step analysis. Users are not trying to collect a transcript. They are trying to iteratively shape an economic view, chart, and dataset through natural-language instructions.

This document reframes the product as a result workspace with a conversational control surface.

## Problem Statement

The current UX breaks down in multi-turn usage for four reasons:

1. The primary artifact is the result, but the interface is organized as if the primary artifact is the chat turn.
2. The composer is visually and spatially disconnected from the current result after the first query.
3. History is low-fidelity and not useful as a recoverable analysis log.
4. Refresh and session restore are fragile because state is only partially persisted.

The result is a UI that feels fine for "ask once, inspect once" but weak for "iterate until the chart says what I need."

## Product Thesis

FRED Query should not feel like "ChatGPT for macro data."

It should feel like an economic analysis workspace where:

- the main pane is a persistent result canvas
- the left rail is the history of analysis instructions
- the message box is a way to refine, augment, or replace the current result
- each prompt produces a new result revision, not just another transcript entry

The conversation is still present, but it is subordinate to the evolving analytical artifact.

## Design Principles

1. Result-first
   The user should always understand what the current active result is.

2. Iteration over transcript
   The interface should emphasize how each prompt changes the result, not just that a prompt occurred.

3. Stable working surface
   After the first query, the user should stay in a workspace with a persistent canvas and a persistent composer.

4. Recoverable sessions
   Refreshing the page should restore the workspace, current result, and prior revisions.

5. Explicit mutation model
   The app should clearly distinguish whether a prompt refines, augments, replaces, or starts a new workspace.

6. Inspectable provenance
   Users should be able to understand what data series, filters, and transforms produced the current view.

## Non-Goals

- Building a general-purpose agent IDE
- Supporting arbitrary dashboard authoring in v1
- Introducing multi-user collaboration in this phase
- Perfect automatic classification of user intent for every mutation type before the UI ships

## User Jobs To Be Done

1. Start with a broad economic question and get a useful initial view.
2. Ask short follow-up instructions without restating the whole query.
3. See the current chart/dashboard update as the analysis evolves.
4. Review earlier prompts and restore an earlier result state if needed.
5. Refresh or return later without losing the working context.

## Core Mental Model

The user operates inside a workspace.

A workspace contains:

- a revision history of prompts
- a current active result snapshot
- the data, parameters, and provenance needed to reproduce that snapshot

Each submitted prompt creates a revision. A revision may:

- refine the current result
- augment the current result
- replace the current result
- branch into a new workspace

For v1, revisions can stay linear. Branching can be deferred to a later phase.

## Information Architecture

### Entry State

Before the first query:

- centered hero
- large initial composer
- example prompts
- no left rail yet

### Workspace State

After the first successful query:

- left rail for prompt history
- main result canvas
- sticky composer near the bottom of the viewport
- visible workspace title or summary
- obvious "New workspace" affordance

### Left Rail

The left rail should show compact revision items rather than chat bubbles.

Each item should include:

- the user prompt
- a short system-generated label for the resulting revision
- a status marker such as `Completed`, `Needs clarification`, or `Unsupported`
- a timestamp or relative ordering

Interactions:

- click to restore that revision into the main pane
- hover or focus to preview metadata
- optionally pin significant revisions later

### Main Result Canvas

The main pane should present the active revision.

Suggested vertical structure:

1. Active result summary
2. Primary chart or ranking visualization
3. Derived metrics
4. Series detail / provenance
5. Query details / parser intent / warnings

This is not a transcript view. The assistant's answer text is a caption or interpretation layer for the result, not the centerpiece of the screen.

### Composer

After workspace entry, the composer should become a sticky control surface.

It should support:

- free-form prompt entry
- context-aware placeholder text such as "Refine this result..."
- submit action
- "New workspace" action nearby

Later extensions:

- explicit chips for refine / compare / rank / transform
- prompt suggestions derived from the active result

## Interaction Model

### Mutation Types

Every prompt in workspace mode should be interpreted as one of four actions.

#### Refine

The user changes parameters of the current result.

Examples:

- "show since 2015"
- "make that year over year"
- "use monthly data"

Expected behavior:

- retain same analytical subject where possible
- update chart and metrics in place
- create a new revision item

#### Augment

The user adds a new dimension, series, comparison, or analysis mode to the current result.

Examples:

- "compare it to unemployment"
- "what's the relationship with CPI?"
- "rank the top 5 states"

Expected behavior:

- preserve the original result context where sensible
- expand or transform the canvas to include the new comparison
- create a new revision item

#### Replace

The user abandons the current subject and asks for a different one.

Examples:

- "actually switch to housing starts"
- "forget Brent, show mortgage rates"

Expected behavior:

- start a fresh linear revision from the current workspace
- visually indicate that the active subject changed
- keep earlier history accessible

#### New Workspace

The user wants a clean slate.

Examples:

- clicking `New workspace`
- entering a prompt after explicitly abandoning the current analysis

Expected behavior:

- create a new workspace with its own revision history
- do not silently reuse prior context

### Clarification Flow

Clarification should attach to the active workspace, not appear as a disconnected inline exception.

When clarification is required:

- preserve the current active result if one exists
- show a clarification panel within the main result canvas
- add a pending revision item in the left rail
- allow the clarification response to resolve into a completed revision

Clarification is part of result evolution, not a separate mode.

### Revision Restore

Selecting an earlier revision should:

- load that revision's result into the main pane
- update the visible context for follow-up prompts
- make it clear whether the next prompt will continue from that revision

V1 can treat a restored revision as the active base state for the next prompt.

## Example User Flow

1. User enters: "What's the price of Brent crude right now?"
2. App enters workspace mode and shows the result canvas for Brent.
3. Left rail now contains revision 1.
4. User enters: "What's the relationship with unemployment?"
5. App interprets that as augment.
6. Main pane updates to relationship analysis using Brent and unemployment.
7. Left rail contains revision 2, with revision 1 still restorable.
8. User enters: "now make it since 2010"
9. App interprets that as refine.
10. Main pane updates date range and creates revision 3.

At every step, the user feels like they are editing an analysis, not chatting into a void.

## Functional Requirements

### Frontend

1. Two major visual states: entry and workspace.
2. Left-rail revision history in workspace mode.
3. Persistent active result canvas.
4. Sticky composer in workspace mode.
5. Ability to restore a previous revision.
6. Full client-side persistence of workspace state across refresh.
7. Clear `New workspace` action.
8. Clarification UI integrated into the workspace model.

### Backend

1. Session model must store more than the last turn.
2. Workspace history must be retrievable by session or workspace ID.
3. Revision payloads must be serializable and restorable.
4. Clarification and unsupported states must be stored as revisions, not just transient responses.
5. Session continuity must survive process restart once server-backed persistence is added.

## Data Model Direction

The current backend stores only `last_query` and `last_response`. That is sufficient for follow-up parsing, but not for a recoverable workspace UX.

Target direction:

### Workspace

- `workspace_id`
- `created_at`
- `updated_at`
- `title`
- `active_revision_id`

### Revision

- `revision_id`
- `workspace_id`
- `created_at`
- `prompt`
- `mode`
  - `refine`
  - `augment`
  - `replace`
  - `clarification`
  - `unsupported`
- `status`
  - `pending`
  - `completed`
  - `needs_clarification`
  - `unsupported`
  - `failed`
- `response_payload`
  - answer text
  - intent
  - chart spec / plot payload
  - analysis result
  - candidate series when relevant
- `base_revision_id`
  optional pointer to the revision this one built from

For v1 frontend-only persistence, this structure can exist entirely in browser storage first.

## State Strategy

### Phase 1

Store full workspaces and revisions in browser storage.

Recommended:

- `localStorage` for durable restore across refresh and browser restart
- optional URL parameter for active workspace ID

This phase does not require backend schema changes.

### Phase 2

Add backend workspace persistence and retrieval APIs.

Suggested endpoints:

- `POST /api/workspaces`
- `GET /api/workspaces/{workspace_id}`
- `GET /api/workspaces/{workspace_id}/revisions`
- `POST /api/workspaces/{workspace_id}/ask`

This can coexist with the current `/api/ask` route during migration.

## UI Layout Spec

### Desktop

- left rail width: approximately 280px to 340px
- main content fills remaining width
- composer sticky at bottom of main pane or viewport
- charts allowed to grow much wider than the current 720px shell

### Mobile

- result canvas remains primary
- revision history collapses into a drawer or top sheet
- sticky composer remains available

### Visual Tone

The workspace should feel like an analytical product, not a generic messenger.

This suggests:

- denser use of structured panels
- stronger hierarchy around the active result
- more restrained transcript styling
- clearer chart prominence

## Copy Guidance

Avoid chatty system language.

Prefer labels such as:

- `Active result`
- `Revisions`
- `New workspace`
- `Refine this result`
- `Needs clarification`

Avoid language that implies a general chatbot persona.

## Migration Plan

The migration should be phased so we improve UX quickly without requiring a full backend rewrite up front.

### Phase 0: Spec and Alignment

Deliverables:

- this document
- implementation plan
- identified open questions

### Phase 1: Frontend Workspace Skeleton

Goal:

Replace the current transcript-plus-results layout with a result-workspace layout while still using the existing `/api/ask` backend contract.

Tasks:

1. Add workspace state model to `app.js`.
2. Replace `sessionStorage` snippet history with full revision snapshots.
3. Redesign `index.html` into entry state plus workspace layout.
4. Redesign `styles.css` for left rail, main canvas, and sticky composer.
5. Render every response as a revision object.
6. Allow clicking prior revisions to restore them into the main pane.
7. Integrate clarification as a revision state.

Out of scope:

- backend persistence
- multiple saved workspaces list

### Phase 2: Better Mutation Semantics

Goal:

Make refine / augment / replace more legible and predictable.

Tasks:

1. Add frontend revision metadata for inferred mode.
2. Surface subtle UI cues when a prompt replaced the subject rather than refined it.
3. Add follow-up suggestions based on active result.
4. Tune parser-context logic to better support workspace semantics.

### Phase 3: Backend Workspace Persistence

Goal:

Make refresh and restore durable beyond browser storage.

Tasks:

1. Introduce backend workspace and revision models.
2. Store full revision payloads.
3. Add retrieval endpoints.
4. Restore active workspace on page load.
5. Optionally support multiple named workspaces.

### Phase 4: Advanced Workspace Features

Possible extensions:

1. Branch from earlier revision
2. Compare revisions side by side
3. Pin important views
4. Export result snapshot
5. Shareable workspace URLs

## Engineering Task Breakdown

### Workstream A: Frontend Architecture

- define `workspace`, `revision`, and `activeRevisionId` state shapes
- centralize rendering around active revision
- separate entry-state render from workspace-state render

### Workstream B: Layout and Visual Design

- replace single-column shell with split workspace layout
- add left rail
- add sticky composer
- widen result canvas and chart area

### Workstream C: Revision Persistence

- persist full revision payloads client-side
- restore on page load
- preserve active revision selection
- preserve clarification state

### Workstream D: Interaction Semantics

- define inferred revision mode
- handle refine / augment / replace transitions
- update copy and affordances around workspace continuity

### Workstream E: Backend Evolution

- design persistent workspace store
- add read APIs
- transition from last-turn memory to revision history

## Suggested Immediate Implementation Order

1. Build the frontend workspace skeleton using the current backend.
2. Make revisions restorable from browser storage.
3. Clean up clarification behavior in the new layout.
4. Add backend workspace persistence.

This order gives the biggest UX improvement early, while preserving momentum.

## Execution Backlog

The following tasks are intended to be small enough to implement and review incrementally.

### Milestone 1: Workspace Shell

#### Task 1.1

Create a new workspace-oriented HTML structure.

Acceptance criteria:

- entry state remains available before first query
- workspace layout appears after first successful query
- layout includes left rail, main canvas, and workspace composer region

#### Task 1.2

Refactor frontend state around `workspace` and `activeRevisionId`.

Acceptance criteria:

- app state no longer treats `results` as a separate singleton output
- responses can be stored as revisions
- active revision can be switched without re-querying

#### Task 1.3

Render the active result from revision state.

Acceptance criteria:

- summary, chart, metrics, series detail, and query details all render from one revision object
- current result can be replaced by selecting another revision

### Milestone 2: Revision History

#### Task 2.1

Replace snippet history with full revision storage in the browser.

Acceptance criteria:

- each revision stores prompt, status, answer text, intent, chart payload, and analysis payload
- page refresh restores revision history and active revision

#### Task 2.2

Implement clickable revision items in the left rail.

Acceptance criteria:

- clicking a revision restores its result in the main pane
- active revision is visibly highlighted
- revision list supports at least pending, completed, and clarification states

#### Task 2.3

Add `New workspace` behavior.

Acceptance criteria:

- resets active workspace state cleanly
- does not leave stale revisions or clarification UI behind

### Milestone 3: Composer and Clarification

#### Task 3.1

Move from top-anchored form to workspace composer.

Acceptance criteria:

- composer stays accessible while inspecting results
- submitting a prompt creates a new pending revision

#### Task 3.2

Integrate clarification into revision flow.

Acceptance criteria:

- clarification appears in the main canvas
- unresolved clarification is represented in the left rail
- resolving clarification updates the pending revision into a completed revision

#### Task 3.3

Improve copy and placeholders for result-iteration behavior.

Acceptance criteria:

- placeholder text suggests refining or extending the current result
- system labels avoid generic chatbot phrasing

### Milestone 4: Result Semantics

#### Task 4.1

Infer and store revision mode metadata.

Acceptance criteria:

- revisions capture whether the prompt behaved like refine, augment, replace, clarification, or unsupported
- metadata is available for future UI treatment even if lightly displayed at first

#### Task 4.2

Add lightweight cues when the active subject changes materially.

Acceptance criteria:

- users can tell when they are no longer looking at a refinement of the same analysis

### Milestone 5: Backend Persistence

#### Task 5.1

Extend backend session storage from last-turn memory to revision history.

Acceptance criteria:

- backend can return a full revision list for a workspace or session
- current follow-up behavior still works during migration

#### Task 5.2

Add workspace restore API.

Acceptance criteria:

- frontend can reload a workspace from the backend
- restore survives server restart once persistence storage is introduced

#### Task 5.3

Move frontend restore source of truth from browser-only to backend-backed state.

Acceptance criteria:

- browser storage can remain as a cache
- backend becomes canonical for existing workspaces

## Open Questions

1. Should a hard subject switch inside a workspace remain in the same revision history, or should the UI encourage spinning up a new workspace?
2. Should restored earlier revisions create a new branch immediately, or simply become the active linear base for the next prompt?
3. How visible should inferred mutation mode be to the user?
4. Do we want one workspace per browser tab in v1, or a small saved-workspaces list?
5. Should the active result canvas support multiple charts/panels in v1, or remain a single primary visualization plus detail panels?

## Recommended Answers For V1

1. Keep subject switches in the same workspace unless the user explicitly chooses `New workspace`.
2. Treat restored revisions as the active linear base state. Defer branching.
3. Keep mutation mode mostly implicit, with lightweight labels only where useful.
4. Start with one active workspace and local persistence.
5. Keep one primary visualization plus detail panels. Do not build a freeform dashboard builder yet.

## Success Criteria

The redesign is successful if:

- users can iteratively evolve one analysis without feeling they are fighting a chat transcript
- the active result remains visually central through follow-up prompts
- refresh restores the working state reliably
- prior revisions are useful and restorable
- the product feels more like a data workspace than a chatbot wrapper
