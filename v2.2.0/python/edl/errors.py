# Copyright 2016 Autodesk, Inc. All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

# Some particular errors / exceptions apps might want to catch and handle


class BadFrameRateError(ValueError):
    """
    Thin wrapper around ValueError for frame rate errors, allowing them to be
    caught easily.
    """

    # Standard error message for bad frame rate errors
    __ERROR_MSG = (
        "Invalid frame value [%d], it must be smaller than the "
        "specified frame rate [%d]"
    )

    def __init__(self, frame_value, frame_rate, *args, **kwargs):
        """
        Instantiate a new BadFrameRateError, setting a standard error message from
        the given frame value and frame rate.

        :param frame_value: An integer, the frame value which caused the error.
        :param frame_rate: An integer, the frame rate for which the frame value
                           caused the error.
        """
        super(BadFrameRateError, self).__init__(
            self.__ERROR_MSG % (frame_value, frame_rate), *args, **kwargs
        )
        # Store value internally, in case some apps want to retrieve them
        self._frame_value = frame_value
        self._frame_rate = frame_rate

    @property
    def frame_value(self):
        """
        Return the frame value which caused the error.

        :returns: An integer
        """
        return self._frame_value

    @property
    def frame_rate(self):
        """
        Return the frame rate value for which the frame value caused the error.

        :returns: An integer
        """
        return self._frame_rate


class BadDropFrameError(ValueError):
    """
    Thin wrapper around ValueError for drop frame errors, allowing them to be
    caught easily.
    """

    # Standard error message for bad frame rate errors
    __ERROR_MSG = (
        'Timecode format "%s" indicates drop frame which conflicts with the '
        'explicit drop_frame parameter setting "%s". Drop frame timecodes are '
        "delimited with a ; or , between the seconds and frames. To fix this, either "
        "call this function with drop_frame=True or modify your timecode format to use "
        "only non-drop frame delimiters: %s."
    )

    def __init__(self, timecode_str, drop_frame, valid_delimiters, *args, **kwargs):
        """
        Instantiate a new BadFrameRateError, setting a standard error message from
        the given frame value and frame rate.

        :param timecode_str: Timecode string that contributed to the error.
        :param drop_frame: Boolean value indicating the use of drop frame or not that conflicts
                           with timecode string format.
        :param valid_delimiters: List of valid delimiters for drop frame notation.
        """
        super(BadDropFrameError, self).__init__(
            self.__ERROR_MSG % (timecode_str, drop_frame, valid_delimiters),
            *args,
            **kwargs
        )
        # Store values internally, in case some apps want to retrieve them.
        self._timecode_str = timecode_str
        self._drop_frame = drop_frame
        self._valid_delimiters = valid_delimiters

    @property
    def timecode_str(self):
        """
        Return the timecode string which contributed to the error.

        :returns: Timecode as a string.
        """
        return self._timecode_str

    @property
    def drop_frame(self):
        """
        Return the drop frame value that contributed to the error.

        :returns: Boolean
        """
        return self._drop_frame

    @property
    def valid_delimiters(self):
        """
        Return the valid delimiters for drop frame notation.

        :returns: List of strings representing valid drop frame notation delimiters.
        """
        return self._valid_delimiters


class UnsupportedEDLFeature(NotImplementedError):
    """
    Base class for all exceptions related to EDL features not being supported by
    the current implementation.

    If needed, more specific Exceptions can be implemented by just deriving from
    this class and changing the error message.
    """

    def __init__(self, edl_name, *args, **kwargs):
        """
        Instantiate a new UnsupportedEDLFeature.

        :param edl_name: A string, the EDL file name.
        """
        super(UnsupportedEDLFeature, self).__init__(
            self._error_message() % edl_name, *args, **kwargs
        )

    def _error_message(self):
        """
        Return a standard error message to use as the exception message.

        Deriving classes can return any arbitrary string, as long as it includes
        '%s' to receive the EDL file name.

        :returns: A string
        """
        return "%s uses some EDL features which are not currently supported."


# Some specific exceptions for most common missing features encountered in production
class BadBLError(UnsupportedEDLFeature):
    """
    Thin wrapper around UnsupportedEDLFeature for BL errors, allowing them
    to be caught easily.
    """

    def _error_message(self):
        """"
        Return a standard error message to use as the exception message.

        :returns: A string
        """
        return "%s has a black slug (BL) event, which is not supported."


class BadFCMError(UnsupportedEDLFeature):
    """
    Thin wrapper around UnsupportedEDLFeature for drop frame errors, allowing them
    to be caught easily.
    """

    def _error_message(self):
        """"
        Return a standard error message to use as the exception message.

        :returns: A string
        """
        return (
            "Unknown FCM setting found in %s. Unable to determine drop frame setting."
        )
