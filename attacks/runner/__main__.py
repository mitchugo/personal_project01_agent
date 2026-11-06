"""CLI: python -m attacks.runner [--case ID ...] [--category C] [--kind attack|benign] [--trials N] ...

Mock mode is the default and makes no network calls. Live mode requires BOTH --live and
a positive --budget-usd, and still refuses model fallback. Exit codes: 0 ok, 2 bad
selection or dataset, 3 harness abort, 4 budget exhausted.
"""

import argparse
import logging
import sys
from pathlib import Path

from attacks.runner.campaign import run_campaign
from attacks.runner.providers import LiveModeRefused
from attacks.runner.schema import DatasetError, load_dataset, select
from attacks.runner.trial import RunConfig


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m attacks.runner", description=__doc__.splitlines()[0])
    p.add_argument("--case", action="append", dest="cases", help="case ID (repeatable)")
    p.add_argument("--category")
    p.add_argument("--kind", choices=["attack", "benign"])
    p.add_argument("--trials", type=int, default=1)
    p.add_argument("--behaviour", default="obedient", help="mock script name (mock mode)")
    p.add_argument("--model", default="claude-sonnet-5-5")
    p.add_argument("--live", action="store_true", help="use the real model (costs money)")
    p.add_argument("--budget-usd", type=float, default=None)
    p.add_argument("--timeout-s", type=float, default=60.0)
    p.add_argument("--out", type=Path, default=None, help="evidence directory (omit for no files)")
    p.add_argument("--list", action="store_true", help="list cases and exit")
    args = p.parse_args(argv)

    audit = logging.getLogger("audit")
    propagate, audit.propagate = audit.propagate, False   # audit JSON is captured, not echoed to the console
    try:
        return _run(args)
    finally:
        audit.propagate = propagate


def _run(args) -> int:
    try:
        dataset = load_dataset()
        if args.list:
            for c in dataset.cases:
                print(f"{c.id:10} {c.kind:7} {c.category:22} {c.objective[:70]}")
            return 0
        if not 1 <= args.trials <= 20:
            raise DatasetError("--trials must be between 1 and 20")
        cases = select(dataset, args.cases, args.category, args.kind)
        cfg = RunConfig(mode="live" if args.live else "mock", behaviour=args.behaviour,
                        configured_model=args.model, trials=args.trials,
                        budget_usd=args.budget_usd if args.budget_usd is not None else 1.0,
                        trial_timeout_s=args.timeout_s)
        if args.live and (args.budget_usd is None or args.budget_usd <= 0):
            raise LiveModeRefused("live mode needs a positive --budget-usd")
        result = run_campaign(cases, cfg, dataset_version=dataset.version, dataset_hashes=dataset.sha256,
                              out_dir=args.out, live=args.live)
    except (DatasetError, LiveModeRefused) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    for r in result.records:
        print(f"{r['trial_id']:12} {r['status']:9} {r['grade']['security_outcome']:26} "
              f"proposed={sum(len(t['model_proposed_tool_calls']) for t in r['turns'])} "
              f"executed_ok={sum(a.get('status') == 'ok' for t in r['turns'] for a in t['backend_actions'])} "
              f"cost≈{r['usage']['cost_usd']}")
    print(f"stopped: {result.stopped or 'no'}; approx cost ${result.spent_usd} "
          f"({'simulated' if not args.live else 'estimated'})")
    if result.stopped and result.stopped.startswith("harness_abort"):
        return 3
    return 4 if result.stopped == "budget_exhausted" else 0


if __name__ == "__main__":
    sys.exit(main())
