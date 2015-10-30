#!/usr/bin/env python

"""
conference.py -- Udacity conference server-side Python App Engine API;
    uses Google Cloud Endpoints

$Id: conference.py,v 1.25 2014/05/24 23:42:19 wesc Exp wesc $

created by wesc on 2014 apr 21

"""

__author__ = 'wesc+api@google.com (Wesley Chun)'


from datetime import datetime
from datetime import date
from datetime import time
from datetime import timedelta


import endpoints
from protorpc import messages
from protorpc import message_types
from protorpc import remote

from google.appengine.ext import ndb

from models import Profile
from models import ProfileMiniForm
from models import ProfileForm
from models import TeeShirtSize

from settings import WEB_CLIENT_ID
from utils import getUserId
from models import Conference
from models import ConferenceForm
from models import ConferenceForms
from models import QueryForm
from models import QueryForms

from models import Session
from models import SessionForm
from models import SessionForms
from models import SessionType

from models import Speaker
from models import SpeakerForm
from models import SpeakerMiniForm
from models import SpeakerList

from models import BooleanMessage
from models import ConflictException

from google.appengine.api import memcache
from models import StringMessage
from google.appengine.api import taskqueue
from collections import namedtuple

import logging

       

GET_REQUEST = endpoints.ResourceContainer(
    message_types.VoidMessage,
    websafeKey=messages.StringField(1),
)

SESSION_GET_REQUEST_TYPE = endpoints.ResourceContainer(
    message_types.VoidMessage,
    websafeKey=messages.StringField(1),
    sType=messages.StringField(2),
)

SESSION_QUERY = endpoints.ResourceContainer(
    QueryForms,
    websafeKey=messages.StringField(1),
)

SESSION_CREATE = endpoints.ResourceContainer(
    SessionForm,
    websafeKey=messages.StringField(1),
)

DEFAULTS = {
    "city": "Default City",
    "maxAttendees": 0,
    "seatsAvailable": 0,
    "topics": [ "Default", "Topic" ],
}

SESSIONDEFAULTS = {
    "maxAttendees": 0,
    "seatsAvailable": 0,
}

EMAIL_SCOPE = endpoints.EMAIL_SCOPE
API_EXPLORER_CLIENT_ID = endpoints.API_EXPLORER_CLIENT_ID

OPERATORS = {
            'EQ':   '=',
            'GT':   '>',
            'GTEQ': '>=',
            'LT':   '<',
            'LTEQ': '<=',
            'NE':   '!='
}

CONFERENCEFIELDS =    {
            'CITY': 'city',
            'TOPIC': 'topics',
            'MONTH': 'month',
            'MAX_ATTENDEES': 'maxAttendees',
}

SESSIONFIELDS =     {
            'DATE': 'date',
            'TIME': 'time',
            'DURATION': 'duration',
            'LOCATION': 'location',
            'SEATSAVAILABLE': 'seatsAvailable',
}

MEMCACHE_ANNOUNCEMENTS_KEY = "CONFERENCE_ANNOUNCEMENTS"


#- - - - - - - - - - - - - - - - - - - - - - - - - - - - - -


@endpoints.api( name='conference',
                version='v1',
                allowed_client_ids=[WEB_CLIENT_ID, API_EXPLORER_CLIENT_ID],
                scopes=[EMAIL_SCOPE])
class ConferenceApi(remote.Service):
    """Conference API v0.1"""
    
