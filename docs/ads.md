# Ads on the house-brand pages

Status: built and switched off. The slot, the split CSP and the tests
are in the codebase; with no ``ADSENSE_CLIENT_ID`` in the environment
no ad code loads, so turning it on is an env var and an AdSense
account, not a deploy of new code.

## Scope

Ads, if any, appear only on pages served in the house brand: the root
app and the public pages owned by personal accounts. Organisation pages
never carry them, in any option.

The audiences are different, which is the reason for the split. An
organisation's pages are its own members. The house-brand pages are
whoever typed an address at the root: a sports club, a neighbourhood
barbecue, a school trip. Normal web monetisation is a reasonable
expectation there.

`routers/spa.py::_brand_slug_for` already resolves which of the two a
page is, and `brand_svc.HOUSE_BRAND` is the value that means "no
organisation owns this". That is the condition the whole feature hangs
off.

## Which networks are available

**The privacy-first networks are not.** They price per thousand
impressions, so they all have traffic floors. EthicalAds (no cookies,
contextual targeting only, 70% revenue share) requires roughly 50,000
views a month. Carbon Ads is invite-only, which is the same floor by
another name. We are far below both.

**AdSense is.** It has no traffic minimum, only site approval. It is the
one real option at current size.

## What AdSense costs

1. **A consent banner.** Google requires a certified CMP on TCF for any
   publisher serving the EEA or UK. Google's own Privacy & messaging
   CMP is free and certified, so this costs nothing in euros. It costs a
   cookie dialog in front of the root, which is the page where a
   stranger types an address and creates an account.
2. **No targeting cookies when consent is denied.** Google's limited
   ads mode serves on contextual signals only: page content, device
   type, coarse location. Cookies and local storage are still used for
   invalid-traffic detection, which Google states does not require
   consent. So a visitor who rejects still sees an ad, priced below a
   personalised one. This is what DatumPrikker.nl does.
3. **A loosened CSP.** AdSense needs `pagead2.googlesyndication.com` in
   `script-src`, `googleads.g.doubleclick.net` in `frame-src`, and open
   `img-src` / `connect-src`, because creatives come from whichever
   advertiser won the auction.
4. **An edit to `CLAUDE.md`.** The invariant currently reads "No
   third-party analytics or tracking pixels. Ever." AdSense breaks it.

## Revenue

A non-commercial Dutch site runs roughly EUR 1 to 4 RPM. At 10,000
monthly views that is EUR 10 to 40 a month. Rejected consent lowers the
rate rather than zeroing it, because limited ads still serve.

## The format: two vertical rails

One ad on each side of the content column, and nothing anywhere else.

### Sizing

The content column is 720px (`.container` in `theme.css`). The unit is
a 160x600 wide skyscraper, the vertical size advertisers actually
produce, with a 64px gutter on each side:

```
16 + 160 + 64 + 720 + 64 + 160 + 16 = 1200px
```

The rails appear at viewports of 1200px and up. Below that they are not
rendered at all: no ad, no script, no gap.

The rails are pinned to the edges of the viewport, not to the content
column. 1200px is therefore the width at which the gutter is at its
64px minimum, and it is the only width at which the ads are that close.
On a 1920px display each rail sits roughly 380px from the content.

An earlier draft used the narrower 120x600 to keep the page quieter.
The wider unit is the one with real advertiser demand, so it fills more
often, and distance from the content does the work of keeping the page
calm instead.

### The slot when there is no ad

The box is always the ad's exact size, whether or not an ad is in it.
An ad script measures its container and refuses a zero-width one, and a
slot that quietly collapsed would hide where the ads are.

What sits in it, in order:

1. The ad, when a network is configured.
2. Otherwise, "Want to help us keep this ad free?" and each service's
   own Buy Me a Coffee and Patreon button, when
   `SUPPORT_COFFEE_URL` or `SUPPORT_PATREON_URL` is set. The buttons are
   their official artwork, committed to `brands/opkomst/` and served
   from this app rather than from their CDNs, wrapped in ordinary
   links. No embed widget, no third-party request, no CSP hole.
3. Otherwise, the words "No ads".

In cases 2 and 3 the box carries a dashed outline, so it reads as the
place an ad would go rather than as a card of its own.

### The support buttons also sit under every form

Independently of the slot, whenever `SUPPORT_COFFEE_URL` or
`SUPPORT_PATREON_URL` is set the two buttons appear at the left of the
action row under every form, organiser and public alike, opposite the
primary action on the right. They are rendered at 26px and at 75%
opacity: an aside, not a competitor to the button someone came to
press. On brands an organisation owns they do not appear at all,
because `brand().ads` is null there and it is their page to ask on, not
ours.

`public_shared/support.ts` is the one list, read by both the slot's
empty state and the form footers, so the two cannot disagree about
what is configured.

### The phone format

Below 1120px there is no room for a rail, so phones get one horizontal
banner instead: a 320x50 mobile banner at the end of the page, after
the content and after the disclosure card.

One or the other, never both. The viewport is either wide enough for
the rails or it gets the banner.

