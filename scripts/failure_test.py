import argparse
import random


FAILURE_MODES = ("none", "timeout_before_success", "timeout_after_success", "worker_crash_after_response")


def run(count=1000, seed=2026):
    rng = random.Random(seed)
    refunds = {}
    writes = {}
    succeeded = set()

    for number in range(count):
        workflow_id = f"wf-{number}"
        key = f"refund:{workflow_id}"
        mode = rng.choice(FAILURE_MODES)
        for attempt in (1, 2):
            if key in refunds:
                succeeded.add(workflow_id)
                break
            injected = mode if attempt == 1 else "none"
            if injected == "timeout_before_success":
                continue
            refunds[key] = workflow_id
            writes[key] = writes.get(key, 0) + 1
            if injected in {"timeout_after_success", "worker_crash_after_response"}:
                if injected == "timeout_after_success":
                    succeeded.add(workflow_id)
                    break
                continue
            succeeded.add(workflow_id)
            break

    duplicate_refunds = sum(max(0, total - 1) for total in writes.values())
    lost_refunds = count - len(succeeded)
    print(f"workflows={count}")
    print(f"duplicate_refunds={duplicate_refunds}")
    print(f"lost_refunds={lost_refunds}")
    assert duplicate_refunds == 0
    assert lost_refunds == 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run randomized AgentLedger failure simulations.")
    parser.add_argument("--count", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args()
    run(args.count, args.seed)

