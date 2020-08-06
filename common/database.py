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


import sys
sys.path.insert(0, "..")
from os import path
from datetime import datetime
from datetime import timedelta
import pytz
import sqlite3
import uuid

from common import config
from common import error
from common import smsgwglobals


class Database(object):
    """Base class for Database handling - SQLite3

    Attributes:
        configfile -- path to configuration file
        to read [db] section from.

                     [db]
                     dbname = n0r1sk_smsgateway
                     loglevel = CRITICAL | ERROR | WARNING | INFO | DEBUG
                     logdirectory = absolut path to log directory
                     fallback is local \log directory
                     logfile = database.log
                     """
    __smsconfig = None
    __path = path.abspath(path.join(path.dirname(__file__),
                                    path.pardir))
    __con = None
    __cur = None

    # Constructor
    def __init__(self, configfile=(__path + "/conf/smsgw.conf")):
        # read SmsConfigs
        self.__smsconfig = config.SmsConfig(configfile)
        dbname = self.__smsconfig.getvalue('dbname', 'n0r1sk_smsgateway', 'db')
        dbname = (self.__path + "/common/sqlite/" + dbname + ".sqlite")
        smsgwglobals.dblogger.info("SQLite: Database file used: %s", dbname)

        # connect to database
        smsgwglobals.dblogger.debug("SQLite: Connecting to database...")
        self.db_connect(dbname)

        # create tables and indexes if not exit
        self.create_table_users()
        self.create_table_sms()
        self.create_table_stats()

        # delete sms older than configured timetoleave dbttl
        # default is 90 days in seconds
        dbttl = int(self.__smsconfig.getvalue('dbttl', 315569520, 'db'))
        self.delete_old_sms(dbttl)

    # Destructor (called with "del <Databaseobj>"
    def __del__(self):
        # shutting down connecitons to SQLite
        self.__con.close()

    # Connect to Database
    def db_connect(self, dbname="db.sqlite"):
        try:
            self.__con = sqlite3.connect(dbname, check_same_thread=False)
            # change row-factory to get
            self.__con.row_factory = sqlite3.Row
            self.__cur = self.__con.cursor()
        except Exception as e:
            smsgwglobals.dblogger.critical("SQLite: Unable to connect! " +
                                           "[EXCEPTION]:%s", e)
            raise error.DatabaseError('Connection problem!', e)

    # Create table users
    def create_table_users(self):
        smsgwglobals.dblogger.info("SQLite: Create table 'users'")
        query = ("CREATE TABLE IF NOT EXISTS users (" +
                 "user TEXT PRIMARY KEY UNIQUE, " +
                 "password TEXT, " +
                 "salt TEXT, " +
                 "changed TIMESTAMP)")
        self.__cur.execute(query)

    # Create table and index for table sms
    def create_table_sms(self):
        smsgwglobals.dblogger.info("SQLite: Create table 'sms'")
        # if smsid is not insertet it is automatically set to a free number
        query = ("CREATE TABLE IF NOT EXISTS sms (" +
                 "smsid TEXT PRIMARY KEY, " +
                 "modemid TEXT, " +
                 "imsi TEXT, " +
                 "targetnr TEXT, " +
                 "content TEXT, " +
                 "priority INTEGER, " +
                 "appid TEXT, " +
                 "sourceip TEXT, " +
                 "xforwardedfor TEXT, " +
                 "smsintime TIMESTAMP, " +
                 "status INTEGER, " +
                 "statustime TIMESTAMP)"
                 )
        self.__cur.execute(query)

        # index sms_status_modemid
        query = ("CREATE INDEX IF NOT EXISTS sms_status_modemid " +
                 "ON sms (status, modemid)"
                 )
        self.__cur.execute(query)

    # Create table stats
    def create_table_stats(self):
        smsgwglobals.dblogger.info("SQLite: Create table 'stats'")
        query = ("CREATE TABLE IF NOT EXISTS stats (" +
                 "type TEXT PRIMARY KEY UNIQUE, " +
                 "lasttimestamp TIMESTAMP)")
        self.__cur.execute(query)

    # Insert or replaces a stats timestamp data
    def write_statstimestamp(self, timestamp, intype='SUC_SMS_STATS'):
        """Insert or replace a stats entry timestamp
        """
        query = ("INSERT OR REPLACE INTO stats " +
                 "(type, lasttimestamp) " +
                 "VALUES (?, ?) ")
        # set changed timestamp to utcnow if not set

        try:
            smsgwglobals.dblogger.debug("SQLite: Write into stats" +
                                        " :intype: " + str(intype) +
                                        " :lasttimestamp: " + str(timestamp)
                                        )
            self.__cur.execute(query, (intype, timestamp))
            self.__con.commit()
            smsgwglobals.dblogger.debug("SQLite: Insert done!")

        except Exception as e:
            smsgwglobals.dblogger.critical("SQLite: " + query +
                                           " failed! [EXCEPTION]:%s", e)
            raise error.DatabaseError("Unable to INSERT stats! ", e)

    # Insert or replaces a users data
    def write_users(self, user, password, salt, changed=None):
        """Insert or replace a users entry
        Attributes: user ... text-the primary key - unique
        password ... text-password
        salt ... text-salt
        changed ... datetime.utcnow-when changed
        """
        query = ("INSERT OR REPLACE INTO users " +
                 "(user, password, salt, changed) " +
                 "VALUES (?, ?, ?, ?) ")
        # set changed timestamp to utcnow if not set
        if changed is None:
            changed = datetime.utcnow()

        try:
            smsgwglobals.dblogger.debug("SQLite: Write into users" +
                                        " :user: " + user +
                                        " :password-len: " +
                                        str(len(password)) +
                                        " :salt-len: " + str(len(salt)) +
                                        " :changed: " + str(changed)
                                        )
            self.__cur.execute(query, (user, password, salt, changed))
            self.__con.commit()
            smsgwglobals.dblogger.debug("SQLite: Insert done!")

        except Exception as e:
            smsgwglobals.dblogger.critical("SQLite: " + query +
                                           " failed! [EXCEPTION]:%s", e)
            raise error.DatabaseError("Unable to INSERT user! ", e)

    # Insert sms
    def insert_sms(self, modemid='00431234', imsi='1234567890', targetnr='+431234',
                   content='♠♣♥♦Test', priority=1, appid='demo',
                   sourceip='127.0.0.1', xforwardedfor='172.0.0.1',
                   smsintime=None, status=0, statustime=None, smsid=None):
        """Insert a fresh SMS out of WIS
        Attributes: modemid ... string-countryexitcode+number (0043664123..)
        imsi ... string-no SIM card IMSI
        targetnr ... string-no country exit code (+436761234..)
        content ... string-message
        prioirty ... int-0 low, 1 middle, 2 high
        appid ... sting (uuid) for consumer
        sourceip ... string with ip (172.0.0.1)
        xforwaredfor ... stirng with client ip
        smsintime ... datetime.utcnow()
        status ... int-0 new, ???
        statustime ... datetime.utcnow()
        """
        # check if smsid is empty string or None
        if smsid is None:
            smsid = str(uuid.uuid1())
        if not smsid:
            smsid = str(uuid.uuid1())

        now = datetime.utcnow()
        if smsintime is None:
            smsintime = now
            if statustime is None:
                statustime = now

        query = ("INSERT INTO sms " +
                 "(smsid, modemid, imsi, targetnr, content, priority, " +
                 "appid, sourceip, xforwardedfor, smsintime, " +
                 "status, statustime) " +
                 "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)" +
                 "ON CONFLICT(smsid) DO UPDATE SET " +
                 "modemid=excluded.modemid, imsi=excluded.imsi, statustime=excluded.statustime, status=excluded.status")

        try:
            smsgwglobals.dblogger.debug("SQLite: Insert SMS" +
                                        " :smsid: " + smsid +
                                        " :imsi: " + imsi +
                                        " :modemid: " + modemid +
                                        " :targetnr: " + targetnr +
                                        " :content: " + content +
                                        " :priority: " + str(priority) +
                                        " :appid: " + appid +
                                        " :sourceip: " + sourceip +
                                        " :xforwardedfor: " + xforwardedfor +
                                        " :smsintime: " + str(smsintime) +
                                        " :status: " + str(status) +
                                        " :statustime: " + str(statustime)
                                        )
            self.__con.execute(query, (smsid, modemid, imsi, targetnr,
                                       content, priority,
                                       appid, sourceip, xforwardedfor,
                                       smsintime, status, statustime))
            self.__con.commit()
            smsgwglobals.dblogger.debug("SQLite: Insert done!")

        except Exception as e:
            smsgwglobals.dblogger.critical("SQLite: " + query +
                                           " failed! [EXCEPTION]:%s", e)
            raise error.DatabaseError("Unable to INSERT sms! ", e)

    # update sms (input is a list)
    def update_sms(self, smslist=[]):
        """Updates Sms entries out of a list to reflect the new values
        all columns of sms have to be set!
        Attributes: smslsit ... list of sms in dictionary structure
        (see read_sms)
        """
        smsgwglobals.dblogger.debug("SQLite: Will update "
                                    + str(len(smslist)) + "sms.")
        # for each sms in the list
        for sms in smslist:
            smsgwglobals.dblogger.debug("SQLite: Update SMS: " + str(sms))
            query = ("UPDATE sms SET " +
                     "modemid = ?, " +
                     "imsi = ?, " +
                     "targetnr = ?, " +
                     "content = ?, " +
                     "priority = ?, " +
                     "appid = ?, " +
                     "sourceip = ?, " +
                     "xforwardedfor = ?, " +
                     "smsintime = ?, " +
                     "status = ?, " +
                     "statustime = ? " +
                     "WHERE smsid = ?"
                     )
            try:
                self.__con.execute(query, (sms['modemid'], sms['imsi'], sms['targetnr'],
                                           sms['content'], sms['priority'],
                                           sms['appid'], sms['sourceip'],
                                           sms['xforwardedfor'],
                                           sms['smsintime'], sms['status'],
                                           sms['statustime'], sms['smsid']))
                self.__con.commit()
                smsgwglobals.dblogger.debug("SQLite: Update for smsid: " +
                                            str(sms['smsid']) + " done!")

            except Exception as e:
                smsgwglobals.dblogger.critical("SQLite: " + query +
                                               " failed! [EXCEPTION]:%s", e)
                raise error.DatabaseError("Unable to UPDATE sms! ", e)

    # Merge userlist with userlist out of db
    def merge_users(self, userlist=[]):
        """ Merges user entries from database with those given in userlist
        older values are replaced and new ones are inserted on both sites
        Attributes: userlist ... list of sms in dictionary structure
        (see read_users)
        Return: new userlist ... list of merged users out of DB
        """
        # read db users
        dbuserlist = self.read_users()
        smsgwglobals.dblogger.debug("SQLite: Will merge " + str(len(userlist)) +
                                    " given user with " + str(len(dbuserlist)) +
                                    " user from db.")

        # iterate userlist and update form db if entries there newer
        mergeduserlist = []
        for user in userlist:
            smsgwglobals.dblogger.debug("SQLite: Now on user: " + user['user'])

            for dbuser in dbuserlist:
                if user['user'] == dbuser['user'] and \
                        user['changed'] < dbuser['changed']:
                    smsgwglobals.dblogger.debug("SQLite: User " +
                                                dbuser['user'] +
                                                " in database is newer!")
                    user = dbuser

            # add entry to mergeduserlist
            mergeduserlist.append(user)

        # insert/replace mergeduserlist to db
        for user in mergeduserlist:
            self.write_users(user['user'], user['password'], user['salt'],
                             user['changed'])

        # return full user list out of db
        return self.read_users()

    # Delete one user entry
    def delete_one_user(self, user):
        smsgwglobals.dblogger.debug("SQlite: Deleting user entry for user: " +
                                    user)
        query = ("DELETE FROM users " +
                 "WHERE user = ?")
        try:
            self.__con.execute(query, [user])
            self.__con.commit()

            smsgwglobals.dblogger.debug("SQLite: User: " + user +
                                        " deleted!")
        except Exception as e:
            smsgwglobals.dblogger.critical("SQLite: " + query +
                                           " failed! [EXCEPTION]:%s", e)
            raise error.DatabaseError("Unable to DELETE from users! ", e)

    # Delete UNITTEST sms
    def delete_unittest_sms(self, modemid):
        smsgwglobals.dblogger.debug("SQLite: Deleting" +
                                    " unittest sms for :modemid: " +
                                    modemid)
        query = ("DELETE FROM sms " +
                 "WHERE modemid = ?")
        try:
            result = self.__con.execute(query, [modemid])
            count = result.rowcount
            self.__con.commit()

            smsgwglobals.dblogger.debug("SQLite: " + str(count) +
                                        " sms for modemid: " +
                                        modemid + " deleted!")
        except Exception as e:
            smsgwglobals.dblogger.critical("SQLite: " + query +
                                           " failed! [EXCEPTION]:%s", e)
            raise error.DatabaseError("Unable to DELETE sms! ", e)

    # Delete SMS older than x seconds (=400 days)
    def delete_old_sms(self, secs=34560000):
        if secs is None:
            secs = 34560000
        days = int(secs)/60/60/24
        smsgwglobals.dblogger.debug("SQLite: Deleting sms older than " +
                                    str(secs) + " sec. (" +
                                    str(days) + " days).")
        now = datetime.utcnow()
        ts = now - timedelta(seconds=int(secs))
        smsgwglobals.dblogger.info("SQLite: Deleting sms created before " +
                                   str(ts) + "...")

        query = ("DELETE FROM sms " +
                 "WHERE smsintime < ?"
                 )
        try:
            result = self.__con.execute(query, [ts])
            count = result.rowcount
            self.__con.commit()

            smsgwglobals.dblogger.info("SQLite: " + str(count) +
                                       " sms before: " +
                                       str(ts) + " deleted!")
        except Exception as e:
            smsgwglobals.dblogger.critical("SQLite: " + query +
                                           " failed! [EXCEPTION]:%s", e)
            raise error.DatabaseError("Unable to DELETE sms! ", e)

    # Read stats timestamp
    def read_statstimestamp(self, intype='SUC_SMS_STATS'):
        smsgwglobals.dblogger.debug("SQLite: Read stats " +
                                    " :type: " + str(intype)
                                    )
        query = ("SELECT " +
                 "type, " +
                 "lasttimestamp " +
                 "FROM stats " +
                 "WHERE type = ?")
        try:
            result = self.__cur.execute(query, [intype])
        except Exception as e:
            smsgwglobals.dblogger.critical("SQLite: " + query +
                                           " failed! [EXCEPTION]:%s", e)
            raise error.DatabaseError("Unable to SELECT FROM stats! ", e)
        else:
            # convert rows to dict
            stats = [dict(row) for row in result]
            smsgwglobals.dblogger.debug("SQLite: " + str(len(stats)) +
                                        " user selected.")
            return stats

    # Read users
    def read_users(self, user=None):
        smsgwglobals.dblogger.debug("SQLite: Read users" +
                                    " :user: " + str(user)
                                    )
        query = ("SELECT " +
                 "user, " +
                 "password, " +
                 "salt, " +
                 "changed " +
                 "FROM users")
        try:
            if user is None:
                result = self.__cur.execute(query)
            else:
                # user is set
                query = query + " WHERE user = ?"
                result = self.__cur.execute(query, [user])
        except Exception as e:
            smsgwglobals.dblogger.critical("SQLite: " + query +
                                           " failed! [EXCEPTION]:%s", e)
            raise error.DatabaseError("Unable to SELECT FROM users! ", e)
        else:
            # convert rows to dict
            user = [dict(row) for row in result]
            smsgwglobals.dblogger.debug("SQLite: " + str(len(user)) +
                                        " user selected.")
            return user

    # Read sms
    def read_sms_date(self, date=None):

        if date is None:
            date = datetime.utcnow().date().strftime("%Y-%m-%d") + "%"

        smsgwglobals.dblogger.debug("SQLite: Read SMS" +
                                    " :date: " + str(date))
        query = ("SELECT " +
                 "smsid, " +
                 "modemid, " +
                 "imsi, " +
                 "targetnr, " +
                 "content, " +
                 "priority, " +
                 "appid, " +
                 "sourceip, " +
                 "xforwardedfor, " +
                 "smsintime, " +
                 "status, " +
                 "statustime " +
                 "FROM sms ")
        try:
            query = query + "WHERE smsintime LIKE ?"
            result = self.__cur.execute(query, [date])
        except Exception as e:
            smsgwglobals.dblogger.critical("SQLite: " + query +
                                           " failed! [EXCEPTION]:%s", e)
            raise error.DatabaseError("Unable to SELECT FROM sms! ", e)

        sms = [dict(row) for row in result]
        smsgwglobals.dblogger.debug("SQLite: " + str(len(sms)) +
                                    " SMS selected.")
        return sms

    # Read sms
    def read_sms(self, status=None, modemid=None, smsid=None):

        smsgwglobals.dblogger.debug("SQLite: Read SMS" +
                                    " :modemid: " + str(modemid) +
                                    " :status: " + str(status) +
                                    " :smsid: " + str(smsid)
                                    )
        query = ("SELECT " +
                 "smsid, " +
                 "modemid, " +
                 "imsi, " +
                 "targetnr, " +
                 "content, " +
                 "priority, " +
                 "appid, " +
                 "sourceip, " +
                 "xforwardedfor, " +
                 "smsintime, " +
                 "status, " +
                 "statustime " +
                 "FROM sms ")

        orderby = " ORDER BY priority DESC, smsintime ASC;"
        try:
            if smsid is not None:
                query = query + "WHERE smsid = ?" + orderby
                result = self.__cur.execute(query, [smsid])
            elif modemid is None:
                if status is None:
                    query = query + orderby
                    result = self.__cur.execute(query)
                else:
                    # status only
                    query = query + "WHERE status = ?" + orderby
                    result = self.__cur.execute(query, [status])
            else:
                if status is None:
                    # modemid only
                    query = query + "WHERE modemid = ?" + orderby
                    result = self.__cur.execute(query, [modemid])
                else:
                    # status and modemid
                    query = query + "WHERE status = ? AND modemid = ?" + orderby
                    result = self.__cur.execute(query, (status, modemid))
        except Exception as e:
            smsgwglobals.dblogger.critical("SQLite: " + query +
                                           " failed! [EXCEPTION]:%s", e)
            raise error.DatabaseError("Unable to SELECT FROM sms! ", e)
        else:
            sms = [dict(row) for row in result]
            smsgwglobals.dblogger.debug("SQLite: " + str(len(sms)) +
                                        " SMS selected.")
            return sms

    # Read successfuly sent sms for stats
    def read_sucsmsstats(self, timestamp=None):

        smsgwglobals.dblogger.debug("SQLite: Read SMS stats" +
                                    " with :timestamp: gt " + str(timestamp)
                                    )
        query = ("SELECT " +
                 "smsid, " +
                 "modemid, " +
                 "imsi, " +
                 "targetnr, " +
                 "content, " +
                 "priority, " +
                 "appid, " +
                 "sourceip, " +
                 "xforwardedfor, " +
                 "smsintime, " +
                 "status, " +
                 "statustime " +
                 "FROM sms " +
                 "WHERE (status = 4 OR status = 5)"
                 )
        # status 4 or 5 -> successfully send sms

        orderby = " ORDER BY statustime ASC;"
        try:
            if timestamp is None:
                query = query + orderby
                result = self.__cur.execute(query)
            else:
                # greater than timestamp
                query = query + "AND statustime > ?" + orderby
                result = self.__cur.execute(query, [timestamp])
        except Exception as e:
            smsgwglobals.dblogger.critical("SQLite: " + query +
                                           " failed! [EXCEPTION]:%s", e)
            raise error.DatabaseError("Unable to SELECT stats FROM sms! ", e)
        else:
            sms = [dict(row) for row in result]
            smsgwglobals.dblogger.debug("SQLite: " + str(len(sms)) +
                                        " SMS for stats selected.")
            return sms

    # Read number of sms sent for last 24h per SIM IMSI in UKRAINE timezone
    def read_sms_count_by_imsi(self, imsi):

        utc_timezone = pytz.timezone("UTC")
        ua_timezone = pytz.timezone("Europe/Kiev")

        today = datetime.utcnow().astimezone(ua_timezone).date()
        start = datetime(today.year, today.month, today.day, tzinfo=ua_timezone).astimezone(utc_timezone)
        end = start + timedelta(1)

        smsgwglobals.dblogger.debug("SQLite: Read SMS stats" +
                                    " with :imsi: " + imsi +
                                    " for last 24 hours"
                                    )
        query = ("SELECT count(*) " +
                 "FROM sms " +
                 "WHERE imsi = ? " +
                 "AND statustime BETWEEN ? AND ?"
                 )
        try:
            result = self.__cur.execute(query, [ imsi, start, end])
        except Exception as e:
            smsgwglobals.dblogger.critical("SQLite: " + query +
                                           " failed! [EXCEPTION]:%s", e)
            raise error.DatabaseError("Unable to SELECT sms_count FROM sms! ", e)
        else:
            sms_count = result.fetchone()[0]
            smsgwglobals.dblogger.debug("SQLite: Sent " + str(sms_count) +
                                        " SMS for IMSI " + imsi + ".")
            return sms_count


def main():
    db = Database()

    print("List SMS:")
    for sms in db.read_sms():
        print(sms)

    # TODO delete
    """
    print("List routes:")
    for route in db.read_routing():
        print(route)
    """

    print("List user:")
    for user in db.read_users():
        print(user)


def printsms(allsms):
    for sms in allsms:
        # print(sms)
        print(sms['targetnr'] + " : " + sms['content'] +
              " : " + str(sms['status']))

if __name__ == "__main__":
    main()