In the page flow, not anchored to the bottom of the screen. AdSense
offers an anchor format that floats above the content with a close
button; we are not using it. On a sign-up page the submit button is
near the bottom, and a floating bar is the one thing guaranteed to sit
on top of it on a small screen.

### Where the ads run

Both formats run on every house-brand page: the root app and the public
sign-up, form, datepoll and roster pages owned by personal accounts.
The public pages carry most of the traffic, which is the point.

Two costs that follow from including them, both worth knowing rather
than discovering:

- **Page weight.** The mini-apps ship around 30KB precisely because
  someone opening a WhatsApp link on mobile data should not wait. The
  ad script is loaded from Google, so our own bundle barely grows, but
  the page pulls roughly 100KB of additional script before it can show
  an ad. Every phone visitor pays that now.
- **The consent dialog moves onto the sign-up path.** It is no longer
  only in front of the person building an event. It is in front of the
  person who was invited to one, before they can sign up.

### Rules

- One unit per rail, two per page on wide screens, one at the foot of
  the page on narrow ones. Never inside the content column.
- Fixed 120x600 box, so the space is reserved and nothing moves when an
  ad loads or fails to fill.
- The served ad is never scaled, transformed or clipped. AdSense allows
  choosing a unit size and setting it with CSS; it forbids altering how
  the delivered ad renders.
- Sticky within the rail so it stays put while a long form scrolls.
  Never floating over content, never an overlay, never expanding.
- No ads on the post-signup confirmation screen. That screen is
  deliberately the only card on the page so the edit link cannot be
  missed (`PublicConfirmation.vue` says so in a comment).
- No ads on any page served in an organisation's brand.

### Where the code goes

The client already knows which brand it is wearing:
`window.__OPKOMST_BRAND__.slug`, injected into every shell. So the
condition is `brand().slug === HOUSE_BRAND` plus a `matchMedia`
check for the breakpoint. Both have to gate whether the ad element is
*created*, not merely hidden, because a hidden slot makes the ad script
report a zero-width container.

- `public_shared/AdSlot.vue`: one component, both formats, the brand
  gate and the breakpoint. It lives in `public_shared/` because both
  the admin SPA and the four mini-apps mount it, the same way
  `BrandMark` and `Disclosure` are shared today.
- The admin SPA mounts it in `App.vue` around the router view; each
  mini-app mounts it in its own shell.

### CSP

The main document keeps `default-src 'self'` on organisation pages and
gets the loosened policy on house-brand pages only.
`SecurityHeadersMiddleware` sets the header after `call_next`, so the
route has already run; the handlers in `spa.py` resolve `brand_slug`
anyway and set `request.state.ads_allowed`. The middleware picks the
strict or the loose template from that.

Isolating the ad in an iframe on its own subdomain would have confined
the loose policy to the frame, but AdSense forbids iframed ads without
authorisation, and inside a frame their script cannot read the
surrounding page to target against. So the split by brand is as tight
as this gets.

A test pins that an organisation-owned page never receives the loosened
header.

### Turning it on, in order

The code is written. Everything below is configuration, and the order
matters because the earlier steps are what let the later ones verify.

1. **Set `ADSENSE_CLIENT_ID` and deploy.** The `ca-pub-…` value from
   the account. On its own this publishes `/ads.txt`, which is how
   AdSense confirms that the account and the domain belong to the same
   person, and it starts loading the ad tag. The two slot ids can wait:
   without them the slot renders its unconfigured state, and the page
   already carries the tag that verification looks for.
2. **Add the site in AdSense and let it verify.** Verification is
   real-time for the tag; the `ads.txt` crawl can take a few days to
   show as verified in the console. Nothing else waits on it.
3. **Create two display ad units**, one 160x600 and one 320x50, and put
   their ids in `ADSENSE_SLOT_RAIL` and `ADSENSE_SLOT_BANNER`. This is
   the deploy that actually starts showing ads.
4. **Turn on Privacy & messaging** in the console and publish the GDPR
   message. The AdSense tag delivers it, so there is no second script
   and no CSP change; the loosened policy already allows its host. Do
   this before step 3 reaches production traffic in the EEA.
5. **Set the blocking controls** under Brand safety, at least the
   sensitive categories. See the section on selection below: this is
   the only real control over what appears.
6. **Set `PRIVACY_CONTACT_EMAIL`** (and `PRIVACY_CONTROLLER`), then
   give AdSense `https://opkomst.nu/privacy` as the policy URL for the
   consent message. The page itself is built; without the contact
   variable it says so on the page, which is worse than saying nothing.

`/privacy` is served by `routers/privacy.py` outside the SPA, and that
is the point rather than a detail. Google asks that the policy the
consent dialog links to sit on a path the dialog does not itself cover,
so that "learn more" does not land the reader back in front of the
dialog. A page outside the SPA loads no bundle, so it loads no ad tag,
so no dialog can appear on it. `tests/test_ads.py` pins that, including
with a network configured.

Until step 1 the app behaves exactly as it does today: strict CSP, no
Google code, no consent dialog, no cookie, and `/ads.txt` answering
404 because there is nobody to authorise.

### ads.txt

`routers/ads_txt.py` serves one line, built from the environment:

