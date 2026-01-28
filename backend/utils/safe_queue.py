import queue
from backend.utils.log_util import logger


class SafeQueue:
    """
    一个“丢最旧元素”的有界队列：
    - put(): 队列满时会丢弃最旧的元素，然后插入新元素，不会阻塞
    - get(timeout=None): 默认阻塞等待；timeout 超时会抛 queue.Empty
    """

    def __init__(self, maxsize: int = 0, name: str = "SafeQueue"):
        self._q = queue.Queue(maxsize=maxsize)
        self.name = name

    def put(self, item):
        while True:
            try:
                # 非阻塞插入；如果满了会抛 queue.Full
                self._q.put(item, block=False)
                return
            except queue.Full:
                logger.info(f"{self.name} 队列已满，移除最旧的值")
                try:
                    # 丢弃最旧的一个
                    self._q.get_nowait()
                except queue.Empty:
                    # 极端情况下被其他消费者抢走了，继续重试
                    pass

    def get(self):
        # while True:
        try:
            return self._q.get()
        except queue.Empty:
            logger.info(f"{self.name} 队列为空")
            return None
