import asyncio
import json
import logging
import uuid

import aiohttp
import aiohttp_jinja2
import jinja2
import yaml
from aiohttp import web
from aiohttp.abc import Request
from discord.ext import commands
from src import cache, settings
from src.loader import CustomLoader
from src.logging_config import stream_handler
from src.music.music_actions import MusicActions
from src.music.music_manager import MusicManager
from src.music.music_state import MusicState

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(stream_handler)


class MusicServer(commands.Cog):
    def __init__(self, config_path, host, port):
        self.app = self._init_app()
        self.runner = None
        self.host = host
        self.port = port
        self.discord_context = None
        self.is_running = False
        self.config_path = config_path
        self.music_manager = None

    def _init_app(self):
        """
        Initializes the web application.
        """
        app = web.Application()
        app["websockets"] = {}
        app["websocket_tasks"] = {}
        app.on_shutdown.append(self._shutdown_app)
        aiohttp_jinja2.setup(app, loader=jinja2.PackageLoader("src"))
        app.router.add_get("/", self.index)
        app.router.add_static("/static/", path=settings.PROJECT_ROOT / "static", name="static")
        return app

    async def _shutdown_app(self, app):
        """
        Called when the app shut downs. Performs clean-up.
        """
        for task in self.app["websocket_tasks"].values():
            task.cancel()

    @commands.command()
    async def start(self, ctx):
        """
        Starts the web server.
        """
        if self.is_running:
            await ctx.send("The server is already running!")
            return
        with open(self.config_path) as config_file:
            config = yaml.load(config_file, Loader=CustomLoader)
        self.music_manager = MusicManager(config["music"], self.on_state_change)
        self.discord_context = ctx
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, self.host, self.port)
        logger.info(f"Server started on http://{self.host}:{self.port}")
        self.is_running = True
        await site.start()

    @commands.command()
    async def stop(self, ctx):
        """
        Stops the web server.
        """
        if not self.is_running:
            await ctx.send("The server is not running.")
            return
        await self.music_manager.cancel(self.discord_context)
        await self.runner.cleanup()
        await self.discord_context.voice_client.disconnect()
        self.is_running = False
        logger.info("Server shut down.")

    @commands.command()
    async def clear(self, ctx):
        """
        Clears the cache (downloads).
        """
        if self.is_running:
            await ctx.send("Cannot clear cache while the server is running (type '!stop' to stop it).")
            return
        success = cache.clear_cache()
        if success:
            logger.info("Cleared cache.")
        else:
            logger.error("Failed to clear the cache.")

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

    def _get_page(self, request):
        """
        Returns the index page.
        """
        context = {
            "music": {
                "volume": self.music_manager.volume,
                "currently_playing": self.music_manager.currently_playing,
                "groups": self.music_manager.groups,
            }
        }
        return aiohttp_jinja2.render_template("index.html", request, context)

    async def index(self, request):
        """
        Handles the client connection.
        """
        ws_current = web.WebSocketResponse()
        ws_current.force_close()
        ws_ready = ws_current.can_prepare(request)
        if not ws_ready.ok:
            return self._get_page(request)
        await ws_current.prepare(request)
        ws_identifier = str(uuid.uuid4())
        task = asyncio.create_task(self._handle_websocket_connection(request, ws_current, ws_identifier))
        request.app["websocket_tasks"][ws_identifier] = task
        await task

    async def _handle_websocket_connection(self, request, ws, ws_identifier):
        request.app["websockets"][ws_identifier] = ws
        logger.info(f"Client {ws_identifier} connected.")
        try:
            while not ws.closed:
                msg = await ws.receive()
                await self._handle_message(request, msg)
        except Exception:
            pass
        finally:
            logger.info(f"Client {ws_identifier} disconnected.")
            request.app["websockets"].pop(ws_identifier, None)
            request.app["websocket_tasks"].pop(ws_identifier, None)

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
        await self.music_manager.play_track_list(self.discord_context, request, group_index, track_list_index)

    async def _stop_music(self):
        """
        Stops the music.
        """
        await self.music_manager.cancel(self.discord_context)

    async def _set_music_master_volume(self, request, volume):
        """
        Sets the music master volume.
        """
        await self.music_manager.set_master_volume(self.discord_context, request, volume)

    async def _set_track_list_volume(self, request, group_index, track_list_index, volume):
        """
        Sets the volume for a specific track list.
        """
        await self.music_manager.set_track_list_volume(
            self.discord_context, request, group_index, track_list_index, volume
        )

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
