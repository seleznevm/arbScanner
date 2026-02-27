from __future__ import annotations

import argparse
import logging

import uvicorn

from arbscanner.worker import main as worker_main


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Arbitrage Scanner MVP launcher")
    parser.add_argument(
        "mode",
        nargs="?",
        default="api",
        choices=["api", "worker"],
        help="Run API server or background worker",
    )
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    args = parse_args()
    if args.mode == "worker":
        worker_main()
        return
    uvicorn.run(
        "arbscanner.api.app:create_app",
        host=args.host,
        port=args.port,
        factory=True,
        log_level="info",
    )


if __name__ == "__main__":
    main()
