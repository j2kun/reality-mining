import scipy.io
from datetime import datetime, timedelta
import time
import sys, os
import itertools
import numpy
from collections import deque

#start_date = 1094601600 #First day of classes in 04-05 academic year
#end_date = 1133740800 #Last day of classes in 04-05 academic year

def hasNumeric(obj, field):
   try:
      obj[field][0][0]
      return True
   except:
      return False


def getNumeric(obj, field):
   return obj[field][0][0]


def hasArray(obj, field):
   try:
      obj[field][0]
      return True
   except:
      return False


def getArray(obj, field):
   return obj[field][0]


def validSubjects(allSubjects):
   return [s for s in allSubjects if hasNumeric(s,'mac') and hasNumeric(s,'my_hashedNumber')]


# idDicts: subjects -> {int: subject}, {float: (int, subject)}, {int: (int, subject)}
# First hash is contiguousId: subjectObject
# second hash is macAddress: contiguousId, subjectObject
# third hash is hashedNumber: contiguousId, subjectObject
# because the id dictionaries reference the subject object, we can replace
# the array of subject objects with these dictionaries.
def idDicts(subjects):
   return (dict((i, s) for (i,s) in enumerate(subjects)),
      dict((getNumeric(s,'mac'), (i, s)) for (i,s) in enumerate(subjects)),
      dict((getNumeric(s, 'my_hashedNumber'), (i, s)) for (i,s) in enumerate(subjects)))


def allCommEvents(idDictionary):
   events = []
   for subjectId, subject in idDictionary.items():
      if hasArray(subject, 'comm'):
         events.extend([(subjectId, event) for event in getArray(subject, 'comm')])

   print("%d total comm events" % len(events))
   return events


# extract those call events which are voice calls and only between
# two members of the study.
def callsWithinStudy(commEvents, hashNumDict):
   calls = [(subjectId, e) for (subjectId, e) in commEvents if getArray(e, 'description') == "Voice call"
                                             and getNumeric(e, 'hashNum') in hashNumDict]
   print("%d total calls within study" % len(calls))
   return calls


def convertDatetime(dt):
   return datetime.fromordinal(int(dt)) + timedelta(days=dt%1) - timedelta(days=366) - timedelta(hours=5)


def processCallEvents(callEvents, hashNumDict):
   processedCallEvents = []

   for subjectId, event in callEvents:
      direction = getArray(event, 'direction')
      duration = 0 if direction == 'Missed' else getNumeric(event, 'duration')
      date = convertDatetime(getNumeric(event, 'date'))
      hashNum = getNumeric(event, 'hashNum')
      otherPartyId = hashNumDict[hashNum][0]

      eventAsDict = {'subjectId': subjectId,
                      'direction': direction,
                      'duration': duration,
                      'otherPartyId': otherPartyId,
                      'date': date}
      processedCallEvents.append(eventAsDict)

   print("%d call event dictionaries" % len(processedCallEvents))
   return processedCallEvents


def inRange(dateRange, timevalue):
   start, end = dateRange
   unixTime = int(time.mktime(timevalue.timetuple()))
   return start <= unixTime <= end


def filterByDate(dateRange, events):
   filteredCalls = [e for e in events if inRange(dateRange, e['date'])]
   print("%d calls after filtering by date" % len(filteredCalls))
   return filteredCalls


def writeCallEvents(callEventDicts, filename):
   with open(filename, 'w') as outfile:
      outfile.write('subjectId\totherPartyId\tduration\tdirection\tdate\n')
      for d in callEventDicts:
         values = [d['subjectId'], d['otherPartyId'], d['duration'], d['direction'], d['date']]
         line = '\t'.join(("%s" % (v,)) for v in values)
         outfile.write('%s\n' % line)


def createPhoneCallDataset(idDictionaries):
   startDate = 1095984000
   endDate = 1105142400

   # this data contains the subject records as well
   idDict, macDict, hashNumDict = idDictionaries

   print("Extracting intra-study calls...")
   calls = callsWithinStudy(allCommEvents(idDict), hashNumDict)

   print("Converting call events to a reasonable format...")
   convertedCallEvents = processCallEvents(calls, hashNumDict)

   print("Filtering calls within the given date range...")
   callsToWrite = filterByDate((startDate, endDate), convertedCallEvents)

   print("Writing the calls to reality-mining-calls.txt...")
   writeCallEvents(callsToWrite, 'reality-mining-calls.txt')


# survey values are either numeric or numpy.nan, so we need special
# functions to account for means/maxes involving nan.
def mean(x, y):
   if numpy.isnan(x):
      return mean(0, y)
   if numpy.isnan(y):
      return mean(x, 0)

   return float(x + y) / 2


def myMax(x, y):
   if numpy.isnan(x):
      return myMax(0, y)
   if numpy.isnan(y):
      return myMax(x, 0)

   return max(x,y)


# For simplicity: take the avg of estimates, and the max of the friendship reporting
def getSurveyResponse(network, id1, id2):
   friends = myMax(network['friends'][id1][id2], network['friends'][id2][id1])
   inLabProximity = mean(network['lab'][id1][id2], network['lab'][id2][id1])
   outLabProximity = mean(network['outlab'][id1][id2], network['outlab'][id2][id1])

   return (id1, id2, friends, inLabProximity, outLabProximity)


