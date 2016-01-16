#!/bin/sh -e

# Edit the following to change the name of the database user that will be created:
APP_DB_USER=$RKC_DB_USER
APP_DB_PASS=$RKC_DB_PASS

# Edit the following to change the name of the database that is created (defaults to the user name)
APP_DB_NAME=$APP_DB_USER

# Edit the following to change the version of PostgreSQL that is installed
PG_VERSION=9.5

###########################################################
# Changes below this line are probably not necessary
###########################################################
print_db_usage () {
  echo "Your PostgreSQL database has been setup and can be accessed on your local machine on the forwarded port (default: 5432)"
  echo "  Host: localhost"
  echo "  Port: 5432"
  echo "  Database: $APP_DB_NAME"
  echo "  Username: $APP_DB_USER"
  echo "  Password: $APP_DB_PASS"
  echo ""
  echo "Admin access to postgres user via VM:"
  echo "  vagrant ssh"
  echo "  sudo su - postgres"
  echo ""
  echo "psql access to app database user via VM:"
  echo "  vagrant ssh"
  echo "  sudo su - postgres"
  echo "  PGUSER=$APP_DB_USER PGPASSWORD=$APP_DB_PASS psql -h localhost $APP_DB_NAME"
  echo ""
  echo "Env variable for application development:"
  echo "  DATABASE_URL=postgresql://$APP_DB_USER:$APP_DB_PASS@localhost:5432/$APP_DB_NAME"
  echo ""
  echo "Local command to access the database via psql:"
  echo "  PGUSER=$APP_DB_USER PGPASSWORD=$APP_DB_PASS psql -h localhost -p 5432 $APP_DB_NAME"
}

export DEBIAN_FRONTEND=noninteractive

PROVISIONED_ON=/etc/vm_provision_on_timestamp
if [ -f "$PROVISIONED_ON" ]
then
  echo "VM was already provisioned at: $(cat $PROVISIONED_ON)"
  echo "To run system updates manually login via 'vagrant ssh' and run 'apt-get update && apt-get upgrade'"
  echo ""
  print_db_usage
  exit
fi

PG_REPO_APT_SOURCE=/etc/apt/sources.list.d/pgdg.list
if [ ! -f "$PG_REPO_APT_SOURCE" ]
then
  # Add PG apt repo:
  echo "deb http://apt.postgresql.org/pub/repos/apt/ trusty-pgdg main" > "$PG_REPO_APT_SOURCE"

  # Add PGDG repo key:
  wget --quiet -O - https://apt.postgresql.org/pub/repos/apt/ACCC4CF8.asc | apt-key add -
fi

# Update package list and upgrade all packages
apt-get update
apt-get -y upgrade

apt-get -y install "postgresql-$PG_VERSION" "postgresql-contrib-$PG_VERSION" "postgresql-server-dev-$PG_VERSION"

pip install python-pgsql
pip install psycopg2

PG_CONF="/etc/postgresql/$PG_VERSION/main/postgresql.conf"
PG_HBA="/etc/postgresql/$PG_VERSION/main/pg_hba.conf"
PG_DIR="/var/lib/postgresql/$PG_VERSION/main"

# Edit postgresql.conf to change listen address to '*':
sed -i "s/#listen_addresses = 'localhost'/listen_addresses = '*'/" "$PG_CONF"

# Append to pg_hba.conf to add password auth:
echo "host    all             all             all                     md5" >> "$PG_HBA"

# Explicitly set default client_encoding
echo "client_encoding = utf8" >> "$PG_CONF"

# Restart so that all new config is loaded:
service postgresql restart

cat << EOF | su - postgres -c psql
-- Create the database user:
CREATE USER $APP_DB_USER WITH PASSWORD '$APP_DB_PASS';

-- Create the database:
CREATE DATABASE $APP_DB_NAME WITH OWNER=$APP_DB_USER
                                  LC_COLLATE='C'
                                  LC_CTYPE='C'
                                  ENCODING='UTF8'
                                  TEMPLATE=template0;
EOF

# Create the required database tables

cat << EOF | su - postgres -c psql
\connect $RKC_DB_NAME

DROP TABLE if exists feeds;
-- Create the feeds table
CREATE TABLE feeds (
        title varchar (500),
        language varchar (15),
        description varchar (1000),
        url varchar (500) PRIMARY KEY
);
GRANT ALL PRIVILEGES ON TABLE feeds TO $RKC_DB_USER;


DROP TABLE if exists entries;
-- Create the entries table
CREATE TABLE entries (
        title varchar (500) NOT NULL,
        language varchar (15),
        description varchar (1000),
        published timestamptz,
        scraped boolean NOT NULL,
        feed varchar (200) NOT NULL,
        url varchar (500) PRIMARY KEY,
        term_file varchar (36)
);
GRANT ALL PRIVILEGES ON TABLE entries TO $RKC_DB_USER;



DROP TABLE if exists terms;
-- Create the terms table
CREATE TABLE terms (
        term varchar (150) PRIMARY KEY,
        censored boolean
);
GRANT ALL PRIVILEGES ON TABLE terms TO $RKC_DB_USER;

DROP TABLE if exists censorship;
-- Create the censorship table
CREATE TABLE censorship (
        event varchar (36) PRIMARY KEY,
        term varchar (150) NOT NULL,
        censored_start timestamp NOT NULL,
        censored_end timestamp
);
GRANT ALL PRIVILEGES ON TABLE censorship TO $RKC_DB_USER;



-- CREATE TEST DATA
-- INSERT INTO feeds (url, title) VALUES ('http://seamustuohy.com/rss', 'seamus tuohy');
INSERT INTO feeds (url, title) VALUES ('http://www.bbc.com/persian/index.xml', 'BBC Persian');

EOF

# Tag the provision time:
date > "$PROVISIONED_ON"

echo "Successfully created PostgreSQL dev virtual machine."
echo ""
print_db_usage
