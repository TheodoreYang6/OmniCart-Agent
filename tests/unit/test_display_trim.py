"""网格展示数量修整单测（core/display.py）。

用户实拍反馈：每行 3 卡时 7 个排成 3/3/1 落单丑；5 个（3/2）可接受。
口径被候选集（compiler/response_agent）与装配终点（retrieval_agent/graph）共用，
错位会重现"回答讲了 4 款、卡片只列 3 款"（实拍坐实过）。
"""

from app.core.display import GRID_COLS, trim_for_grid


def test_trim_drops_lonely_last_row():
    """末行落单（% 3 == 1）→ 砍最后一个：4→3、7→6、10→9。"""
    for n, expect in ((4, 3), (7, 6), (10, 9)):
        assert len(trim_for_grid(list(range(n)))) == expect, n


def test_trim_keeps_acceptable_two_in_last_row():
    """末行 2 个可接受（用户明确反馈）：5→5、8→8；整行 3/6/9 不动。"""
    for n in (5, 8, 3, 6, 9, 12):
        assert len(trim_for_grid(list(range(n)))) == n, n


def test_trim_never_empties_small_lists():
    """1/2/3 个不处理（砍了丢信息且 1 个本就正常）。"""
    for n in (0, 1, 2, 3):
        assert len(trim_for_grid(list(range(n)))) == n, n


def test_trim_drops_lowest_priority_tail():
    """砍掉的必须是最后一项（列表约定按得分降序）。"""
    out = trim_for_grid(["a", "b", "c", "d"])
    assert out == ["a", "b", "c"]


def test_trim_returns_new_list():
    """不修整时也返回新列表，不共享引用（防调用方原地改动串味）。"""
    src = [1, 2, 3]
    out = trim_for_grid(src)
    assert out == src and out is not src


def test_grid_cols_matches_frontend():
    """列数常量与前端 sm:grid-cols-3 对齐；若前端改列数，此测提醒同步。"""
    assert GRID_COLS == 3
