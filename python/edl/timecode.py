# Copyright 2016 Autodesk, Inc. All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#
import decimal
import re
from .errors import BadFrameRateError, BadDropFrameError


# FYI: Number of drop frames per minute is 6.6666...% of framerate rounded to nearest integer.
# This is convention from other code. While not an absolute exact science, it is exact
# enough for all of the frame rates in use today. This comes out to 2 for 29.97 and 4 for 59.94.
# In case we need to calculate this more dynamically in the future...

# Define constants for helping drop frame calculations:
# - count: The number of frames to drop per-minute.
# - fps_int: The frame rate (fps) rounded to the nearest int.
# - fp10m: Frames per 10 minutes (fps_int * 60 seconds * 10 minutes - (9 minutes * count))
DROP_FRAME = {
    29.97: {"count": 2, "fps_int": 30, "fp10m": 17982},
    59.94: {"count": 4, "fps_int": 60, "fp10m": 35964},
}
VALID_DROP_FRAME_FPS = list(DROP_FRAME.keys())

# Our official delimiters.
DROP_FRAME_DELIMITER = ";"
NON_DROP_FRAME_DELIMITER = ":"

VALID_DROP_FRAME_DELIMITERS = [";", ",", "."]
VALID_NON_DROP_FRAME_DELIMITERS = [":"]
VALID_TIMECODE_DELIMITERS = (
    VALID_DROP_FRAME_DELIMITERS + VALID_NON_DROP_FRAME_DELIMITERS
)


# Some helpers to convert timecodes to frames, back and forth.
def frame_from_timecode(timecode, fps=24, drop_frame=None):
    """
    Return the frame number for the given timecode.

    :param timecode: A timecode as a string (formatted as ``hh:mm:ss:ff`` for non-drop frame
                     or ``hh:mm:ss;ff`` for drop frame) or as a (hours, minutes, seconds, frames)
                     tuple.
    :param fps: Number of frames per second as an int or float. Default is 24.
    :param drop_frame: Boolean determining whether timecode should use drop frame or not. None if
                       this value should be determined by the timecode's delimiter notation.
                       Default is None.
    :return: Corresponding frame number, as an int.
    :raises: NotImplementedError if ``drop_frame`` is ``True`` and the fps value is unsupported
             for drop frame.
    """
    if isinstance(timecode, str):
        # This supports timecode up to 999:59:59:59.
        hour, minute, second, frame = Timecode.parse_timecode(timecode)
        tc_drop_frame = _compute_drop_frame_setting(timecode, drop_frame)

        if tc_drop_frame and fps not in VALID_DROP_FRAME_FPS:
            raise NotImplementedError(
                'Invalid fps setting "%s". Time code calculation logic only supports drop frame '
                "calculations for the following fps values: %s."
                % (fps, VALID_DROP_FRAME_FPS)
            )
    else:  # Assume a 4 elements tuple
        hour, minute, second, frame = timecode
        # Set drop frame solely based on the passed in drop_frame parameter.
        if drop_frame:
            tc_drop_frame = drop_frame
        else:
            tc_drop_frame = False

    hours = int(hour)
    minutes = int(minute)
    seconds = int(second)
    frames = int(frame)

    if tc_drop_frame:
        drop_frames_per_min = DROP_FRAME[fps]["count"]
    else:
        drop_frames_per_min = 0

    # We don't need the exact framerate anymore if we're using drop frame, we just need it
    # rounded to nearest integer. Non-drop frame will return the same value.
    fps_int = int(round(fps))

    # Number of frames per hour (non-drop)
    frames_per_hour = fps_int * 60 * 60
    # Number of frames per minute (non-drop)
    frames_per_minute = fps_int * 60
    # Total number of minutes (non-drop)
    total_minutes = (60 * hours) + minutes

    # Put it all together.
    frame_number = (
        (frames_per_hour * hours)
        + (frames_per_minute * minutes)
        + (fps_int * seconds)
        + frames
    )

    # If we're using drop frame, calculate the total frames to drop by multiplying the number of
    # frames we drop each minute, by the total number of minutes MINUS the number of 10-minute
    # intervals.
    frames_to_drop = drop_frames_per_min * (total_minutes - int(total_minutes / 10))
    # Subtract any frames to drop to get our final frame number.
    frame_number -= frames_to_drop

    return frame_number