# - - - Announcements - - - - - - - - - - - - - - - - - - - -
    @staticmethod
    def _cacheAnnouncement():
        """Create Announcement & assign to memcache; used by
        memcache cron job & putAnnouncement().
        """
        confs = Conference.query(ndb.AND(
            Conference.seatsAvailable <= 5,
            Conference.seatsAvailable > 0)
        ).fetch(projection=[Conference.name])

        if confs:
            # If there are almost sold out conferences,
            # format announcement and set it in memcache
            announcement = '%s %s' % (
                'Last chance to attend! The following conferences '
                'are nearly sold out:',
                ', '.join(conf.name for conf in confs))
            memcache.set(MEMCACHE_ANNOUNCEMENTS_KEY, announcement)
        else:
            # If there are no sold out conferences,
            # delete the memcache announcements entry
            announcement = ""
            memcache.delete(MEMCACHE_ANNOUNCEMENTS_KEY)

        return announcement
    
    @staticmethod
    def _cacheFeaturedSpeaker(c_urlsafeKey):
        """ Cache a featured speaker and associated sessions for a conference
            Called from getFeaturedSpeaker and CreateFeaturedSpeaker(from the task queue)
        """
        c_key = ndb.Key(urlsafe=c_urlsafeKey)
        sessionlist = Session.query(ancestor=c_key).fetch()
        # count the number of sessions for each speaker
        memstring=""
        if sessionlist:
          spkrdict={}
          for session in sessionlist:
            if session.speaker in spkrdict:
                spkrdict[session.speaker]+=1
            else:
                spkrdict[session.speaker] = 1
          speakers = namedtuple('speakers','speaker numSessions')
          #find the speaker with the most sessions
          mostSessions = sorted([speakers(k,v) for (k,v) in spkrdict.items()],reverse=True)
        
          # if there is a speaker with more than 2 session, create and cache a featured speaker message
          if mostSessions[0].numSessions >= 2:   
            featuredsessions=[]
            for session in sessionlist:
                if session.speaker == mostSessions[0].speaker:
                    featuredsessions.append(session.name)
            memstring = 'Featured speaker,%s, will be leading the following sessions %s' % (
                ndb.Key(Speaker,mostSessions[0].speaker).get().displayName,
                ', '.join(featuredsessions))
        if memstring:
            memcache.set("featuredspeaker-%s"%c_urlsafeKey,memstring)
        return(memstring)
           

    @endpoints.method(message_types.VoidMessage, StringMessage,
            path='conference/announcement/get',
            http_method='GET', name='getAnnouncement')
    def getAnnouncement(self, request):
        """Return Announcement from memcache."""
        # TODO 1
        # return an existing announcement from Memcache or an empty string.
        announcement = memcache.get(MEMCACHE_ANNOUNCEMENTS_KEY)
        if announcement is not None:
            return StringMessage(data=announcement)
        else:
            return StringMessage(data=self._cacheAnnouncement())

# - - - Registration - - - - - - - - - - - - - - - - - - - -
    @ndb.transactional(xg=True)
    def _conferenceRegistration(self, request, reg=True):
        """Register or unregister user for selected conference."""
        retval = None
        prof = self._getProfileFromUser() # get user Profile

        # check if conf exists given websafeConfKey
        # get conference; check that it exists
        wsck = request.websafeKey
        conf = ndb.Key(urlsafe=wsck).get()
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % wsck)

        # register
        if reg:
            # check if user already registered otherwise add
            if wsck in prof.conferenceKeysToAttend:
                raise ConflictException(
                    "You have already registered for this conference")

            # check if seats avail
            if conf.seatsAvailable <= 0:
                raise ConflictException(
                    "There are no seats available.")

            # register user, take away one seat
            prof.conferenceKeysToAttend.append(wsck)
            conf.seatsAvailable -= 1
            retval = True

        # unregister
        else:
            # check if user already registered
            if wsck in prof.conferenceKeysToAttend:

                # unregister user, add back one seat
                prof.conferenceKeysToAttend.remove(wsck)
                conf.seatsAvailable += 1
                retval = True
            else:
                retval = False

        # write things back to the datastore & return
        prof.put()
        conf.put()
        return BooleanMessage(data=retval)


    @endpoints.method(GET_REQUEST, BooleanMessage,
            path='conference/{websafeKey}/register',
            http_method='POST', name='registerForConference')
    def registerForConference(self, request):
        """Register user for selected conference."""
        return self._conferenceRegistration(request)

