import logging
from contextlib import asynccontextmanager
from typing import Generic, TypeVar, Type

import anyio
from anyio.abc import ObjectSendStream, ObjectReceiveStream

T = TypeVar("T")


class BroadcastStream(Generic[T]):
    def __init__(self):
        self.streams: list[ObjectSendStream[T]] = []

    async def broadcast(self, packet):
        logging.debug(f"Broadcasting {packet} to {len(self.streams)} streams")
        for stream in self.streams:
            try:
                await stream.send(packet)
            except anyio.BrokenResourceError:
                logging.error("Broken resource error")
                # self.streams.remove(stream)

    @asynccontextmanager
    async def open_stream(self):
        # 1000 seems like a reasonable number, if more than 1000 messages come in before someone deals with them it will
        #  start stalling the APNs connection itself
        send, recv = anyio.create_memory_object_stream[T](max_buffer_size=1000)
        self.streams.append(send)
        async with recv:
            yield recv
            self.streams.remove(send)
            await send.aclose()


W = TypeVar("W")
F = TypeVar("F", covariant=True)


class FilteredStream(ObjectReceiveStream[F]):
    def __init__(self, source: ObjectReceiveStream[W], filter: Type[F]):
        self.source = source
        self.filter = filter

    async def receive(self) -> F:
        async for item in self.source:
            if isinstance(item, self.filter):
                return item
        raise anyio.EndOfStream

    async def aclose(self):
        await self.source.aclose()


def exponential_backoff(f):
    async def wrapper(*args, **kwargs):
        backoff = 1
        while True:
            try:
                return await f(*args, **kwargs)
            except Exception as e:
                logging.warning(
                    f"Error in {f.__name__}: {e}, retrying in {backoff} seconds"
                )
                await anyio.sleep(backoff)
                backoff *= 2

    return wrapper
