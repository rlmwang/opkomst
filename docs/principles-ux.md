# UX principles

The product is a one-page-per-task tool used by volunteer
organisers and one-time visitors. Speed-to-first-action and
forgiveness on flaky connections matter more than power-user
features. Distilled principles, with pointers.

## 1. Repeated UI idioms become composables

Three identical patterns is the trigger to extract. The current
extracted set:

- ``useGuardedMutation`` — confirm + mutate + toast. The
  destructive-action idiom. ``ok``/``fail`` accept either a
  string or a ``(data) => { summary, detail }`` function so
  result-aware toasts (``"queued 12 emails"``) don't drop back
  to hand-rolled try/catch.
- ``useDialog<T>`` — open / target / submitting / openWith /
  close / submit. Replaces the three-ref + four-handler pattern
  every dialog page used to grow.
- ``useFormDraft<T>`` — debounced localStorage persistence with
  a reactive key. Forms longer than three fields get one.
- ``useConfirms.ask`` — the only call-site for confirmation
  dialogs. Brand-consistent buttons, single icon convention.

*Why:* every page that adopts these ends up a coherent shape.
Pages that haven't (``EventFormPage``, ``PublicEventPage``)
deliberately don't fit — both follow a "validate up-front,
mutate, navigate on success, error toast" shape that
``useGuardedMutation`` would force-fit awkwardly. The principle
is "share the idiom when it's actually shared", not "force every
mutation through one composable".

*Where:* ``frontend/src/composables/``, ``frontend/src/lib/``.

## 2. Vue Query owns server state; Pinia owns user state only

The only Pinia store is ``stores/auth``. Lists, mutations, cache
invalidation all flow through ``@tanstack/vue-query``. Mutations
declare their own ``onSettled: () => qc.invalidateQueries(...)``
so consumers don't manually call ``refetch()``.

*Why:* Pinia stores grow into "kitchen sinks" with bespoke fetch
+ cache + invalidate logic per entity. Vue Query already does
that, correctly, with stale-while-revalidate and request
deduplication out of the box.

*Where:* ``frontend/src/composables/useEvents.ts``,
``useAdmin.ts``, ``useChapters.ts``, ``useFeedback.ts``.

## 3. Drafts persist mid-edit, by default

Every form long enough to lose work survives a page refresh, a
tab close, or a mobile reception drop. Cleared on submit; cleared
on cancel. Keyed per entity so two tabs editing two events don't
clobber each other.

*Why:* the typical visitor signs up over flaky 4G mid-event. The
typical organiser fills out the create-event form on a phone
between trains. Reload-tolerance is a baseline expectation, not
a "nice to have".

*Where:* ``frontend/src/composables/useFormDraft.ts``,
``frontend/src/pages/EventFormPage.vue``,
``frontend/src/pages/PublicEventPage.vue``.

## 4. Toasts for outcomes, not for narration

A toast fires once at a terminal event: success, validation warn,
error. It never narrates progress, never explains what's about to
happen. Validation warns fire *before* a mutation; results toast
*after*. The progress signal is a button ``loading`` state.

*Why:* a toast that says "saving..." and then "saved" is two
notifications for one outcome. The user already knows the click
landed.

*Where:* ``frontend/src/lib/toasts.ts`` is the only toast
factory; the three methods (``success``, ``warn``, ``error``)
exhaustively describe what toasts do.

## 5. Disabled-with-reason over hidden

A button that can't fire stays in the layout, disabled, with a
muted single-sentence reason rendered below it. The user always
knows why they can't act, and the layout doesn't reflow when
state changes.

*Why:* hidden affordances make users hunt for missing buttons.
Disabled-with-reason is a teaching moment in a footer line, not a
mystery.

*Where:* ``EventDetailsPage.vue::triggerDisabledReason``;
``feedback`` summary "no responses yet" empty-state language.

## 6. One ``AppDialog``, one shape

Every dialog uses the ``AppDialog`` wrapper: header + body slot +
footer slot, 420px default width. The footer is right-aligned,
0.5rem-gap. Cancel is secondary text, the primary action is
brand-red. Direct PrimeVue ``Dialog`` is not used.

*Why:* dialog drift is the easiest place for visual inconsistency
to creep in. One wrapper means one place to update when the
brand colour changes.

*Where:* ``frontend/src/components/AppDialog.vue``.

## 7. Privacy is in front of the form, not behind a settings page

The public sign-up page carries a foldable explainer ("what does
opkomst do with my email?") with bullets that link directly to
the rendered email previews — the visitor can read the actual
template that would land in their inbox before deciding. The
explainer also links to the open-source repository.

*Why:* "we use your email for X" is more believable when X is one
click away from being verifiable. A privacy policy page nobody
reads is a compliance artefact, not user trust.

*Where:* ``frontend/src/pages/PublicEventPage.vue::emailUseBullets``,
``backend/routers/events.py::email_preview``.

## 8. Locale per event, not per user

The public sign-up page renders in the *event's* locale,
regardless of the visitor's persisted preference. The visitor's
own locale setting isn't touched (no localStorage write on event
view) so following a foreign-language link doesn't change their
default.

*Why:* an event organiser who set "Dutch" did so because their
audience speaks Dutch. The visitor's UI preference is for the
visitor, not for the events they happen to land on.