def writeSurveyEvents(surveyRecords, filename):
   with open(filename, 'w') as outfile:
      outfile.write('id1\tid2\tclose-friends?\tinlab-proximity\toutlab-proximity\n')
      for values in surveyRecords:
         line = '\t'.join(("%s" % (v,)) for v in values)
         outfile.write('%s\n' % line)


def createFriendshipDataset(networkObj, idDictionaries):
   idDict, macDict, hashNumDict = idDictionaries

   networkIdDict = dict((i, (hashNum, hashNumDict[hashNum][0]))
         for i,hashNum in enumerate(getArray(networkObj, 'sub_sort'))
         if hashNum in hashNumDict) # this guarantees the subject is valid

   convertId = lambda i: networkIdDict[i][1]

   print("Creating network survey dataset (friendship/proximity/close friends)")
   networkSurvey = [getSurveyResponse(networkObj,i,j)
         for i,j in itertools.combinations(networkIdDict.keys(), 2)]

   print("Converting ids")
   convertedNetworkSurvey = [(convertId(x[0]), convertId(x[1]), x[2], x[3], x[4])
         for x in networkSurvey if x[2] != 0 or x[3] != 0 or x[4] != 0]

   print("Writing the survey data to reality-mining-survey.txt")
   writeSurveyEvents(convertedNetworkSurvey, 'reality-mining-survey.txt')


# turn each (date, tower) pair into a (dateInterval, tower) pair
# so we can compute the amount of time spent within one tower range,
# or the overlap of two people in the same tower rage.
def makeCellTowerIntervals(subject):
   events = subject['locs']
   dt = convertDatetime
   return [((dt(events[i][0]), dt(events[i+1][0])), events[i][1])
           for i in range(len(events) - 1) if events[i][1] > 0] # condition ensures there was signal


def dateIntervalOverlap(dtint1, dtint2):
   start1, end1 = dtint1
   start2, end2 = dtint2

   if start1 <= start2 <= end1:
      return (start2, min(end1, end2))
   elif start2 <= start1 <= end2:
      return (start1, min(end1, end2))
   else:
      return None


def listProximityEvents(intervals1, intervals2):
   if len(intervals1) == 0 or len(intervals2) == 0:
      print("Found an empty interval list?")
      return []

   D1, D2 = deque(intervals1), deque(intervals2)
   events = deque()

   print('Processing new pairs of intervals')
   dateInterval1, towerId1 = D1.popleft()
   dateInterval2, towerId2 = D2.popleft()
   while len(D1) > 0 and len(D2) > 0:
      if dateInterval2[0] >= dateInterval1[1]:
         dateInterval1, towerId1 = D1.popleft()
      elif dateInterval1[0] >= dateInterval2[1]:
         dateInterval2, towerId2 = D2.popleft()
      else:
         if towerId1 == towerId2:
            theOverlap = dateIntervalOverlap(dateInterval1, dateInterval2)
            if (theOverlap[1] - theOverlap[0]).total_seconds() > 1:
               events.append((theOverlap, towerId1))
               #print('Found a match! %s, %s at tower %s' % (theOverlap[0], theOverlap[1], towerId1))

         if dateInterval1[0] < dateInterval2[0]:
            dateInterval1, towerId1 = D1.popleft()
         else:
            dateInterval2, towerId2 = D2.popleft()

   return events


def writeProximityEvents(proxEventsDict, filename):
   with open(filename, 'w') as outfile:
      outfile.write('id1\tid2\tcellTower\tstart\tend\n')
      for k in proxEventsDict:
         id1, id2 = k
         for event in proxEventsDict[k]:
            values = [id1, id2, event[1], event[0][0], event[0][1]]
            line = '\t'.join(("%s" % (v,)) for v in values)
            outfile.write('%s\n' % line)


def createCellTowerDataset(idDictionaries):
   idDict, macDict, hashNumDict = idDictionaries

   print("Making cell tower intervals.")
   cellTowerIntervals = dict((i, makeCellTowerIntervals(idDict[i])) for i in idDict)

   print("Computing cell tower proximity events.")
   proximityEvents = dict(((i, j), listProximityEvents(cellTowerIntervals[i], cellTowerIntervals[j]))
         for i,j in itertools.combinations(cellTowerIntervals.keys(), 2))

   print("Writing proximity events to reality-mining-proximity.txt")
   writeProximityEvents(proximityEvents, 'reality-mining-proximity.txt')


if __name__ == "__main__":
   matlab_filename = sys.argv[1]
   print("Loading in matlab data - this takes a while and about 2gb memory")
   matlab_obj = scipy.io.loadmat(matlab_filename)
   print("Done loading matlab data.")

   print('Extracting valid subjects and creating id dictionaries.')
   subjects = validSubjects(matlab_obj['s'][0])
   idDictionaries = idDicts(subjects)

   #createFriendshipDataset(matlab_obj['network'][0][0], idDictionaries)
   #createPhoneCallDataset(idDictionaries)
   createCellTowerDataset(idDictionaries)

   print("Cleaning up...")

