import logging

from discord.ext import commands
from src import settings
from src.logging_config import stream_handler
from src.music_server import MusicServer

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(stream_handler)


class MusicBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=commands.when_mentioned_or("!"), description="D&DJ Music Bot")
        self.add_cog(MusicServer(self))

    def run(self):
        with open(settings.TOKEN_FILE, "r") as file:
            token = file.readline()
            super().run(token)

    async def on_ready(self):
        logger.info(f"Logged in as {self.user}")
