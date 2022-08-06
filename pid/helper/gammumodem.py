#!/usr/bin/python
# Copyright 2015 Neuhold Markus and Kleinsasser Mario
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import time
import gammu
import re
from os import path
from common import smsgwglobals
import pidglobals

USSD_REPLY = None

class USBModem(object):
    __status = None
    __config = None
    __section = None
    __ctryexitcode = None
    __statemachine = None

    def __init__(self, config, section=0, pin=None, ctryexitcode="00"):
        self.__config = config
        self.__section = section
        self.__ctryexitcode = ctryexitcode

        # Get Connection to Modem
        self.__statemachine = gammu.StateMachine()

        status = self.init_usbmodem(config, section, pin)

        self.__status = status

    def init_usbmodem(self, config, section, pin):
        try:
            # Read config file
            self.__statemachine.ReadConfig(Section=section, Filename=config)

            # Connect to USBModem
            self.__statemachine.Init()

            # Enable debugging if configured
            if pidglobals.gammudebug:
                self.__statemachine.SetDebugFile(pidglobals.gammudebugfile)
                self.__statemachine.SetDebugLevel("textalldate")

            # Set_Pin
            status = self.set_pin(pin)
            return status

        except Exception as e:
            smsgwglobals.pidlogger.warning("MODEM: Error at connect - " +
                                           str(e))
            return False

    def get_status(self):
        return self.__status

    def get_sim_imsi(self):
        return self.__statemachine.GetSIMIMSI()

    def get_modem_imei(self):
        return self.__statemachine.GetIMEI()

    def get_modem_carrier(self):
        network_dict = {
            "255 01" : "Vodafone",
            "255 06" : "lifecell"
        }
        netinfo = self.__statemachine.GetNetworkInfo()

        try:
            return network_dict[netinfo["NetworkCode"]]
        except KeyError as e:
            return netinfo["NetworkCode"]

    def ussd_callback(self, state_machine, callback_type, data):
        global USSD_REPLY
        if callback_type != 'USSD':
            print('Unexpected event type: {0}'.format(callback_type))
            return

        USSD_REPLY = data

    def process_ussd(self, ussd_code):
        self.__statemachine.SetIncomingCallback(self.ussd_callback)
        try:
            self.__statemachine.SetIncomingUSSD()
        except gammu.ERR_NOTSUPPORTED:
            smsgwglobals.pidlogger.warning("Incoming USSD notification is not supported")
            return None

        global USSD_REPLY

        USSD_REPLY = None
        smsgwglobals.pidlogger.info("Calling USSD code: " + ussd_code)
        try:
            self.__statemachine.DialService(ussd_code)
            loops = 0
            while not USSD_REPLY and loops < 20:
                self.__statemachine.ReadDevice()
                loops += 1

            smsgwglobals.pidlogger.info("Received USSD answer " + str(USSD_REPLY) + " for USSD code: " + ussd_code)
        except Exception as e:
            # We fail on USS, sent nothing
            smsgwglobals.pidlogger.info("Received ERROR during dial for USSD code: " + ussd_code)
            pass
        return USSD_REPLY

    def parse_ussd(self, ussd_reply, ussd_regex):
        ussd_status = "N/A"
        if ussd_reply is not None and "Text" in ussd_reply:
            ussd_matches = re.search(ussd_regex, ussd_reply["Text"])
            if ussd_matches is not None:
                ussd_status = ussd_matches.group(1)
        return ussd_status

    def check_sim_blocked(self, modem):
        # Send sms to fake number
        self.send_SMS("TEST_BLOCK", "+3812345678910")

        abspath = pidglobals.abspath
        gammulogfile = modem["logfile"] if modem.get("logfile") else pidglobals.abspath +  "/logs/modem_" + modem["modemid"] + ".log"
        with open (gammulogfile, 'r', encoding = "utf-8") as fd:
            gammulog_lines = fd.readlines()

        blocked_regex_list = [".*CMS Error 8:.*"]
        active_regex_list = [".*CMS Error 69:.*", ".*CMS Error 21:.*"]
        blocked = "N/A"
        for logline in gammulog_lines:
            for blocked_regex in blocked_regex_list:
                blocked_match = re.search(blocked_regex, logline)
                if blocked_match is not None:
                    blocked = "Yes"

            for active_regex in active_regex_list:
                active_match = re.search(active_regex, logline)
                if active_match is not None:
                    blocked = "No"

        smsgwglobals.pidlogger.debug("MODEM: SIM card (IMSI: " + modem["imsi"] + ") inside Modem #" + modem["modemid"] +
                                     " blocked status '" +
                                     blocked + "' ")
        return blocked

    def set_pin(self, pin):
        # Check if PIN is needed
        secstatus = self.__statemachine.GetSecurityStatus()

        if secstatus is None:
            # No Pin is needed
            status = True

        elif secstatus == 'PIN':
            # PIN is needed
            self.__statemachine.EnterSecurityCode('PIN', pin)
            # Wait 5 seconds to get PIN set
            time.sleep(5)

            # Recheck security status
            secstatus_again = self.__statemachine.GetSecurityStatus()
            if secstatus_again is None:
                status = True
            else:
                status = False
        else:
            # unhandled status
            status = False

        smsgwglobals.pidlogger.debug("MODEM: Set PIN (" + pin +
                                     ") with status '" +
                                     str(status) + "' ")
        return status

    def transform_targetnr(self, targetnr):
        # trim leading '+' and add ctryexitcode
        tonr = self.__ctryexitcode + targetnr.lstrip('+')
        return tonr

    def send_SMS(self, content, targetnr):

        # Check if String holds only ASCII characters or is Unicode
        try:
            content.encode('ascii')
            isUnicode = False
        except UnicodeEncodeError:
            isUnicode = True

        smsgwglobals.pidlogger.debug("MODEM: isUnicode = " + str(isUnicode))

        # if content fits in a short sms send a standard Text message else
        # send a ConcatenatedTextLong message
        lencontent = len(content)

        if (isUnicode and lencontent <= 70):
            whichID = 'Text'
        elif (not isUnicode and lencontent <= 160):
            whichID = 'Text'
        else:
            whichID = 'ConcatenatedTextLong'

        # Fixes issue #43 - changing to not setting a SMS Class
        smsinfo = {
            'Class': -1,
            'Unicode': isUnicode,
            'Entries': [
                {
                    'ID': whichID,
                    'Buffer': content
                }
            ]}

        # Encode message
        encoded = gammu.EncodeSMS(smsinfo)

        # Replace + with country exit code of Modem
        tonr = self.transform_targetnr(targetnr)

        # Send message
        for message in encoded:
            message['SMSC'] = {'Location': 1}
            message['Number'] = tonr

            try:
                msgref = self.__statemachine.SendSMS(message)
                status = True
                status_code = 1
            except gammu.GSMError as e:
                status_code = e.args[0]["Code"]
                msgref = str(e)
                status = False
            except Exception as e:
                msgref = str(e)
                status = False

        smsgwglobals.pidlogger.debug("MODEM: send_SMS to " + str(targetnr) +
                                     " has status: " + str(status) + " and " +
                                     "msgref (" + str(msgref) + ")")
        return status, status_code
