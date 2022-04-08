# Copyright 2016 Autodesk, Inc. All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#
import logging


class FrameworkLogHandler(logging.StreamHandler):
    """
    A logging Handler to log messages with the Framework log_xxxx methods
    """

    def __init__(self, framework, *args, **kwargs):
        """
        Instantiate a new handler for the given Framework

        :param framework: A Toolkit framework
        """
        super(FrameworkLogHandler, self).__init__(*args, **kwargs)
        self._framework = framework

    def emit(self, record):
        """
        Emit the given record
        """
        if self._framework:
            # Pick up the right framework method, given the record level
            if record.levelno == logging.INFO:
                self._framework.log_info(record.getMessage())
            elif record.levelno == logging.INFO:
                self._framework.log_debug(record.getMessage())
            elif record.levelno == logging.WARNING:
                self._framework.log_warning(record.getMessage())
            elif record.levelno == logging.ERROR:
                self._framework.log_error(record.getMessage())


def get_logger(level=logging.WARN):
    """
    Retrieve a logger
    """
    logger_parts = __name__.split(".")
    if len(logger_parts) > 1:
        # Remove the last part which should be this file
        # name
        logger_name = ".".join(logger_parts[:-1])
    else:
        logger_name = logger_parts[0]
    logger = logging.getLogger(logger_name)
    # Check if we are running this module from a Toolkit
    # framework. The only dependency we have with Toolkit
    # if for logging, so it's worth trying to allow using
    # this module from non Toolkit apps, using regular Python
    # imports
    try:
        import sgtk

        # Raising an exception will activate the except clause
        framework = sgtk.platform.current_bundle()
        if not framework:
            raise Exception("No framework")
        logger.addHandler(FrameworkLogHandler(framework))
        logger.setLevel(level)
    except:
        # Default to basic logging
        logging.basicConfig(level=level)
    return logger
