import time
from collections import deque
import numpy as np
from cache_infra import CacheKey, CacheValue, BlockSize


def choose_oldest(cache: dict[CacheKey, CacheValue]):
    oldest_key = None
    oldest_access_time = float("inf")

    # Iterate through the cache and find the least recently used entry
    for key, value in cache.items():
        if value.access_time < oldest_access_time:
            oldest_key = key
            oldest_access_time = value.access_time
    return oldest_key


class EvictionPolicy():
    def choose_victim(self, cache: dict[CacheKey, CacheValue]):
        pass

    def update_internal_cache(self, cache: dict[CacheKey, CacheValue], key: CacheKey):
        pass

# Calculate a score based on the past up-to-ten call per offset
# More weight given to recent accesses using an exponential decay scheme.
# 64 KB' chunks offset score is 1/8 of the equivalent 8 KB' chunk
# The key with the lowest score will be evicted
class LFUDADecayFactorEvictor(EvictionPolicy):
    def __init__(self, decay_factor=0.5):
        #self.frequency_count: dict[CacheKey, int] = {}
        self.recent_accesses: dict[CacheKey, deque[float]] = {}
        self.max_recent_accesses = 10
        self.decay_factor = decay_factor


    def choose_victim(self, cache: dict[CacheKey, CacheValue]):
        # Calculate dynamic aging score
        # should be adjusted
        min_score = float("inf")
        victim = None
        current_time = time.time()
        for key, access_timestamps in self.recent_accesses.items():
            if access_timestamps:
                recency_score = 1 / (
                    current_time *2 - sum(access_timestamps * (self.decay_factor ** np.arange(len(access_timestamps)))))
            else:
                recency_score = 0
            if key.size.name == BlockSize.B64.name:
                recency_score = recency_score / 8
            if key in cache and recency_score < min_score:
                victim = key
                min_score = recency_score
        return victim
    # Background operation
    def update_internal_cache(self, cache: dict[CacheKey, CacheValue], key: CacheKey):
        if key not in self.recent_accesses:
            self.recent_accesses[key] = deque(maxlen=self.max_recent_accesses)
        self.recent_accesses[key].append(time.time())


# This keeps the requests count and the latest request timestamp, and calculates a 'score' based on them.
# A few notes:
# 1. I would calculate the score for x number of requests for each key (call it last_access_times of type queue).
# Keys older then, for example, 1 hour would be dequeue, and the max size would be 5 (depending on the avg frequency)
class LFUDAEvictor(EvictionPolicy):
    def __init__(self):
        self.frequency_count: dict[CacheKey, int] = {}
        #self.cache_age_start: float = time.time()
        self.last_access_time: dict[CacheKey, float] = {}

    def choose_victim(self, cache: dict[CacheKey, CacheValue]):
        # Calculate dynamic aging score

        # Calculate combined score
        combined_scores = {}
        for key, value in self.frequency_count.items():
            # age_score = (time.time() - self.cache_age_start) / 100
            time_passed = (time.time() - self.last_access_time.get(key, 0.0))
            if time_passed == 0:
                recency_score = 1
            elif not self.last_access_time.get(key):
                recency_score = 0
            else:
                recency_score = 1 / (time.time() - self.last_access_time.get(key))
            combined_score = (value
                              # + age_score
                              + recency_score)
            combined_scores[key] = combined_score if key.size == BlockSize.B8 else combined_score / 8

        # Find entry with minimum score using a loop
        victim = None
        min_score = float("inf")
        for key, score in combined_scores.items():
            if key in cache and score < min_score:
                victim = key
                min_score = score
        return victim

    # Background operation
    def update_internal_cache(self, cache: dict[CacheKey, CacheValue], key: CacheKey):
        if key not in self.frequency_count:
            self.frequency_count[key] = 0
        self.frequency_count[key] += 1
        self.last_access_time[key] = time.time()


###### Standard policies for Test #########

class LRUEvictor(EvictionPolicy):
    def choose_victim(self, cache: dict[CacheKey, CacheValue]):
        """
        Chooses the victim to evict from the cache based on the LRU policy.

        Args:
            cache: A dictionary containing the cached data and its corresponding values.

        Returns:
            The CacheKey of the victim to evict.
        """

        return choose_oldest(cache)

    def update_internal_cache(self, cache: dict[CacheKey, CacheValue], key: CacheKey):
        return True

class LFUEvictor:
    def __init__(self):
        self.frequency_count: dict[CacheKey, int] = {}

    def choose_victim(self, cache: dict[CacheKey, CacheValue]):
        for key, data in cache.items():
            if key not in self.frequency_count:
                self.frequency_count[key] = 0
            self.frequency_count[key] += 1

        return min(cache, key=self.frequency_count.get)

    def update_internal_cache(self, cache: dict[CacheKey, CacheValue], key: CacheKey):
        return True


# hot_block_threshold should be adjusted.

class HotBlockEvictor(EvictionPolicy):
    def __init__(self, hot_block_threshold: float = 10) -> None:
        """
        Initializes the HotBlockEvictor object with the specified threshold.

        Args:
            hot_block_threshold: The threshold for considering a block hot.
        """
        self.hot_block_threshold = hot_block_threshold
        self.hot_blocks: dict[CacheKey, float] = {}

    def choose_victim(self, cache: dict[CacheKey, CacheValue]) -> CacheKey:
        """
        Chooses the victim to evict from the cache based on the hot block heuristic.

        Args:
            cache: A dictionary containing the cached data and its corresponding values.
            access_time: A dictionary storing the access time for each key in the cache.

        Returns:
            The CacheKey of the victim to evict.
        """

        # Identify recently accessed blocks
        recently_accessed_blocks = {key for key, value in cache.items() if
                                    (time.time() - value.access_time) < self.hot_block_threshold}

        # Update hot block dictionary
        for key in recently_accessed_blocks:
            if key not in self.hot_blocks:
                self.hot_blocks[key] = 0
            self.hot_blocks[key] += 1

        # Choose victim based on hotness score
        victim = None
        hottest_score = 0
        for key, score in self.hot_blocks.items():
            if key in cache and score > hottest_score:
                victim = key
                hottest_score = score

        # Remove victim from hot blocks if it's not in the cache anymore
        if victim not in cache:
            del self.hot_blocks[victim]

        return victim

    def update_internal_cache(self, cache: dict[CacheKey, CacheValue], key: CacheKey):
        return True

lFUDADecayFactorEvictor = LFUDADecayFactorEvictor()

lFUDAEvictor = LFUDAEvictor()
hot_block_evictor = HotBlockEvictor()
lru_evictor = LRUEvictor()
lfu_evictor = LFUEvictor()
