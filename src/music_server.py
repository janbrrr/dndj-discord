import json
import logging
import uuid

import aiohttp
import aiohttp_jinja2
import jinja2
from aiohttp import web
from aiohttp.abc import Request
from discord.ext import commands
from src import settings
from src.logging_config import stream_handler
from src.music.music_actions import MusicActions
from src.music.music_state import MusicState

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(stream_handler)


class MusicServer(commands.Cog):
    def __init__(self, bot, host, port):
        self.app = None
        self.runner = None
        self.host = host
        self.port = port
        self.bot = bot
        self.discord_context = None

    @commands.command()
    async def start(self, ctx):
        """
        Starts the web server.
        """
        self.discord_context = ctx
        self.app = await self._init_app()
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, self.host, self.port)
        logger.info(f"Server started on http://{self.host}:{self.port}")
        await site.start()

    @commands.command()
    async def stop(self, ctx):
        """
        Stops the web server.
        """
        await self.runner.cleanup()
        await ctx.voice_client.disconnect()
        logger.info("Server shut down.")

    @start.before_invoke
    async def ensure_voice(self, ctx):
        """
        Ensures that the bot connects to the voice channel of the user.
        """
        if ctx.voice_client is None:
            if ctx.author.voice:
                await ctx.author.voice.channel.connect()
            else:
                await ctx.send("You are not connected to a voice channel.")
                raise commands.CommandError("Author not connected to a voice channel.")

    async def _init_app(self):
        """
        Initializes the web application.
        """
        app = web.Application()
        app["websockets"] = {}
        app.on_shutdown.append(self._shutdown_app)
        aiohttp_jinja2.setup(app, loader=jinja2.PackageLoader("src"))
        app.router.add_get("/", self.index)
        app.router.add_static("/static/", path=settings.PROJECT_ROOT / "static", name="static")
        return app

    async def _shutdown_app(self, app):
        """
        Called when the app shut downs. Performs clean-up.
        """
        for ws in app["websockets"].values():
            await ws.close()
        app["websockets"].clear()

    def _get_page(self, request):
        """
        Returns the index page.
        """
        context = {
            "music": {
                "volume": self.bot.music.volume,
                "currently_playing": self.bot.music.currently_playing,
                "groups": self.bot.music.groups,
            }
        }
        return aiohttp_jinja2.render_template("index.html", request, context)

    async def index(self, request):
        """
        Handles the client connection.
        """
        ws_current = web.WebSocketResponse()
        ws_ready = ws_current.can_prepare(request)
        if not ws_ready.ok:
            return self._get_page(request)
        await ws_current.prepare(request)

        ws_identifier = str(uuid.uuid4())
        request.app["websockets"][ws_identifier] = ws_current
        logger.info(f"Client {ws_identifier} connected.")
        try:
            while True:
                msg = await ws_current.receive()
                await self._handle_message(request, msg)
        except RuntimeError:
            logger.info(f"Client {ws_identifier} disconnected.")
            del request.app["websockets"][ws_identifier]
            return ws_current

    async def _handle_message(self, request, msg):
        if msg.type != aiohttp.WSMsgType.text:
            return
        data_dict = json.loads(msg.data)
        if "action" not in data_dict:
            return
        action = data_dict["action"]
        if action == "playMusic":
            if "groupIndex" in data_dict and "trackListIndex" in data_dict:
                group_index = int(data_dict["groupIndex"])
                track_list_index = int(data_dict["trackListIndex"])
                await self._play_music(request, group_index, track_list_index)
        elif action == "stopMusic":
            await self._stop_music()
        elif action == "setMusicMasterVolume":
            if "volume" in data_dict:
                volume = int(data_dict["volume"])
                await self._set_music_master_volume(request, volume)
        elif action == "setTrackListVolume":
            if "groupIndex" in data_dict and "trackListIndex" in data_dict and "volume" in data_dict:
                group_index = int(data_dict["groupIndex"])
                track_list_index = int(data_dict["trackListIndex"])
                volume = int(data_dict["volume"])
                await self._set_track_list_volume(request, group_index, track_list_index, volume)

    async def _play_music(self, request, group_index, track_list_index):
        """
        Starts to play the music.
        """
        await self.bot.music.play_track_list(self.discord_context, request, group_index, track_list_index)

    async def _stop_music(self):
        """
        Stops the music.
        """
        await self.bot.music.cancel(self.discord_context)

    async def _set_music_master_volume(self, request, volume):
        """
        Sets the music master volume.
        """
        await self.bot.music.set_master_volume(self.discord_context, request, volume)

    async def _set_track_list_volume(self, request, group_index, track_list_index, volume):
        """
        Sets the volume for a specific track list.
        """
        await self.bot.music.set_track_list_volume(self.discord_context, request, group_index, track_list_index, volume)

    async def on_state_change(self, action: MusicActions, request: Request, state: MusicState):
        """
        Callback function used by the `MusicManager` at `self.music`.

        Notifies all connected web sockets about the changes.
        """
        if action == MusicActions.START:
            logger.debug("Music Callback: Start")
            for ws in request.app["websockets"].values():
                await ws.send_json(
                    {
                        "action": "nowPlaying",
                        "groupIndex": state.group_index,
                        "trackListIndex": state.track_list_index,
                        "groupName": state.group_name,
                        "trackName": state.track_list_name,
                    }
                )
        elif action == MusicActions.STOP:
            logger.debug("Music Callback: Stop")
            for ws in request.app["websockets"].values():
                await ws.send_json({"action": "musicStopped"})
        elif action == MusicActions.FINISH:
            logger.debug("Music Callback: Finish")
            for ws in request.app["websockets"].values():
                await ws.send_json({"action": "musicFinished"})
        elif action == MusicActions.MASTER_VOLUME:
            logger.debug("Music Callback: Master Volume")
            for ws in request.app["websockets"].values():
                await ws.send_json({"action": "setMusicMasterVolume", "volume": state.master_volume})
        elif action == MusicActions.TRACK_LIST_VOLUME:
            logger.debug("Music Callback: Track List Volume")
            for ws in request.app["websockets"].values():
                await ws.send_json(
                    {
                        "action": "setTrackListVolume",
                        "groupIndex": state.group_index,
                        "trackListIndex": state.track_list_index,
                        "volume": state.track_list_volume,
                    }
                )