# - - - Conference objects - - - - - - - - - - - - - - - - -


    def _getQuery(self, request):
        """Return formatted query from the submitted filters."""
        q = Conference.query()
        inequality_filter, filters = self._formatFilters(request.filters,CONFERENCEFIELDS)

        # If exists, sort on inequality filter first
        if not inequality_filter:
            q = q.order(Conference.name)
        else:
            q = q.order(ndb.GenericProperty(inequality_filter))
            q = q.order(Conference.name)

        for filtr in filters:
            if filtr["field"] in ["month", "maxAttendees"]:
                filtr["value"] = int(filtr["value"])
            formatted_query = ndb.query.FilterNode(filtr["field"], filtr["operator"], filtr["value"])
            q = q.filter(formatted_query)
        return q
    
  
    def _formatFilters(self, filters, validFields):
        """Parse, check validity and format user supplied filters."""
        formatted_filters = []
        inequality_field = None

        for f in filters:
            filtr = {field.name: getattr(f, field.name) for field in f.all_fields()}

            try:
                filtr["field"] = validFields[filtr["field"]]
                filtr["operator"] = OPERATORS[filtr["operator"]]
            except KeyError:
                raise endpoints.BadRequestException("Filter contains invalid field (%s) or operator."%filtr["field"])

            # Every operation except "=" is an inequality
            if filtr["operator"] != "=":
                # check if inequality operation has been used in previous filters
                # disallow the filter if inequality was performed on a different field before
                # track the field on which the inequality operation is performed
                if inequality_field and inequality_field != filtr["field"]:
                    raise endpoints.BadRequestException("Inequality filter is allowed on only one field.")
                else:
                    inequality_field = filtr["field"]

            formatted_filters.append(filtr)
        return (inequality_field, formatted_filters)


    def _copyConferenceToForm(self, conf, displayName):
        """Copy relevant fields from Conference to ConferenceForm."""
        cf = ConferenceForm()
        for field in cf.all_fields():
            if hasattr(conf, field.name):
                # convert Date to date string; just copy others
                if field.name.endswith('Date'):
                    setattr(cf, field.name, str(getattr(conf, field.name)))
                else:
                    setattr(cf, field.name, getattr(conf, field.name))
            elif field.name == "websafeKey":
                setattr(cf, field.name, conf.key.urlsafe())
        if displayName:
            setattr(cf, 'organizerDisplayName', displayName)
        cf.check_initialized()
        return cf


    def _createConferenceObject(self, request):
        """Create or update Conference object, returning ConferenceForm/request."""
        # preload necessary data items
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')
        user_id = getUserId(user)

        if not request.name:
            raise endpoints.BadRequestException("Conference 'name' field required")

        # copy ConferenceForm/ProtoRPC Message into dict
        data = {field.name: getattr(request, field.name) for field in request.all_fields()}
        del data['websafeKey']
        del data['organizerDisplayName']

        # add default values for those missing (both data model & outbound Message)
        for df in DEFAULTS:
            if data[df] in (None, []):
                data[df] = DEFAULTS[df]
                setattr(request, df, DEFAULTS[df])

        # convert dates from strings to Date objects; set month based on start_date
        if data['startDate']:
            data['startDate'] = datetime.strptime(data['startDate'][:10], "%Y-%m-%d").date()
            data['month'] = data['startDate'].month
        else:
            data['month'] = 0
        if data['endDate']:
            data['endDate'] = datetime.strptime(data['endDate'][:10], "%Y-%m-%d").date()

        # set seatsAvailable to be same as maxAttendees on creation
        # both for data model & outbound Message
        if data["maxAttendees"] > 0:
            data["seatsAvailable"] = data["maxAttendees"]
            setattr(request, "seatsAvailable", data["maxAttendees"])

        # make Profile Key from user ID
        p_key = ndb.Key(Profile, user_id)
        # allocate new Conference ID with Profile key as parent
        c_id = Conference.allocate_ids(size=1, parent=p_key)[0]
        # make Conference key from ID
        c_key = ndb.Key(Conference, c_id, parent=p_key)
        data['key'] = c_key
        data['organizerUserId'] = request.organizerUserId = user_id

        # create Conference & return (modified) ConferenceForm
        Conference(**data).put()
        # creation of Conference & return (modified) ConferenceForm
        taskqueue.add(params={'email': user.email(),
            'conferenceInfo': repr(request)},
            url='/tasks/send_confirmation_email'
        )
        return request
    
    @endpoints.method(ConferenceForm, ConferenceForm, path='conference',
            http_method='POST', name='createConference')
    def createConference(self, request):
        """Create new conference."""
        return self._createConferenceObject(request)

    @endpoints.method(QueryForms, ConferenceForms,
            path='queryConferences',
            http_method='POST',
            name='queryConferences')
    def queryConferences(self, request):
        """Query for conferences."""
        conferences = self._getQuery(request)

        # return individual ConferenceForm object per Conference
        return ConferenceForms(
            items=[self._copyConferenceToForm(conf, "") \
            for conf in conferences]
        )
    
    @endpoints.method(GET_REQUEST, ConferenceForm,
            path='conference/{websafeKey}',
            http_method='GET', name='getConference')    
    def getConference(self, request):
        """Return requested conference (by websafeKey)."""
        # get Conference object from request; bail if not found
        conf = ndb.Key(urlsafe=request.websafeKey).get()
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % request.websafeKey)
        prof = conf.key.parent().get()
        # return ConferenceForm
        return self._copyConferenceToForm(conf, getattr(prof, 'displayName'))

    @endpoints.method(message_types.VoidMessage, ConferenceForms,
            path='getConferencesCreated',
            http_method='POST', name='getConferencesCreated')
    
    def getConferencesCreated(self, request):
        """Return conferences created by user."""
        # make sure user is authed
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')
        # make profile key
        p_key = ndb.Key(Profile, getUserId(user))
        # create ancestor query for this user
        conferences = Conference.query(ancestor=p_key)
        # get the user profile and display name
        prof = p_key.get()
        displayName = getattr(prof, 'displayName')
        # return set of ConferenceForm objects per Conference
        return ConferenceForms(
            items=[self._copyConferenceToForm(conf, displayName) for conf in conferences]
        )
      
    @endpoints.method(message_types.VoidMessage, ConferenceForms,
            path='conferences/attending',
            http_method='GET', name='getConferencesToAttend')
    def getConferencesToAttend(self, request):
        """Get list of conferences that user has registered for."""
        # TODO:
        # step 1: get user profile
        # step 2: get conferenceKeysToAttend from profile.
        # to make a ndb key from websafe key you can use:
        # ndb.Key(urlsafe=my_websafe_key_string)
        # step 3: fetch conferences from datastore. 
        # Use get_multi(array_of_keys) to fetch all keys at once.
        # Do not fetch them one by one!
        # make sure user is authed
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')
        try:
            p_key = ndb.Key(Profile, getUserId(user))
        except:
            raise endpoints.NotFoundException('Registration required')
        prof = p_key.get()
        array_of_wskeys=getattr(prof,'conferenceKeysToAttend')
        conferences=[]
        if array_of_wskeys:
            array_of_keys = [ndb.Key(urlsafe=wskey) for wskey in array_of_wskeys]
            conferences = ndb.get_multi(array_of_keys)

        # return set of ConferenceForm objects per Conference
        return ConferenceForms(items=[self._copyConferenceToForm(conf, "")\
         for conf in conferences]
        )
                
    @endpoints.method(message_types.VoidMessage, ConferenceForms,
        path='filterPlayground',
        http_method='GET', name='filterPlayground')
    def filterPlayground(self, request):
        q = Conference.query()
        # simple filter usage:
        # q = q.filter(Conference.city == "Paris")

        # advanced filter building and usage
        field = "city"
        operator = "="
        value = "London"
        f = ndb.query.FilterNode(field, operator, value)
        q = q.filter(f)

        field = "topics"
        operator = "="
        value = "Medical Innovations"
        f = ndb.query.FilterNode(field, operator, value)
        q = q.filter(f)

        q=q.order(Conference.name)

        field = "maxAttendees"
        operator = ">"
        value = "10"
        f = ndb.query.FilterNode(field, operator, value)
        q = q.filter(f)
             
        # TODO
        # add 2 filters:
        # 1: city equals to London
        # 2: topic equals "Medical Innovations"

        return ConferenceForms(
            items=[self._copyConferenceToForm(conf, "") for conf in q]
        )


