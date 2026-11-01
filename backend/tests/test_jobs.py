from app.jobs import claim_job, complete_job, enqueue_job, fail_job, recover_expired_leases
from app.models import Job, Workspace, utcnow
from datetime import timedelta


def _workspace(session, owner="owner-a"):
    workspace = Workspace(owner_id=owner)
    session.add(workspace)
    session.commit()
    return workspace


def test_claim_heartbeat_and_recovery(session):
    workspace = _workspace(session)
    job = enqueue_job(session, owner_id="owner-a", workspace_id=workspace.id, kind="analyse", payload={})
    claimed = claim_job(session, "worker-1")
    assert claimed is not None
    assert claimed.id == job.id
    assert claimed.status == "leased"
    assert claim_job(session, "worker-2") is None

    claimed.lease_expires_at = utcnow() - timedelta(seconds=5)
    session.commit()
    recovered = recover_expired_leases(session)
    assert recovered == 1
    again = claim_job(session, "worker-2")
    assert again is not None
    assert again.id == job.id
    assert again.attempts == 2


def test_idempotent_enqueue(session):
    workspace = _workspace(session)
    first = enqueue_job(
        session,
        owner_id="owner-a",
        workspace_id=workspace.id,
        kind="extract",
        payload={"asset_id": "1"},
        idempotency_key="abc",
    )
    second = enqueue_job(
        session,
        owner_id="owner-a",
        workspace_id=workspace.id,
        kind="extract",
        payload={"asset_id": "1"},
        idempotency_key="abc",
    )
    assert first.id == second.id


def test_fail_then_dead_letter(session):
    workspace = _workspace(session)
    job = enqueue_job(session, owner_id="owner-a", workspace_id=workspace.id, kind="extract", payload={})
    job.max_attempts = 2
    session.commit()
    claimed = claim_job(session, "w")
    fail_job(session, claimed, "temporary")
    stored = session.get(Job, job.id)
    assert stored.status == "queued"
    stored.available_at = utcnow()
    session.commit()
    claimed = claim_job(session, "w")
    assert claimed is not None
    fail_job(session, claimed, "still failing")
    assert session.get(Job, job.id).status == "failed"


def test_complete_persists_result(session):
    workspace = _workspace(session)
    job = enqueue_job(session, owner_id="owner-a", workspace_id=workspace.id, kind="analyse", payload={})
    claimed = claim_job(session, "w")
    complete_job(session, claimed, {"ok": True})
    stored = session.get(Job, job.id)
    assert stored.status == "succeeded"
    assert stored.result == {"ok": True}
