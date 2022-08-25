# Copyright 2016 Autodesk, Inc. All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#
from .timecode import Timecode
from . import logger
from .errors import BadBLError, BadFCMError
import os
import re

# A list of keywords we will be looking for in comments
_COMMENTS_KEYWORDS = [
    "LOC",
    "SOURCE FILE",
    "TO CLIP NAME",
    "FROM CLIP NAME",
    "CLIP NAME",
    "ASC_SOP",
    "ASC_SAT",
]
# Build a regular expression to match the keywords above, matching lines beginning
# with :
# * KEYWORD:
# The regexp is build with : "((?:" + keyword1 + ")|(?:" + keyword2 + ... + "))"
# ")|(?:" being used to join the different keywords together
_COMMENT_REGEXP = re.compile(
    "\*?\s*(?P<type>(?:%s))\s*:\s+(?P<value>.*)" % ")|(?:".join(_COMMENTS_KEYWORDS)
)




_FIXUP_SOURCE = True

class EditProcessor(object):
    """
    An example of keeping previous parsed edit event around, while using the process
    edit function.
    """

    def __init__(self, shot_regexp=None):
        super(EditProcessor, self).__init__()
        self._previous_edit = None
        self._shot_regexp = shot_regexp

    def process(self, edit, logger):
        """
        Example : process the current edit and display previous and current one
        """
        process_edit(edit, logger, self._shot_regexp)
        logger.info("Treated edit %s previous was %s" % (edit, self._previous_edit))
        self._previous_edit = edit


def process_edit(edit, logger, shot_regexp=None):
    """
    Extract standard meta data from comments for an Edit:

    - name from ``* LOC: 01:00:00:12 YELLOW  MR0200``
    - clip name from ``* FROM CLIP NAME:  246AA-6``
    - tape from ``* SOURCE FILE: LR9907610``
    - asc_sop and asc_sat from::

        ASC_SOP (1.0854 1.0451 0.9943)(0.0009 0.0022 -0.0292)(1.0163 1.0105 0.9424)
        ASC_SAT 1.0000

    If a regular expression is given, it will be used to extract extra information
    from the edit name.

    - a shot name
    - a type
    - a format

    Typical values for the regular expression would be as simple as a single group
    to extract the shot name, e.g. ``^(\w+)_.+$``
    or more advanced regular expression with named groups to extract additional
    information, e.g. ``(?P<shot_name>\w+)_(?P<type>\w\w\d\d)_(?P<version>[V,v]\d+)$``

    :param edit: An Edit instance.
    :param logger: A standard logger.
    :param shot_regexp: A regular expression to extract extra information from the
                        edit name.
    """
    # Add our runtime attributes
    edit._name = None
    edit._tape = None
    edit._shot_name = None
    edit._clip_name = None
    edit._asc_sop = None
    edit._asc_sat = None
    edit._type = None
    edit._format = None
    # edit._version = None
    # Treat all comments
    for comment in edit.comments:
        m = _COMMENT_REGEXP.match(comment)
        if m:
            comment_type = m.group("type")
            value = m.group("value")
            logger.debug("Found in comments [%s]: %s" % (comment_type, value))
            if comment_type == "LOC":
                tokens = value.split()
                if len(tokens) > 2:
                    edit._name = tokens[2]
            elif comment_type == "SOURCE FILE":
                edit._tape = value.split()[-1]
            # The clip name can either be explicitly called out with CLIP NAME or if we only
            # have FROM CLIP NAME, then we use that. For transitions, we'll have FROM CLIP NAME
            # and TO CLIP NAME in which case we want to use TO CLIP NAME.
            elif comment_type == "CLIP NAME":
                edit._clip_name = value
            elif comment_type == "TO CLIP NAME":
                edit._clip_name = value
            elif comment_type == "FROM CLIP NAME":
                edit._clip_name = value
            elif comment_type == "ASC_SOP":
                edit._asc_sop = value
            elif comment_type == "ASC_SAT":
                edit._asc_sat = value

    # Extract a shot name
    # Default assignment
    edit._shot_name = edit._name
    if edit._name and shot_regexp:
        # Support pre-compiled regexp or strings
        if isinstance(shot_regexp, str):
            regexp = re.compile(shot_regexp)
        else:
            regexp = shot_regexp
        logger.debug("Parsing %s with %s" % (edit._name, str(regexp)))
        m = regexp.search(edit._name)
        if m:
            logger.debug("Matched groups: %s" % str(m.groups()))
            if regexp.groups == 1:  # Only one capturing group, use it for the shot name
                edit._shot_name = m.group(1)
            else:
                grid = regexp.groupindex
                if "shot_name" not in grid:
                    raise ValueError(
                        'No "shot_name" named group in regular expression %s'
                        % regexp.pattern
                    )
                edit._shot_name = m.group("shot_name")
                if "type" in grid:
                    edit._type = m.group("type")
                if "format" in grid:
                    edit._format = m.group("format")
                if "version" in grid:
                    edit._version = m.group("version")


