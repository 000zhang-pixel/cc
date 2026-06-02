from __future__ import annotations

import pytest
from utils.helpers import parse_count, safe_filename, chunk_list


def test_parse_count_wan():
    assert parse_count("1.2万") == 12000

def test_parse_count_yi():
    assert parse_count("2.1亿") == 210000000

def test_parse_count_k():
    assert parse_count("3.8k") == 3800

def test_parse_count_plain():
    assert parse_count("12345") == 12345

def test_parse_count_empty():
    assert parse_count("") == 0

def test_safe_filename():
    name = safe_filename("你好/世界:*?")
    assert "/" not in name
    assert ":" not in name

def test_chunk_list():
    assert chunk_list([1,2,3,4,5], 2) == [[1,2],[3,4],[5]]
