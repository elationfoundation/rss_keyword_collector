from feed import FeedService
from parse import ParserService
from reporting import ReportingService
from collections import namedtuple
from os import environ
from twisted.application import service

# Set default variables
feed_db = namedtuple("feed_db", ["dbmodule", "name", "user", "password", "host", "port"])
feed_db.dbmodule = "psycopg2"
feed_db.name = environ['RKC_DB_NAME']
feed_db.user = environ['RKC_DB_USER']
feed_db.password = environ['RKC_DB_PASS']
feed_db.host = environ['RKC_DB_HOST']
feed_db.port = environ['RKC_DB_PORT']


# Create a MultiService, and hook up services to it as children.
keywordCollector = service.MultiService()


feedServ = FeedService(feed_db).setServiceParent(keywordCollector)
parseServ = ParserService(feed_db).setServiceParent(keywordCollector)
writerServ = ReportingService(feed_db).setServiceParent(keywordCollector)


# Create an application as normal
application = service.Application("KeywordCollector")

# Connect our MultiService to the application, just like a normal service.
keywordCollector.setServiceParent(application)
