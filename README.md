App Engine application for the Udacity training course.

# Project 4 for Udacity Fullstack Web Developer Nanodegree
## Overview
This provides the backend for a scalable web application to create and manage conferences.  It does not provide the front end interface.  Use the api explorer (
https://localhost:8080/_ah/api/explorer) to explore and test the endpoint capabilities.
## Products
- [App Engine][1]

## Language
- [Python][2]

## APIs
- [Google Cloud Endpoints][3]

## Acknowledgements
This code is based on the code provided by Udacity for the "Developing Scalable Apps in Python" course

##  Setup
1. Update the value of `application` in `app.yaml` to the app ID you
   have registered in the App Engine admin console and would like to use to host
   your instance of this sample.
1. Start the app locally from the App Engine console.
1. Deploy your application.
1. Use the api explorer to exercise the local and deployed instances of the app

## Task 1: Session and Speaker Class Design Choices
I chose to create sessions as children of a conference.  This facilitates finding all the sessions associated with a conference.  It also make logical sense since a session cannot exist independently of a conference.

I chose to represent the speaker as an entity for several reasons: the speaker name may not be unique and may not be entered in a consistent manner, defining the speaker as an entity allows storing additional information such as a bio and contact information. It also allowed me to store a list of the session keys for the sessions the speaker is presenting. This facilitates queries from the perspective of the speaker.

### Session Entity Properties (Key id will be auto allocated, parent=conference)
* speaker - required StringProperty containing the key id (email) for the speaker
* date - requred DateProperty containing the date (YYYY-MM-DD) of the session
* time - required TimeProperty containing the start time (HH:MM) of the session.  Separating the date and time enables queries for sessions at specific times of the day or on a specific date.
* duration - required IntegerProperty specifying the length of the session
* location - required StringProperty containing the location of the session
* name - required StringProperty containing the name of the session
* sessionType - StringProperty that defaults to lecture if not provided.  This will be converted to an EnumField when presented to the user to provide a limited choice of values.
* description - optional TextProperty allowing an unlimited length entry that wil not be indexed.
* maxAttendees - IntegerProperty that will default to 0 when session is creation
* seatsAvailable - IntegerProperty that will be set equal to maxAttendees when session is created.

### Speaker Entity Properties (Key id=mainEmail, no parent)
* displayName - required StringProperty 
* mainEmail - required StringProperty containing the speaker's email.  This is assumed to be unique and will be used as the key id.
* bio - optional TextProperty allowing unlimited length entry that will not be indexed.
* sessionKeys - repeated StringProperty that contains a list of the websafekeys for the sessions at which this speaker is speaking.  

## Task 2: Add Sessions to User Wishlist
I chose to allow users to add a session to their wishlist regardless of whether they were registered for the associated conference.  This may allow targeted advertising for perspective conference attendees.

##Task 3: Work on indexes and queries

### Create indexes
Indexes are created by default for each property.  Indexes for multiple properties are generated automatically by executing the desired queries locally.

### Come up with 2 additional queries
I created 2 queries: querySessions() and queryConferenceSessions(), both of which call _getSessionQuery().  These routines take QueryForms as input which allows flexibility in creating new queries.  Indexes exist to support queries for sessions in a specific date and time range, for a specific location, date and time and for sessions with available seats for a specific date and time.  Use the values defined in conference.py in the OPERATORS and SESSIONFIELDS dictionaries when entering information in api explorer.

### Query related problem
The problem is to find sessions that are not workshops and start before 7pm.  This would require inequality filters on two different properties which is not supported by the App Engine Datastore.  My proposed solution is to perform a query to return all the sessions that start before 7pm.  I would then iterate through the results to find all the non-workshop sessions.

## Task 4: Add a Task
Per the instructions, added code to _createSessionObject() to check if the speaker for the new session is presenting at 2 or more sessions at the specified conference.  If he/she is, a push task, using the default queue, is added to run CacheFeaturedSpeaker.  CacheFeatureSpeaker calls _cacheFeaturedSpeaker() which identifies the speaker with the most sessions for the specified conference and creates a featured speaker announcement in memcache.



[1]: https://developers.google.com/appengine
[2]: http://python.org
[3]: https://developers.google.com/appengine/docs/python/endpoints/
[4]: https://console.developers.google.com/
[5]: https://localhost:8080/_ah/api/explorer
[6]: https://developers.google.com/appengine/docs/python/endpoints/endpoints_tool
