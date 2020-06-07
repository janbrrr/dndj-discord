from typing import Callable

from aiohttp.web_request import Request
from src.music.music_actions import MusicActions
from src.music.music_state import MusicState


class MusicCallbackHandler:
    def __init__(self, callback_fn: Callable = None):
        self.callback_fn = callback_fn

    async def __call__(self, action: MusicActions, request: Request, state: MusicState):
        if self.callback_fn is not None:
            await self.callback_fn(action, request, state)
