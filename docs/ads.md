# Ads

Status: built and switched off. Without an AdSense client id in the
environment no ad code loads at all, so turning it on is a
configuration change rather than a deploy.

## Where they may run

Only on pages served in the house brand: the root app and the public
pages of personal accounts. An organisation's pages never carry them,
and the CSP that allows an ad script is loosened per response for the
house-brand pages alone.

The split is about who the audience is. An organisation's pages are its
own members, and putting an advertising network in front of them
breaks the thing this app is for. The house-brand pages are whoever
typed an address at the root.

## What it costs to run

A certified consent banner, because a publisher serving the EEA needs
one. A visitor who refuses still sees an ad, served on page content
rather than on a profile, priced lower.

Ads sit in two rails beside the content column, on viewports wide
enough to hold them, and nowhere else. Below that width nothing renders
and no script loads. Never inside the reading column, never between a
question and its answer.

## When they load

Two deferrals, both because an ad should never be what a visitor waits
for.

**Google's script is fetched when the browser goes idle**, with a
three-second timeout so it arrives even on a page that never settles.
The tag has always carried `async`, which is the form Google publishes
and what they mean by calling their code "fully asynchronous", so it
never blocked parsing. What it did do was compete for bandwidth and the
main thread during hydration, which is the part of a page load a person
feels.

**A unit asks for its ad when it comes within 300px of the viewport**,
not when it mounts. The phone banner sits at the foot of the page and on
most visits is never reached; asking on mount billed an advertiser for
an impression nobody had. A desktop rail is beside the content, so it is
already intersecting and asks immediately.

Each unit pushes exactly once. A second push against the same `<ins>` is
an ad request that can never render, and requests that do not render are
what Google warns hand-rolled lazy loading tends to produce — their own
guidance points publishers at Google Publisher Tag for this. The
once-only guard is the reason this is safe without it, and
`frontend/src/__tests__/ad-slot.test.ts` holds that line.

Neither of these touches the ad code itself. What Google forbids
modifying is how ads are placed, sized and targeted (hiding units with
`display:none`, overlapping content, manipulating targeting); when their
tag is added to the page is not on that list, and lazy loading is
described in Ad Manager's own viewability guidance as a way to raise
viewability rather than as something to avoid.

## What stays true regardless

No analytics, no tracking pixels, and nothing third-party on an
organisation's pages. The ad script is the single exception to the
first half of that rule, and it is confined to the pages above.
