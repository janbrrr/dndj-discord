import os
from functools import lru_cache
from typing import List

import youtube_dl

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CACHE_DIR = os.path.join(BASE_DIR, ".dndj_cache")
DOWNLOAD_DIR = os.path.join(CACHE_DIR, "downloads")

if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)


def _get_youtube_ids_in_cache() -> List[str]:
    files = [file for file in os.listdir(DOWNLOAD_DIR) if os.path.isfile(os.path.join(DOWNLOAD_DIR, file))]
    return [os.path.splitext(file)[0] for file in files]


_YOUTUBE_IDS_IN_CACHE = tuple(_get_youtube_ids_in_cache())


_ytdl_options = {
    "format": "bestaudio/best",
    "outtmpl": os.path.join(DOWNLOAD_DIR, "%(id)s.%(ext)s"),
    "restrictfilenames": True,
    "noplaylist": True,
    "nocheckcertificate": True,
    "ignoreerrors": False,
    "logtostderr": False,
    "quiet": True,
    "no_warnings": True,
    "default_search": "auto",
    "source_address": "0.0.0.0",  # bind to ipv4 since ipv6 addresses cause issues sometimes
}

_ytdl = youtube_dl.YoutubeDL(_ytdl_options)


def download_youtube_audio_if_not_in_cache(url: str) -> bool:
    """
    Downloads a youtube video if it has not been already downloaded.
    :param url: url of the youtube video
    :return: `True` if the video had to be downloaded, `False` otherwise
    """
    youtube_id = get_youtube_id(url)
    if youtube_id not in _YOUTUBE_IDS_IN_CACHE:
        _ytdl.extract_info(url, download=True)
        return True
    return False


@lru_cache(maxsize=50)
def get_youtube_id(url: str) -> str:
    info_dict = _ytdl.extract_info(url, download=False)
    return info_dict["id"]


@lru_cache(maxsize=50)
def get_filename_of_youtube_url(url: str) -> str:
    info_dict = _ytdl.extract_info(url, download=False)
    return _ytdl.prepare_filename(info_dict)
