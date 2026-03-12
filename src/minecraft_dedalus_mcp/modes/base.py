from __future__ import annotations

from enum import Enum

from ..constants import GAME_MODE_CREATIVE, GAME_MODE_SURVIVAL


class GameMode(str, Enum):
    SURVIVAL = GAME_MODE_SURVIVAL
    CREATIVE = GAME_MODE_CREATIVE


class ModeManager:
    def __init__(self, mode: GameMode = GameMode.SURVIVAL) -> None:
        self._mode = mode

    @property
    def mode(self) -> GameMode:
        return self._mode

    def set_mode(self, mode: GameMode | str) -> GameMode:
        if isinstance(mode, str):
            mode = GameMode(mode.lower())
        self._mode = mode
        return self._mode

    def is_creative(self) -> bool:
        return self._mode == GameMode.CREATIVE

    def is_survival(self) -> bool:
        return self._mode == GameMode.SURVIVAL
