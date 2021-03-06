#!/usr/bin/env python

"""models.py

Udacity conference server-side Python App Engine data & ProtoRPC models

$Id: models.py,v 1.1 2014/05/24 22:01:10 wesc Exp $

created/forked from conferences.py by wesc on 2014 may 24

"""

__author__ = 'wesc+api@google.com (Wesley Chun)'

import httplib
import endpoints
from protorpc import messages
from google.appengine.ext import ndb

class StringMessage(messages.Message):
    """StringMessage-- outbound (single) string message"""
    data = messages.StringField(1, required=True)
    
# needed for conference registration
class BooleanMessage(messages.Message):
    """BooleanMessage-- outbound Boolean value message"""
    data = messages.BooleanField(1)

class ConflictException(endpoints.ServiceException):
    """ConflictException -- exception mapped to HTTP 409 response"""
    http_status = httplib.CONFLICT


class Conference(ndb.Model):
    """Conference -- Conference object"""
    name            = ndb.StringProperty(required=True)
    description     = ndb.StringProperty()
    organizerUserId = ndb.StringProperty()
    topics          = ndb.StringProperty(repeated=True)
    city            = ndb.StringProperty()
    startDate       = ndb.DateProperty()
    month           = ndb.IntegerProperty()
    endDate         = ndb.DateProperty()
    maxAttendees    = ndb.IntegerProperty()
    seatsAvailable  = ndb.IntegerProperty()

class ConferenceForm(messages.Message):
    """ConferenceForm -- Conference outbound form message"""
    name            = messages.StringField(1)
    description     = messages.StringField(2)
    organizerUserId = messages.StringField(3)
    topics          = messages.StringField(4, repeated=True)
    city            = messages.StringField(5)
    startDate       = messages.StringField(6)
    month           = messages.IntegerField(7)
    maxAttendees    = messages.IntegerField(8)
    seatsAvailable  = messages.IntegerField(9)
    endDate         = messages.StringField(10)
    websafeKey      = messages.StringField(11)
    organizerDisplayName = messages.StringField(12)

class ConferenceForms(messages.Message):
    """ConferenceForms -- multiple Conference outbound form message"""
    items = messages.MessageField(ConferenceForm, 1, repeated=True)

class QueryForm(messages.Message):
    """QueryForm -- query inbound form message"""
    field = messages.StringField(1)
    operator = messages.StringField(2)
    value = messages.StringField(3)

class QueryForms(messages.Message):
    """QueryForms -- multiple QueryForm inbound form message"""
    filters = messages.MessageField(QueryForm, 1, repeated=True)

class Speaker(ndb.Model):
    """Speaker -- Speaker profile object"""
    displayName = ndb.StringProperty(required=True)
    mainEmail = ndb.StringProperty(required=True)
    bio = ndb.TextProperty()
    sessionKeys = ndb.StringProperty(repeated=True)

class SpeakerForm(messages.Message):
    """SpeakerForm -- Speaker outbound form message"""
    displayName = messages.StringField(1)
    mainEmail = messages.StringField(2)
    bio = messages.StringField(3)

class SpeakerMiniForm(messages.Message):
    """SpeakerMiniForm -- Speaker outbound form message"""
    displayName = messages.StringField(1)
    mainEmail = messages.StringField(2)

class SpeakerList(messages.Message):
    items = messages.MessageField(SpeakerMiniForm, 1, repeated=True)

class Session(ndb.Model):
    """Session -- Session object"""
    speaker         = ndb.StringProperty(required=True)
    date            = ndb.DateProperty(required=True)
    time            = ndb.TimeProperty(required=True)
    duration        = ndb.IntegerProperty(required=True)
    location        = ndb.StringProperty(required=True)
    name            = ndb.StringProperty(required=True)
    sessionType     = ndb.StringProperty(default='lecture',indexed=True)
    description     = ndb.TextProperty()
    maxAttendees    = ndb.IntegerProperty()
    seatsAvailable  = ndb.IntegerProperty()
    

class SessionForm(messages.Message):
    """SessionForm -- Session outbound form message"""
    speaker         = messages.StringField(1)
    date            = messages.StringField(2)
    time            = messages.StringField(3)
    duration         = messages.IntegerField(4)
    location        = messages.StringField(5)
    name            = messages.StringField(6)
    sessionType     = messages.EnumField('SessionType',7)
    description     = messages.StringField(8)
    maxAttendees    = messages.IntegerField(9)
    seatsAvailable  = messages.IntegerField(10)
    websafeKey      = messages.StringField(11)

class SessionForms(messages.Message):
    """SessionForms -- multiple Session outbound form message"""
    items = messages.MessageField(SessionForm, 1, repeated=True)

class SessionType(messages.Enum):
    """type of session enumeration value"""
    lecture = 1
    workshop = 2
    keynote = 3

class Profile(ndb.Model):
    """Profile -- User profile object"""
    displayName = ndb.StringProperty()
    mainEmail = ndb.StringProperty()
    teeShirtSize = ndb.StringProperty(default='NOT_SPECIFIED')
    conferenceKeysToAttend = ndb.StringProperty(repeated=True)
    sessionKeysWishList = ndb.StringProperty(repeated=True)

class ProfileMiniForm(messages.Message):
    """ProfileMiniForm -- update Profile form message"""
    displayName = messages.StringField(1)
    teeShirtSize = messages.EnumField('TeeShirtSize', 2)

class ProfileForm(messages.Message):
    """ProfileForm -- Profile outbound form message"""
    displayName = messages.StringField(1)
    mainEmail = messages.StringField(2)
    teeShirtSize = messages.EnumField('TeeShirtSize', 3)

class TeeShirtSize(messages.Enum):
    """TeeShirtSize -- t-shirt size enumeration value"""
    NOT_SPECIFIED = 1
    XS_M = 2
    XS_W = 3
    S_M = 4
    S_W = 5
    M_M = 6
    M_W = 7
    L_M = 8
    L_W = 9
    XL_M = 10
    XL_W = 11
    XXL_M = 12
    XXL_W = 13
    XXXL_M = 14
    XXXL_W = 15
