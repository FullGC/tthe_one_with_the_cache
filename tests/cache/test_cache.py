import csv
import os
import random
from pathlib import Path
from time import sleep

import pytest

from cache.cache import Cache
from cache.cache_infra import BlockSize
from evictor_policies import lru_evictor, lfu_evictor, lFUDADecayFactorEvictor

path = Path(os.path.abspath(__file__)).parents[0] / "data.bin"

file_size = 3 * 1024


@pytest.fixture
def random_file(tmpdir):
    os.remove(path)

    with open(path, "wb") as f:
        f.write(os.urandom(file_size))
    return path

@pytest.mark.parametrize("evictor, num_reads",
[
    (lru_evictor, 1500),
    (lfu_evictor, 1500),
    (lFUDADecayFactorEvictor, 1500),
    (lru_evictor, 3000),
    (lfu_evictor, 3000),
    (lFUDADecayFactorEvictor, 3000),
    (lru_evictor, 5000),
    (lfu_evictor, 5000),
    (lFUDADecayFactorEvictor, 5000),
]
)
def test_cache_hit_ratio(random_file, evictor, num_reads):

    max_cache_size = 1 * 512
    lowest_metadata_first_offsets_range = file_size / 10
    highest_metadata_first_offsets_range = file_size / 5
    max_hot_offsets_range_start = file_size / 100
    metadata_only_blocks_ratio = 0.7
    delay_between_calls = 1 / 10000  # 0.0001 seconds
    new_hot_offset_chance = 0.01

    # Track hits and misses
    hits = 0
    misses = 0
    prev_offset = -1
    prev_size = None

    # Run reads with random offsets and sizes
    for _ in range(5):
        # random range of offsets (up to a file_size /100)
        hot_offsets_range_start = random.randint(0, file_size - 1)
        hot_offsets_range_end = min(hot_offsets_range_start + int(max_hot_offsets_range_start), file_size - 1)
        metadata_first_offsets_range = random.randint(int(lowest_metadata_first_offsets_range), int(highest_metadata_first_offsets_range))
        cache = Cache(path, max_size=max_cache_size, evictor=evictor)

        for _ in range(num_reads):
            if random.random() < metadata_only_blocks_ratio:
                if prev_size is BlockSize.B8 and 0 < prev_offset < metadata_first_offsets_range:
                    offset = prev_offset
                    size = BlockSize.B64
                else:
                    offset = random.randint(hot_offsets_range_start, hot_offsets_range_end)
                    size = BlockSize.B8
            else:
                if prev_size is BlockSize.B8 and 0 < prev_offset < metadata_first_offsets_range:
                    offset = prev_offset
                    size = BlockSize.B64
                else:
                    offset = random.randint(0, file_size - 1)
                    size = BlockSize.B8
            data = cache.get(offset, size)
            sleep(delay_between_calls)
            prev_offset = offset
            prev_size = size
            if data.is_hit:
                hits += 1
            else:
                misses += 1
            if random.random() < new_hot_offset_chance:
                hot_offsets_range_start = random.randint(0, file_size - 1)
                hot_offsets_range_end = min(hot_offsets_range_start + int(max_hot_offsets_range_start), file_size - 1)

    # Calculate hit ratio
    hit_ratio = hits / (hits + misses)
    print(f"hit_ratio: {hit_ratio} for evictor: {evictor.__class__}, reads = {num_reads}")
    # Assert hit ratio
    #assert hit_ratio > 0.5, f"Cache hit ratio is not greater than 0.5 with max_size={max_size}"
    with open("cache_hit_ratio_results.csv", "a") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow([evictor.__class__.__name__, num_reads, hit_ratio])
