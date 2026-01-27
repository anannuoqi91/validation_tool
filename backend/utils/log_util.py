from settings import app_config
import logging
import os
import sys
import time
from logging.handlers import RotatingFileHandler


class ColoredFormatter(logging.Formatter):
    COLOR_CODES = {
        'WARNING': '\033[93m',  # yellow
        'ERROR': '\033[91m',  # red
        'CRITICAL': '\033[41m',  # red background
        'RESET_SEQ': '\033[0m'  # normal
    }

    def format(self, record):
        log_level = record.levelname
        full_msg = super().format(record)
        if log_level in self.COLOR_CODES:
            full_msg = f"{self.COLOR_CODES[log_level]}{full_msg}{self.COLOR_CODES['RESET_SEQ']}"
        return full_msg


def setup_logger(name, log_file=None, level='info', stream=True, max_bytes=10 * 1024 * 1024, backup_count=200):
    logger = logging.getLogger(name)
    write_file = log_file is not None
    if log_file is not None:
        base_dir = os.path.dirname(log_file)
        if not os.path.exists(base_dir):
            os.makedirs(base_dir)
    level_map = {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warning": logging.WARNING,
        "error": logging.ERROR,
    }
    logger.setLevel(level_map[level.lower()])
    if write_file:
        file_handler = RotatingFileHandler(
            log_file, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter(
            '[%(asctime)s] [%(levelname)s] [%(name)s] [%(filename)s:%(lineno)d] [%(funcName)s] %(message)s'))
        logger.addHandler(file_handler)
    if stream:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(ColoredFormatter(
            '[%(asctime)s] [%(levelname)s] [%(name)s] [%(filename)s:%(lineno)d] [%(funcName)s] %(message)s'))
        logger.addHandler(stream_handler)

    def handle_unhandled_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logger.error("Uncaught exception", exc_info=(
            exc_type, exc_value, exc_traceback))

    sys.excepthook = handle_unhandled_exception
    return logger


LOG_PATH = app_config.log.log_dir
LOG_LEVEL = app_config.log.log_level
APP_START_TIME = time.strftime("%Y%m%d_%H%M%S", time.localtime())
log_file = os.path.join(LOG_PATH, f'{APP_START_TIME}.log')
logger = setup_logger('SIMPL_CAMERA', log_file=log_file,
                      level=LOG_LEVEL, stream=True)