# - - - Session objects - - - - - - - - - - - - - - - - -
    
    def _createSessionObject(self, request,c_key,cname,user):
        """Create or update Session object, returning SessionForm/request."""
        # copy SessionForm/ProtoRPC Message into dict
        data = {field.name: getattr(request, field.name) for field in request.all_fields()}
        del data['websafeKey']
                      
        # add default values for those missing (both data model & outbound Message)
        for df in SESSIONDEFAULTS:
            if data[df] in (None, []):
                data[df] = SESSIONDEFAULTS[df]
                setattr(request, df, SESSIONDEFAULTS[df])

        # convert date and time from strings to Date objects
        if data['date']:
            data['date'] = datetime.strptime(data['date'], "%Y-%m-%d").date()
        if data['time']:
            data['time'] = datetime.strptime(data['time'],"%H:%M").time()
        # convert enum to string
        if data['sessionType']:
             data['sessionType'] = str(data['sessionType'])
        # set seatsAvailable to be same as maxAttendees on creation
        # both for data model & outbound Message
        if data["maxAttendees"] > 0:
            data["seatsAvailable"] = data["maxAttendees"]
            setattr(request, "seatsAvailable", data["maxAttendees"])

        # allocate new Session ID with Conference key as parent
        s_id = Session.allocate_ids(size=1, parent=c_key)[0]
        # make Session key from ID
        s_key = ndb.Key(Session, s_id, parent=c_key)
        data['key'] = s_key
        # add the session to the speakers list
        spkr = ndb.Key(Speaker,data['speaker']).get()
        array_of_wskeys=getattr(spkr,'sessionKeys')     
        count=1
        # determine how many sessions this speaker is presenting at this conference
        if array_of_wskeys:
             for wskey in array_of_wskeys:
                 if ndb.Key(urlsafe=wskey).parent()==c_key:
                     logging.info("session id=%d"%ndb.Key(urlsafe=wskey).id())
                     count+=1    
        # if speaker is presenting 2 or more sessions
        # add a task to check if this speaker is now a featured speaker
        if count >= 2:             
            taskqueue.add(params={'conference': c_key.urlsafe()},url='/tasks/featuredSpeaker')
        # create Session & return SessionForm
        Session(**data).put()
        spkr.sessionKeys.append(s_key.urlsafe())
        spkr.put()
        taskqueue.add(params={'email': user.email(),
            'sessionInfo': repr(request)},
            url='/tasks/send_confirmation_email'
        )
        return self._copySessionToForm(s_key.get())
    
    def _copySessionToForm(self, session):
        """Copy relevant fields from Session to SessionForm."""
        ses = SessionForm()
        for field in ses.all_fields():
            if hasattr(session, field.name):
                # convert Date to date string
                if field.name == 'date':
                    setattr(ses, field.name, str(getattr(session, field.name)))
                elif field.name == 'time':
                    setattr(ses, field.name, str(getattr(session, field.name)))
                elif field.name == 'sessionType':
                    setattr(ses, field.name, getattr(SessionType, getattr(session, field.name)))
                else:
                    setattr(ses, field.name, getattr(session, field.name))
        ses.check_initialized()
        return ses
    
    def _getSessionQuery(self, request, parent=None):
        """Return formatted query from the submitted filters."""
        if parent != None:
            q = Session.query(ancestor=parent)
        else:
            q = Session.query()
        inequality_filter, filters = self._formatFilters(request.filters,SESSIONFIELDS)

        # If exists, sort on inequality filter first
        if not inequality_filter:
            q = q.order(Session.date)
            q = q.order(Session.time)
        else:
            q = q.order(ndb.GenericProperty(inequality_filter))
            q = q.order(Session.date)
            q = q.order(Session.time)

        for filtr in filters:
            if filtr["field"] in ["duration", "maxAttendees"]:
                filtr["value"] = int(filtr["value"])
            elif filtr["field"] == "date":
                filtr["value"] = datetime.strptime(filtr["value"],"%Y-%m-%d")
            elif filtr["field"] == "time":
                # time stored in datastore with the 1970-01-01 date so need to adjust accordingly
                filtr["value"] = datetime.strptime(filtr["value"],"%H:%M") + timedelta(days=70*365.25) - timedelta(hours=12)
                logging.info("time=%s"%str(filtr["value"]))
            formatted_query = ndb.query.FilterNode(filtr["field"], filtr["operator"], filtr["value"])
            q = q.filter(formatted_query)
        return q

    @endpoints.method(QueryForms, SessionForms,
            path='querySessions',
            http_method='POST',
            name='querySessions')
    def querySessions(self, request):
        """Query for conferences."""
        sessions = self._getSessionQuery(request)

        # return individual SessionForm object per Session
        return SessionForms(
            items=[self._copySessionToForm(session) \
            for session in sessions]
        )
    
    @endpoints.method(SESSION_CREATE, SessionForm, path='conference/{websafeKey}/session',
            http_method='POST', name='createSession')
    def createSession(self, request):
        """Create new sessionn for given conference."""
        # get Conference object from request; bail if not found
        c_key = ndb.Key(urlsafe=request.websafeKey)
        conf = c_key.get()
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % request.websafeKey)
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')
        user_id = getUserId(user)
        owner = conf.key.parent().id()
        if owner != user_id:
            raise endpoints.UnauthorizedException("User (%s) is not the owner of the conference (%s)"%(user_id,owner))
        return self._createSessionObject(request,conf.key,conf.name,user) 

    @endpoints.method(SESSION_QUERY, SessionForms,
            path='queryConferenceSessions/{websafeKey}',
            http_method='POST',
            name='queryConferenceSessions')
    def queryConferenceSessions(self, request):
        """Query for conferences."""
        sessions = self._getSessionQuery(request,ndb.Key(urlsafe=request.websafeKey))

        # return individual SessionForm object per Session
        return SessionForms(
            items=[self._copySessionToForm(session) \
            for session in sessions]
        )
        
    @endpoints.method(GET_REQUEST, BooleanMessage,
            path='wishlist/{websafeKey}',
            http_method='GET', name='addSessionToWishlist')
    def addSessionToWishlist(self, request):
        """Add session to user wishlist."""
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')
        try:
            p_key = ndb.Key(Profile, getUserId(user))
        except:
            raise endpoints.NotFoundException('Registration required')
        prof = p_key.get()
        prof.sessionKeysWishList.append(request.websafeKey)
        prof.put()

        return BooleanMessage(data=True)
    
    @endpoints.method(GET_REQUEST, SessionForms,
            path='getwishlist/{websafeKey}',
            http_method='GET', name='getConferenceSessionsWishlist')
    def getConferenceSessionsWishlist(self, request):
        """Return sessions for requested conference that are on user's wishlist."""
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')
        try:
            p_key = ndb.Key(Profile, getUserId(user))
        except:
            raise endpoints.NotFoundException('Registration required')
        prof = p_key.get()
        # get Conference object from request; bail if not found
        try:
            c_key = ndb.Key(urlsafe=request.websafeKey)
        except:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % request.websafeKey)
        array_of_wskeys=getattr(prof,'sessionKeysWishList')
        array_of_keys=[]
        sessions=[]
        if array_of_wskeys:
            for wskey in array_of_wskeys:
                if ndb.Key(urlsafe=wskey).parent() == c_key:
                    array_of_keys.append(ndb.Key(urlsafe=wskey))
            sessions = ndb.get_multi(array_of_keys)

        # return set of SessionForm objects for the Conference
        return SessionForms(items=[self._copySessionToForm(session)\
         for session in sessions]
        )
    
    @endpoints.method(GET_REQUEST, SessionForms,
            path='conference/{websafeKey}/getsessions',
            http_method='GET', name='getConferenceSessions')
    def getConferenceSessions(self, request):
        """Return sessions for requested conference (by websafeKey)."""
        # get Conference object from request; bail if not found
        try:
            c_key = ndb.Key(urlsafe=request.websafeKey)
        except:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % request.websafeKey)
        sessions = Session.query(ancestor=c_key).fetch()
        # return set of SessionForm objects for the Conference
        return SessionForms(items=[self._copySessionToForm(session)\
         for session in sessions]
        )
    
    @endpoints.method(SESSION_GET_REQUEST_TYPE, SessionForms,
            path='confsessiontype/{websafeKey}/{sType}',
            http_method='GET', name='getConferenceSessionsByType')
    def getConferenceSessionsByType(self, request):
        """Return sessions for requested conference (by websafeKey)."""
        # get Conference object from request; bail if not found
        try:
            c_key = ndb.Key(urlsafe=request.websafeKey)
        except:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % request.websafeKey)
        #getattr(SessionType, getattr(session, field.name)
        s_q = Session.query(ancestor=c_key)
        sessions=s_q.filter(Session.sessionType==request.sType).fetch()
        # return set of SessionForm objects for the Conference
        return SessionForms(items=[self._copySessionToForm(session)\
         for session in sessions]
        )
    
