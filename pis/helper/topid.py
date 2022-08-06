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

import pisglobals
# from common import error
from common import smsgwglobals
import json
from common.helper import GlobalHelper


class PID(object):
    """Class used to store SocketHandlers into pisglobals.knownpids
       and for doing communication with the PID
    """
    @staticmethod
    def addclient(address, handler):
        address = str(address)
        pisglobals.knownpids[address] = {'handler': handler,
                                         'smslist': []}
        smsgwglobals.pislogger.info("/ws: " + address +
                                    " - connected.")

    @staticmethod
    def addclientinfo(address, pidid=None, modemlist=None):
        address = str(address)
        if pidid:
            pisglobals.knownpids[address]['pidid'] = pidid
            smsgwglobals.pislogger.debug("/ws: " + address +
                                         "- adding pidid: " + pidid)
            if modemlist:
                pisglobals.knownpids[address]['modemlist'] = modemlist
                smsgwglobals.pislogger.debug("/ws: " + address +
                                             "- adding modemlist: "
                                             + str(modemlist))

    @staticmethod
    def addclientsms(address, smsid, status="SENTTOMODEM", status_code = 0):
        # add tupple wisid/smsid to form list of forwarded to PID
        address = str(address)
        element = {'smsid': smsid,
                   'status': status,
                   'status_code': status_code}
        pisglobals.knownpids[address]['smslist'].append(element)

    @staticmethod
    def getclientsmsstatus(address, smsid):
        """ Set or get clientsmsstatus
        """
        address = str(address)
        for sms in pisglobals.knownpids[address]['smslist']:
            if sms['smsid'] == smsid:
                # Get status
                smsgwglobals.pislogger.debug("PID: SMSstatus " +
                                             sms['status'] +
                                             ", SMSStatusCode " +
                                             str(sms['status_code']) +
                                             " for SMS with id " +
                                             smsid +
                                             " found.")
                return sms['status'], sms['status_code']

        smsgwglobals.pislogger.debug("PID: No matching SMS for id " +
                                     smsid + "found!")
        return False

    @staticmethod
    def setclientsmsstatus(address, smsid, status, status_code):
        if PID.removeclientsms(address, smsid):
            PID.addclientsms(address, smsid, status, status_code)
            smsgwglobals.pislogger.debug("PID: SMSstatus " +
                                         status +
                                         ", SMSStatusCode " +
                                         str(status_code) +
                                         " for SMS with ID " +
                                         smsid +
                                         " set!")

    @staticmethod
    def removeclientsms(address, smsid):
        # remove smsid from list of sms for PID
        straddress = str(address)
        status, status_code = PID.getclientsmsstatus(address, smsid)
        if status:
            element = {'smsid': smsid,
                       'status': status,
                       'status_code': status_code}
            pisglobals.knownpids[straddress]['smslist'].remove(element)
            smsgwglobals.pislogger.debug("PID: Removed SMS with ID " +
                                         smsid +
                                         " from smslist.")
            return True
        else:
            return False

    @staticmethod
    def delclient(address=None, code=None, reason=None):
        if address is None:
            # if no PID is connected init pisglobals
            pisglobals.knownpids = None

        else:
            # else remove only clients from one PID
            address = str(address)
            try:
                del pisglobals.knownpids[address]["modemlist"]
                del pisglobals.knownpids[address]["handler"]
            except:
                pass
            smsgwglobals.pislogger.debug("/ws: " + address +
                                         " - disconnected. Code: " +
                                         str(code) + " Reason: " + str(reason))

    @staticmethod
    def getclientmodemlist(address=None):
        modemlist = []

        if address is None:
            for address in pisglobals.knownpids:
                if 'modemlist' in pisglobals.knownpids[address]:
                    modems = pisglobals.knownpids[address]['modemlist']
                    for modem in modems:
                        modemlist.append(modem)

            smsgwglobals.pislogger.debug("PID: Full Modemlist " +
                                         str(modemlist) +
                                         " returned.")
        else:
            address = str(address)
            smsgwglobals.pislogger.debug("PID: Modemlist for " +
                                         address +
                                         " returned.")
            if 'modemlist' in pisglobals.knownpids[address]:
                modemlist = pisglobals.knownpids[address]['modemlist']

        return modemlist

    @staticmethod
    def sendtopid(address, data):
        asjson = json.dumps(data)
        tosend = GlobalHelper.encodeAES(asjson)

        client = PID.getclienthandler(address)
        client.send(tosend)
        smsgwglobals.pislogger.debug("/ws: Sending data to " +
                                     str(address) + " - " +
                                     str(data))

    @staticmethod
    def getclienthandler(address):
        smsgwglobals.pislogger.debug("PID: Handler for " +
                                     address +
                                     " returned.")
        return pisglobals.knownpids[address]['handler']

    @staticmethod
    def getclientaddress(modemid):
        smsgwglobals.pislogger.debug("PID: Query address for modemid: " +
                                     modemid)
        smsgwglobals.pislogger.debug("PID: getclientaddress has kownpids = " +
                                     str(pisglobals.knownpids))
        for address in pisglobals.knownpids:
            client = pisglobals.knownpids[address]
            modems = client["modemlist"] if "modemlist" in client else {}
            for modem in modems:
                if modem is not None and modem['modemid'] == modemid:
                    smsgwglobals.pislogger.debug("PID: Address " +
                                                 address +
                                                 " returned.")
                    return address

        smsgwglobals.pislogger.debug("PID: No matching client found!")
        return False
