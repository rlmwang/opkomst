# UX principles

The app is one page per task, used by volunteer organisers and by
visitors who will see it once. Speed to first action beats everything
else.

**A repeated idiom becomes a composable.** The third page that needs a
draft, a confirm dialog or a search box gets the shared one, not a
fourth copy.

**Server state is Vue Query, user state is Pinia.** There is one store,
`auth.ts`. Everything else is a query with a key.

**Drafts survive a refresh.** Mid-edit form state is kept per entity, so
a lost tab does not cost somebody their evening's work.

**Toasts report outcomes, not narration.** "Saved" when something
saved. Nothing on the way there.

**Disabled with a reason beats hidden**, except where the reason is
"you cannot have this". A control that cannot be used is explained; a
feature that is not on your plan is simply not there, because a switch
you cannot flip is an advertisement.

**The privacy contract sits in front of the form.** Above the field
that asks for an address, not behind a link to a policy.

**Locale is a property of the thing, not of the reader.** An event
written in English stays English for everybody who opens it, including
in its mail.

**No visible string is hard-coded.** Every one of them is in the two
locale files, and a test fails on a key that only one language has.

**Mutations invalidate queries.** A page never refetches by hand after a
write.

**Optimistic for routine, pessimistic for irreversible.** A toggle flips
immediately and rolls back if the server disagrees. A delete waits.

**Public pages never echo backend error text.** The server's message is
for the organiser and the log; the visitor gets a sentence they can act
on.

**No font smaller than the body size**, and every interactive element
has a label or a tooltip.

**One fold on every organiser form.** What the thing is sits above it,
the switches sit inside it, the page language sits below it, and it
starts closed (`docs/design-public-pages-ux.md`).