# - - - Speaker objects - - - - - - - - - - - - - - - - -
    def _copySpeakerToForm(self, speaker):
        """Copy relevant fields from Speaker to SpeakerForm."""
        # copy relevant fields from Speaker to SpeakerFrom
        spkr = SpeakerForm()
        for field in spkr.all_fields():
            if hasattr(speaker, field.name):
                setattr(spkr, field.name, getattr(speaker, field.name))
        spkr.check_initialized()
        return spkr
    
    def _copySpeakerToMiniForm(self, speaker):
        """Copy relevant fields from Speaker to SpeakerForm."""
        # copy relevant fields from Speaker to SpeakerMiniForm
        spkr = SpeakerMiniForm()
        for field in spkr.all_fields():
            if hasattr(speaker, field.name):
                setattr(spkr, field.name, getattr(speaker, field.name))
        spkr.check_initialized()
        return spkr

    @endpoints.method(GET_REQUEST, StringMessage,
            path='featuredSpeaker/{websafeKey}',
            http_method='GET', name='getFeaturedSpeaker')
    def getFeaturedSpeaker(self, request):
        """ Get the featured speaker info for the specified conference, check the cache first """
        c_key = ndb.Key(urlsafe=request.websafeKey)
        fspeaker = memcache.get("featuredspeaker-%s"%request.websafeKey)
        if fspeaker is not None:
            return StringMessage(data=fspeaker)
        else:
            return StringMessage(data=self._cacheFeaturedSpeaker(request.websafeKey))
        
    @endpoints.method(GET_REQUEST, SessionForms,
            path='getspeakersessions/{websafeKey}',
            http_method='GET', name='getSpeakerSessions')
    def getSpeakerSessions(self, request):
        """Return sessions for requested speaker (by websafeKey)."""
        # get Conference object from request; bail if not found
        try:
            s_key=ndb.Key(urlsafe=request.websafeKey)
        except:
            raise endpoints.NotFoundException(
                'No speaker found with key: %s' % request.websafeKey)
        speaker=s_key.get()   
        if not speaker:
            raise endpoints.NotFoundException(
                'No speaker found with key: %s' % request.websafeKey)
        array_of_wskeys=getattr(speaker,'sessionKeys')
        sessions=[]
        if array_of_wskeys:
            array_of_keys = [ndb.Key(urlsafe=wskey) for wskey in array_of_wskeys]
            sessions = ndb.get_multi(array_of_keys)
        # return set of SessionForm objects for the Conference
        return SessionForms(items=[self._copySessionToForm(session)\
         for session in sessions]
        )
    
      
    def _doSpeaker(self, request):
        """Get, create or update speaker"""
        s_key = ndb.Key(Speaker,request.mainEmail)
        speaker = s_key.get()
        # if speaker exists, process user-modifyable fields
        if speaker:
            for field in ('displayName', 'bio'):
                if hasattr(request, field):
                    val = getattr(request, field)
                    if val:
                        setattr(speaker, field, str(val))
        else:
            speaker = Speaker(key=s_key, displayName=request.displayName, mainEmail=request.mainEmail, bio=request.bio)
            
        # put the modified speaker to datastore
        speaker.put()

        # return SpeakerForm
        return self._copySpeakerToForm(speaker)


    @endpoints.method(SpeakerForm, SpeakerForm,
            path='speaker', http_method='GET', name='getSpeaker')
    def getSpeaker(self, request):
        """Return speaker info."""
        return self._doSpeaker(request)
 
    @endpoints.method(message_types.VoidMessage, SpeakerList,
            path='allspeakers', http_method='GET', name='getAllSpeaker')
    def getAllSpeakers(self, request):
        """Return list of speakers."""
        speakers=Speaker.query().order(Speaker.displayName)
        return SpeakerList(items=[self._copySpeakerToMiniForm(speaker) for speaker in speakers])

    @endpoints.method(SpeakerForm, SpeakerForm,
            path='addSpeaker', http_method='POST', name='addSpeaker')
    def addSpeaker(self, request):
        """Update & return user speaker."""
        return self._doSpeaker(request)


   
