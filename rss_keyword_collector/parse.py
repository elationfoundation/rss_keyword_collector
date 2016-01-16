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

from collections import namedtuple
from datetime import date, datetime
import feedparser
import md5
from os import environ, path
from urlparse import urlparse
from bs4 import BeautifulSoup, Comment
import re
from uuid import uuid4
import codecs
from polyglot.text import Text

from twisted.application import service
from twisted.enterprise import adbapi
from twisted.internet import task, protocol
from twisted.internet.defer import inlineCallbacks
from twisted.web.client import getPage


class ParserService(service.Service):

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
        self.entry_parser = EntryParser(self.dbpool)
        # Every [interval] run the collector
        self.call = task.LoopingCall(self.startService).start(self.interval)

    def startService(self):
        print("Starting Entry Parser")
        self.entry_parser.run()

    def stopService(self):
        # stop the reactor.call
        if self.call:
            self.call.cancel()


def get_netloc(url):
    """ Creates an escaped netloc from a supplied URL.

    Netloc will be escaped by replacing periods with underscores and
    downcaseing the string.

    Args:
        url (str): A URL that follows the general URL pattern.
                   e.g. "scheme://netloc/path;parameters?query#fragment".

    """
    parsed = urlparse(url)
    raw_netloc = ""
    # If url does not have a scheme specified XXX://
    # then parse the netloc out of the path
    # https://docs.python.org/3.0/library/urllib.parse.html#urllib.parse.urlparse
    if parsed.netloc != "":
        raw_netloc = parsed.netloc
    else:
        raw_netloc = parsed.path.split("/")[0]


    if raw_netloc == "":
        raise ValueError("{0} is not parsable.".format(url) +
                         "Please provide a url that follows the format " +
                         "scheme://netloc/path")
    raw_netloc = raw_netloc.replace(".", "_").lower()
    return raw_netloc

class EntryParser(protocol.ClientFactory):
    def __init__(self, dbconn):
        self.dbpool = dbconn
        self.entries = {}
        self.keyword_dir = environ['RKC_KEYWORD_PATH']


    def parse(self, feed):
        pass

    @inlineCallbacks
    def run(self):
        entries = yield self.get_unparsed_entries()
        for item in entries:
            entry = namedtuple("entry", ["page", "url", "lang"])
            entry.url = item[0]
            # Download the entries url
            entry.page = yield getPage(entry.url)

            # Run text extraction
            text_extractor = ExtractText(entry.url, entry.page)
            page_text = text_extractor.text
            entry.lang = text_extractor.lang

            # Get terms from text
            terms = ExtractTerms(page_text, entry.lang).terms
            UUID = uuid4().hex

            if terms != []:
                # Write the keyword list to file
                self.write_keyword_file(terms, UUID, entry.url)

                # Update Keywords
                kdb = yield self.update_keywords(terms)

            # Update entries
            edb = yield self.update_entry(entry.url, UUID)


    def write_keyword_file(self, keywords, keyword_hash, url):
        keyword_path = path.join(self.keyword_dir, keyword_hash)
        with codecs.open(keyword_path, mode="w+", encoding="utf-8") as keyword_file:
            keyword_file.write(u"# " + url + u"\n\n")
            keyword_file.write(u"# " + str(datetime.now()) + u"\n")
            for keyword in keywords:
                keyword_file.write(keyword + u"\n")

    def update_keywords(self, keywords):
        """Update entry with id & location of scraped keywords."""
        insert_string = "INSERT INTO terms "
        value_string = "(term, censored) VALUES "
        term_string = ""
        conflict_string = " ON CONFLICT (term) DO NOTHING"
        _first = True
        for keyword in keywords:
            if _first:
                # Double up single quotes to excape in sql
                term_string += "('%s', false)" % keyword.replace("'","''")
                _first = False
            else:
                #print(keyword)
                term_string += ", ('%s', false)" % keyword.replace("'","''")

        sql_statement = insert_string + value_string + term_string + conflict_string

        #print(sql_statement)

        db = self.dbpool.runOperation(sql_statement)
        return db

    def update_entry(self, url, keyword_hash):
        """Update entry with id & location of scraped keywords."""
        db = self.dbpool.runOperation("UPDATE entries "
                                      "SET term_file = %s, "
                                      "scraped = true "
                                      "WHERE url = %s",
                                      (keyword_hash, url))
        return db

    def get_unparsed_entries(self):
        return self.dbpool.runQuery("SELECT url FROM entries "
                                    "WHERE scraped = false")

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
        return self.dbpool.runQuery("SELECT url, language FROM feeds")

    def update_entries(self, page, feed_url):
        feed = feedparser.parse(page)

        channel_items = ["language"]
        entry_items = ["title", "link", "description",
                       "author", "category", "pubDate",
                       "guid", "comments"]
        entries = {}

        for entry in feed.entries:
            entries[entry["title"]] = {item: entry.get(item, "") for item in entry_items}
            for item in channel_items:
                entries[entry["title"]][item] = feed.feed.get(item, "")

        db = self.dbpool.runOperation("INSERT INTO entries "
                                      "(url, language, description, "
                                      "title, published, scraped, feed) "
                                      "VALUES "
                                      "(%s, %s, %s, %s, %s, 'false', %s) "
                                      "ON CONFLICT (url) DO NOTHING ",
                                      (entries.get('link', ""),
                                       entries.get('language', ""),
                                       entries.get('description', ""),
                                       entries.get('title', ""),
                                       entries.get('pubDate', date.today()),
                                       feed_url))
        return db





