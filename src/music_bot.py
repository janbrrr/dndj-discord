import logging

import yaml
from discord.ext import commands
from src import settings
from src.loader import CustomLoader
from src.logging_config import stream_handler
from src.music.music_manager import MusicManager
from src.music_server import MusicServer

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(stream_handler)


class MusicBot(commands.Bot):
    def __init__(self, config_path, host, port):
        super().__init__(command_prefix=commands.when_mentioned_or("!"), description="D&DJ Music Bot")
        self.add_cog(MusicServer(self, host, port))
        with open(config_path) as config_file:
            config = yaml.load(config_file, Loader=CustomLoader)
        self.music = MusicManager(config["music"])

    def run(self):
        with open(settings.TOKEN_FILE, "r") as file:
            token = file.readline()
            super().run(token)

    async def on_ready(self):
        logger.info(f"Logged in as {self.user}")
