import uuid
import logging
import aiohttp_jinja2
import jinja2

from discord.ext import commands
from aiohttp import web

from src.logging_config import stream_handler
from src import settings

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(stream_handler)


class MusicServer(commands.Cog):

    def __init__(self, bot):
        self.app = None
        self.runner = None
        self.host = None
        self.port = None
        self.bot = bot

    @commands.command()
    async def start(self, ctx, host="127.0.0.1", port=8080):
        """
        Starts the web server.
        """
        self.host = host
        self.port = port
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
        context = {}
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
        except RuntimeError:
            logger.info(f"Client {ws_identifier} disconnected.")
            del request.app["websockets"][ws_identifier]
            return ws_current
