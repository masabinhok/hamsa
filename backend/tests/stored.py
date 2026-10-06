"""Helpers for tests that need a real (temporary) case database."""

from pathlib import Path

from app.pipeline.contracts import RouteDecision
from app.pipeline.run import Result
from app.router.route import StageOutputs, route
from app.store.cases import Database, claim_job, complete_job, create_case
from app.store.models import Case, Channel
from tests.factories import outputs


def database(tmp_path: Path) -> Database:
    db = Database(f"sqlite:///{tmp_path / 'hamsa.db'}")
    db.create_all()
    return db


def routed_result(stage_outputs: StageOutputs | None = None) -> Result:
    result = stage_outputs or outputs()
    return Result(outputs=result, decision=route(result), seconds={"extract": 1.0})


def add_case(db: Database, case_id: str, text: str = "मेलम्ची बजार बगायो") -> None:
    with db.session.begin() as session:
        create_case(session, case_id, Channel.WEB, text, None, [])


def add_routed_case(db: Database, case_id: str, result: Result | None = None) -> RouteDecision:
    add_case(db, case_id)
    result = result or routed_result()
    with db.session.begin() as session:
        claimed = claim_job(session)
        assert claimed is not None
        complete_job(
            session,
            claimed[0],
            session.get_one(Case, case_id),
            result.outputs,
            result.decision,
            result.seconds,
        )
    return result.decision