*Where:* ``frontend/src/pages/PublicEventPage.vue`` ``watch(event)``
on the locale ref.

## 9. Hardcode no visible string

Every visible string flows through ``t()``. Dutch and English are
locked-step at the keys; missing keys fail loudly during build.
This includes button labels, placeholders, ARIA labels, error
toasts, confirm dialog headers, and email subject lines.

*Why:* hardcoded strings are technical debt the moment a second
locale arrives. Build the discipline before it costs us.

*Where:* ``frontend/src/locales/{nl,en}.json``; CLAUDE.md
guardrail.

## 10. Mutations invalidate queries; pages don't refetch

The mutation hook owns its invalidation: ``useUpdateEvent`` ends
with ``onSettled: () => qc.invalidateQueries({ queryKey:
["events"] })``. Pages don't call ``query.refetch()`` after
``mutateAsync``. The page's reactive state updates from the
invalidation cycle, not from a hand-coded refetch.

*Why:* "what to invalidate" is a property of the mutation, not of
each page that uses it. Every page that forgot a refetch was a
stale-data bug; every page that did one would have to repeat
itself.

*Where:* ``frontend/src/composables/useEvents.ts`` (every
mutation hook), ``useAdmin.ts``, ``useFeedback.ts``.

## 11. Optimistic UI for routine state, pessimistic for irreversible action

Toggling an admin flag, picking a chapter, renaming a label —
optimistic, instant feedback. Sending an email batch, archiving
a chapter, deleting a user — confirm dialog + pessimistic await.
The dividing line is "is this reversible without effort".

*Why:* fast-feeling UI for the 95% case; explicit-feeling UI for
the 5% that has consequences.

*Where:* ``AdminPage.vue::toggleAdmin`` (optimistic-feeling via
no confirm); ``askDeleteUser`` and ``askTriggerNow`` (pessimistic
via ``useGuardedMutation`` + confirm).

## 12. Public surfaces never echo backend error text

Visitors signing up never see "ValidationError: 'email' must be a
valid email address". They see ``t("public.submitFail")`` — one
localised generic. Organiser surfaces are slightly looser
(``e.message`` is acceptable for ``ApiError``) because the
audience can read English stack traces and act on them.

*Why:* raw backend text leaks implementation details; localised
strings build trust on the public surface.

*Where:* ``frontend/src/pages/PublicEventPage.vue::submit``
catch-all.

## 13. No font smaller than the body size

13px (``0.8125rem``) is the floor. If content doesn't fit, fix
the layout — don't shrink the type. CLAUDE.md guardrail rules
this in writing; the codebase honours it.

*Why:* every "let me just shrink this label" is the start of a
mobile UX regression. The constraint forces better layouts.

*Where:* CLAUDE.md guardrail; ``frontend/src/assets/theme.css``.

## 14. Every interactive element has a tooltip or visible label

Icon-only buttons (copy, edit, delete, calendar-add, share)
carry ``v-tooltip`` plus an ``aria-label``. Visible-label buttons
don't get redundant tooltips. The principle: a sighted user
hovering and a screen-reader user tabbing should both learn what
the button does.

*Where:* ``EventDetailsPage.vue`` (copy/QR/edit buttons),
``AdminPage.vue`` (trash, edit-pencil).

## Reflection

The frontend, like the backend, mostly honours its rules. A few
places where the principles read as aspirational rather than
described:

- **Principle 1 (composables)** is consistent, but the recent
  audit found that two of three "candidate" pages
  (``EventFormPage``, ``PublicEventPage``) didn't actually fit
  ``useGuardedMutation``. The principle is honest about that:
  share the idiom when it's actually shared, don't force-fit.
  The single page that did fit (``EventDetailsPage``) was
  migrated. ``AdminPage`` remains the canonical example.

- **Principle 3 (drafts)** is fully adopted on the two forms
  that need it. No regression risk visible — but the pattern
  exists in case a third long form ever appears, and the next
  contributor should know to reach for it rather than rebuild
  localStorage logic.

- **Principle 7 (privacy in front of form)** depends on a few
  stable URLs (``/api/v1/events/by-slug/{slug}/email-preview/{channel}``).
  If these ever 404, the explainer's credibility evaporates;
  worth a mental note that those routes are user-facing
  trust-anchors, not internal previews.

- **Principle 11 (optimistic vs pessimistic)** is applied
  consistently. The chapter-archive case (pessimistic + confirm,
  with a ``getChapterUsage`` pre-fetch that opens the dialog)
  used to leave the trash icon looking frozen on slow
  connections; ``EditableList`` now takes an optional
  ``loading-key`` and ``AdminPage`` passes the in-flight chapter
  id through it, so the row's trash button shows a spinner
  instead of nothing.

- **Principle 14 (label every icon)** is honoured in the audit
  surface, but icon-only Buttons are the easiest place to
  regress. A lint rule (``no-icon-only-button-without-aria``)
  would close the loop; today it lives in review.

What's notably absent — again — is any layer of UI infrastructure
beyond what's necessary: no design system package, no global
theme provider beyond a CSS file, no story-book. The components
in ``frontend/src/components/`` are domain-shaped (``EventMap``,
``ChapterPicker``, ``LocationPicker``) rather than primitive
("Card", "Button"). PrimeVue 4 supplies the primitives; we
compose them.
