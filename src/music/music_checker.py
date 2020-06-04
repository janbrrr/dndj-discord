import logging
from typing import Iterable

import src.music.utils as utils
from src.cache import download_youtube_audio_if_not_in_cache
from src.check_version import is_latest_youtube_dl_version
from src.logging_config import stream_handler
from src.music.music_group import MusicGroup

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(stream_handler)


class MusicChecker:
    def do_all_checks(self, groups: Iterable[MusicGroup], default_dir):
        """
        Perform all the available checks.

        :param groups: `MusicGroup` instances to check
        :param default_dir: default directory where the tracks are located
        """
        self.download_youtube_videos(groups)
        self.check_track_list_names(groups)
        self.check_tracks_do_exist(groups, default_dir)

    def download_youtube_videos(self, groups: Iterable[MusicGroup]):
        """
        Downloads all youtube videos.

        :param groups: `MusicGroup` instances to check
        """
        logger.info("Downloading youtube videos...")
        is_latest_ytdl_version = is_latest_youtube_dl_version()
        if not is_latest_ytdl_version:
            logger.warning("A new version of the 'youtube-dl' package is available.")
            logger.warning("YouTube support may not work if the package is not updated.")
            logger.warning("Type 'pip install --upgrade youtube-dl' to update it.")
        for group, track_list, track in utils.music_tuple_generator(groups):
            if track.is_youtube_link:
                new_download = download_youtube_audio_if_not_in_cache(track.file)
                if new_download:
                    logger.info(f"Downloaded youtube video with url={track.file}")
        logger.info("Success! All youtube videos have been downloaded.")

    def check_track_list_names(self, groups: Iterable[MusicGroup]):
        """
        Iterates through every track list, checks that the names are unique and that their `next` attributes (if set)
        point to existing track list names.

        Raises a `RuntimeError` if the names are not unique or a `next` attribute points to a non-existing track list.
        """
        logger.info("Checking that track lists have unique names and their `next` parameters...")
        names = set()
        next_names = set()
        for group in groups:
            for track_list in group.track_lists:
                if track_list.name not in names:
                    names.add(track_list.name)
                else:
                    logger.error(f"Found multiple track lists with the same name '{track_list.name}'.")
                    raise RuntimeError(
                        f"The names of the track lists must be unique. Found duplicate with name "
                        f"'{track_list.name}'."
                    )
                if track_list.next is not None:
                    next_names.add(track_list.next)
        if not next_names.issubset(names):
            for next_name in next_names:
                if next_name not in names:
                    logger.error(f"'{next_name}' points to a non-existing track list.")
                    raise RuntimeError(f"'{next_name}' points to a non-existing track list.")
        logger.info("Success! Names are unique and `next` parameters point to existing track lists.")

    def check_tracks_do_exist(self, groups: Iterable[MusicGroup], default_dir):
        """
        Iterates through every track and attempts to get its path. Logs any error and re-raises any exception.
        """
        logger.info("Checking that tracks point to valid paths...")
        for group, track_list, track in utils.music_tuple_generator(groups):
            try:
                utils.get_track_path(group, track_list, track, default_dir=default_dir)
            except Exception as ex:
                logger.error(f"Track '{track.file}' does not point to a valid path.")
                raise ex
        logger.info("Success! All tracks point to valid paths.")