```
google.com, pub-0000000000000000, DIRECT, f08c47fec0942fa0
```

It is generated rather than committed for the same reason nothing else
about advertising is committed: a deployment with no client id
authorises nobody and returns 404, rather than publishing an empty file
or somebody else's publisher id. The `ca-` prefix belongs to the ad tag
and is stripped here, which is the usual reason a publisher id reads as
missing in the console. The route is registered before the SPA
fallback, or the file would answer with the app's HTML shell and read
as malformed rather than absent.

## The strategy: traffic over click-through

We optimise for traffic by being the event and date-picker app people
prefer, and we accept a lower click-through rate as the price.

That is a choice, and it is worth writing down because every design
decision in this document follows from it. A page that keeps its
readers is worth more over time than a page that squeezes clicks out of
each one. Advertising here is a way to cover costs, not the product,
and the product is the reason anyone arrives.

The reasoning is symmetric and ordinary. Advertisers use attention
research to be seen; publishers use the same research to decide what
their pages emphasise. Nobody is owed a click-through rate, and on a
cost-per-click buy a click that never happens costs the advertiser
nothing. What we owe is an ad that renders honestly where we said it
would.

There is one line, and it is narrow: never make an ad unviewable while
its impression still fires. No zero-opacity containers, no off-screen
or clipped-to-nothing frames, no element stacked on top, no unit sized
to hide. Those are policy violations, viewability is measured either
way, and inventory nobody can see does not pay. Everything else about
placement, size, framing and the design of the page around it is ours
to decide.

### What the attention literature offers, and where we already are

Each of these is a finding from the eye-tracking work in
``docs/focus.md``, read as a lever rather than as an observation.

| Lever | What the research says | Where we are |
|---|---|---|
| Position | The right rail is the most-ignored region on a page, with its own literature. Top banners are the original 1997 finding. | Vertical rails at the window edges, the two most-ignored positions available. |
| Separation | Native and in-content formats get substantially more attention, because they defeat the learned filter. Distinct, framed, isolated ads keep it working. | A dashed frame, its own region, never inside the content column. This is also what the policy asks for. |
| Labelling | An explicit "Advertisement" is among the fastest classification cues a reader has. | Labelled, on live ads only. |
| Distance | Content next to ads gets caught by the same filter; ads next to content get caught by the reader's task focus. | 64px minimum gutter, widening with the window. |
| Density | More ad-shaped blocks train the filter faster. | Two rails or one banner. Nothing to gain without adding units. |
| Task focus | Goal-directed readers filter harder than browsing ones. | Someone opening a sign-up link is maximally goal-directed. ``docs/focus.md`` strengthens this for free. |
| Motion | Animation defeats blindness, which is why animated formats sell. | Declined. This one has a real revenue cost and we are paying it. |

Nearly everything the literature offers is already applied, and each
piece was independently defensible on its own merits before it was ever
read as a lever. There is little left to win on the visual side.

### The remaining lever is selection, not rendering

The control that is actually still open is which ads are eligible at
all. In the AdSense console, under **Brand safety > Blocking
controls**:

- **Sensitive categories.** Gambling, alcohol, dating, weight loss,
  politics and similar, blockable as a group.
- **General categories.** Around thirty of them (clothing, travel,
  finance). Blocking narrows the auction, so this is the one control
  here with a direct revenue cost.
- **Advertiser URLs.** A blocklist by destination domain. This is how a
  landlords' association or a payday lender stays off the page.
- **Ad review centre.** Individual creatives, blockable before they run
  for placement-targeted ads and after first appearance otherwise.
- **Site-level blocking.** All of the above per site, so opkomst.nu can
  be stricter than anything else on the account.

None of it exists until there is an AdSense account with the site
verified. The earlier attempts at controlling what the ads look like
kept hitting a wall because they aimed at rendering, which belongs to
the advertiser. Selection belongs to us.

## The alternative, if the goal is money rather than ads

A "steun dit project" link in the footer or the existing disclosure
card, pointing at a donation page. One i18n string and one anchor. No
banner, no cookies, no CSP change.

This is a separate decision and is not assumed here.

## Sources

- [Google consent management requirements for the EEA, UK and Switzerland](https://support.google.com/adsense/answer/13554116?hl=en)
- [Comply with the EU user consent policy](https://support.google.com/adsense/answer/7670013?hl=en)
- [Limited ads, AdSense](https://support.google.com/adsense/answer/14210870?hl=en)
- [Limited ads, Ad Manager](https://support.google.com/admanager/answer/9882911?hl=en)
- [AdSense cookie consent publisher guide, 2026](https://kukie.io/blog/google-adsense-cookie-consent)
- [EthicalAds publisher policy](https://www.ethicalads.io/publisher-policy/)
- [Brand safety: control the ads that appear on your site](https://support.google.com/adsense/answer/1059482?hl=en)
- [Guide to allow and block ads](https://support.google.com/adsense/answer/180609?hl=en)
- [Block sensitive categories](https://support.google.com/adsense/answer/164131?hl=en)
- [Fight against right-rail blindness](https://www.nngroup.com/articles/fight-right-rail-blindness/)
