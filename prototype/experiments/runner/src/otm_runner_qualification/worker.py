"""Owned subprocess entry points for runner/crash qualification, never a production worker CLI."""

import argparse
import sys

from otm_runner_qualification.harness import QUEUE, build_runner, engine_for_test, stage_acceptance


# Run a candidate native worker or pause a toy acceptance process at a signaled boundary.
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("worker", "before_commit", "after_commit"))
    parser.add_argument("--request-key")
    parser.add_argument("--wait", action="store_true")
    args = parser.parse_args()
    engine = engine_for_test()
    try:
        if args.mode == "worker":
            runner = build_runner(engine, worker=True)
            runner.app.run_worker(
                queues=[QUEUE],
                wait=args.wait,
                concurrency=2,
                fetch_job_polling_interval=0.05,
                listen_notify=False,
                update_heartbeat_interval=0.1,
                stalled_worker_timeout=0.5,
            )
        else:
            runner = build_runner(engine)
            with runner.app.open():
                with engine.begin() as connection:
                    stage_acceptance(connection, runner.task, args.request_key)
                    if args.mode == "before_commit":
                        print("boundary-ready", flush=True)
                        sys.stdin.readline()
                if args.mode == "after_commit":
                    print("boundary-ready", flush=True)
                    sys.stdin.readline()
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
