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
    uv run python scripts/bench.py --fill 500                   # another

``--fill N`` writes N submissions to the seeded form, quiz and kompas
first, straight through SQLAlchemy: the point is a page with something
on it, not a benchmark of the write path. It is idempotent in the sense
that it tops each entity up to N.

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


def _fill(target: int) -> None:
    """Top the seeded form, quiz and kompas up to ``target`` submissions.

    Written with ``bulk_save_objects`` rather than one flush per row:
    filling to a few thousand is setup, and setup that takes a minute
    stops anybody running the benchmark.
    """
    from sqlalchemy import text

    from backend.config import tenants_list
    from backend.database import SessionLocal
    from backend.models import (
        Form,
        FormQuestion,
        FormQuestionOption,
        FormResponse,
        FormResponseChoice,
        FormSubmission,
    )
    from backend.services import tenancy
    from backend.services import tenants as tenants_svc

    db = SessionLocal()
    try:
        tenant = tenants_svc.find_live_organisation_by_slug(db, tenants_list()[0][0])
        assert tenant is not None
        tenancy.bind(tenant.id, tenant.brand_slug)

        for form in db.query(Form).filter(Form.archived_at.is_(None)).all():
            have = db.query(FormSubmission).filter(FormSubmission.form_id == form.id).count()
            if have >= target:
                print(f"  {form.mode:8} {form.slug}: {have} submissions, already at target")
                continue
            questions = (
                db.query(FormQuestion).filter(FormQuestion.form_id == form.id).order_by(FormQuestion.ordinal).all()
            )
            options = {
                q.id: db.query(FormQuestionOption).filter(FormQuestionOption.question_id == q.id).all()
                for q in questions
            }
            subs, answers, choices = [], [], []
            for n in range(target - have):
                sub_id = str(uuid.uuid7()) if hasattr(uuid, "uuid7") else str(uuid.uuid4())
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

        # Without this the first run measures the planner working from
        # statistics gathered when these tables were nearly empty, which
        # is a different query plan from the one production would pick.
        # It cost an afternoon once: every read looked slow, and the
        # ranking it produced was an artefact of the load, not of the
        # code.
        db.execute(text("ANALYZE form_submissions, form_responses, form_response_choices"))
        db.commit()
        print("  analyzed")
    finally:
        db.close()


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
            Case(f"{noun} public", f"/api/v1/{noun}/by-slug/{one['slug']}", auth=False),
        ]

    events = (await client.get("/api/v1/event", headers=headers)).json()
    if events:
        one = events[0]
        cases += [
            Case("event details", f"/api/v1/event/{one['id']}"),
            Case("event occurrences", f"/api/v1/event/{one['id']}/occurrences"),
            Case("event feedback-summary", f"/api/v1/event/{one['id']}/feedback-summary"),
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
        cases.append(Case("datepoll summary", f"/api/v1/datepoll/{polls[0]['id']}/summary"))

    chapters = (await client.get("/api/v1/chapters", headers=headers)).json()
    if chapters:
        cases.append(Case("chapter agenda", f"/api/v1/tenants/rsp/agenda/{chapters[0]['slug']}", auth=False))
    return cases


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default=DEFAULT_BASE)
    parser.add_argument("--fill", type=int, default=0, help="top every form up to N submissions first")
    parser.add_argument("--requests", type=int, default=40, help="requests per endpoint per level")
    parser.add_argument("--levels", default="1,8", help="concurrency levels, comma separated")
    args = parser.parse_args()

    if args.fill:
        print(f"filling to {args.fill} submissions per form")
        _fill(args.fill)

    levels = [int(n) for n in args.levels.split(",")]
    async with httpx.AsyncClient(base_url=args.base, timeout=60.0) as client:
        token_res = await client.post("/api/v1/auth/dev-issue-token", json={"email": ORGANISER, "tenant": "rsp"})
        token_res.raise_for_status()
        headers = {"Authorization": f"Bearer {token_res.json()['token']}"}
        cases = await _discover(client, headers)

        print(f"\n{len(cases)} endpoints, {args.requests} requests each, at concurrency {levels}\n")
        header = f"{'endpoint':26}" + "".join(f"{'c=' + str(n):>26}" for n in levels)
        print(header)
        print(f"{'':26}" + "".join(f"{'p50':>8}{'p95':>9}{'rps':>9}" for _ in levels))
        print("-" * len(header))

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
