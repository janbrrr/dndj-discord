import logging

stream_handler = logging.StreamHandler()
_formatter = logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)-20s | %(message)s", datefmt="%H:%M:%S")
stream_handler.setFormatter(_formatter)
