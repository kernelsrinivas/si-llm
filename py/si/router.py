"""Single-layer orthogonal autorouter. Not length-matched, not a diff-pair router, not a via router."""

from __future__ import annotations

import heapq

STEP = 0.5


def _grid(value: float, origin: float) -> int:
    return int(round((value - origin) / STEP))


def _mm(cell: int, origin: float) -> float:
    return round(origin + cell * STEP, 3)


def _corners(cells: list[tuple[int, int]], origin_x: float, origin_y: float) -> list[list[float]]:
    if not cells:
        return []
    keep = [cells[0]]
    for prev, cur, nxt in zip(cells, cells[1:], cells[2:]):
        if (cur[0] - prev[0], cur[1] - prev[1]) != (nxt[0] - cur[0], nxt[1] - cur[1]):
            keep.append(cur)
    keep.append(cells[-1])
    return [[_mm(x, origin_x), _mm(y, origin_y)] for x, y in keep]


def _search(start: tuple[int, int], goal: tuple[int, int], blocked: set[tuple[int, int]], width: int, height: int):
    def left(cell: tuple[int, int]) -> int:
        return abs(cell[0] - goal[0]) + abs(cell[1] - goal[1])

    queue = [(left(start), 0, start)]
    came: dict[tuple[int, int], tuple[int, int]] = {}
    cost = {start: 0}
    while queue:
        _, spent, cur = heapq.heappop(queue)
        if cur == goal:
            path = [cur]
            while cur in came:
                cur = came[cur]
                path.append(cur)
            path.reverse()
            return path
        if spent != cost.get(cur):
            continue
        x, y = cur
        for nxt in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if not (0 <= nxt[0] < width and 0 <= nxt[1] < height):
                continue
            if nxt in blocked and nxt != goal:
                continue
            nxt_cost = spent + 1
            if nxt_cost < cost.get(nxt, 10**9):
                cost[nxt] = nxt_cost
                came[nxt] = cur
                heapq.heappush(queue, (nxt_cost + left(nxt), nxt_cost, nxt))
    return None


def route_board(parts: list[dict], nets: list[dict], outline: list, min_track: float) -> tuple[list[dict], list[str]]:
    if len(parts) < 2 or not nets:
        return [], ["Place at least two parts and one net."]
    by_ref = {part["ref"]: part for part in parts}
    xs = [float(part["x"]) for part in parts]
    ys = [float(part["y"]) for part in parts]
    if len(outline) == 2 and outline[0] and outline[1]:
        origin_x, origin_y = 0.0, 0.0
        far_x, far_y = float(outline[0]), float(outline[1])
    else:
        origin_x, origin_y = min(xs) - 6, min(ys) - 6
        far_x, far_y = max(xs) + 8, max(ys) + 8
    width = max(4, _grid(far_x, origin_x) + 1)
    height = max(4, _grid(far_y, origin_y) + 1)
    if width * height > 400_000:
        return [], ["Board is too large for this 0.5 mm grid."]
    blocked: set[tuple[int, int]] = set()
    terminals: dict[str, tuple[int, int]] = {}
    for part in parts:
        cell = (_grid(float(part["x"]), origin_x), _grid(float(part["y"]), origin_y))
        cell = (min(max(cell[0], 0), width - 1), min(max(cell[1], 0), height - 1))
        terminals[part["ref"]] = cell
        blocked.add(cell)
    ordered = sorted(
        [net for net in nets if net["a"] in terminals and net["b"] in terminals],
        key=lambda net: abs(terminals[net["a"]][0] - terminals[net["b"]][0]) + abs(terminals[net["a"]][1] - terminals[net["b"]][1]),
        reverse=True,
    )
    tracks = []
    failed = []
    for net in ordered:
        start, goal = terminals[net["a"]], terminals[net["b"]]
        if start == goal:
            tracks.append({"name": net["name"], "a": net["a"], "b": net["b"], "width": min_track, "points": [[_mm(start[0], origin_x), _mm(start[1], origin_y)]]})
            continue
        found = _search(start, goal, blocked, width, height)
        if not found:
            failed.append(f"{net['name']} {net['a']}-{net['b']}")
            continue
        power = net["name"] in {"VBUS", "GND", "SW"}
        width_mm = max(min_track, 0.5 if power else min_track)
        for cell in found[1:-1]:
            blocked.add(cell)
        tracks.append(
            {
                "name": net["name"],
                "a": net["a"],
                "b": net["b"],
                "width": round(width_mm, 3),
                "points": _corners(found, origin_x, origin_y),
            }
        )
    return tracks, failed