class EditEvent(object):
    """
    An entry, or event, or edit from an edit list

    New attributes can be added at runtime, provided that they don't
    clash with :class:`EditEvent` regular attributes, by just setting their value, e.g.
    ``edit.my_own_attribute = "awesome"``
    They then are accessible like other regular attributes, e.g.
    ``print edit.my_own_attribute``

    This implementation assume timecodes out are exclusive, meaning that a one
    frame long record would be ``00:00:00:01 00:00:00:02`` ( not ``00:00:00:01`` )

    """

    # Our known attributes
    # Every other attributes will go into the _meta_data dictionary
    __mine = [
        "_effects",
        "_comments",
        "_meta_data",
        "_retime",
        "_id",
        "_reel",
        "_channels",
        "_source_in",
        "_source_out",
        "_record_in",
        "_record_out",
    ]
    # Protect accessors clashes by building a list of them
    # from internal attributes
    __protected = [x[1:] for x in __mine]

    def __init__(
        self,
        id=None,
        reel=None,
        channels=None,
        source_in=None,
        source_out=None,
        record_in=None,
        record_out=None,
        fps=24,
        drop_frame=None,
    ):
        """
        Instantiate a new EditEvent

        :param id: The edit id in a Edit Decision list, as an int.
        :param reel: The reel for this edit as a str.
        :param channels: Channels for this edit, video, audio, etc. as a str.
        :param source_in: Timecode in for the source, as a string formatted as
                          hh:mm:ss:ff for non-drop frame or hh:mm:ss;ff for drop frame.
        :param source_out: Timecode out for the source, as a string formatted as
                          hh:mm:ss:ff for non-drop frame or hh:mm:ss;ff for drop frame.
        :param record_in: Timecode in for the recorder, as a string formatted as
                          hh:mm:ss:ff for non-drop frame or hh:mm:ss;ff for drop frame.
        :param record_out: Timecode out for the recorder, as a string formatted as
                          hh:mm:ss:ff for non-drop frame or hh:mm:ss;ff for drop frame.
        :param fps: Number of frames per second for this edit, as an int or float.
        :param drop_frame: Boolean indicating whether this edit uses drop frame or not or None
                           if it's not specified. Default is None.
        """

        # If new attributes are added here, their name should be added to the
        # __mine list as well, otherwise will end up in the meta data dictionary
        self._effects = []
        self._comments = []
        self._meta_data = {}  # A place holder where additional meta data can be stored
        self._retime = {}
        self._fps = fps
        self._drop_frame = drop_frame
        self._id = int(id)
        self._reel = reel
        self._channels = channels
        self._source_in = Timecode(source_in, fps=fps, drop_frame=drop_frame, source=True)
        self._source_out = Timecode(source_out, fps=fps, drop_frame=drop_frame, source=True)
        self._record_in = Timecode(record_in, fps=fps, drop_frame=drop_frame)
        self._record_out = Timecode(record_out, fps=fps, drop_frame=drop_frame)

    @property
    def fps(self):
        """
        Return the fps for this edit.

        :returns: Frame rate setting used by this EditEvent as an int or float.
        """
        return self._fps

    @property
    def drop_frame(self):
        """
        Return the drop frame value for this edit.

        :returns: Boolean indicating if this EditEvent is drop frame or not.
        """
        return self._drop_frame

    @property
    def channels(self):
        """
        Return the channels for this edit.

        :returns: String representing the channels in this EditEvent (eg. "AV", "V", etc.)
        """
        return self._channels

    @property
    def id(self):
        """
        Return the id for this edit.

        :returns: Id of this EditEvent as an int.
        """
        return self._id

    @property
    def reel(self):
        """
        Return the reel for this edit.

        :returns: Reel for this EditEvent as a str.
        """
        return self._reel

    @property
    def comments(self):
        """
        Return the comments for this edit, as a list.

        :returns: List of comment strings for this EditEvent.
        """
        return self._comments

    @property
    def pure_comments(self):
        """
        An iterator over "pure" comments, that is comments which
        do not contain known keywords.

        :yields: Iterator for looping over pure (non-keyword) comments.
        """
        for comment in self._comments:
            if not _COMMENT_REGEXP.match(comment):
                yield comment

    @property
    def timecodes(self):
        """
        Return the source in, source out, record in, record out timecodes for this
        edit as a tuple.

        :returns: Tuple of timecodes for this EditEvent as
                  ``(source_in, source_out, record_in, record_out)``.
        """
        return (self._source_in, self._source_out, self._record_in, self._record_out)

    @property
    def source_in(self):
        """
        Return the source in timecode for this edit.

        :returns: Timecode string representing the source in for this EditEvent.
        """
        return self._source_in

    @property
    def source_out(self):
        """
        Return the source out timecode for this edit.

        :returns: Timecode string representing the source out for this EditEvent.
        """
        return self._source_out

    @property
    def source_duration(self):
        """
        Return the source duration, in frames.

        :returns: Int representing the source duration in frames.
        """
        # Timecode out are exclusive, e.g.
        # 00:00:00:01 -> 00:00:00:02 is only one frame long
        return self._source_out.to_frame() - self._source_in.to_frame()

    @property
    def record_in(self):
        """
        Return the record in timecode for this edit.

        :returns: Timecode string representing the record in for this EditEvent.
        """
        return self._record_in

    @property
    def record_out(self):
        """
        Return the record out timecode for this edit.

        :returns: Timecode string representing the record out for this EditEvent.
        """
        return self._record_out

    @property
    def record_duration(self):
        """
        Return the record duration, in frames.

        :returns: Int representing the record duration in frames.
        """
        # Timecode out are exclusive, e.g.
        # 00:00:00:01 -> 00:00:00:02 is only one frame long
        return self._record_out.to_frame() - self._record_in.to_frame()

    @property
    def has_effects(self):
        """
        Return ``True`` if this :class:`EditEvent` has some effect(s).

        :returns: Boolean indicating whether this EditEvent has effects.
        """
        return bool(self._effects)

    def add_effect(self, tokens):
        """
        For now, just register the effect line as a string and append it to the
        list of effects for this EditEvent.

        Later we might want to parse the tokens, and store some actual
        effects value on this edit.

        :param tokens: List of tokens for the effect.
        """
        self._effects.append(" ".join(tokens))

    def add_comments(self, comments):
        """
        Associate a comment line to this edit.

        :param comments: Comment string to append to the list of comments for this
                         EditEvent.
        """
        self._comments.append(comments)

    @property
    def has_retime(self):
        """
        Return ``True`` if this edit has some retime.

        :returns: Boolean indicating whether this EditEvent has a retime.
        """
        return bool(self._retime)


    @property
    def retime_comment(self):
        return self._retime['comment']

    def add_retime(self, tokens):
        """
        For now, just register the retime line as a string and append it to the
        list of retimes for this EditEvent.

        Later we might want to parse the tokens, and store some actual
        retime values.

        NOW WE ARE GOING TO REPROCESS THE SOURCE IN / OUT

        :param tokens: List of tokens for the retime.
        """
        retime = {}
        _RETIME_COMMENTS = ["Freeze Frame", "Reverse motion", "Slow motion"]
        retime['tokens'] = tokens
        retime['source_in'] = Timecode(
                            tokens[3], fps=self.fps, drop_frame=self._drop_frame,source=True
                        )
        retime['speed'] = tokens[2]
        record_duration = self._record_out.to_frame()-self.record_in.to_frame()
        if abs(float(tokens[2])) < 0.0001:
            retime['comment'] = "%s (duration %s)" % (_RETIME_COMMENTS[0], record_duration)
        else:
            if float(tokens[2]) < 0:
                retime['comment'] = "%s (%s fps , record dur %s)" % (_RETIME_COMMENTS[1], tokens[2], record_duration)
            else:
                if float(tokens[2]) > 0:
                    retime['comment'] = "%s (%s fps , record dur %s)" % (_RETIME_COMMENTS[2], tokens[2], record_duration)

        self._retime = retime
        # self._retime = " ".join(tokens)
        if _FIXUP_SOURCE:
            duration = self._record_out.to_frame() - self._record_in.to_frame()
            source_duration = float(tokens[2])/self._fps * duration
            if source_duration < 0:
                source_retime_in_frames = retime['source_in'].to_frame() + source_duration
                if source_retime_in_frames < 0:
                    retime['comment'] = retime['comment'] + " Warn: source is %s frames short!" % int(abs(source_retime_in_frames))
                    source_retime_in_frames = 0
                self._source_in = Timecode.from_frame(source_retime_in_frames + 1, self._fps, self._drop_frame)

    def __str__(self):
        """
        String representation for this :class:`EditEvent`
        """
        return "%03d %s %s %s %s %s %s %s" % (
            self._id,
            self._reel,
            self._channels,
            "C",
            str(self._source_in),
            str(self._source_out),
            str(self._record_in),
            str(self._record_out),
        )

    def __setattr__(self, attr_name, value):
        """
        Allow new attributes to be added on the fly, e.g. when parsing a file
        with a visitor.

        :param attr_name: Name of the attribute that needs setting.
        :param value: The value the attribute should take.
        """
        if attr_name in self.__protected:
            raise AttributeError(
                "EditEvent %s attribute can't be redefined" % attr_name
            )
        if attr_name in self.__mine:
            object.__setattr__(self, attr_name, value)
        else:
            self._meta_data[attr_name] = value

    def __getattr__(self, attr_name):
        """
        Retrieve runtime attributes from meta_data dictionary.

        :param attr_name: An attribute name.
        :return: The value for the given attribute name.
        :raise: ``AttributeError`` if the attribute can't be found.
        """
        if attr_name in self._meta_data:
            return self._meta_data[attr_name]
        raise AttributeError("EditEvent has no attribute %s" % attr_name)


