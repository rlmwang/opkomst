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

## What stays true regardless

No analytics, no tracking pixels, and nothing third-party on an
organisation's pages. The ad script is the single exception to the
first half of that rule, and it is confined to the pages above.