def timecode_from_frame(frame_number, fps=24, drop_frame=False):
    """
    Return the timecode corresponding to the given frame.

    .. note::
        We don't need to use the :mod:`decimal` module here because frame/timecode calculations
        are not exact (there is no such thing as a fractional frame).

        When using a float frame rate (fps) calculations of frames and timecode are not
        technically exact, and will cause time drift away from "wall clock" time. But
        this is still correct. Drop frame was created to help mitigate this and it attempts
        to correct the drift by skipping frame numbers at certain intervals. However, it's
        still technically not exact and will usually be a fraction of time off. But it's
        exact enough for the editorial world (and is therefore "correct").

    :param frame_number: A frame number, as an int.
    :param fps: Number of frames per seconds, as an int or float. Default is 24.
    :param drop_frame: Boolean determining whether timecode should use drop frame or not. Default
                       is False.
    :returns: Timecode as string, e.g. ``01:02:12:32`` (non-drop frame) or
              ``01:02:12;32`` (drop frame).
    :raises: NotImplementedError if drop_frame is True and the fps value is unsupported for drop
             frame.
    """
    if drop_frame and fps not in VALID_DROP_FRAME_FPS:
        raise NotImplementedError(
            'Invalid fps setting "%s". Time code calculation logic only supports drop frame '
            "calculations for the following fps values: %s."
            % (fps, VALID_DROP_FRAME_FPS)
        )

    if drop_frame:
        fps_int = DROP_FRAME[fps]["fps_int"]
        # drop-frame-mode
        # for 30 fps jump 2 frames every minute but not every 10 minutes
        # for 60 fps jump 4 frames every minute but not every 10 minutes
        #
        # D = Drop Frame
        # ND = Non-Drop Frame
        #
        # Example at the one minute / 30-sec mark:
        #             30 fps                         60 fps
        # -------------------------------------------------------------------------
        # frame: 1798 ND: 00:00:59:28 D: 00:00:59;28 ND: 00:00:29:58 D: 00:00:29;58
        # frame: 1799 ND: 00:00:59:29 D: 00:00:59;29 ND: 00:00:29:59 D: 00:00:29;59
        # frame: 1800 ND: 00:01:00:00 D: 00:01:00;02 ND: 00:00:30:00 D: 00:00:30;00
        # frame: 1801 ND: 00:01:00:01 D: 00:01:00;03 ND: 00:00:30:01 D: 00:00:30;01
        # frame: 1802 ND: 00:01:00:02 D: 00:01:00;04 ND: 00:00:30:02 D: 00:00:30;02
        #
        # example at the two minute / one minute mark:
        #
        # frame: 3598 ND: 00:01:59:28 D: 00:01:59;28 ND: 00:00:59:58 D: 00:00:59:58
        # frame: 3599 ND: 00:01:59:29 D: 00:01:59;29 ND: 00:00:00:59 D: 00:00:59:59
        # frame: 3600 ND: 00:02:00:00 D: 00:02:00;02 ND: 00:01:00:00 D: 00:01:00;04
        # frame: 3601 ND: 00:02:00:01 D: 00:02:00;03 ND: 00:01:00:01 D: 00:01:00;05
        # frame: 3602 ND: 00:02:00:02 D: 00:02:00;04 ND: 00:01:00:02 D: 00:01:00;06
        #
        # examples at the ten minute / 5 minute marks:
        #
        # frame: 17980 ND: 00:09:59:10 D: 00:09:59;28  ND: 00:04:59:40 D: 00:04:59;56
        # frame: 17981 ND: 00:09:59:11 D: 00:09:59;29  ND: 00:04:59:41 D: 00:04:59;57
        # frame: 17982 ND: 00:09:59:12 D: 00:10:00;00  ND: 00:04:59:42 D: 00:04:59;58
        # frame: 17983 ND: 00:09:59:13 D: 00:10:00;01  ND: 00:04:59:43 D: 00:04:59;59
        # frame: 17984 ND: 00:09:59:14 D: 00:10:00;02  ND: 00:04:59:44 D: 00:05:00;04

        # frame: 17998 ND: 00:09:59:58 D: 00:10:00;16  ND: 00:04:59:58 D: 00:05:00;18
        # frame: 17999 ND: 00:09:59:59 D: 00:10:00;17  ND: 00:04:59:59 D: 00:05:00;19
        # frame: 18000 ND: 00:10:00:00 D: 00:10:00;18  ND: 00:05:00:00 D: 00:05:00;20
        # frame: 18001 ND: 00:10:00:01 D: 00:10:00;19  ND: 00:05:00:01 D: 00:05:00;21
        # frame: 18002 ND: 00:10:00:02 D: 00:10:00;20  ND: 00:05:00:02 D: 00:05:00;22

        # 30fps: 2
        # 60fps: 4
        drop_frames_per_min = DROP_FRAME[fps]["count"]

        # Number of NON-DROP frames per ten minutes
        # 30fps: 30 * 60 * 10 = 17982
        # 60fps: 60 * 60 * 10 = 35964
        frames_per_10_mins = DROP_FRAME[fps]["fp10m"]

        # Total number of DROP frames per minute
        # fps * 60 (seconds) - (# drop frames per minute)
        # 30fps: 30 * 60 - 2 = 1798
        # 60fps: 60 * 60 - 4 = 3596
        frames_per_min_drop = (fps_int * 60) - drop_frames_per_min

        # Number of frames to add per 10 minute chunk
        # (# frames to drop per minute) * 9 (9 minutes since every 10th minute we *don't* drop)
        # 30fps: 2 * 9 = 18
        # 60fps: 4 * 9 = 36
        additional_frames_per_10m = drop_frames_per_min * 9

        # number of frames to add per 1 minute chunk
        # 30fps: 2
        # 60fps: 4
        additional_frames_per_1m = drop_frames_per_min

        # Number of 10-minute chunks of frames
        ten_minute_chunks = int(frame_number / frames_per_10_mins)
        # Remainder of frames after splitting into 10 minute chunks
        remaining_frames = frame_number % frames_per_10_mins

        if remaining_frames > drop_frames_per_min:
            add_frames = (additional_frames_per_10m * ten_minute_chunks) + (
                additional_frames_per_1m
                * int((remaining_frames - drop_frames_per_min) / frames_per_min_drop)
            )
        else:
            add_frames = additional_frames_per_10m * ten_minute_chunks

        # The final result!
        frame_number += add_frames

        # Drop frame time codes use a ; to delimit the frames by convention.
        frames_token = DROP_FRAME_DELIMITER

    else:
        # Non-drop frame timecodes that are floats are simply rounded to their nearest integer
        # for frame calculation. Since there can't be a fractional frame number and we're not
        # dropping frames to compensate, the timecode will drift from wall clock time as expected.
        # This is often the case in short-form media like commercials (< 1 minute) since drop
        # frame wouldn't ever come in to play anyway.
        fps_int = int(round(fps))
        # Non-drop frame time codes use a : to delimit the frames by convention.
        frames_token = NON_DROP_FRAME_DELIMITER

    # Now split our frames into timecode.
    hours = int(frame_number / (3600 * fps_int))
    minutes = int(frame_number / (60 * fps_int) % 60)
    seconds = int(frame_number / fps_int % 60)
    frames = int(frame_number % fps_int)

    return "%02d:%02d:%02d%s%02d" % (hours, minutes, seconds, frames_token, frames)


