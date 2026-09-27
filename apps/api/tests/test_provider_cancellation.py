import asyncio
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.services.answering.provider_cancellation import (
    ProviderCancelled,
    ProviderRequestScope,
    current_provider_scope,
)


def test_scope_cancels_inflight_provider_coroutine():
    asyncio.run(_run_cancellation_test())


async def _run_cancellation_test():
    entered = asyncio.Event()
    released = asyncio.Event()

    async def provider():
        entered.set()
        try:
            await asyncio.sleep(60)
        finally:
            released.set()

    scope = ProviderRequestScope(asyncio.get_running_loop())
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = asyncio.get_running_loop().run_in_executor(pool, scope.submit, provider())
        await asyncio.wait_for(entered.wait(), 1)
        scope.cancel()
        with pytest.raises(ProviderCancelled):
            await asyncio.wait_for(pending, 1)
        await asyncio.wait_for(released.wait(), 1)



def test_provider_scope_is_isolated_between_concurrent_threads():
    async def run():
        loop = asyncio.get_running_loop()
        first = ProviderRequestScope(loop)
        second = ProviderRequestScope(loop)
        token = current_provider_scope.set(first)
        task_one = asyncio.create_task(asyncio.to_thread(current_provider_scope.get))
        current_provider_scope.reset(token)
        token = current_provider_scope.set(second)
        task_two = asyncio.create_task(asyncio.to_thread(current_provider_scope.get))
        current_provider_scope.reset(token)
        assert await task_one is first
        assert await task_two is second

    asyncio.run(run())



def test_generator_provider_transport_stops_on_scope_cancellation():
    from app.services.answering.openrouter_generator import OpenRouterAnswerGenerator

    async def run():
        loop = asyncio.get_running_loop()
        entered = asyncio.Event()
        closed = asyncio.Event()
        scope = ProviderRequestScope(loop)
        generator = OpenRouterAnswerGenerator(api_key="test")

        async def slow_completion(_kwargs):
            entered.set()
            try:
                await asyncio.sleep(60)
            finally:
                closed.set()

        generator._async_create_completion = slow_completion
        token = current_provider_scope.set(scope)
        try:
            request = asyncio.create_task(
                asyncio.to_thread(
                    generator._create_completion,
                    model="test",
                    messages=[{"role": "user", "content": "test"}],
                    temperature=0,
                    max_tokens=100,
                )
            )
        finally:
            current_provider_scope.reset(token)
        await asyncio.wait_for(entered.wait(), 1)
        scope.cancel()
        with pytest.raises(ProviderCancelled):
            await asyncio.wait_for(request, 1)
        await asyncio.wait_for(closed.wait(), 1)

    asyncio.run(run())
