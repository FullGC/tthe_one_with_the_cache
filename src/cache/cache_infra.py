from enum import Enum

class BlockSize(Enum):
    B8 = 8
    B64 = 64

class CacheKey:
    def __init__(self, offset: int, size: BlockSize):
        self.offset = offset
        self.size = size
    def __eq__(self, other):
        """
        Compares the current CacheKey object with another object for equality.

        Args:
            other: The object to compare with.

        Returns:
            True if the objects have identical offset and size, False otherwise.
        """
        if isinstance(other, CacheKey):
            return self.offset == other.offset and self.size == other.size
        return False
    def __hash__(self):
        return hash((self.offset, self.size))


# Note, keeping metadata in the response(i.e. access_time) is not very efficient.
# Each policy should keep its own metadata / have global 'statistics' metadata
class CacheValue:
    def __init__(self, data: bytes, access_time: float, hit_count: int = 0):
        self.data = data
        self.access_time = access_time
        self.hit_count = hit_count
