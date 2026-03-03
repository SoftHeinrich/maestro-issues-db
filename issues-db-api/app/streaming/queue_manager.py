import asyncio


class QueueManager:
    def __init__(self):
        self.__queues = {}
        self.__max_id = 0
        self.__pending_deletes = set()
        self.__lock = asyncio.Lock()

    def new_queue(self):
        self.__max_id += 1
        self.__queues[self.__max_id] = asyncio.Queue()
        return self.__max_id

    async def dequeue(self, uid):
        return await self.__queues[uid].get()

    async def enqueue(self, item):
        async with self.__lock:
            for uid in self.__pending_deletes:
                try:
                    del self.__queues[uid]
                except KeyError:
                    # Queue was already removed; ignore
                    pass
            for queue in self.__queues.values():
                await queue.put(item)

    async def unsubscribe(self, uid):
        async with self.__lock:
            self.__pending_deletes.add(uid)
