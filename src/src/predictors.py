"""Small, direct-mapped branch predictor reference models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Branch:
    pc: int
    taken: bool


class StaticNotTaken:
    name = "Static not taken"

    def predict(self, pc: int) -> bool:
        return False

    def update(self, pc: int, taken: bool) -> None:
        pass


class OneBit:
    name = "One-bit BHT"

    def __init__(self, entries: int):
        if entries <= 0:
            raise ValueError("entries must be positive")

        self.entries = [False] * entries

    def index(self, pc: int) -> int:
        if pc < 0 or pc % 4:
            raise ValueError(
                "PC must be a nonnegative, 4-byte-aligned address"
            )

        return (pc >> 2) % len(self.entries)

    def predict(self, pc: int) -> bool:
        return self.entries[self.index(pc)]

    def update(self, pc: int, taken: bool) -> None:
        self.entries[self.index(pc)] = taken


class TwoBit:
    name = "Two-bit BHT"

    def __init__(self, entries: int):
        if entries <= 0:
            raise ValueError("entries must be positive")

        # 0 = strongly not taken
        # 1 = weakly not taken
        # 2 = weakly taken
        # 3 = strongly taken
        self.entries = [1] * entries

    def index(self, pc: int) -> int:
        if pc < 0 or pc % 4:
            raise ValueError(
                "PC must be a nonnegative, 4-byte-aligned address"
            )

        return (pc >> 2) % len(self.entries)

    def predict(self, pc: int) -> bool:
        return self.entries[self.index(pc)] >= 2

    def update(self, pc: int, taken: bool) -> None:
        idx = self.index(pc)

        if taken:
            self.entries[idx] = min(
                3,
                self.entries[idx] + 1,
            )
        else:
            self.entries[idx] = max(
                0,
                self.entries[idx] - 1,
            )


def evaluate(
    predictor,
    branches: list[Branch],
    penalty_cycles: int,
) -> dict:
    if penalty_cycles < 0:
        raise ValueError("penalty_cycles must be nonnegative")

    if not branches:
        raise ValueError(
            "trace must contain at least one branch"
        )

    misses = 0

    for branch in branches:
        misses += (
            predictor.predict(branch.pc) != branch.taken
        )

        predictor.update(
            branch.pc,
            branch.taken,
        )

    return {
        "predictor": predictor.name,
        "branches": len(branches),
        "mispredictions": misses,
        "accuracy": (
            len(branches) - misses
        ) / len(branches),
        "penalty_cycles_only": misses * penalty_cycles,
    }