class EditList(object):
    """
    An Edit Decision List.

    Typical use of EditList could look like this::

        # Define a visitor to extract some extra information from comments or locators.
        def edit_parser(edit):
            # New attributes can be added on the fly.
            if edit.id % 2:
                edit.is_even = False
            else:
                edit.is_even = True

        edl = EditList(file_path="/tmp/my_edl.edl", visitor=edit_parser)
        for edit in edl.edits:
            print str(edit)
            # Added attributes are reachable like regular ones.
            print edit.is_even
    """

    __logger = logger.get_logger()

    def __init__(self, fps=24, file_path=None, visitor=None):
        """
        Instantiate a new Edit Decision List.

        :param fps: Number of frames per second for this EditList as an int or float.
        :param file_path: Full path to a file to read.
        :param visitor: A callable which will be called on every edit and should
                        accept as input an :class:`EditEvent` and a logger.
        """
        self._title = None
        self._edits = []
        self._fps = fps
        self._has_transitions = False
        self._drop_frame = None
        if file_path:
            _, ext = os.path.splitext(file_path)
            if ext.lower() != ".edl":
                raise NotImplementedError(
                    "Can't read %s: don't know how to read files with %s extension",
                    file_path,
                    ext,
                )
            self.read_cmx_edl(file_path, fps=self._fps, visitor=visitor)

    @classmethod
    def set_logger(cls, logger):
        """
        Allow to use another logger than the default one provided in this
        framework.
        """
        cls.__logger = logger


    def set_tape(self,tape):
        """

        :param tape:
        :return:
        """
        self._tape = tape



    @property
    def has_transitions(self):
        """
        Return ``True`` if this EditList contains events with transitions.

        :returns: Boolean indicating if this EditList contains events with transitions.
        """
        return self._has_transitions

    @property
    def drop_frame(self):
        """
        Return ``True`` if this EditList is drop frame.

        :returns: Boolean indicating if this EditList uses drop frame or not.
        """
        return self._drop_frame

    @property
    def edits(self):
        """
        Return a list of all edit events in this :class:`EditList`.

        :returns: List of edit event objects in this edit list.
        """
        return self._edits

    @property
    def title(self):
        """
        Return this :class:`EditList`'s title

        :returns: Title of this edit list as a str.
        """
        return self._title

    @property
    def fps(self):
        """
        Return the number of frame per seconds used by this :class:`EditList`.

        :returns: Frame rate setting used by this edit list as an int or float.
        """
        return self._fps

    def read_cmx_edl(self, path, fps=24, visitor=None):
        """
        Parse the given edl file, extract a list of versions that need to be
        created.

        .. seealso::
            - http://xmil.biz/EDL-X/CMX3600.pdf
            - http://www.scottsimmons.tv/blog/2006/10/12/how-to-read-an-edl/
            - http://www.edlmax.com/maxguide.html

        :param path: Full path to a cmx compatible file to read.
        :param fps: Number of frames per-second for this :class:`EditList` as an int or float.
        :param visitor: A callable which will be called on every edit and should
                        accept as input an :class:`EditEvent` and a logger.
        """
        # Reset default values
        self._title = None
        self._edits = []
        # And read the file
        self.__logger.info("Parsing EDL %s" % path)
        with open(path, "rU") as handle:
            edit = None
            id_offset = 0
            try:
                for line in handle:
                    # Not sure why we have to do that ...
                    # Some crappy Windows thing ?
                    line = line.replace("\x1a", "").strip(" \n")
                    if not line:
                        continue

                    self.__logger.debug("Treating: [%s]" % line)
                    line_tokens = line.split()
                    if line.startswith("TITLE:"):
                        if len(line_tokens) > 1:
                            self._title = " ".join(line_tokens[1:])
                    elif line.startswith("FCM:"):
                        # Frame Code Mode: Can be DROP FRAME or NON DROP FRAME. If it's
                        # something else, raise an error.
                        if line_tokens[1] == "DROP" and line_tokens[2] == "FRAME":
                            drop_frame = True
                        elif line_tokens[1] == "NON-DROP" and line_tokens[2] == "FRAME":
                            drop_frame = False
                        else:
                            raise BadFCMError(os.path.basename(path))
                        # Only set the EDL drop frame value once.
                        # Some EDLS contain additional FCM notes for transitions. It's
                        # unclear if these can conflict with the EDL setting or not but for
                        # now we will ignore it if that happens and issue a warning.
                        if self._drop_frame is None:
                            self._drop_frame = drop_frame
                        else:
                            if self._drop_frame != drop_frame:
                                self.__logger.warning(
                                    'Found an FCM note "%s" that conflicts with the EDL\'s '
                                    "drop frame setting. Only one FCM note is supported for "
                                    "setting the drop frame mode for the entire EDL. Any "
                                    "additional FCM notes will be ignored." % line
                                )
                    elif len(line_tokens) > 1 and line_tokens[1] == "BL":
                        raise BadBLError(os.path.basename(path))
                    elif line_tokens[0] == "M2":  # Retime
                        if not edit:
                            raise RuntimeError("Found unexpected line")
                        edit.add_retime(line_tokens)
                    elif line_tokens[0].isdigit():
                        media_type = line_tokens[2]
                        event_type = line_tokens[3]
                        # If we have an audio track, ignore it and adjust the
                        # event id numbering to reflect that.
                        if media_type == "AA":
                            id_offset += 1
                            continue
                        id = int(line_tokens[0]) - id_offset
                        # New edit
                        # Time to call the visitor (if any) with the previous
                        # edit (if any)
                        if edit:
                            if edit.id == id:
                                # Duplicated id, it is an effect
                                edit.add_effect(line_tokens)
                                continue
                            if visitor:
                                self.__logger.debug("Visiting: [%s]" % edit)
                                visitor(edit, self.__logger)
                        # Include our event if it's a Cut type (C) and not
                        # an audio track (AA).
                        if event_type == "C" and media_type != "AA":  # cut
                            # Number of tokens can vary in the middle
                            # so tokens at the end of the line are indexed with
                            # negative indexes
                            edit = EditEvent(
                                fps=fps,
                                id=id,
                                reel=line_tokens[1],
                                channels=media_type,
                                source_in=line_tokens[-4],
                                source_out=line_tokens[-3],
                                record_in=line_tokens[-2],
                                record_out=line_tokens[-1],
                                drop_frame=self._drop_frame,
                            )
                            self._edits.append(edit)
                        else:
                            if not edit:
                                raise RuntimeError("Found unexpected effect")
                            edit.add_effect(line_tokens)
                    else:
                        # A comment
                        if edit:
                            edit.add_comments(line)
                # Call the visitor (if any) with the last edit (if any)
                if edit and visitor:
                    self.__logger.debug("Visiting: [%s]" % edit)
                    visitor(edit, self.__logger)
            except Exception as e:  # Catch the exception so we can add the current line contents
                args = [
                    "%s.\n\nError reported while parsing %s at line:\n\n%s"
                    % (e.args[0], path, line)
                ] + list(e.args[1:])
                e.args = args
                raise
        # Once we have our edits list, we can loop through it and adjust any
        # timecode we like to account for effects (like transitions).
        for count_edits, edit in enumerate(self._edits):
            prev = count_edits - 1
            for effect in edit._effects:
                effect_tokens = effect.split()
                # Modify some timecode if we have a cross-dissolve.
                if re.match(r'[Dd].*|[wW].*', effect_tokens[3]):
                # if effect_tokens[3] == "D":
                    self._has_transitions = True
                    # We don't want to go negative here, else we'll grab edits
                    # from the end of the list.
                    #TODO This does not need to be done as the previous edit is not related to the dissolve?
                    # For now only doing for dissolve !!
                    if prev > -1 and effect_tokens[3] == "D":
                        # Add the transition duration to the previous edit's source out.
                        trans_duration = Timecode(
                            effect_tokens[4], fps=edit.fps, drop_frame=self._drop_frame
                        ).to_frame()
                        self._edits[prev]._source_out = Timecode(
                            str(
                                self._edits[prev]._source_out.to_frame()
                                + trans_duration
                            ),
                            fps=self._edits[prev].fps,
                            drop_frame=self._drop_frame,
                            source=True
                        )
                        self._edits[prev]._record_out = Timecode(
                            str(
                                self._edits[prev]._record_out.to_frame()
                                + trans_duration
                            ),
                            fps=self._edits[prev].fps,
                            drop_frame=self._drop_frame,
                        )
                    #Take the values from the Dissolve effect for the current edit.
                    edit._source_in = Timecode(
                        effect_tokens[5], fps=edit.fps, drop_frame=self._drop_frame
                    )
                    edit._source_out = Timecode(
                        effect_tokens[6], fps=edit.fps, drop_frame=self._drop_frame
                    )
                    edit._record_in = Timecode(
                        effect_tokens[7], fps=edit.fps, drop_frame=self._drop_frame
                    )
                    edit._record_out = Timecode(
                        effect_tokens[8], fps=edit.fps, drop_frame=self._drop_frame
                    )
