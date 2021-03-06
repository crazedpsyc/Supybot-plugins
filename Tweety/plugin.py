# coding=utf8
###
# Copyright (c) 2011, Terje Hoås
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#   * Redistributions of source code must retain the above copyright notice,
#     this list of conditions, and the following disclaimer.
#   * Redistributions in binary form must reproduce the above copyright notice,
#     this list of conditions, and the following disclaimer in the
#     documentation and/or other materials provided with the distribution.
#   * Neither the name of the author of this software nor the name of
#     contributors to this software may be used to endorse or promote products
#     derived from this software without specific prior written consent.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED.  IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

###

import urllib, urllib2
import json
import datetime
import string
import supybot.utils as utils
from supybot.commands import *
import supybot.plugins as plugins
import supybot.ircutils as ircutils
import supybot.callbacks as callbacks

#libraries for time_created_at
import time
from datetime import tzinfo, datetime, timedelta

# for unescape
import re, htmlentitydefs


class Tweety(callbacks.Plugin):
    """Simply use the commands available in this plugin. Allows fetching of the
    latest tween from a specified twitter handle, and listing of top ten
    trending tweets."""
    threaded = True

    def _unescape(self, text):
        text = text.replace("\n", " ")
        def fixup(m):
            text = m.group(0)
            if text[:2] == "&#":
                # character reference
                try:
                    if text[:3] == "&#x":
                        return unichr(int(text[3:-1], 16))
                    else:
                        return unichr(int(text[2:-1]))
                except (ValueError, OverflowError):
                    pass
            else:
                # named entity
                try:
                    text = unichr(htmlentitydefs.name2codepoint[text[1:-1]])
                except KeyError:
                    pass
            return text # leave as is
        return re.sub("&#?\w+;", fixup, text)
  
    def _time_created_at(self, s):
        """
        recieving text element of 'created_at' in the response of Twitter API,
        returns relative time string from now.
        """

        plural = lambda n: n > 1 and "s" or ""

        # twitter search and timelines use different timeformats
        # timeline's created_at Tue May 08 10:58:49 +0000 2012
        # search's created_at Thu, 06 Oct 2011 19:41:12 +0000

        try:
            ddate = time.strptime(s, "%a %b %d %H:%M:%S +0000 %Y")[:-2]
        except ValueError:
            try:
                ddate = time.strptime(s, "%a, %d %b %Y %H:%M:%S +0000")[:-2]
            except ValueError:
                return "", ""

        created_at = datetime(*ddate, tzinfo=None)
        d = datetime.utcnow() - created_at

        if d.days:
            rel_time = "%s days ago" % d.days
        elif d.seconds > 3600:
            hours = d.seconds / 3600
            rel_time = "%s hour%s ago" % (hours, plural(hours))
        elif 60 <= d.seconds < 3600:
            minutes = d.seconds / 60
            rel_time = "%s minute%s ago" % (minutes, plural(minutes))
        elif 30 < d.seconds < 60:
            rel_time = "less than a minute ago"
        else:
            rel_time = "less than %s second%s ago" % (d.seconds, plural(d.seconds))
        return  rel_time

    def _woeid_lookup(self, lookup):
        """
        Use Yahoo's API to look-up a WOEID.
        """

        query = "select * from geo.places where text='%s'" % lookup

        params = {
                "q": query,
                "format":"json",
                "diagnostics":"false",
                "env":"store://datatables.org/alltableswithkeys"
        }

        try:
            response = urllib2.urlopen("http://query.yahooapis.com/v1/public/yql",urllib.urlencode(params))
            data = json.loads(response.read())

            if data['query']['count'] > 1:
                woeid = data['query']['results']['place'][0]['woeid']
            else:
                woeid = data['query']['results']['place']['woeid']

            self.log.info(("I found WOEID: %s from searching: %s") % (woeid, lookup))
        except Exception, err:
            return None

        return woeid

    def woeidlookup(self, irc, msg, args, lookup):
        """[location]
        Search Yahoo's WOEID DB for a location. Useful for the trends variable.
        """

        woeid = self._woeid_lookup(lookup)
        if woeid:
            irc.reply(("I found WOEID: %s while searching for: '%s'") % (ircutils.bold(woeid), lookup))
        else:
            irc.reply(("Something broke while looking up: '%s'") % (lookup))

    woeidlookup = wrap(woeidlookup, ['text'])

    def trends(self, irc, msg, args, woeid):
        """[location]
        Returns the Top 10 Twitter trends for a specific location. Use optional argument location for trends, otherwise will use config variable.
        """

        if woeid:
            try:
                woeid = self._woeid_lookup(woeid)
            except:
                woeid = self.registryValue('woeid', msg.args[0]) # Where On Earth ID
        else:
            woeid = self.registryValue('woeid', msg.args[0]) # Where On Earth ID

        try:
            req = urllib2.Request('https://api.twitter.com/1/trends/%s.json' % woeid)
            stream = urllib2.urlopen(req)
            datas = stream.read()
        except urllib2.HTTPError, err:
            if err.code == 404:
                irc.reply("No trend found for given location.")
                self.log.warning("Twitter trends: Failed to find location with WOEID %s." % woeid)
            else:
                self.log.warning("Twitter trends: API returned http error %s" % err.code)
            return

        try:
            data = json.loads(datas)
        except:
            irc.reply("Error: Failed to parsed receive data.")
            self.log.warning("Here are data:")
            self.log.warning(data)
            return

        ttrends = string.join([trend['name'] for trend in data[0]['trends']], " | ")
        location = data[0]['locations'][0]['name']

        retvalue = ircutils.bold(("Top 10 Twitter Trends in %s: ") % (location)) + ttrends

        irc.reply(retvalue)

    trends = wrap(trends, [optional('text')])


    def tsearch(self, irc, msg, args, optlist, term):
        """ [--num number] [--searchtype mixed,recent,popular] [--lang xx] <term>

        Searches Twitter for the <term> and returns the most recent results.
        Number is number of results. Must be a number higher than 0 and max 10.
        searchtype being recent, popular or mixed. Popular is the default.
        """

        url = "http://search.twitter.com/search.json?include_entities=false&q=" + urllib.quote(term)
        # https://dev.twitter.com/docs/api/1/get/search
        # https://dev.twitter.com/docs/using-search
        args = {'num': self.registryValue('defaultResults', msg.args[0]), 'searchtype': None, 'lang': None}

        max = self.registryValue('maxResults', msg.args[0])
        if args['num'] > max:
            self.log.info("Twitter: defaultResults is set to be higher than maxResults in channel %s." % msg.args[0])

        if optlist:
            for (key, value) in optlist:
                if key == 'num':
                    args['num'] = value
                if key == 'searchtype':
                    args['searchtype'] = value
                if key == 'lang':
                    args['lang'] = value

        if args['num'] > max or args['num'] <= 0:
            irc.reply("Error: '{0}' is not a valid number of tweets. Range is above 0 and max {1}.".format(args['num'], max))
            return
        url += "&rpp=" + str(args['num'])

        # mixed: Include both popular and real time results in the response.
        # recent: return only the most recent results in the response
        # popular: return only the most popular results in the response.
        if args['searchtype']:
            url += "&result_type=" + args['searchtype']
        
        # lang . Uses ISO-639 codes like 'en'
        # http://en.wikipedia.org/wiki/ISO_639-1
        if args['lang']:
            url += "&lang=" + args['lang']

        try:
            req = urllib2.Request(url)
            stream = urllib2.urlopen(req)
            datas = stream.read()
        except urllib2.HTTPError, (err):
            if (err.code and err.code == 406):
                irc.reply("Invalid format is specified in the request.")
            elif (err.code and err.code == 420):
                irc.reply("You are being rate-limited by the Twitter API.")
            else:
                if (err.code):
                    irc.reply("Missing error" + str(err.code))
                else:
                    irc.reply("Error: Failed to open url.")
            return
        try:
            data = json.loads(datas)
        except:
            irc.reply("Error: Failed to parsed receive data.")
            self.log.warning("Plugin Twitter failed to parse json-data.")
            self.log.warning(data)
            return

        results = data["results"]
        outputs = 0
        if len(results) == 0:
            if not args['lang']:
                irc.reply("Error: No Twitter Search results found for '%s'" % term)
            else:
                irc.reply("Error: No Twitter Search results found for '{0}' in language '{1}'".format(term, args['lang']))
        else:
            for result in results:
                if outputs >= args['num']:
                    return
                nick = result["from_user"].encode('utf-8')
                name = result["from_user_name"].encode('utf-8')
                text = self._unescape(result["text"]).encode('utf-8')
                date = result["created_at"]
                relativeTime = self._time_created_at(date)
                tweetid = result["id"]
                self._outputTweet(irc, msg, nick, name, text, relativeTime, tweetid)
                outputs += 1

    tsearch = wrap(tsearch, [getopts({'num':('int'), 'searchtype':('literal', ('popular', 'mixed', 'recent')), 'lang':('something')}), ('text')])

    def _outputTweet(self, irc, msg, nick, name, text, time, tweetid):
        ret = ircutils.underline(ircutils.bold("@" + nick))
        hideName = self.registryValue('hideRealName', msg.args[0])
        if not hideName:
            ret += " ({0})".format(name)
        ret += ": {0} ({1})".format(text, ircutils.bold(time))
        if self.registryValue('addShortUrl', msg.args[0]):
            url = self._createShortUrl(nick, tweetid)
            if (url):
                ret += " {0}".format(url)
        irc.reply(ret)

    def _createShortUrl(self, nick, tweetid):
        longurl = "https://twitter.com/#!/{0}/status/{1}".format(nick, tweetid)
        try:
            req = urllib2.Request("http://is.gd/api.php?longurl=" + urllib.quote(longurl))
            f = urllib2.urlopen(req)
            shorturl = f.read()
            return shorturl
        except:
            return False

    def twitter(self, irc, msg, args, options, nick):
        """[--reply] [--rt] [--num number] <nick> | <--id id> | [--info nick]

        Returns last tweet or 'number' tweets (max 10). Only replies tweets that are
        @replies or retweets if specified with the appropriate arguments.
        Or returns tweet with id 'id'.
        Or returns information on user with --info. 
        """
        args = {'id': False, 'rt': False, 'reply': False, 'num': 1, 'info': False}
        max = self.registryValue('maxResults', msg.args[0])
        if args['num'] > max:
            self.log.info("Twitter: defaultResults is set to be higher than maxResults in channel %s." % msg.args[0])

        if options:
            for (key, value) in options:
                if key == 'id':
                    args['id'] = True
                if key == 'rt':
                    args['rt'] = True
                if key == 'reply':
                    args['reply'] = True
                if key == 'num':
                    args['num'] = value
                if key == 'info':
                    args['info'] = True
        if nick and not args['id']:
            nick = nick.replace('@', '')
        if args['num'] > max or args['num'] <= 0:
            irc.reply("Error: '{0}' is not a valid number of tweets. Range is above 0 and max {1}.".format(args['num'], max))
            return

        if args['id']:
            url = "http://api.twitter.com/1/statuses/show/%s.json" % urllib.quote(nick)
        elif args['info']:
            url = "https://api.twitter.com/1/users/show.json?screen_name=%s" % urllib.quote(nick)
        else:
            url = "http://api.twitter.com/1/statuses/user_timeline/%s.json" % urllib.quote(nick)
        if args['rt'] and not args['id']:
            url += "?include_rts=true"

        try:
            req = urllib2.Request(url)
            stream = urllib2.urlopen(req)
            datas = stream.read()
        except urllib2.HTTPError, (err):
            if (err.code and err.code == 404):
                irc.reply("User or tweet not found.")
            elif (err.code and err.code == 401):
                irc.reply("Not authorized. Protected tweets?")
            else:
                if (err.code):
                    irc.reply("Error: Looks like I haven't bothered adding a special case for http error #" + str(err.code))
                else:
                    irc.reply("Error: Failed to open url. API might be unavailable.")
            return
        try:
            data = json.loads(datas)
        except:
            irc.reply("Error: Failed to parsed receive data.")
            self.log.warning("Plugin Twitter failed to parse json-data. Here are the data:")
            self.log.warning(data)
            return

        # If an ID was given.
        if args['id']:
            text = self._unescape(data["text"]).encode('utf-8')
            nick = data["user"]["screen_name"].encode('utf-8')
            name = data["user"]["name"].encode('utf-8')
            date = data["created_at"]
            relativeTime = self._time_created_at(date)
            tweetid = data["id"]
            self._outputTweet(irc, msg, nick, name, text, relativeTime, tweetid)
            return

        # If info was given
        if args['info']:
            location = data['location'].encode('utf-8')
            followers = data['followers_count']
            friends = data['friends_count']
            description = data['description'].encode('utf-8')
            screen_name = data['screen_name'].encode('utf-8')
            name = data['name'].encode('utf-8')
            url = data['url']
            if url:
                url = url.encode('utf-8')
    
            ret = ircutils.underline(ircutils.bold("@" + nick))
            ret += " ({0}):".format(name)
            if url:
                ret += " {0}".format(ircutils.underline(url))
            if description:
                ret += " {0}".format(description)
            ret += " {0} friends,".format(ircutils.bold(friends))
            ret += " {0} followers.".format(ircutils.bold(followers))
            if location: 
                ret += " " + location
            #irc.reply("%s %s %s %s %s %s %s" % (screen_name, name, url, description, friends, followers, location))
            ret = ret.replace("\r", "")
            ret = ret.replace("\n", " ")
            irc.reply(ret)
            return

        # If it was a regular nick
        if len(data) == 0:
            irc.reply("User has not tweeted yet.")
            return
        indexlist = []
        counter = 0
        # Loop over all tweets
        for i in range(len(data)):
            if counter >= args['num']:
                break
            # If we don't want @replies
            if (not args['reply'] and not data[i]["in_reply_to_screen_name"]):
                indexlist.append(i)
                counter += 1
            # If we want this tweet even if it is an @reply
            elif (args['reply']):
                indexlist.append(i)
                counter += 1
        for index in indexlist:
            text = self._unescape(data[index]["text"]).encode('utf-8')
            nick = data[index]["user"]["screen_name"].encode('utf-8')
            name = data[index]["user"]["name"].encode('utf-8')
            date = data[index]["created_at"]
            tweetid = data[index]["id"]
            relativeTime = self._time_created_at(date)
            self._outputTweet(irc, msg, nick, name, text, relativeTime, tweetid)

        # If more tweets were requested than were found
        if len(indexlist) < args['num']:
            irc.reply("You requested {0} tweets but there were {1} that matched your requirements.".format(args['num'], len(indexlist)))
    twitter = wrap(twitter, [getopts({'reply':'', 'rt': '', 'info': '', 'id': '', 'num': ('int')}), ('something')])


    def tagdef(self, irc, msg, args, term):
        """<term>
        Returns the tag defition from tagdef.com
        """

        # tagdef API: http://api.tagdef.com/
        # tagdef seems to break when you ask and issue
        # #hashtag when you need to submit hashtag
        term = term.replace('#','')

        try:
            req = urllib2.Request('http://api.tagdef.com/one.%s.json' % term)
            stream = urllib2.urlopen(req)
            datas = stream.read()
        except urllib2.HTTPError, err:
            if err.code == 404:
                irc.reply("No tag definition found for: %s" % term)
                self.log.warning("Failed to find definition for %s." % term)
            else:
                self.log.warning("tagdef API returned error %s" % err.code)
            return

        try:
            data = json.loads(datas)
        except:
            irc.reply("Error: Failed to parse received data.")
            self.log.warning("Failed to parse tagdef data.")
            self.log.warning(datas)
            return

        number_of = data['num_defs'] # number of definitions
        definition = data['defs']['def']['text']
        # time = data['defs']['def']['time']
        # upvotes = data['defs']['def']['upvotes']
        # downvotes = data['defs']['def']['downvotes']
        uri = data['defs']['def']['uri']

        retvalue = ircutils.underline("Tagdef: #%s" % term) + " " + definition + " " + uri
        irc.reply(retvalue)
    tagdef = wrap(tagdef, ['text'])

Class = Tweety


# vim:set shiftwidth=4 softtabstop=4 expandtab textwidth=279:
