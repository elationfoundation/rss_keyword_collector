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

from datetime import datetime
import feedparser

from twisted.application import service
from twisted.enterprise import adbapi
from twisted.internet import task, protocol
from twisted.internet.defer import inlineCallbacks
from twisted.web.client import getPage


class FeedService(service.Service):

    def __init__(self, feed_db, interval=30):
        """
        Args:
        feed (named_tuple):
            dbmodule: an import string to use to obtain a DB-API compatible module (e.g. 'pyPgSQL.PgSQL')
            name: The name of the database to connect to within the module
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
        self.feed_collector = FeedCollector(self.dbpool)
        # Every [interval] run the collector
        self.call = task.LoopingCall(self.startService).start(self.interval)

    def startService(self):
        print("Starting Feed Collector")
        self.feed_collector.run()

    def stopService(self):
        # stop the reactor.call
        if self.call:
            self.call.cancel()

class FeedCollector(protocol.ClientFactory):
    def __init__(self, dbconn):
        self.dbpool = dbconn
        self.feeds = set()

    @inlineCallbacks
    def run(self):
        feeds = yield self.get_feed_list()
        #print(feeds)
        for url in feeds:
            page = yield getPage(url[0])
            entry_feeds = self.parse_entries(page, url)
            for entry_name, entry_items in entry_feeds.iteritems():
                #print(entry_name)
                entry = yield self.update_entries(entry_items)


    def query_feeds(self):
        for feed in self.feeds:
            page = getPage(feed)
            page.addCallback(self.update_feed, url=feed)
            yield page, feed

    def update_feed(self, page, url):
        feed = feedparser.parse(page)
        channel_info = {}
        channel_items = ["title", "description",
                         "language", "lastBuildDate",
                         "ttl", "pubDate", "copyright",
                         "webMaster", "managingEditor"]

        channel_info = {item: feed.feed.get(item, "") for item in channel_items}

        db = self.dbpool.runOperation("UPDATE feeds "
                                      "SET title = %s, "
                                      "language = %s, "
                                      "description = %s "
                                      "WHERE url = %s",
                                      (channel_info['title'],
                                       channel_info['language'],
                                       channel_info['description'],
                                       url))
        return db


    def get_feed_list(self):
        return self.dbpool.runQuery("SELECT url FROM feeds")

    def parse_entries(self, page, feed_url):
        feed = feedparser.parse(page)

        channel_items = ["language"]
        entry_items = ["title", "link", "description",
                       "author", "category", "guid", "comments"]

        entries = {}

        for entry in feed.entries:
            entries[entry["title"]] = {item: entry.get(item, "") for item in entry_items}
            entries[entry["title"]]["pubDate"] = entry.get("pubDate", datetime.now())
            entries[entry["title"]]["scraped"] = datetime.now()
            entries[entry["title"]]["url"] = feed_url

            # Enforcing the database string limits
            entries[entry["title"]]["description"] = entries[entry["title"]]["description"][0:1000]
            entries[entry["title"]]["url"] = entries[entry["title"]]["url"][0:512]
            entries[entry["title"]]["title"] = entries[entry["title"]]["title"][0:500]


            for item in channel_items:
                entries[entry["title"]][item] = feed.feed.get(item, "")
        return entries

    def update_entries(self, entry):
        #print("updating entries")
        # print(entry)
        db = self.dbpool.runOperation("INSERT INTO entries "
                                  "(url, language, description, "
                                      "title, published, scraped, feed) "
                                      "VALUES "
                                      "(%s, %s, %s, %s, %s, 'false', %s) "
                                      "ON CONFLICT (url) DO NOTHING ",
                                      (entry.get('link', ""),
                                       entry.get('language', ""),
                                       entry.get('description', ""),
                                       entry.get('title', ""),
                                       entry.get('pubDate', datetime.now()),
                                       entry.get('url', ""),))
        return db