class ExtractText(object):

    def __init__(self, url, raw):
        self.url = url
        self.raw = raw
        results = self.extract()
        self.text = results[0]
        self.title = results[1]
        self.lang = results[2]

    def extract(self):
        """ Extracts the raw text from a URL using the appropriate extractor.

        This function retreives a website text extractor function of this
        object that corresponds to the following pattern where NETLOC
        corresponds to the escaped netloc of a url.
            def extractor_NETLOC(self, url):

        Returns:
            Tuple containing two string objects: (text, title).
            Where:
                text (str) The raw text of the page.
                title (str) An appropriate title for the pages content.
        """
        netloc = get_netloc(self.url)
        #print("Attempting to retreive extractor for {0}".format(netloc))
        extractor = getattr(self, 'extractor_%s' % (netloc,), None)

        if extractor is None: # no such domain extractor
            text, title, lang = self.extractor_generic(self.raw)
            return (text, title, lang)
        else:
            text, title, lang = extractor(self.raw)
            return (text, title, lang)

    def extractor_generic(self, raw):
        """ Generic website text extractor for unknown and undefined websites.

        Returns:
            Two string objects: text, title
            Where:
                text (str) The raw text of the page.
                title (str) An appropriate title for the pages content.
        """
        html_obj = BeautifulSoup(raw, 'lxml')
        html_title = html_obj.title.string.strip()
        html_lang = html_obj.html['lang']
        # Remove all comment elements
        comments = html_obj.findAll(text=lambda text:isinstance(text, Comment))
        [comment.extract() for comment in comments]
        #print(html_obj)

        # print and reparse html or we get an error for some reason
        html_obj = BeautifulSoup(html_obj.prettify(), 'lxml')

        # remove all script and style elements
        for unwanted in html_obj(["script", "style"]):
            unwanted.extract()

        # print and reparse html or we get an error for some reason
        html_obj = BeautifulSoup(html_obj.prettify(), 'lxml')

        # get the text
        text = html_obj.get_text()

        # break into lines and remove leading and trailing space on each
        lines = (line.strip() for line in text.splitlines())
        # break multi-headlines into a line each
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        # drop blank lines
        text = '\n'.join(chunk for chunk in chunks if chunk)
        return text, html_obj.title.string, html_lang


    def extractor_www_bbc_com(self, raw):
        """ Text extractor for BBC news articles.

        Returns:
            Two string objects: text, title
            Where:
                text (str) The raw text of the page.
                title (str) An appropriate title for the pages content.
        """
        html_obj = BeautifulSoup(raw, 'lxml')
        try:
            story_title = html_obj.find("h1", class_="story-body__h1").get_text()
        except AttributeError:
            story_title = html_obj.find("title").get_text()
        html_lang = html_obj.html['lang']
        article_contents = []
        try:
            for section in html_obj.find("div", "story-body__inner").descendants:
                if section.name == "p":
                    article_contents.append(section.get_text())
            if article_contents != []:
                article_text = "\n".join(article_contents)
            else:
                raise ValueError("No body text found in article.")
        except (AttributeError, ValueError):
            article_text = ""
            print(u"No body text found in article {0}".format(story_title))

        return article_text, story_title, html_lang

class ExtractTerms(object):

    def __init__(self, raw, language="english", remove_stopwords=False):
        """

        Args:

        language (str): What language should the keyword extractor treat the keywords as? [Each language used requires it's own
        without_stopwords (bool): Should the keyword extractor remove stop words from the keywords that it identifies? (True, False)

        """
        self.raw = raw
        self.language = str(language)
        self.remove_stopwords = remove_stopwords
        self.keywords, self.entities = None, None
        self.extract()

    def extract(self):
        #print("Attempting to retreive {0} language keyword extractor".format(self.language))
        extractor = getattr(self, 'extractor_%s' % (self.language,), None)

        if extractor is None:
            #print("{0} language extractor not found. ".format(self.language) +
            #         "Using generic word extractor without stopwords.")
            self.keywords, self.entities = self.extractor_generic(self.raw)
        else:
            print("Using {0} language extractor.".format(self.language))
            self.keywords, self.entities = extractor(self.raw)

    @property
    def terms(self):
        return self.keywords + self.entities

    def extractor_generic(self, raw):
        from nltk import word_tokenize
        # Keywords
        tokens = word_tokenize(raw)
        lowered = [x.lower() for x in tokens]
        # Remove any special characters
        unicode_non_words = re.compile('\W+', re.UNICODE)
        plain = [re.sub(unicode_non_words, '', x) for x in lowered]
        unique_words = set(plain)
        no_blanks = [x for x in unique_words if len(x) > 1]
        entities = self.get_entities(raw)
        return no_blanks, entities

    def extractor_en(self, raw):
        from nltk import word_tokenize
        from nltk.corpus import stopwords

        tokens = word_tokenize(raw)
        lowered = [x.lower() for x in tokens]
        # Remove any special characters
        unicode_non_words = re.compile('\W+', re.UNICODE)
        plain = [re.sub(unicode_non_words, '', x) for x in lowered]
        unique_words = set(plain)

        if self.remove_stopwords == True:
            stop_words = stopwords.words('english')
            words_no_stop = [x for x in unique_words if x not in stop_words]
            unique_words = words_no_stop

        no_blanks = [x for x in unique_words if len(x) > 1]
        entities = self.get_entities(raw)
        return no_blanks, entities

    def extractor_fa(self, raw):
        """
        Persian lanague keyword extractor.

        Args:
        raw (str): Raw text to be split into keywords.

        Notes:
            Requires Hazm (https://github.com/sobhe/hazm)

            Stop-Words for persian need to be installed
                in the NLTK folder
                /home/$HOME/nltk_data/corpora/stopwords/persian

            Stop-Words I use for Persian:
                https://github.com/kharazi/persian-stopwords.git
        """
        from hazm import word_tokenize
        from nltk.corpus import stopwords

        tokens = word_tokenize(raw)
        lowered = [x.lower() for x in tokens]
        # Remove any special characters
        unicode_non_words = re.compile('\W+', re.UNICODE)
        plain = [re.sub(unicode_non_words, '', x) for x in lowered]
        unique_words = set(plain)

        if self.remove_stopwords == True:
            stop_words = stopwords.words('persian')
            words_no_stop = [x for x in unique_words if x not in stop_words]
            unique_words = words_no_stop

        no_blanks = [x for x in unique_words if len(x) > 1]
        entities = self.get_entities(raw)
        return no_blanks, entities

    @classmethod
    def get_entities(self, raw, min_text_length=50):
        if len(raw) < min_text_length:
            return []

        text = Text(raw)
        entities = []
        for ent in text.entities:
            entities.append(u" ".join(ent))
        return entities
