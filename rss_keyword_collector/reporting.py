#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# This file is part of rss_keyword_parser, a simple term extractor from rss feeds.
# Copyright © 2015 seamus tuohy, <stuohy@internews.org>
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option)
# any later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE. See the included LICENSE file for details.

from os import environ, mkdir, path
from datetime import datetime
import codecs

from twisted.application import service
from twisted.enterprise import adbapi
from twisted.internet import task, reactor, protocol, defer
from twisted.internet.defer import inlineCallbacks
from twisted.web.client import getPage
from twisted.python import log


class ReportingService(service.Service):

    def __init__(self, feed_db, interval=600):
        """
        Args:
        feed (named_tuple):
            dbmodule: an import string to use to obtain a DB-API compatible module (e.g. 'pyPgSQL.PgSQL')
            name: The name of the database to connect to within the module.
            user: The username to log in to the database with.
            password: The users password to the database.
            host: The host where the database can be reached
            port: The port used to access the database
        interval (int): Number of minutes between feed queries (rounded to nearest minute).
        """
        self.interval = int(interval / 60)
        if self.interval <= 60:
            self.interval = 60
        self.dbpool = adbapi.ConnectionPool(feed_db.dbmodule,
                                            host = feed_db.host,
                                            port = feed_db.port,
                                            database = feed_db.name,
                                            user = feed_db.user,
                                            password = feed_db.password,
                                            cp_noisy = True)
        # Create a feed collector
        self.report_writer = ReporterWriter(self.dbpool)
        # Every [interval] run the collector
        self.call = task.LoopingCall(self.startService).start(self.interval)

    def startService(self):
        print("Starting Reporting Writer")
        self.report_writer.update_files()

    def stopService(self):
       # stop the reactor.call
       if self.call:
           self.call.cancel()

class ReporterWriter(protocol.ClientFactory):

    def __init__(self, dbconn):
        self.dbpool = dbconn
        # Create output_dir if it does not exist
        self.output_dir = path.abspath(environ['RKC_REPORT_PATH'])
        if not path.exists(self.output_dir):
            mkdir(self.output_dir)

    def _write_term_file(self, keywords, state):
        if keywords == []:
            return
        keyword_path = path.join(self.output_dir, "{0}.report".format(state))
        with codecs.open(keyword_path, mode="w+", encoding="utf-8") as keyword_file:
            keyword_file.write(u"# " + str(datetime.now()) + u"\n")
            for keyword in keywords:
                kw_newline = keyword[0].decode("utf-8") + u"\n"
                keyword_file.write(kw_newline)

    @inlineCallbacks
    def update_files(self):
        for state in ["censored", "uncensored"]:
            yield self.update(state)

    def update(self, state):
        terms = self._get_terms(state)
        terms.addCallback(self._write_term_file, state=state)

    def _get_terms(self, state):
        query = self._get_query(state)
        qwhere = "WHERE {0}".format(query)
        return self.dbpool.runQuery("SELECT term FROM terms {0}".format(qwhere))

    @staticmethod
    def _get_query(state):
        queries = {"censored" : "censored = true",
                   "uncensored" : "censored = false"}
        try:
            return queries[state]
        except KeyError:
            raise ValueError("{0} is not a valid query".format(query))


    def set_censored(self, term, state=True):
        if state == True:
            censored = "true"
        elif state == False:
            censored = "false"
        else:
            raise ValueError("state must be a bool value")

        db = self.dbpool.runOperation("UPDATE terms "
                                      "SET censored = %s, "
                                      "WHERE term = %s",
                                      (censored, term))
        return db