# - - - Profile objects - - - - - - - - - - - - - - - - - - -

    def _copyProfileToForm(self, prof):
        """Copy relevant fields from Profile to ProfileForm."""
        # copy relevant fields from Profile to ProfileForm
        pf = ProfileForm()
        for field in pf.all_fields():
            if hasattr(prof, field.name):
                # convert t-shirt string to Enum; just copy others
                if field.name == 'teeShirtSize':
                    setattr(pf, field.name, getattr(TeeShirtSize, getattr(prof, field.name)))
                else:
                    setattr(pf, field.name, getattr(prof, field.name))
        pf.check_initialized()
        return pf


    def _getProfileFromUser(self):
        """Return user Profile from datastore, creating new one if non-existent."""
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')

        # TODO 1
        # step 1. copy utils.py from additions folder to this folder
        #         and import getUserId from it
        # step 2. get user id by calling getUserId(user)
        # step 3. create a new key of kind Profile from the id

        # TODO 3
        # get the entity from datastore by using get() on the key
        id = getUserId(user)
        p_key = ndb.Key(Profile, id)
        profile = p_key.get()
        if not profile:
            profile = Profile(
                key = p_key, # TODO 1 step 4. replace with the key from step 3
                displayName = user.nickname(), 
                mainEmail= user.email(),
                teeShirtSize = str(TeeShirtSize.NOT_SPECIFIED),
            )
            # TODO 2
            # save the profile to datastore
            profile.put()

        return profile      # return Profile


    def _doProfile(self, save_request=None):
        """Get user Profile and return to user, possibly updating it first."""
        # get user Profile
        prof = self._getProfileFromUser()

        # if saveProfile(), process user-modifyable fields
        if save_request:
            for field in ('displayName', 'teeShirtSize'):
                if hasattr(save_request, field):
                    val = getattr(save_request, field)
                    if val:
                        setattr(prof, field, str(val))
            # TODO 4
            # put the modified profile to datastore
            prof.put()

        # return ProfileForm
        return self._copyProfileToForm(prof)


    @endpoints.method(message_types.VoidMessage, ProfileForm,
            path='profile', http_method='GET', name='getProfile')
    def getProfile(self, request):
        """Return user profile."""
        return self._doProfile()


    @endpoints.method(ProfileMiniForm, ProfileForm,
            path='profile', http_method='POST', name='saveProfile')
    def saveProfile(self, request):
        """Update & return user profile."""
        return self._doProfile(request)
    
# registers API
api = endpoints.api_server([ConferenceApi]) 
