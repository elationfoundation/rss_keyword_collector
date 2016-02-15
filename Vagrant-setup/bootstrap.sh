#!/usr/bin/env bash

#!/usr/bin/env bash
#
# This file is part of rss-keyword-collector, a package that reads rss feeds and extracts keywords from them..
# Copyright © 2016 seamus tuohy, <s2e at seamustuohy.com>
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option)
# any later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE. See the included LICENSE file for details.

# Setup

#Bash should terminate in case a command or chain of command finishes with a non-zero exit status.
#Terminate the script in case an uninitialized variable is accessed.
#See: https://github.com/azet/community_bash_style_guide#style-conventions
set -e
set -u

# TODO remove DEBUGGING
set -x

# Read Only variables

#readonly PROG_DIR=$(readlink -m $(dirname $0))
#readonly readonly PROGNAME=$(basename )
#readonly PROGDIR=$(readlink -m $(dirname ))

readonly testing_user=vagrant
readonly testing_group=rsskeyword
readonly nltk_data_dir='/usr/lib/nltk_data'


main() {
    base_setup
    dependencies
    set_environment_vars
    setup_keyword_dir
    setup_permissions
}

set_environment_vars() {
    # Store testing systems config values in the environment
    echo "RKC_DB_NAME=$RKC_DB_NAME" >> /etc/environment
    echo "RKC_DB_USER=$RKC_DB_USER" >> /etc/environment
    echo "RKC_DB_PASS=$RKC_DB_PASS" >> /etc/environment
    echo "RKC_DB_HOST=$RKC_DB_HOST" >> /etc/environment
    echo "RKC_DB_PORT=$RKC_DB_PORT" >> /etc/environment
    echo "RKC_KEYWORD_PATH=$RKC_KEYWORD_PATH" >> /etc/environment
    echo "RKC_REPORT_PATH=$RKC_REPORT_PATH" >> /etc/environment
}

setup_permissions() {
    groupadd --force "$testing_group"
    id -u "$testing_user" &>/dev/null || useradd "$testing_user"
    usermod -a -G "$testing_group" "$testing_user"

    chown --recursive "$testing_user":"${testing_group}" "$RKC_KEYWORD_PATH"
    chmod --recursive g+rw "$RKC_KEYWORD_PATH"

    chown --recursive "$testing_user":"${testing_group}" "$RKC_REPORT_PATH"
    chmod --recursive g+rw "$RKC_REPORT_PATH"
}

setup_keyword_dir() {
    mkdir --parents "$RKC_KEYWORD_PATH"
    mkdir --parents "$RKC_REPORT_PATH"
}

base_setup() {
    apt-get update
}

dependencies() {
    #apt_install "python3"
    #apt_install "python3-pip"
    #apt_install "python3-dev"

    apt_install "python"
    apt_install "python-pip"
    apt_install "python-dev"
    # lxml requirements
    apt_install "libxml2-dev"
    apt_install "libxslt1-dev"
    apt_install "zlib1g-dev"
    apt_install "libssl-dev"

    # Required for polyglot
    apt_install "libicu-dev"
    apt_install "python-numpy"

    apt_install "git"

    #pip_install "hazm"
    #pip_install "beautifulsoup4"
    pip_install "feedparser"
    pip_install "twisted"
    pip_install "service_identity"
    pip_install "beautifulsoup4"
    pip_install "hazm"
    pip_install "lxml"
    pip_install "polyglot"

    # required for polyglot but not in pip requrements?
    pip_install "futures"

    # Faster better encoding detection
    pip_install "cchardet"

    #pip_three_install "hazm"
    #pip_three_install "beautifulsoup4"
    #pip_three_install "feedparser"
    #pip_three_install "twisted"
    #pip_three_install "python-pgsql"
    get_nltk_libraries
}

get_nltk_libraries() {
    mkdir -p "$nltk_data_dir"
    #python -m nltk.downloader maxent_treebank_pos_tagger
    #python -m nltk.downloader maxent_ne_chunker
    python  -m nltk.downloader punkt -d "$nltk_data_dir"
    #python -m nltk.downloader words
    stop_words
    polyglot_lang_support
}


stop_words() {
    python -m nltk.downloader stopwords -d "$nltk_data_dir"
    persian_stop_words
}

polyglot_lang_support() {
    # english
    polyglot download embeddings2.en
    polyglot download ner2.en
    # persian
    polyglot download ner2.fa
}


persian_stop_words() {
    mkdir -p "${nltk_data_dir}/corpora/stopwords/"
    get_git_package /tmp/pstop_words https://github.com/kharazi/persian-stopwords.git
    cp /tmp/pstop_words/persian "${nltk_data_dir}/corpora/stopwords/persian"
}


# Installation helpers

apt_install(){
    local package="${1}"
    local installed=$(dpkg --get-selections \
                               | grep -v deinstall \
                               | grep -E "^${package}\s+install"\
                               | grep -o "${package}")
    if [[ "${installed}" = ""  ]]; then
        echo "Installing ${package} via apt-get"
        sudo apt-get -y install "${package}"
        echo "Installation of ${package} completed."
    else
        echo "${package} already installed. Skipping...."
    fi
}

pip_install(){
    local package="${1}"
    local installed=$(pip list \
                             | grep -E "^${package}\s\([0-9\.]*\)$" \
                             | grep -o "${package}")
    if [[ "${installed}" = ""  ]]; then
        echo "Installing ${package} via python pip"
        sudo pip install "${package}"
        echo "Installation of ${package} completed."
    else
        echo "${package} already installed. Skipping...."
    fi
}

pip_three_install(){
    local package="${1}"
    local installed=$(pip3 list \
                             | grep -E "^${package}\s\([0-9\.]*\)$" \
                             | grep -o "${package}")
    if [[ "${installed}" = ""  ]]; then
        echo "Installing ${package} via python pip3"
        sudo pip3 install "${package}"
        echo "Installation of ${package} completed."
    else
        echo "${package} already installed. Skipping...."
    fi
}


get_git_package() {
    local package_dir="${1}"
    local repo="${2}"
    if [[ ! -e $package_dir ]]; then
        git clone "$repo"  "$package_dir"
    else # Update to the latest version for good measure.
        git --git-dir="$package_dir"/.git --work-tree="$package_dir"  pull
    fi
}

main
