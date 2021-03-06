import asyncio
import logging
from collections import namedtuple
from typing import Tuple

import discord
from src.logging_config import stream_handler
from src.music import utils
from src.music.music_actions import MusicActions
from src.music.music_callbacks import MusicCallbackHandler
from src.music.music_checker import MusicChecker
from src.music.music_group import MusicGroup
from src.music.music_state import MusicState

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(stream_handler)

_CurrentlyPlaying = namedtuple("_CurrentlyPlaying", ["group_index", "track_list_index"])


class MusicManager:
    def __init__(self, config, callback_fn):
        """
        Initializes a `MusicManager` instance.

        The `config` parameter is expected to be a dictionary with the following keys:
        - "volume": an integer between 0 (mute) and 100 (max)
        - "directory": the default directory to use if no directory is further specified (Optional)
        - "sort": whether to sort the groups alphabetically (Optional, default=True)
        - "groups": a list of configs for `MusicGroup` instances. See `MusicGroup` class for more information

        The `callback_fn` is an async coroutine that should accept the following arguments:
        - "action": value of type `MusicActions`
        - "request": the request that caused the action
        - "state": an instance of `MusicState` (fields are `None` if nothing is being played)

        :param config: `dict`
        :param callback_fn: function to call when the state of the music changes
        """
        self.volume = int(config["volume"])
        self.directory = config["directory"] if "directory" in config else None
        groups = [MusicGroup(group_config) for group_config in config["groups"]]
        if "sort" not in config or ("sort" in config and config["sort"]):
            groups = sorted(groups, key=lambda x: x.name)
        self.groups = tuple(groups)
        self._currently_playing = None
        self.is_cancelled = False
        self.callback_handler = MusicCallbackHandler(callback_fn=callback_fn)
        MusicChecker().do_all_checks(self.groups, self.directory)
        self.event_loop = asyncio.get_event_loop()

    def __eq__(self, other):
        if isinstance(other, MusicManager):
            attrs_are_the_same = self.volume == other.volume and self.directory == other.directory
            if not attrs_are_the_same:
                return False
            if len(self.groups) != len(other.groups):
                return False
            for my_group, other_group in zip(self.groups, other.groups):
                if my_group != other_group:
                    return False
            return True
        return False

    @property
    def currently_playing(self) -> MusicState:
        """
        Returns information about the music that is currently being played.
        Fields are `None` if nothing is being played.
        """
        if self._currently_playing is not None:
            group_index = self._currently_playing.group_index
            group = self.groups[group_index]
            track_list_index = self._currently_playing.track_list_index
            track_list = group.track_lists[track_list_index]
            return MusicState(
                group_index, group.name, track_list_index, track_list.name, self.volume, track_list.volume
            )
        return MusicState(None, None, None, None, self.volume, None)

    async def cancel(self, discord_context):
        """
        If a track is currently being played, the replay will be cancelled.
        """
        self.is_cancelled = True
        discord_context.voice_client.stop()
        while self._currently_playing is not None:
            await asyncio.sleep(0.01)

    async def play_track_list(self, discord_context, request, group_index, track_list_index):
        """
        If a track list is already being played, it will be cancelled and the new track list will be played.
        """
        if self._currently_playing is not None:
            await self.cancel(discord_context)
        group = self.groups[group_index]
        track_list = group.track_lists[track_list_index]
        logger.info(f"Loading '{track_list.name}'")
        self._currently_playing = _CurrentlyPlaying(group_index, track_list_index)
        await self.callback_handler(action=MusicActions.START, request=request, state=self.currently_playing)
        await self._play_track(discord_context, request, group, track_list, track_list.tracks)

    async def _play_track(self, discord_context, request, group, track_list, tracks_to_play):
        """
        Plays the given track from the given track list and group.
        """
        if self.is_cancelled:
            self._currently_playing = None
            self.is_cancelled = False
            logger.info(f"Cancelled '{track_list.name}'")
            await self.callback_handler(action=MusicActions.STOP, request=request, state=self.currently_playing)
            return
        if len(tracks_to_play) == 0:
            if not track_list.loop:
                self._currently_playing = None
                logger.info(f"Finished '{track_list.name}'")
                await self.callback_handler(action=MusicActions.FINISH, request=request, state=self.currently_playing)
                if track_list.next is None:
                    return
                next_group_index, next_track_list_index = self._get_track_list_index_from_name(track_list.next)
                if next_group_index is None or next_track_list_index is None:
                    logger.error(f"Could not find a track list named '{track_list.next}'")
                    return
                await self.play_track_list(discord_context, request, next_group_index, next_track_list_index)
                return
            tracks_to_play = track_list.tracks
        track = tracks_to_play.pop(0)
        path = utils.get_track_path(group, track_list, track, default_dir=self.directory)
        ffmpeg_before_options = ""
        if track.start_at is not None:
            ffmpeg_before_options += f" -ss {track.start_at}ms"
        if track.end_at is not None:
            ffmpeg_before_options += f" -to {track.end_at}ms"
        logger.info(f"Now Playing: {track.file}")
        source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(path, before_options=ffmpeg_before_options))
        volume = (self.volume * track_list.volume) // 100
        source.volume = volume / 100
        discord_context.voice_client.play(
            source,
            after=lambda e: logger.error(f"Player error: {e}")
            if e
            else asyncio.run_coroutine_threadsafe(
                self._play_track(discord_context, request, group, track_list, tracks_to_play), self.event_loop
            ),
        )

    def _get_track_list_index_from_name(self, name_of_track_list: str) -> Tuple[int, int]:
        """
        Returns the group index and the track list index given the name of the track list. Values are `None`
        if no track list has the given name.

        :param name_of_track_list: name of the track list
        :return: tuple of the form (<group_index>, <track_list_index>)
        """
        next_group_index = None
        next_track_list_index = None
        for _group_index, _group in enumerate(self.groups):
            for _track_list_index, _track_list in enumerate(_group.track_lists):
                if _track_list.name == name_of_track_list:
                    next_group_index = _group_index
                    next_track_list_index = _track_list_index
                    break
        return next_group_index, next_track_list_index

    async def set_master_volume(self, discord_context, request, volume):
        """
        Sets the master volume for the music.
        """
        if self._currently_playing is not None:
            group_index = self._currently_playing.group_index
            track_list_index = self._currently_playing.track_list_index
            track_list = self.groups[group_index].track_lists[track_list_index]
            new_volume = (volume * track_list.volume) // 100
            discord_context.voice_client.source.volume = new_volume / 100
        self.volume = volume
        await self.callback_handler(action=MusicActions.MASTER_VOLUME, request=request, state=self.currently_playing)
        logger.info(f"Changed music master volume to {volume}")

    async def set_track_list_volume(self, discord_context, request, group_index, track_list_index, volume):
        """
        Sets the volume for a specific track list.

        :param discord_context: discord context
        :param request: the request that caused the action
        :param group_index: index of the group of the track list
        :param track_list_index: index of the track list within the group
        :param volume: value between 0 (mute) and 100 (max)
        """
        group = self.groups[group_index]
        track_list = group.track_lists[track_list_index]
        track_list.volume = volume
        if (
            self._currently_playing is not None
            and self._currently_playing.group_index == group_index
            and self._currently_playing.track_list_index == track_list_index
        ):
            new_volume = (self.volume * track_list.volume) // 100
            discord_context.voice_client.source.volume = new_volume / 100
        await self.callback_handler(
            action=MusicActions.TRACK_LIST_VOLUME,
            request=request,
            state=MusicState(
                group_index, group.name, track_list_index, track_list.name, self.volume, track_list.volume
            ),
        )
        logger.info(f"Changed tracklist volume for group={group_index}, track_list={track_list_index} to {volume}")
