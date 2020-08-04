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

import hashlib
import sys
sys.path.insert(0, "..")
from os import path
from datetime import datetime
from common.config import SmsConfig
from common.database import Database
from common.helper import GlobalHelper
from common import error
from common import smsgwglobals
from application import apperror
from application import wisglobals
import uuid
import urllib.request
import json
import re
import socket
import pytz


class Helper(object):

    @staticmethod
    def processsms(sms, reprocess_sms = None):
        # if reprocess_sms = True - recreate smsid - as we need to create new SMS
        if reprocess_sms:
            sms.smsdict["smsid"] = str(uuid.uuid1())

        sms.smsdict["smsintime"] = datetime.utcnow()
        possibleroutes = []

        if Helper.allowed_time():
            try:
                routes = wisglobals.rdb.read_routing()

                # check if we have routes
                if routes is None or len(routes) == 0:
                    sms.smsdict["status"] = 104
                    sms.smsdict["modemid"] = "NoRoutes"
                    sms.smsdict["imsi"] = ""
                    sms.smsdict["statustime"] = datetime.utcnow()
                    sms.writetodb()
                    smsgwglobals.wislogger.debug("ROUTES empty!")
                    raise apperror.NoRoutesFoundError()

                # try to match routes, get possible routes
                for route in routes:
                    match = re.search(route["regex"], sms.smsdict["targetnr"])
                    if match is not None:
                        possibleroutes.append(route)

                # if no matches than take default modem
                if possibleroutes is None or len(possibleroutes) == 0:
                    for route in routes:
                        match = re.search(route["regex"], "fallback")
                        if match is not None:
                            possibleroutes.append(route)

                # if there are obsolete routes remove them from possible
                possibleroutes[:] = [d for d in possibleroutes if d['obsolete'] < 1]

                # if there routes with sms_count == sms_limit remove them from possible
                possibleroutes[:] = [d for d in possibleroutes if d['sms_count'] < d['sms_limit']]

                # if there routes with account_balance == 0.00 remove them from possible
                #possibleroutes[:] = [d for d in possibleroutes if int(d['account_balance']) >= 0]

                smsgwglobals.wislogger.debug("HELPER: receiverouting %s", str(possibleroutes))

                # if we still have no possible routes raise error
                if possibleroutes is None or len(possibleroutes) == 0:
                    sms.smsdict["status"] = 104
                    sms.smsdict["modemid"] = "NoPossibleRoutes"
                    sms.smsdict["imsi"] = ""
                    sms.smsdict["statustime"] = datetime.utcnow()
                    sms.writetodb()
                    smsgwglobals.wislogger.debug("POSSIBLE ROUTES empty!")
                    raise apperror.NoRoutesFoundError()

                # decide modemid to send sms
                # if only one possibility just set it and save it
                if len(possibleroutes) == 1:
                    sms.smsdict["modemid"] = possibleroutes[0]["modemid"]
                    sms.smsdict["imsi"] = possibleroutes[0]["imsi"]
                    sms.smsdict["status"] = 0
                    sms.smsdict["statustime"] = datetime.utcnow()
                    wisglobals.rdb.raise_sms_count(sms.smsdict["modemid"])
                    sms.writetodb()
                    smsgwglobals.wislogger.debug("HELPER: receiverouting One route found!")
                    smsgwglobals.wislogger.debug("HELPER: receiverouting %s ", possibleroutes)
                else:
                    smsgwglobals.wislogger.debug("More than one route found!")
                    lbcount = 1000000
                    selectedroute = None
                    for route in possibleroutes:
                        if route["sms_count"] / route["lbfactor"] <= lbcount:
                            lbcount = route["sms_count"] / route["lbfactor"]
                            selectedroute = route

                    smsgwglobals.wislogger.debug("HELPER: One route selected!")
                    smsgwglobals.wislogger.debug("HELPER: receiverouting %s ", possibleroutes)
                    sms.smsdict["modemid"] = selectedroute["modemid"]
                    sms.smsdict["imsi"] = selectedroute["imsi"]
                    sms.smsdict["status"] = 0
                    sms.smsdict["statustime"] = datetime.utcnow()
                    wisglobals.rdb.raise_sms_count(sms.smsdict["modemid"])
                    sms.writetodb()
            except error.DatabaseError as e:
                smsgwglobals.wislogger.debug(e.message)
        else:
            sms.smsdict["status"] = 105
            sms.smsdict["modemid"] = "NotAllowedTimeFrame"
            sms.smsdict["imsi"] = ""
            sms.smsdict["statustime"] = datetime.utcnow()
            sms.writetodb()
            smsgwglobals.wislogger.debug("Not allowed timeframe to process SMS!")
            raise apperror.NotAllowedTimeFrame()

    @staticmethod
    def allowed_time():
        allowed = False
        start_h, start_m = wisglobals.allowedstarttime.split(":")
        finish_h, finish_m = wisglobals.allowedfinishtime.split(":")

        ua_timezone = pytz.timezone("Europe/Kiev")
        now_ua = datetime.utcnow().astimezone(ua_timezone)
        allowed_start_time = datetime(now_ua.year, now_ua.month, now_ua.day, int(start_h), int(start_m), tzinfo=ua_timezone)
        allowed_end_time = datetime(now_ua.year, now_ua.month, now_ua.day, int(finish_h), int(finish_m), tzinfo=ua_timezone)

        if now_ua > allowed_start_time and now_ua < allowed_end_time:
            allowed = True

        return allowed

    @staticmethod
    def checkrouting():
        # check if directly connected wis is
        # still alive, if not, mark all of
        # its routes obsolete

        # get conf peers
        abspath = path.abspath(path.join(path.dirname(__file__),
                                         path.pardir))
        configfile = abspath + '/../conf/smsgw.conf'
        cfg = SmsConfig(configfile)
        peersjson = cfg.getvalue('peers', '[{}]', 'wis')
        smsgwglobals.wislogger.debug(peersjson)

        peers = json.loads(peersjson)
        smsgwglobals.wislogger.debug("HELPER: Routes to check " +
                                     str(len(peers)))

        for p in peers:
            try:
                if "url" not in p:
                    continue
                smsgwglobals.wislogger.debug(p["url"] +
                                             "/")
                request = \
                    urllib.request.Request(p["url"] +
                                           "/")
                f = urllib.request.urlopen(request, timeout=5)
                smsgwglobals.wislogger.debug(f.getcode())

                if f.getcode() != 200:
                    smsgwglobals.wislogger.debug("XXX WIS DELETE")
                    wisglobals.rdb.delete_routing_wisurl(
                        p["url"])
            except urllib.error.URLError as e:
                smsgwglobals.wislogger.debug(e)
                wisglobals.rdb.delete_routing_wisurl(
                    p["url"])
            except socket.timeout as e:
                smsgwglobals.wislogger.debug(e)
                smsgwglobals.wislogger.debug("HELPER: ceckrouting socket connection timeout")

        # check routing table entries
        routes = wisglobals.rdb.read_routing()
        for route in routes:
            try:
                smsgwglobals.wislogger.debug(route["wisurl"] +
                                             "/")
                request = \
                    urllib.request.Request(route["wisurl"] +
                                           "/")
                f = urllib.request.urlopen(request, timeout=5)
                smsgwglobals.wislogger.debug(f.getcode())

                if f.getcode() != 200:
                    smsgwglobals.wislogger.debug("XXX WIS DELETE")
                    wisglobals.rdb.delete_routing_wisurl(
                        p["url"])
            except urllib.error.URLError as e:
                smsgwglobals.wislogger.debug(e)
                wisglobals.rdb.delete_routing_wisurl(
                    p["url"])
            except socket.timeout as e:
                smsgwglobals.wislogger.debug(e)
                smsgwglobals.wislogger.debug("HELPER: checkrouting socket connection timeout")

    @staticmethod
    def receiverouting():
        # get conf peers
        abspath = path.abspath(path.join(path.dirname(__file__),
                                         path.pardir))
        configfile = abspath + '/../conf/smsgw.conf'
        cfg = SmsConfig(configfile)
        peersjson = cfg.getvalue('peers', '[{}]', 'wis')
        smsgwglobals.wislogger.debug(peersjson)

        peers = json.loads(peersjson)

        # read all active routes
        try:
            routes = wisglobals.rdb.read_routing()
        except error.DatabaseError as e:
            smsgwglobals.wislogger.debug(e.message)

        # if we have an empty rounting table,
        # try to get one from our direct connected
        # neighbor = backup
        if len(routes) == 0 or routes is None:
            Helper.requestrouting(initial=True)

        # for all routes but myself
        # send the full table
        for route in routes:
            # remove route von conf routes
            # if exist
            for p in list(peers):
                if "url" not in p:
                    continue
                if route["wisurl"] == p["url"]:
                    peers.remove(p)

            if route["wisid"] != wisglobals.wisid:
                smsgwglobals.wislogger.debug("Sending to "
                                             + route["wisurl"])
                # encode to json
                jdata = json.dumps(routes)
                data = GlobalHelper.encodeAES(jdata)

                request = \
                    urllib.request.Request(
                        route["wisurl"] +
                        "/api/receiverouting")

                request.add_header("Content-Type",
                                   "application/json;charset=utf-8")

                try:
                    f = urllib.request.urlopen(request, data, timeout=5)
                    smsgwglobals.wislogger.debug(f.getcode())
                except urllib.error.URLError as e:
                    smsgwglobals.wislogger.debug(e)
                    smsgwglobals.wislogger.debug("Get peers NOTOK")
                except socket.timeout as e:
                    smsgwglobals.wislogger.debug(e)
                    smsgwglobals.wislogger.debug("HELPER: receiverouting socket connection timeout")

        # check if there are remaining peers which
        # are not recognized by routing table to send
        # routing table to
        if len(peers) != 0:
            for p in peers:
                if "url" not in p:
                    continue
                jdata = json.dumps(routes)
                data = GlobalHelper.encodeAES(jdata)

                request = \
                    urllib.request.Request(
                        p["url"] +
                        "/api/receiverouting")

                request.add_header("Content-Type",
                                   "application/json;charset=utf-8")

                try:
                    f = urllib.request.urlopen(request, data, timeout=5)
                    smsgwglobals.wislogger.debug(f.getcode())
                    smsgwglobals.wislogger.debug("HELPER: " +
                                                 "sending to " +
                                                 p["url"])
                except urllib.error.URLError as e:
                    smsgwglobals.wislogger.debug(e)
                    smsgwglobals.wislogger.debug("Get peers NOTOK")
                    pass
                except socket.timeout as e:
                    smsgwglobals.wislogger.debug(e)
                    smsgwglobals.wislogger.debug("HELPER: receiverouting socket connection timeout")
                except socket.error as e:
                    smsgwglobals.wislogger.debug(e)
                    smsgwglobals.wislogger.debug("HELPER: receiverouting socket connection error")

    @staticmethod
    def requestrouting(peers=None, initial=False):

        def getUrl(url):
            try:
                data = GlobalHelper.encodeAES('{"get": "peers"}')
                request = \
                    urllib.request.Request(url +
                                           "/api/requestrouting")
                request.add_header("Content-Type",
                                   "application/json;charset=utf-8")
                f = urllib.request.urlopen(request, data, timeout=5)
                if f.getcode() != 200:
                    smsgwglobals.wislogger.debug("Get peers NOTOK," +
                                                 " Error Code: ",
                                                 f.getcode())
                    return

                smsgwglobals.wislogger.debug("Get peers OK")
                rawbody = f.read().decode('utf-8')
                plaintext = GlobalHelper.decodeAES(rawbody)
                routelist = json.loads(plaintext)
                smsgwglobals.wislogger.debug(routelist)

                wisglobals.rdb.merge_routing(routelist)

            except urllib.error.URLError as e:
                smsgwglobals.wislogger.debug(e)
                smsgwglobals.wislogger.debug("Get peers NOTOK")
            except error.DatabaseError as e:
                smsgwglobals.wislogger.debug(e.message)
            except socket.timeout as e:
                smsgwglobals.wislogger.debug(e)
                smsgwglobals.wislogger.debug("HELPER: requestrouting socket connection timeout")

        if initial is True:
            abspath = path.abspath(path.join(path.dirname(__file__),
                                             path.pardir))
            configfile = abspath + '/../conf/smsgw.conf'
            cfg = SmsConfig(configfile)
            peersjson = cfg.getvalue('peers', '[{}]', 'wis')

            smsgwglobals.wislogger.debug(peersjson)
            peers = json.loads(peersjson)

            for peer in peers:
                if "url" not in peer:
                    continue
                smsgwglobals.wislogger.debug(peer["url"])
                getUrl(peer["url"])

    @staticmethod
    def checkpassword(username, password):
        try:
            db = Database()
            erg = db.read_users(username)

            if erg is None or len(erg) == 0:
                raise error.UserNotFoundError()

            retpasswordhash = erg[0]["password"]
            retpasswordsalt = erg[0]["salt"]

            givpasswordhash = hashlib.sha512((password +
                                              retpasswordsalt)
                                             .encode('utf-8')).hexdigest()

            if retpasswordhash == givpasswordhash:
                return True
            else:
                return False

        except error.DatabaseError as e:
            smsgwglobals.wislogger.debug(e.message)