def _compute_drop_frame_setting(timecode_str, drop_frame):
    """
    Calculate the "correct" drop frame setting based on the timecode string and the
    drop_frame parameter (if any).

    .. note::
        While it's clear that timecodes with ; or , or . delimiters indicate drop frame, the absence
        of them doesn't necessarily indicate non-drop frame. More specifically, when calling this
        function, we may not want to require that the user always know to add the correct drop
        frame delimiters in the timecode string. So we are only raising an error here if the
        timecode indicates drop frame and the user has explicitly indicated non-drop frame.

    :param timecode_str: A timecode as a string (eg. "hh:mm:ss:ff" for non-drop frame
                         or "hh:mm:ss;ff" for drop frame).
    :param drop_frame: Boolean indicating whether the user intends to use drop frame or not. None
                       if the user did not pass in a drop_frame value explicitly indicating we
                       should rely on the existence of drop frame notation in the timecode string.

    :returns: Boolean indicating whether to use drop frame (True) or not (False).
    :raises: BadDropFrameError if the drop_frame parameter is explicitly set to False but the
             timecode string uses drop frame notation, indicating a conflict.
    """
    # Infer drop frame setting from the timecode.
    tc_drop_frame = Timecode.str_is_drop_frame(timecode_str)

    if drop_frame is not None:
        if drop_frame is False and tc_drop_frame:
            raise BadDropFrameError(
                timecode_str, drop_frame, VALID_NON_DROP_FRAME_DELIMITERS
            )
        elif drop_frame is True and not tc_drop_frame:
            # We will accept that this timecode should be drop frame despite the fact that
            # it does not contain the typical drop frame delimiter(s).
            # @todo: Log a warning about this once we have a logger in the framework.
            tc_drop_frame = True

    return tc_drop_frame


