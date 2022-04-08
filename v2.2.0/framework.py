# Copyright 2016 Autodesk, Inc. All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#
import sgtk


class EditorialFramework(sgtk.platform.Framework):

    ##########################################################################################
    # init and destroy

    def init_framework(self):
        self.log_debug("%s: Initializing..." % self)

    def destroy_framework(self):
        self.log_debug("%s: Destroying..." % self)
