import sys
import asyncio

# Fix for Playwright on Windows: Force ProactorEventLoop
# This is needed because uvicorn/fastapi might use SelectorEventLoop by default,
# but Playwright requires ProactorEventLoop for subprocesses.
if sys.platform == 'win32':
    try:
        if isinstance(asyncio.get_event_loop_policy(), asyncio.WindowsSelectorEventLoopPolicy):
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except Exception:
        pass
