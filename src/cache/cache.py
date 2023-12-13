import time

from cache_infra import CacheKey, CacheValue, BlockSize
from evictor_policies import EvictionPolicy, lFUDADecayFactorEvictor


class CacheResponse:
    def __init__(self, data: bytes, is_hit: bool):
        self.data = data
        self.is_hit = is_hit


# Note, this should have been a 'DB Client' class (or something like that), that has a Cache object.
# For simplicity, it's both :). Means that this Cache object should always return data. It indicates whether the data was retrieved
# using cache or DB when calling 'get'
# We assume that it makes sense to call consecutive 8KB(Metadata) offsets, and use this assumption to try and compose
# The required 64KB chunk if the full data is not in the cache
class Cache:
    def __init__(self, file_path, max_size: int = 10 * 1024, evictor: EvictionPolicy = lFUDADecayFactorEvictor) -> None:
        """
        Initializes the Cache object with the specified parameters.

        Args:
            max_size: The maximum size of the cache in bytes.
        """
        self.frequency_count: dict[CacheKey, int] = {}
        self.max_size = max_size
        self.cache: dict[CacheKey, CacheValue] = {}
        # self.recently_accessed: dict[CacheKey, float] = {} # size 100
        self.size: int = 0
        self.evictor: EvictionPolicy = evictor
        self.dynamic_evictor = False
        self.file_path = file_path

    def get(self, offset: int, size: BlockSize) -> CacheResponse:
        """
        Retrieves data from the cache or reads it from the file.

        Args:
            offset: The offset of the data to retrieve.
            size: The size of the data to retrieve.

        Returns:
            A CacheResponse object containing the requested data and a boolean flag indicating whether the data was retrieved from the cache (True) or read from the file (False).
        """

        key = CacheKey(offset, size)
        if key in self.cache:
            value = self.cache[key]
            self.cache[key] = CacheValue(value.data, time.time(), value.hit_count)
            return CacheResponse(value.data, True)  # Data retrieved from cache
        else:
            if key.size.name is BlockSize.B64.name:
                # We might get lucky...
                maybe_data = self.check_and_retrieve_consecutive_blocks(offset)
                if maybe_data:
                    return CacheResponse(maybe_data, True)
                else:
                    return self.insert_and_respond(key=key, offset=offset, size=size)
            else:
                return self.insert_and_respond(key=key, offset=offset, size=size)

    def insert_and_respond(self, key, offset, size):
        data: bytes = self.read_from_file(offset, size, self.file_path)
        self.insert(key, data)
        return CacheResponse(data, False)  # Data read from file

    def insert(self, key: CacheKey, data: bytes) -> None:
        self.evict(data, key)

        self.size += len(data)
        self.cache[key] = CacheValue(data, time.time(), 1)

        # Update eviction strategy
        # if self.dynamic_evictor:
        #     if key.size == BlockSize.B8:
        #         self.evictor = hot_block_evictor
        #     else:
        #         self.evictor = lru_evictor if self.read_pattern_is_frequent(key) else lfu_evictor

    def check_and_retrieve_consecutive_blocks(self, offset: int) -> bytes:
        """
        Checks if there are 8 consecutive offsets with size B8 in the cache, starting from the given offset,
        and returns their concatenated data if found. Otherwise, returns None.

        Args:
            cache: The cache dictionary.
            offset: The starting offset to check for consecutive blocks.

        Returns:
            bytes: The concatenated data of consecutive blocks if found, else None.
        """
        consecutive_blocks = []
        current_offset = offset

        for _ in range(8):
            # Check if the current offset exists in the cache with size B8
            cache_key = CacheKey(current_offset, BlockSize.B8)
            if cache_key not in self.cache:
                return None

            # Get the data
            current_block_data = self.cache[cache_key].data

            # Update current offset and consecutive blocks
            consecutive_blocks.append(current_block_data)
            current_offset += BlockSize.B8

        # Return concatenated data of all consecutive blocks
        print("We got lucky!")
        return b"".join(consecutive_blocks)

    def evict(self, data, key) -> None:
        if self.cache:
            self.evictor.update_internal_cache(self.cache, key)
            if self.size + len(data) > self.max_size:
                key_to_evict = self.evictor.choose_victim(self.cache)
                self.size -= len(self.cache[key_to_evict].data)
                del self.cache[key_to_evict]

    def read_from_file(self, offset: int, size: BlockSize, file_path) -> bytes:
        with open(file_path, "rb") as f:
            # Seek to the desired offset
            f.seek(offset)
            # Read the requested number of bytes
            data = f.read(size.value)

        return data

    # def read_pattern_is_frequent(self, key) -> bool:
    #     # Implement logic to analyze access patterns and determine frequency
    #
    #     # Keep track of access count for each (offset, size) combination
    #     self.access_pattern_count: Counter[CacheKey] = Counter()
    #
    #     # Update access count for the current request
    #     self.access_pattern_count[key] += 1
    #
    #     # Define frequency threshold for considering a pattern frequent
    #     frequent_threshold = 10
    #
    #     # Check if the current pattern is frequent based on the threshold
    #     return self.access_pattern_count[key] >= frequent_threshold
