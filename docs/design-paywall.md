# Design: the paywall (mail is the thing that costs)

Status: built. `tests/test_paywall.py` is what it proves.

Everything Opkomst does is cheap except one thing. A page view costs
nothing that scales, a row costs nothing that scales, but mail scales
with how many people an organiser collects, and one busy roster sends
forever. That is the whole cost of the product, so that is where the
line between free and paid goes.

This is not a new axis. `services/limits.py` already says an
organisation is trusted because an operator put it in `TENANTS`, and a
personal tenant is a stranger who has to be bounded. Paid is the second
rung of the ladder that file already climbs.

## Every mail the app sends

| Mail | Sent by | What multiplies it | Gated |
| --- | --- | --- | --- |
| `login.html` | `routers/auth.py` | one sign-in attempt | no |
| `register_complete.html` | `routers/auth.py` | one new address at an organisation's door | no |
| `started.html` | `routers/start.py` | one anonymous create | no |
| `approved.html` | `routers/admin.py` | one approval, organisations only | no |
| `pending_digest.html` | `services/admin_digest.py` | admins per tenant | no |
| `chore_welcome.html` | `routers/chores_public.py` | one volunteer | no |
| `reminder.html` | `services/mail_lifecycle.py` | **attendees x occurrences** | yes |
| `feedback.html` | `services/mail_lifecycle.py` | **attendees x occurrences** | yes |
| `chore_reminder.html` | `services/mail_lifecycle.py` | **volunteers x shifts, with no end date** | yes |

The first six are one send per human action, and every one of them sits
behind a rate limiter on the endpoint that causes it. The last three fan
out with participant count, and the chore reminder does it on a
repeating cycle that never finishes on its own.

`mail_budget_remaining` already draws exactly this line: it counts
dispatch rows and shift stamps, and its docstring says transactional
mail is deliberately outside the budget. The paywall is that same
distinction with a harder lever.

## The rule

**Gate the push channel, never the product.**

No feature disappears on the free tier. What disappears is us sending
mail on the organiser's behalf. Every gated feature already has a
pull-based path in the codebase, and the free tier keeps all of it:

| Gated | What the free tier gets instead | Already built |
| --- | --- | --- |
| event reminder mail | "add to your calendar" on the public page; their calendar reminds them | `GET /api/v1/events/by-slug/{slug}/event.ics` |
| feedback mail | the feedback form, reached from the event page after the date and from a QR the organiser shows at the meeting | `services/qr.py`, the feedback token flow |
| chore reminder mail | the volunteer's personal page and the month calendar | `GET /api/v1/chores/by-token/{token}`, `/by-token/{token}/calendar` |

The organiser's own outbound channel stays free and always has: the
WhatsApp blast tool (`docs/plan-whatsapp-blast.md`) is push that costs us
nothing per recipient.

`chore_welcome.html` stays free on purpose. It is one send per
volunteer, already bounded by `MAX_PARTICIPANTS`, and it carries the
only link back to that volunteer's page. `EnrollAck` returns the token
once on screen, so the mail is a safety net rather than the only copy,
but losing that net is how a volunteer becomes unreachable.

## The privacy dividend

`PublicEventOut` sends `reminder_enabled` and `feedback_enabled` so the
public page can ask for an address only when something is going to use
it. Both are `false` on a free tenant, so **the free tier's sign-up form
has no email field at all**, with no extra code and no extra flag.

Nothing is collected, nothing is encrypted, nothing has to be wiped. The
free tier ends up strictly more private than the paid one, and the
open-source disclosure on the form gets shorter rather than longer.

The roster is the one place this did not fall out for free.
`PublicRosterOut` did not carry the roster's `reminder_enabled`, so the
enrol page had no way to know, and a volunteer on a free roster could
hand over an address that got encrypted and stored for mail nobody was
going to send. It carries it now, and the retention rule on both write
paths reads it.

## Mechanism

**One column.**

```python
class Tenant(...):
    plan: Mapped[Literal["free", "paid"]]
```

