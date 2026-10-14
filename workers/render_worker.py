import asyncio
import logging
import signal
from app.application import app
from app.jobs.workers import batch_worker

logger = logging.getLogger("render_worker")

async def main():
    try:
        import uvloop
        uvloop.install()
    except ImportError:
        pass

    logger.info("Initializing Render background worker...")
    await app.setup()

    stop_event = asyncio.Event()

    def handle_signal():
        logger.info("Received termination signal.")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, handle_signal)
        except NotImplementedError:
            # Signal handling on Windows / limited event loops
            pass

    worker_task = asyncio.create_task(batch_worker.start())

    await stop_event.wait()
    logger.info("Shutting down Render worker...")
    await batch_worker.stop()
    worker_task.cancel()
    await app.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
