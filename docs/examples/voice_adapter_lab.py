"""Synthetic integration lab: Python 3.12, no network/model/audio/database.

The fake service's in-process storage/lock is NOT production persistence.
Playback evidence is simulated: a real gateway must validate carrier marks.
"""
from dataclasses import dataclass
import hashlib
import json
from threading import Lock


@dataclass(frozen=True)
class Context:
    tenant: str
    actor: str
    call: str


class Rejected(Exception):
    pass


class FakeEnterprise:
    def __init__(self):
        self.lock = Lock()
        self.capacity = 1
        self.results = {}
        self.offer = {"resource_id": "remote-session-123", "version": 3,
                      "starts_at": "2026-10-06T16:00:00+05:30",
                      "ends_at": "2026-10-06T18:00:00+05:30",
                      "price": {"amount_minor": 50000, "currency": "INR"}}

    def authorize(self, context):
        if context.tenant != "sandbox-clinic" or context.actor != "sandbox-staff":
            raise Rejected("NOT_AUTHORIZED")

    def search(self, context):
        self.authorize(context)
        with self.lock:
            return [json.loads(json.dumps(self.offer))] if self.capacity else []

    def reserve(self, context, key, body, lose_response=False):
        self.authorize(context)
        digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        scoped_key = (context.tenant, key)
        with self.lock:
            if scoped_key in self.results:
                old_digest, result = self.results[scoped_key]
                if digest != old_digest:
                    raise Rejected("IDEMPOTENCY_INPUT_CHANGED")
                return dict(result)
            if body["resource_id"] != self.offer["resource_id"]:
                raise Rejected("UNKNOWN_RESOURCE")
            if body["expected_version"] != self.offer["version"]:
                raise Rejected("STALE_VERSION")
            if (body["agreed_amount_minor"], body["currency"]) != (50000, "INR"):
                raise Rejected("TERMS_CHANGED")
            if not self.capacity:
                raise Rejected("CAPACITY_FULL")
            self.capacity -= 1
            result = {"status": "committed", "reference": "SYNTHETIC-001"}
            self.results[scoped_key] = (digest, result)
        if lose_response:
            raise TimeoutError("simulated lost acknowledgement AFTER commit")
        return dict(result)

    def lookup(self, context, key):
        self.authorize(context)
        with self.lock:
            record = self.results.get((context.tenant, key))
            return dict(record[1]) if record else {"status": "unknown"}


def dispatch(name, arguments, context, enterprise):
    if name != "search_availability":
        raise Rejected("TOOL_NOT_ALLOWED")
    if arguments:
        raise Rejected("INVALID_ARGUMENTS")
    return {"ok": True, "options": [
        {"session_id": item["resource_id"], "version": item["version"],
         "starts_at": item["starts_at"], "ends_at": item["ends_at"],
         "fee_minor": item["price"]["amount_minor"],
         "currency": item["price"]["currency"]}
        for item in enterprise.search(context)]}


class ApprovalRuntime:
    def __init__(self, context, option, operation_id):
        self.context, self.operation_id = context, operation_id
        self.body = {"resource_id": option["session_id"],
                     "beneficiary_id": "remote-customer-456",
                     "expected_version": option["version"],
                     "agreed_amount_minor": option["fee_minor"],
                     "currency": option["currency"]}
        self.active = True
        self.segment = "synthetic-segment-1"
        self.completed_turn = None

    def presented(self, segment, turn):
        if not self.active or segment != self.segment:
            raise Rejected("INACTIVE_SEGMENT")
        self.completed_turn = turn

    def interrupt(self):
        self.active = False

    def commit(self, enterprise, approval_turn, intent, lose_response=False):
        if (not self.active or self.completed_turn is None
                or approval_turn <= self.completed_turn or intent != "CONFIRM"):
            raise Rejected("APPROVAL_GUARD_FAILED")
        try:
            return enterprise.reserve(self.context, self.operation_id,
                                      self.body, lose_response)
        except TimeoutError:
            # Never replay here. Missing evidence remains unknown.
            return enterprise.lookup(self.context, self.operation_id)


def expect_rejection(action):
    try:
        action()
    except Rejected:
        return
    raise AssertionError("expected rejection")


def main():
    context = Context("sandbox-clinic", "sandbox-staff", "synthetic-call")
    enterprise = FakeEnterprise()
    result = dispatch("search_availability", {}, context, enterprise)
    print("READ:", json.dumps(result))
    option = result["options"][0]
    runtime = ApprovalRuntime(context, option, "synthetic-operation-1")
    expect_rejection(lambda: runtime.commit(enterprise, 1, "CONFIRM"))
    runtime.presented(runtime.segment, 1)
    expect_rejection(lambda: runtime.commit(enterprise, 1, "CONFIRM"))
    expect_rejection(lambda: runtime.commit(enterprise, 2, "UNCLEAR"))
    committed = runtime.commit(enterprise, 2, "CONFIRM", lose_response=True)
    assert committed["status"] == "committed" and enterprise.capacity == 0
    print("RECOVERED AFTER LOST RESPONSE:", json.dumps(committed))
    assert runtime.commit(enterprise, 2, "CONFIRM") == committed
    assert enterprise.capacity == 0 and len(enterprise.results) == 1
    changed = dict(runtime.body, agreed_amount_minor=60000)
    expect_rejection(lambda: enterprise.reserve(context, runtime.operation_id, changed))
    expect_rejection(lambda: enterprise.reserve(context, "new-operation", runtime.body))
    expect_rejection(lambda: dispatch("commit_booking", {}, context, enterprise))
    expect_rejection(lambda: dispatch("search_availability", {"tenant": "other"},
                                      context, enterprise))
    other = Context("other-tenant", "sandbox-staff", "synthetic-call")
    expect_rejection(lambda: enterprise.lookup(other, runtime.operation_id))
    interrupted = ApprovalRuntime(context, option, "interrupted-operation")
    interrupted.presented(interrupted.segment, 1)
    interrupted.interrupt()
    expect_rejection(lambda: interrupted.commit(enterprise, 2, "CONFIRM"))
    assert enterprise.lookup(context, "never-submitted")["status"] == "unknown"
    print("PASS: synthetic integration checks")


if __name__ == "__main__":
    main()
