"""Load the read endpoints and say where the time goes.

Two axes, because the app slows down along both:

* **Volume** — how much a page has to read. A summary of a form with
  twenty answers and one with two thousand are the same query and a
  different amount of work.
* **Concurrency** — how many organisers are asking at once. Postgres
  has a pool, uvicorn has workers, and a page that is fine alone can
  queue behind itself.

Usage::

    make db-up
    LOCAL_MODE=1 uv run uvicorn backend.main:app --port 8000    # one shell
    uv run python scripts/bench.py --fill                       # another

Two tables come out. **Pages** is what somebody waits for: every
request one screen fires, in parallel, timed from the first to the
last. **Endpoints** is what one read costs on its own, which is where a
regression is diagnosed once a page shows one.

``--fill`` tops every table up to the ``BUSY`` profile below, straight
through SQLAlchemy: the point is a page with something on it, not a
benchmark of the write path. It tops up rather than replaces, so
running it twice fills nothing the second time.

Reads only. Nothing here posts to the app, so a run cannot leave a
half-finished entity behind, and running it twice measures the same
thing twice.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import pathlib
import sys
import time
import uuid
from dataclasses import dataclass, field

import httpx

# Run from anywhere: the fill step imports the app's own models, and a
# script in ``scripts/`` is not on the path by itself.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

DEFAULT_BASE = os.environ.get("BENCH_BASE", "http://localhost:8000")
ORGANISER = os.environ.get("BENCH_EMAIL", "organiser@local.dev")


@dataclass(slots=True)
class Case:
    """One endpoint, and what it is meant to tell us."""

    name: str
    path: str
    auth: bool = True


@dataclass(slots=True)
class Result:
    case: Case
    concurrency: int
    latencies: list[float] = field(default_factory=list)
    errors: int = 0

    @property
    def rps(self) -> float:
        total = sum(self.latencies)
        return (len(self.latencies) * self.concurrency / total) if total else 0.0

    def pct(self, p: float) -> float:
        if not self.latencies:
            return 0.0
        ordered = sorted(self.latencies)
        return ordered[min(len(ordered) - 1, int(len(ordered) * p))] * 1000


async def _run_case(
    client: httpx.AsyncClient,
    case: Case,
    headers: dict[str, str],
    *,
    concurrency: int,
    requests: int,
) -> Result:
    """``requests`` in total, spread over ``concurrency`` workers."""
    result = Result(case=case, concurrency=concurrency)
    per_worker = max(1, requests // concurrency)

    async def worker() -> None:
        for _ in range(per_worker):
            started = time.perf_counter()
            try:
                response = await client.get(case.path, headers=headers if case.auth else {})
                elapsed = time.perf_counter() - started
                if response.status_code >= 400:
                    result.errors += 1
                else:
                    result.latencies.append(elapsed)
            except httpx.HTTPError:
                result.errors += 1

    await asyncio.gather(*(worker() for _ in range(concurrency)))
    return result


# How big "a chapter that has been going a while" is. Every number
# here is a guess at a real one, and the point of writing them down is
# that the guess is visible: two years of a weekly-ish event, twenty
# people at each, a third of them answering the feedback mail, and a
# form that went out to five hundred.
#
# The seeded dev database is a demo: eight events, nine signups, three
# datepoll answers. Every read that joins to those tables looks free
# against it, and the planner picks plans for a table that fits on one
# page. Measuring anything but the forms without filling first says
# nothing.
BUSY = {
    "submissions_per_form": 500,
    "events": 120,
    "datepoll_submissions": 60,
    "shifts": 520,
    "volunteers": 20,
}

# What one event looks like, whatever the scale. ``--scale`` multiplies
# how much there is, never how big each one is: ten times the events is
# a chapter that has been going ten times as long, and it is what a
# read has to sift through. Ten times the people at one meeting is not
# a bigger chapter, it is a different product.
PER_EVENT = {
    "dates": 2,
    "signups_per_date": 20,
    "feedback_per_date": 7,
}


def _uuid7() -> str:
    return str(uuid.uuid7()) if hasattr(uuid, "uuid7") else str(uuid.uuid4())


def _fill_forms(db, tenant, target: int) -> None:
    """Top the seeded form, quiz and kompas up to ``target`` submissions."""
    from backend.models import (
        Form,
        FormQuestion,
        FormQuestionOption,
        FormResponse,
        FormResponseChoice,
        FormSubmission,
    )

    for form in db.query(Form).filter(Form.archived_at.is_(None)).all():
        have = db.query(FormSubmission).filter(FormSubmission.form_id == form.id).count()
        if have >= target:
            print(f"  {form.mode:8} {form.slug}: {have} submissions, already at target")
            continue
        questions = db.query(FormQuestion).filter(FormQuestion.form_id == form.id).order_by(FormQuestion.ordinal).all()
        options = {
            q.id: db.query(FormQuestionOption).filter(FormQuestionOption.question_id == q.id).all() for q in questions
        }
        subs, answers, choices = [], [], []
        for n in range(target - have):
            sub_id = str(_uuid7())
            subs.append(FormSubmission(id=sub_id, form_id=form.id, display_name=f"Bench {n}", tenant_id=tenant.id))
            for q in questions:
                answer_id = str(uuid.uuid4())
                picked = options.get(q.id) or []
                answers.append(
                    FormResponse(
                        id=answer_id,
                        form_id=form.id,
                        question_id=q.id,
                        submission_id=sub_id,
                        answer_int=(n % 5) + 1 if q.kind in ("rating", "number") else None,
                        answer_text=f"antwoord {n}" if q.kind in ("text", "short_text") else None,
                        tenant_id=tenant.id,
                    )
                )
                if picked and q.kind in ("single_choice", "multi_choice"):
                    choices.append(
                        FormResponseChoice(
                            id=str(uuid.uuid4()),
                            response_id=answer_id,
                            option_id=picked[n % len(picked)].id,
                            tenant_id=tenant.id,
                        )
                    )
        db.bulk_save_objects(subs)
        db.bulk_save_objects(answers)
        db.bulk_save_objects(choices)
        db.commit()
        print(f"  {form.mode:8} {form.slug}: {have} -> {target} submissions")


def _fill_events(db, tenant, chapter_id, user_id, *, events: int, per_event: int, signups: int, feedback: int) -> None:
    """Two years of a chapter's events: the dates, who came, and the
    feedback the ones in the past collected.

    An event is the app's busiest shape. Its list is the first page an
    organiser sees, its details page reads four things at once, and
    every one of those reads joins to occurrences and signups. Measured
    against the eight events a fresh install seeds, all four look free.
    """
    from datetime import date, datetime, time, timedelta

    from backend.models import (
        Event,
        EventSourceOption,
        FeedbackResponse,
        Occurrence,
        Registration,
        Signup,
    )
    from backend.services.feedback_questions import QUESTIONS

    have = db.query(Event).filter(Event.chapter_id == chapter_id).count()
    if have >= events:
        print(f"  events: {have}, already at target")
        return

    first = date.today() - timedelta(days=730)
    rows: list[object] = []
    for n in range(have, events):
        on = first + timedelta(days=n * 6)
        event_id = str(_uuid7())
        rows.append(
            Event(
                id=event_id,
                slug=f"bench{n:05d}",
                name_nl=f"Bijeenkomst {n}",
                topic_nl="<p>Waar we het over hebben.</p>",
                location="Amsterdam",
                starts_on=on,
                start_time=time(19, 0),
                end_time=time(21, 0),
                chapter_id=chapter_id,
                created_by=user_id,
                locale="nl",
                # The three that decide what the reads have to do: a
                # listed event is on the public agenda, a source list
                # gives the stats something to group by, and feedback
                # gives the summary rows to count.
                listed=True,
                source_enabled=True,
                feedback_enabled=True,
                tenant_id=tenant.id,
            )
        )
        source_id = str(_uuid7())
        rows.append(EventSourceOption(id=source_id, event_id=event_id, ordinal=1, label="Flyer", tenant_id=tenant.id))
        for k in range(per_event):
            occ_date = on + timedelta(days=k * 7)
            occ_id = str(_uuid7())
            rows.append(
                Occurrence(
                    id=occ_id,
                    event_id=event_id,
                    slug=f"b{n:05d}{k}",
                    starts_at=datetime.combine(occ_date, time(19, 0)),
                    ends_at=datetime.combine(occ_date, time(21, 0)),
                    tenant_id=tenant.id,
                )
            )
            for s in range(signups):
                reg_id = str(_uuid7())
                rows.append(
                    Registration(
                        id=reg_id,
                        event_id=event_id,
                        display_name=f"Bezoeker {s}",
                        party_size=1 + (s % 3),
                        tenant_id=tenant.id,
                    )
                )
                rows.append(
                    Signup(
                        id=str(_uuid7()),
                        registration_id=reg_id,
                        occurrence_id=occ_id,
                        source_option_id=source_id,
                        tenant_id=tenant.id,
                    )
                )
            if occ_date < date.today():
                for f in range(feedback):
                    submission = str(_uuid7())
                    for q in QUESTIONS:
                        rows.append(
                            FeedbackResponse(
                                id=str(_uuid7()),
                                occurrence_id=occ_id,
                                submission_id=submission,
                                question_key=q.key,
                                answer_int=(f % 5) + 1 if q.kind == "rating" else None,
                                answer_text="Ging goed" if q.kind == "text" else None,
                                tenant_id=tenant.id,
                            )
                        )
        if len(rows) > 20000:
            db.bulk_save_objects(rows)
            db.commit()
            rows = []
    db.bulk_save_objects(rows)
    db.commit()
    print(f"  events: {have} -> {events}, {per_event} dates each, {signups} signups a date")


def _fill_datepoll(db, tenant, target: int) -> None:
    """A poll everybody in the chapter answered, on every date it
    offers."""
    from backend.models import Datepoll, DatepollResponse, DatepollSlot, DatepollSubmission

    for poll in db.query(Datepoll).filter(Datepoll.archived_at.is_(None)).all():
        have = db.query(DatepollSubmission).filter(DatepollSubmission.datepoll_id == poll.id).count()
        if have >= target:
            print(f"  datepoll {poll.slug}: {have} submissions, already at target")
            continue
        slots = db.query(DatepollSlot).filter(DatepollSlot.datepoll_id == poll.id).all()
        if not slots:
            continue
        rows: list[object] = []
        for n in range(target - have):
            sub_id = _uuid7()
            rows.append(
                DatepollSubmission(
                    id=sub_id,
                    datepoll_id=poll.id,
                    display_name=f"Bench {n}",
                    note="kan ook later" if n % 4 == 0 else None,
                    tenant_id=tenant.id,
                )
            )
            for i, slot in enumerate(slots):
                rows.append(
                    DatepollResponse(
                        id=_uuid7(),
                        submission_id=sub_id,
                        datepoll_slot_id=slot.id,
                        availability=("yes", "maybe", "no")[(n + i) % 3],
                        tenant_id=tenant.id,
                    )
                )
        db.bulk_save_objects(rows)
        db.commit()
        print(f"  datepoll {poll.slug}: {have} -> {target} submissions over {len(slots)} dates")


def _fill_roster(db, tenant, *, volunteers: int, shifts: int) -> None:
    """A roster that has been running for two years.

    Running, not merely populated: the schedule page projects the rest
    of its window on demand, and that projection is skipped entirely on
    a roster nobody started. A roster left forming measures three
    queries and none of the work.

    Half the shifts are behind today, which is what the accountability
    page counts, and half ahead, which is what the schedule shows.
    """
    from datetime import UTC, date, datetime, timedelta

    from backend.models import Chore, Enrollment, Roster, Shift, Volunteer

    roster = db.query(Roster).filter(Roster.archived_at.is_(None)).first()
    if roster is None:
        print("  roster: none seeded")
        return
    chores = db.query(Chore).filter(Chore.roster_id == roster.id).all()
    if not chores:
        print("  roster: no chores")
        return
    chore_ids = [c.id for c in chores]

    have_volunteers = db.query(Volunteer).filter(Volunteer.roster_id == roster.id).count()
    rows: list[object] = []
    for n in range(have_volunteers, volunteers):
        vid = _uuid7()
        rows.append(Volunteer(id=vid, roster_id=roster.id, display_name=f"Vrijwilliger {n}", tenant_id=tenant.id))
        for chore in chores:
            rows.append(Enrollment(volunteer_id=vid, chore_id=chore.id, tenant_id=tenant.id))
    if rows:
        db.bulk_save_objects(rows)
        db.commit()
    people = db.query(Volunteer).filter(Volunteer.roster_id == roster.id).all()

    first = date.today() - timedelta(days=shifts // 2)
    have = db.query(Shift).filter(Shift.chore_id.in_(chore_ids)).count()
    # One shift per chore per date, so a bigger scale fills the dates
    # around what is already there rather than colliding with it.
    taken = {
        (chore_id, on_date)
        for chore_id, on_date in db.query(Shift.chore_id, Shift.on_date).filter(Shift.chore_id.in_(chore_ids)).all()
    }
    rows = []
    for n in range(shifts):
        on = first + timedelta(days=n)
        chore = chores[n % len(chores)]
        if (chore.id, on) in taken:
            continue
        who = people[n % len(people)] if people else None
        rows.append(
            Shift(
                id=_uuid7(),
                chore_id=chore.id,
                on_date=on,
                slot_index=0,
                volunteer_id=who.id if who else None,
                status="done" if on < date.today() else "scheduled",
                tenant_id=tenant.id,
            )
        )
    if rows:
        db.bulk_save_objects(rows)
    if roster.activated_at is None:
        # A forming roster projects nothing, so the page it is measured
        # through does none of its work.
        roster.activated_at = datetime.now(UTC)
        roster.starts_on = first
    db.commit()
    print(f"  roster: {have} -> {have + len(rows)} shifts, {len(people)} volunteers, running")


def _reset() -> None:
    """Delete what a fill wrote, so the next one starts from the demo.

    Only its own rows: the events it made carry a ``bench`` slug, the
    people it invented are named for it, and the cascades take the rest.
    Running a smaller scale after a bigger one has to remove rows, and
    topping up cannot."""
    from sqlalchemy import text

    from backend.database import SessionLocal

    db = SessionLocal()
    try:
        for statement in (
            "DELETE FROM events WHERE slug LIKE 'bench%'",
            "DELETE FROM registrations WHERE display_name LIKE 'Bezoeker %'",
            "DELETE FROM form_submissions WHERE display_name LIKE 'Bench %'",
            "DELETE FROM datepoll_submissions WHERE display_name LIKE 'Bench %'",
            "DELETE FROM volunteers WHERE display_name LIKE 'Vrijwilliger %'",
            "DELETE FROM shifts WHERE volunteer_id IS NULL",
        ):
            print(f"  {statement}: {db.execute(text(statement)).rowcount}")
        db.commit()
    finally:
        db.close()


def _fill(profile: dict[str, int]) -> None:
    """Fill every table a measured read touches, then re-analyze.

    Without the ANALYZE the first run measures the planner working from
    statistics gathered when these tables were nearly empty, which is a
    different plan from the one production would pick. It cost an
    afternoon once: every read looked slow, and the ranking that came
    out was an artefact of the load rather than of the code.
    """
    from sqlalchemy import text

    from backend.config import tenants_list
    from backend.database import SessionLocal
    from backend.models import Chapter, User
    from backend.services import tenancy
    from backend.services import tenants as tenants_svc

    db = SessionLocal()
    try:
        tenant = tenants_svc.find_live_organisation_by_slug(db, tenants_list()[0][0])
        assert tenant is not None
        tenancy.bind(tenant.id, tenant.brand_slug)
        chapter = db.query(Chapter).filter(Chapter.deleted_at.is_(None)).first()
        assert chapter is not None
        organiser = db.query(User).filter(User.deleted_at.is_(None)).first()
        assert organiser is not None

        _fill_forms(db, tenant, profile["submissions_per_form"])
        _fill_events(
            db,
            tenant,
            chapter.id,
            organiser.id,
            events=profile["events"],
            per_event=PER_EVENT["dates"],
            signups=PER_EVENT["signups_per_date"],
            feedback=PER_EVENT["feedback_per_date"],
        )
        _fill_datepoll(db, tenant, profile["datepoll_submissions"])
        _fill_roster(db, tenant, volunteers=profile["volunteers"], shifts=profile["shifts"])

        db.execute(text("ANALYZE"))
        db.commit()
        print("  analyzed")
    finally:
        db.close()


@dataclass(slots=True)
class Page:
    """A screen, and every request it fires on arrival.

    An endpoint's own number says what one read costs. It does not say
    what a page costs: an organiser opening an event fires five reads
    at once and waits for the slowest, and under load those five
    compete with each other as much as with anybody else's. This
    measures the wait somebody actually has.
    """

    name: str
    paths: list[str]


async def _run_page(
    client: httpx.AsyncClient,
    page: Page,
    headers: dict[str, str],
    *,
    concurrency: int,
    loads: int,
) -> Result:
    """``loads`` page loads in total, ``concurrency`` of them at once.

    One load is every request the page fires, in parallel, timed from
    the first to the last: the browser does not wait between them
    either."""
    result = Result(case=Case(page.name, ""), concurrency=concurrency)
    per_worker = max(1, loads // concurrency)

    async def one() -> None:
        started = time.perf_counter()
        try:
            responses = await asyncio.gather(*(client.get(path, headers=headers) for path in page.paths))
        except httpx.HTTPError:
            result.errors += 1
            return
        if any(r.status_code >= 400 for r in responses):
            result.errors += 1
        else:
            result.latencies.append(time.perf_counter() - started)

    async def worker() -> None:
        for _ in range(per_worker):
            await one()

    await asyncio.gather(*(worker() for _ in range(concurrency)))
    return result


async def _pages(client: httpx.AsyncClient, headers: dict[str, str]) -> list[Page]:
    """The screens, pointed at whatever is seeded.

    Every one of these fires ``/auth/me`` too: the guard resolves the
    session before the route paints, so it is on the critical path of
    every authenticated page and is counted in every one of them.
    """
    me = "/api/v1/auth/me"
    pages: list[Page] = [Page("dashboard", [me, "/api/v1/event", "/api/v1/chapters"])]

    events = (await client.get("/api/v1/event", headers=headers)).json()
    if events:
        one = events[0]["id"]
        occurrences = (await client.get(f"/api/v1/event/{one}/occurrences", headers=headers)).json()["occurrences"]
        occ = occurrences[0]["id"] if occurrences else None
        paths = [me, f"/api/v1/event/{one}", f"/api/v1/event/{one}/occurrences"]
        if occ:
            paths += [
                f"/api/v1/event/{one}/occurrences/{occ}/signups",
                f"/api/v1/event/{one}/occurrences/{occ}/stats",
            ]
        paths.append(f"/api/v1/event/{one}/feedback-summary")
        pages.append(Page("event details", paths))

    for noun in ("form", "quiz", "compass"):
        rows = (await client.get(f"/api/v1/{noun}", headers=headers)).json()
        if not rows:
            continue
        one = rows[0]["id"]
        pages += [
            Page(f"{noun} list", [me, f"/api/v1/{noun}"]),
            Page(f"{noun} details", [me, f"/api/v1/{noun}/{one}", f"/api/v1/{noun}/{one}/summary"]),
        ]

    polls = (await client.get("/api/v1/datepoll", headers=headers)).json()
    if polls:
        one = polls[0]["id"]
        pages.append(
            Page(
                "datepoll details",
                [
                    me,
                    f"/api/v1/datepoll/{one}",
                    f"/api/v1/datepoll/{one}/summary",
                    f"/api/v1/datepoll/{one}/submissions",
                ],
            )
        )

    rosters = (await client.get("/api/v1/chore", headers=headers)).json()
    if rosters:
        one = rosters[0]["id"]
        pages.append(
            Page(
                "roster details",
                [
                    me,
                    f"/api/v1/chore/{one}",
                    f"/api/v1/chore/{one}/schedule",
                    f"/api/v1/chore/{one}/volunteers",
                    f"/api/v1/chore/{one}/accountability",
                ],
            )
        )

    pages.append(Page("users", [me, "/api/v1/admin/users", "/api/v1/chapters"]))
    return pages


async def _discover(client: httpx.AsyncClient, headers: dict[str, str]) -> list[Case]:
    """The endpoints worth timing, pointed at whatever is seeded.

    Discovered rather than hard-coded: an id that has gone stale would
    measure a 404, which is fast and means nothing.
    """
    cases: list[Case] = [
        Case("event list", "/api/v1/event"),
        Case("form list", "/api/v1/form"),
        Case("chapters", "/api/v1/chapters"),
        Case("auth/me", "/api/v1/auth/me"),
    ]

    for noun in ("form", "quiz", "compass"):
        rows = (await client.get(f"/api/v1/{noun}", headers=headers)).json()
        if not rows:
            continue
        one = rows[0]
        cases += [
            Case(f"{noun} details", f"/api/v1/{noun}/{one['id']}"),
            Case(f"{noun} summary", f"/api/v1/{noun}/{one['id']}/summary"),
            Case(f"{noun} submissions", f"/api/v1/{noun}/{one['id']}/submissions"),
            Case(f"{noun} csv", f"/api/v1/{noun}/{one['id']}/submissions.csv"),
            Case(f"{noun} public", f"/api/v1/{noun}/by-slug/{one['slug']}", auth=False),
        ]

    events = (await client.get("/api/v1/event", headers=headers)).json()
    if events:
        one = events[0]
        cases += [
            Case("event details", f"/api/v1/event/{one['id']}"),
            Case("event occurrences", f"/api/v1/event/{one['id']}/occurrences"),
            Case("event feedback-summary", f"/api/v1/event/{one['id']}/feedback-summary"),
            Case("event feedback csv", f"/api/v1/event/{one['id']}/feedback-submissions.csv"),
        ]

    rosters = (await client.get("/api/v1/chore", headers=headers)).json()
    if rosters:
        cases += [
            Case("roster details", f"/api/v1/chore/{rosters[0]['id']}"),
            Case("roster schedule", f"/api/v1/chore/{rosters[0]['id']}/schedule"),
            Case("roster accountability", f"/api/v1/chore/{rosters[0]['id']}/accountability"),
        ]

    polls = (await client.get("/api/v1/datepoll", headers=headers)).json()
    if polls:
        cases += [
            Case("datepoll summary", f"/api/v1/datepoll/{polls[0]['id']}/summary"),
            Case("datepoll csv", f"/api/v1/datepoll/{polls[0]['id']}/submissions.csv"),
        ]

    chapters = (await client.get("/api/v1/chapters", headers=headers)).json()
    if chapters:
        cases.append(Case("chapter agenda", f"/api/v1/tenants/rsp/agenda/{chapters[0]['slug']}", auth=False))
    return cases


def _print_header(label: str, levels: list[int]) -> None:
    header = f"{label:26}" + "".join(f"{'c=' + str(n):>26}" for n in levels)
    print(header)
    print(f"{'':26}" + "".join(f"{'p50':>8}{'p95':>9}{'rps':>9}" for _ in levels))
    print("-" * len(header))


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default=DEFAULT_BASE)
    parser.add_argument("--fill", action="store_true", help="fill every table to the BUSY profile first")
    parser.add_argument("--scale", type=int, default=1, help="multiply the BUSY profile by this")
    parser.add_argument("--reset", action="store_true", help="delete what a previous fill wrote, first")
    parser.add_argument("--requests", type=int, default=40, help="requests per endpoint per level")
    parser.add_argument("--levels", default="1,8", help="concurrency levels, comma separated")
    parser.add_argument("--only", choices=("pages", "endpoints"), help="measure just one of the two tables")
    args = parser.parse_args()

    if args.reset:
        _reset()

    if args.fill:
        profile = {k: v * args.scale for k, v in BUSY.items()}
        print(f"filling to {args.scale}x busy: {profile}")
        _fill(profile)

    levels = [int(n) for n in args.levels.split(",")]
    # One page load is up to six requests, so the pool has to hold
    # levels x paths of them. At the default 100 the client queues
    # against itself and reports the wait as the server's.
    limits = httpx.Limits(max_connections=512, max_keepalive_connections=512)
    async with httpx.AsyncClient(base_url=args.base, timeout=60.0, limits=limits) as client:
        token_res = await client.post("/api/v1/auth/dev-issue-token", json={"email": ORGANISER, "tenant": "rsp"})
        token_res.raise_for_status()
        headers = {"Authorization": f"Bearer {token_res.json()['token']}"}

        if args.only != "endpoints":
            pages = await _pages(client, headers)
            print(f"\npages: every request one screen fires, timed together. {len(pages)} screens\n")
            _print_header("page", levels)
            for page in pages:
                await _run_page(client, page, headers, concurrency=1, loads=1)  # warm
                cells = ""
                for level in levels:
                    r = await _run_page(client, page, headers, concurrency=level, loads=args.requests)
                    flag = "!" if r.errors else ""
                    cells += f"{r.pct(0.5):>8.0f}{r.pct(0.95):>9.0f}{r.rps:>8.0f}{flag:>1}"
                print(f"{page.name + ' (' + str(len(page.paths)) + ')':26}{cells}")

        if args.only != "pages":
            cases = await _discover(client, headers)
            print(f"\nendpoints: one read at a time. {len(cases)} of them\n")
            _print_header("endpoint", levels)
            for case in cases:
                await client.get(case.path, headers=headers if case.auth else {})  # warm
                cells = ""
                for level in levels:
                    r = await _run_case(client, case, headers, concurrency=level, requests=args.requests)
                    flag = "!" if r.errors else ""
                    cells += f"{r.pct(0.5):>8.0f}{r.pct(0.95):>9.0f}{r.rps:>8.0f}{flag:>1}"
                print(f"{case.name:26}{cells}")


if __name__ == "__main__":
    asyncio.run(main())