NOT NULL, no nullable "unset" state, and its default reads the row being
inserted (`_plan_for_kind`): an organisation is in `TENANTS` because an
operator put it there, which is the same decision as paying for it, so
it is born `paid`; everything else is born `free`. `Tenant.is_paid` is
the single spelling of the question, beside `is_personal`.

**One question**, in `limits.py`, beside the ceilings it belongs with:

```python
def can_send_participant_mail(tenant: Tenant) -> bool
def assert_can_send_participant_mail(tenant: Tenant) -> None
```

The refusal is a 422 that names the plan and what a free account gets
instead, like every other refusal in that file.

**Where it is enforced:**

1. **`services/entities.py`**, which is where both doors create an event
   or a roster. Asking for `reminder_enabled` / `feedback_enabled` on a
   free account is refused there once, for the organiser route and the
   anonymous start endpoint together.
2. **The two update routes** (`PUT /events/{id}`, `PUT /chores/{id}`),
   which are the other way a toggle gets switched on.
3. **`mail_lifecycle`**, in both sweeps, as a backstop. A pending row for
   a free account means a write raced a downgrade; the send is skipped,
   logged as `mail_plan_blocked`, and `reap-expired` takes the
   ciphertext on its normal schedule.
4. **The public surfaces.** `PublicRosterOut` carries `reminder_enabled`
   so the enrol page knows whether an address has a use, and both the
   enrol and the edit path refuse to retain one for a roster that sends
   nothing. `PublicEventOut` needed no change: it already sends the two
   toggles, and on a free event they are false, so the sign-up form has
   no email field at all.

`MAX_MAIL_PER_DAY` is unchanged and still applies to a paid personal
tenant. Paying opens the gate; it does not remove the ceiling.

**Moving an account:**

```
python -m backend.cli tenant-plan <address> paid
python -m backend.cli tenant-plan <address> free
```

Personal accounts only, by the address the account was created with: an
organisation's plan follows `TENANTS`, so there is nothing to set. The
downgrade is not just a flag. An account that may not mail its
participants may not have the toggles on either, so the command switches
them off across the account's events and rosters and deletes the pending
dispatch rows behind them, the same cleanup an organiser's own
toggle-off does. Without it a downgraded account would keep ciphertext
on file for mail that is never going to be sent.

## What the UI does

**The toggles are hidden, not disabled.** On a free account the event
form has no reminder and no feedback section, and the roster form has no
reminders section. A greyed-out switch with an upsell under it turns
every form into an advertisement, and the person who cannot pay reads
the pitch every time they make an event.

Where the two event toggles would have been, one line says what a free
event does instead: attendees get a calendar link. Otherwise the form
reads as if the app cannot do reminders at all, which is a worse
impression than "not on this plan". The chore enrol page does the same
with its privacy disclosure: on a roster that sends nothing, the address
is used once for the personal link and not stored, and the copy says
that rather than promising a reminder.

The frontend learns this the way it already learns about ceilings.
`AuthResponse` carries `participant_mail` beside `tenant_kind` and
`participant_cap`, and the store exposes it as `auth.participantMail`,
false when signed out (a visitor at the start door is heading for a free
account). Hiding is not the enforcement; the 422 stands on its own.

## Not gated, and why

- **Sign-in and registration mail.** Gating it removes the only way into
  the product.
- **`started.html`.** It carries the login token for an account the
  visitor does not know they have yet. The whole root-page design exists
  to send that mail; charging for it breaks the funnel at the top.
- **Approvals and the admin digest.** Organisations only, a handful of
  sends, and organisations are the paying side.

## Open

- **Price, and what it is per.** Per account per month is the obvious
  shape. Nothing in this design depends on the number.
- **How a personal account pays.** Self-serve payment needs a payment
  provider, and every automated route needs the organiser to be a
  registered entity, so that work is parked. Until it exists `plan` is
  set from the CLI, same as everything else that is platform-level.
- **There is no upgrade surface.** Nothing links to a way to pay because
  there is nothing to buy yet. A personal account has no admin pages, so
  when there is something, it does not belong in `SettingsPage` (that is
  an organisation's, under Beheer) and needs its own home.
