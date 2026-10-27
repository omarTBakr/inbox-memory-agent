"""Standalone Gmail watcher (`make worker`): the same auto-trigger the API runs, in its own process.

Use it when the API isn't running. The Postgres advisory lock keeps it from handling mail
twice if the API's watcher is also on; whichever started first does the work.
"""

import logging
import signal

from email_assistant.gmail.watcher import watcher


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    signal.signal(signal.SIGTERM, lambda *_: watcher.stop())
    watcher.start()
    try:
        while watcher.alive:
            watcher._thread.join(1)
    except KeyboardInterrupt:
        watcher.stop()


if __name__ == "__main__":
    main()