class Timecode(object):
    """
    A Timecode object.
    """

    def __init__(self, timecode_string, fps=24, drop_frame=None,source=None):
        """
        Instantiate a Timecode object from a timecode or frame number as a string.

        .. note::
            The following sites were referenced for determining the best way to formulate
            the calculations in this module and are provided as a reference:

                - http://andrewduncan.net/timecodes/
                - http://www.davidheidelberger.com/blog/?p=29
                - https://documentation.apple.com/en/finalcutpro/usermanual/index.html#chapter=D%26section=6
                - http://www.connect.ecuad.ca/~mrose/pdf_documents/timecode.pdf
                - http://www.evertz.com/resources/The-Right-Time.pdf

        :param timecode_string: A timecode as a string (formatted as hh:mm:ss:ff for non-drop frame
                                or hh:mm:ss;ff for drop frame) or a frame number as a string.
        :param fps: Frames per second setting as an int or float. Default is 24.
        :param drop_frame: Boolean indicating whether to use drop frame or not. None if the
                           timecode string should determine this value. Default is None.

        :raises: ValueError if timecode_string cannot be transformed into a Timecode object.
        """
        # If we can convert the timecode_string to an int, we assume we
        # have a frame number and convert it to an absolute timecode using
        # our fps value. All calculations, etc. from this point on treat
        # the input as if it was a timecode and not a frame.
        if timecode_string.isdigit():
            try:
                new_timecode_string = timecode_from_frame(
                    int(timecode_string), fps, drop_frame
                )
                (
                    self._hours,
                    self._minutes,
                    self._seconds,
                    self._frames,
                ) = self.parse_timecode(new_timecode_string)
                self._drop_frame = drop_frame
            except ValueError as e:
                raise ValueError(
                    'Frame number "%s" can not be converted to a Timecode: %s'
                    % (timecode_string, e)
                )
        else:
            # Parse the timecode_string into values.
            (
                self._hours,
                self._minutes,
                self._seconds,
                self._frames,
            ) = self.parse_timecode(timecode_string)
            self._drop_frame = _compute_drop_frame_setting(timecode_string, drop_frame)

        if self._drop_frame and fps not in VALID_DROP_FRAME_FPS:
            raise NotImplementedError(
                'Invalid fps setting "%s". Time code calculation logic only supports drop frame '
                "calculations for the following fps values: %s."
                % (fps, VALID_DROP_FRAME_FPS)
            )
        self._fps = fps

        # Use the "correct" frame token delimiter
        if self._drop_frame:
            self._frame_delimiter = DROP_FRAME_DELIMITER
        else:
            self._frame_delimiter = NON_DROP_FRAME_DELIMITER

        # Do some basic validation
        self._validate_values(source)

    def _validate_values(self, source):
        """
        Validate Timecode values are valid.

        :raises: ValueError if minute or second values are > 59.
        :raises: BadFrameRateError if frame value is >= fps setting.
        """
        if self._minutes > 59:
            raise ValueError(
                "Invalid minutes value %d, it must be smaller than 60" % self._minutes
            )
        if self._seconds > 59:
            raise ValueError(
                "Invalid seconds value %d, it must be smaller than 60" % self._seconds
            )
        if not source and self._frames >= self._fps:
            raise BadFrameRateError(self._frames, self._fps)

    @classmethod
    def str_is_drop_frame(cls, timecode_str):
        """
        Determine whether the timecode string uses drop frame notation or not.

        Drop frame timecodes are typically delimited by a ; or , while non-drop frame
        timecodes are delimited by : or .

        :param timecode_str: String representation of the timecode to parse.

        :returns: Boolean True if timecode is using drop frame notation, False if not.
        :raises: ValueError if timecode_str is not a valid hh:mm:ss:ff format and cannot
                 be parsed correctly.
        """
        # Find the delimited being used between the seconds and frames entry.
        m = re.match(".*(%s)\d{2}$" % VALID_TIMECODE_DELIMITERS, timecode_str)
        if not m:
            raise ValueError(
                'Timecode "%s" is not in a valid format (eg. hh:mm:ss:ff or hh:mm:ss;ff). '
                "The timecode must be delimited by one of the following characters: %s"
                % (timecode_str, VALID_TIMECODE_DELIMITERS)
            )
        frame_delimiter = m.group(1)
        # Check the delimiter with those that indicate drop frame notation.
        if frame_delimiter in VALID_DROP_FRAME_DELIMITERS:
            return True
        else:
            return False

    @classmethod
    def parse_timecode(cls, timecode_str):
        """
        Parse a timecode string to valid hour, minute, second, and frame values.

        Splits the timecode string by any non-alphanumeric character. This ensures that that
        we can support various formats of delimiting timecode strings.
        For example::

            00:12:34:21 # NON-DROP FRAME variation 1
            00:12:34.21 # NON-DROP FRAME variation 2
            00:12:34;21 # DROP FRAME variation 1
            00:12:34,21 # DROP FRAME variation 2
            00;12;34;56 # DROP FRAME variation 3

        :param timecode_str: A timecode string (eg. ``hh:mm:ss:ff`` for non-drop frame
                             or ``hh:mm:ss;ff`` for drop frame).
        :return: Tuple of (hours, minutes, seconds, frames) where all values are ints.
        :raises: ValueError if string cannot be parsed.
        """
        m = re.match(r"(\d{2,3}):(\d{2}):(\d{2})[:;\.,](\d{2})", timecode_str)
        if not m:
            raise ValueError(
                'Timecode "%s" is not in a valid format (eg. hh:mm:ss:ff or hh:mm:ss;ff).'
                % timecode_str
            )

        tc_tuple = (
            int(m.group(1)),
            int(m.group(2)),
            int(m.group(3)),
            int(m.group(4)),
        )

        return tc_tuple

    @classmethod
    def from_frame(cls, frame, fps=24, drop_frame=False):
        """
        Return a new :class:`Timecode` for the given frame, at the given fps.

        :param frame: A frame number, as an :obj:`int`.
        :param fps: Number of frames per second, as an :obj:`int` or :obj:`float`. Defaults to 24.
        :param drop_frame: Boolean indicating whether to use drop frame or not. Default
                           is ``False``.

        :return: A :class:`Timecode` instance.
        """
        timecode = timecode_from_frame(frame, fps, drop_frame)
        return Timecode(timecode, fps=fps, drop_frame=drop_frame)

    def to_frame(self):
        """
        Return the frame number corresponding to this :class:`Timecode` instance.

        :return: A frame number, as an :obj:`int`.
        """
        return frame_from_timecode(
            (self._hours, self._minutes, self._seconds, self._frames),
            self._fps,
            self._drop_frame,
        )

    def to_seconds(self):
        """
        Convert this :class:`Timecode` to seconds, using its frame rate.

        .. note::
            We use the :mod:`decimal` module here in order to ensure our math is accurate
            and not subject to rounding errors. The reason we use it here and not when doing
            frame/timecode calculations is because time is an exact calculation
            whereas frames is not (since there is no such thing as a fractional frame).

            When using a float frame rate (fps) calculations of frames and timecode are not
            technically exact, and will cause time drift away from "wall clock" time. But
            this is still correct. Drop frame was created to help mitigate this and it attempts
            to correct the drift by skipping frame numbers at certain intervals. However, it's
            still technically not exact and will usually be a fraction of time off. But it's
            exact enough for the editorial world.

        .. seealso:: https://docs.python.org/2/tutorial/floatingpoint.html#tut-fp-issues

        :return: Number of seconds as a :obj:`Decimal`.
        """
        frame = self.to_frame()
        return decimal.Decimal(frame) / self._fps

    # Redefine some standard operators.
    def __add__(self, right):
        """
        + operator override: Add a Timecode or a number of frames to this :class:`Timecode`
        with the :class:`Timecode` on the right of the operator.

        :param right: Right operand for ``+`` operator, either a :class:`Timecode` instance or an
                      :obj:`int` representing a number of frames.

        :return: A new :class:`Timecode` instance, in this :class:`Timecode` fps, result of the
                 addition.
        """
        if isinstance(right, Timecode):
            return self.from_frame(
                self.to_frame() + right.to_frame(), self._fps, self._drop_frame
            )
        if isinstance(right, int):
            return self.from_frame(self.to_frame() + right, self._fps, self._drop_frame)
        raise TypeError("Unsupported operand type %s for +" % type(right))

    def __radd__(self, left):
        """
        + operator override : Add a number of frames to this :class:`Timecode`, with the
        timecode on the left of the ``+`` operator.

        :param left: Left operand for ``+`` operator, either a :class:`Timecode` instance or an
                     :obj:`int` representing a number of frames.
        :return: A new :class:`Timecode` instance, in this :class:`Timecode` fps, result of the
                 addition.
        """
        return self.__add__(left)

    def __sub__(self, right):
        """
        - operator override : Subtract a Timecode or a number of frames to this :class:`Timecode`
        with the timecode on the right of the operator.

        :param right: Right operand for ``-`` operator, either a :class:`Timecode` instance or an
                      :obj:`int` representing a number of frames.
        :return: A new :class:`Timecode` instance, in this :class:`Timecode` fps, result of the
                 subtraction.
        """
        if isinstance(right, Timecode):
            return self.from_frame(
                self.to_frame() - right.to_frame(), self._fps, self._drop_frame
            )
        if isinstance(right, int):
            return self.from_frame(self.to_frame() - right, self._fps, self._drop_frame)
        raise TypeError("Unsupported operand type %s for -" % type(right))

    def __rsub__(self, left):
        """
        - operator override : Subtract a number of frames to this :class:`Timecode`, with the
        timecode on the left of the ``-`` operator.

        :param left: Left operand for ``-`` operator, either a :class:`Timecode` instance or an
                     :obj:`int` representing a number of frames.
        :return: A new :class:`Timecode` instance, in this :class:`Timecode` fps, result of the
                 subtraction.
        """
        return self.__sub__(left)

    def __str__(self):
        """
        String representation of this :class:`Timecode` instance.
        """
        return "%02d:%02d:%02d%s%02d" % (
            self._hours,
            self._minutes,
            self._seconds,
            self._frame_delimiter,
            self._frames,
        )

    def __repr__(self):
        """
        Code representation of this :class:`Timecode` instance.
        """
        drop = "NDF"
        if self._drop_frame:
            drop = "DF"
        return "<class %s %02d:%02d:%02d%s%02d (%sfps %s)>" % (
            self.__class__.__name__,
            self._hours,
            self._minutes,
            self._seconds,
            self._frame_delimiter,
            self._frames,
            self._fps,
            drop,
        )
