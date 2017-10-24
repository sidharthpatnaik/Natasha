import pyaudio, wave, os, time, sys, cv2, numpy, random, threading, picamera
import speech_recognition as sr
import simplejson as json
import datetime
import requests
import Adafruit_Nokia_LCD as LCD
import Adafruit_GPIO.SPI as SPI
import re
import sqlite3
import math

from os import environ, path
from gtts import gTTS
from multiprocessing import Process, Queue
from subprocess import Popen,PIPE
from pocketsphinx.pocketsphinx import *
from sphinxbase.sphinxbase import *
from sys import byteorder
from array import array
from struct import pack
from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont
from picamera.array import PiRGBArray
from collections import Counter
from string import punctuation
from math import sqrt

#Setting Prerequisites for the display
DC = 23
RST = 24
SPI_PORT = 0
SPI_DEVICE = 0

disp = LCD.PCD8544(DC, RST, spi=SPI.SpiDev(SPI_PORT, SPI_DEVICE, max_speed_hz=4000000))

# Initialize library.
disp.begin(contrast=60)

#default Settings and directory for face model and datasets
size = 4
haar_file = 'haarcascade_frontalface_default.xml'
datasets = 'datasets'
face_cascade = cv2.CascadeClassifier(haar_file)

#default Settings for hot word detection
MODELDIR = "../sphinx/model"
DATADIR = "../sphinx/test/data"

config = Decoder.default_config()
config.set_string('-hmm', path.join(MODELDIR, 'en-us/en-us'))
config.set_string('-lm', path.join(MODELDIR, 'en-us/cus.lm'))
config.set_string('-dict', path.join(MODELDIR, 'en-us/cus.dic'))
config.set_string('-logfn', '/dev/null')
decoder = Decoder(config)

#Variable for Recording Audio

THRESHOLD = 8000
CHUNK_SIZE = 1024
FORMAT = pyaudio.paInt16
RATE = 8000

#Initializing the Dialog Engine !
#Initialize the connection to the database
connection = sqlite3.connect('chatbot.sqlite')
cursor = connection.cursor()
 
# create the tables needed by the program
create_table_request_list = [
    'CREATE TABLE words(word TEXT UNIQUE)',
    'CREATE TABLE sentences(sentence TEXT UNIQUE, used INT NOT NULL DEFAULT 0)',
    'CREATE TABLE associations (word_id INT NOT NULL, sentence_id INT NOT NULL, weight REAL NOT NULL)',
]
for create_table_request in create_table_request_list:
    try:
        cursor.execute(create_table_request)
    except:
        pass

####################################################
########            Dialog Engine           ########
####################################################

def get_id(entityName, text):
    """Retrieve an entity's unique ID from the database, given its associated text.
    If the row is not already present, it is inserted.
    The entity can either be a sentence or a word."""
    tableName = entityName + 's'
    columnName = entityName
    cursor.execute('SELECT rowid FROM ' + tableName + ' WHERE ' + columnName + ' = ?', (text,))
    row = cursor.fetchone()
    if row:
        return row[0]
    else:
        cursor.execute('INSERT INTO ' + tableName + ' (' + columnName + ') VALUES (?)', (text,))
        return cursor.lastrowid
 
def get_words(text):
    """Retrieve the words present in a given string of text.
    The return value is a list of tuples where the first member is a lowercase word,
    and the second member the number of time it is present in the text."""
    wordsRegexpString = '(?:\w+|[' + re.escape(punctuation) + ']+)'
    wordsRegexp = re.compile(wordsRegexpString)
    wordsList = wordsRegexp.findall(text.lower())
    return Counter(wordsList).items()


####################################################
########       Training The Model (FR)      ########
####################################################

print('Training...')

# Create a list of images and a list of corresponding names
(images, labels, names, id) = ([], [], {}, 0)
for (subdirs, dirs, files) in os.walk(datasets):
    for subdir in dirs:
        names[id] = subdir
        subjectpath = os.path.join(datasets, subdir)
        for filename in os.listdir(subjectpath):
            impath = subjectpath + '/' + filename
            label = id
            images.append(cv2.imread(impath, 0))
            labels.append(int(label))
        id += 1
(width, height) = (130, 100)

# Create a Numpy array from the two lists above
(images, labels) = [numpy.array(lis) for lis in [images, labels]]

# OpenCV trains a model from the images
# NOTE FOR OpenCV2: remove '.face'
model = cv2.createFisherFaceRecognizer()
model.train(images, labels)
print 'Trained Model'

####################################################
########        Check who is the user       ########
####################################################

def checkFace():
	camera = picamera.PiCamera(resolution=(480, 320))
	camera.vflip = True
	camera.capture('face1.jpg')
	camera.capture('face2.jpg')
	camera.capture('face3.jpg')
	pc = 1
	sugestions ={}
	sugestions ['none']=1
	while pc < 4:
		im = cv2.imread('face'+str(pc)+'.jpg')
		pc += 1
		#sleep(1)
		gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
		faces = face_cascade.detectMultiScale(gray, 1.3, 5)
		for (x,y,w,h) in faces:
			cv2.rectangle(im,(x,y),(x+w,y+h),(255,0,0),2)
			face = gray[y:y + h, x:x + w]
			face_resize = cv2.resize(face, (width, height))
			#Try to recognize the face
			prediction = model.predict(face_resize)
			#cv2.rectangle(im, (x, y), (x + w, y + h), (0, 255, 0), 3)
			if prediction[1]<500:
				sugestions [names[prediction[0]]] = prediction[1]
				mycount = len([name for name in os.listdir('datasets/'+names[prediction[0]]+'/') if name[len(name)-3::] == 'png'])
				cv2.imwrite('datasets/'+names[prediction[0]]+'/'+str(mycount+1)+'.png',face_resize)
					
	print sugestions
	fce = sorted(sugestions, key=sugestions.get)[len(sugestions)-1]
	textDisp('Hi '+fce+'!',15)
	return fce

def takeShot():
	cam = picamera.PiCamera(resolution=(480, 320))
	cam.vflip = True
	cam.hflip = True
	cam.capture('image.jpg')

def chkFaceDrv(z,que):
	que.put(checkFace())

####################################################
########        Text to speech System       ########
####################################################

def fetchgTTS(x,y):
	try:
		tts = gTTS(text=x, lang='hi')
		tts.save(y)
	except:
		tts = gTTS(text='Sorry I couldnt Process.', lang='hi')
		tts.save(y)

def playgTTS(y):
	os.system('omxplayer '+y)

def fspeak(x, uname= None):
	if uname is None:
		print x
	else:
		if uname == 'none':
			uname = ' '
		x=['well','ok','hmm','so','yes'][random.randint(0,4)]+' '+uname+', '+x
		print x
	y=[]
	j=0
	for i in range(int(math.ceil(len(x.split())/16.0))):
		y.append(' '.join(x.split()[j:j+16:]))
		j +=16

	fetchgTTS(y[0],'read0.mp3')

	for i in range(1,len(y)):
		print i
		p1 = Process (target = playgTTS, args = ("read"+str(i-1)+".mp3",))
		p1.start()
		#p1.join()
		p2 = Process (target = fetchgTTS, args = (y[i],"read"+str(i)+".mp3",))
		p2.start()
		p2.join()
		p1.join()

	playgTTS("read"+str(len(y)-1)+".mp3")

####################################################
########             Text to LCD            ########
####################################################

def textDisp(x,count=0):

	# Clear display.
	disp.clear()
	disp.display()

	# Create blank image for drawing.
	# Make sure to create image with mode '1' for 1-bit color.
	image = Image.new('1', (LCD.LCDWIDTH, LCD.LCDHEIGHT))

	# Get drawing object to draw on image.
	draw = ImageDraw.Draw(image)

	# Draw a white filled box to clear the image.
	draw.rectangle((0,0,LCD.LCDWIDTH,LCD.LCDHEIGHT), outline=255, fill=255)

	# Load default font.
	font = ImageFont.load_default()

	# Alternatively load a TTF font.
	# Some nice fonts to try: http://www.dafont.com/bitmap.php
	# font = ImageFont.truetype('Minecraftia.ttf', 8)

	# Write some text.
	x=x.split()
	c=''
	for i in range(len(x)):
		if(len(c+' '+x[i])<14):
			c+=' '+x[i]
		else:
			if (count == 0):
				draw.text((1,1), c, font=font)
			else:
				draw.text((1,count), c, font=font)
			c=' '+x[i]
			count += 9
	draw.text((1,count), c, font=font)
	
	#draw.text((1,45), 'THis is a ',font=font)

	# Display image.
	disp.image(image)
	disp.display()


#This function is to reset the program

def restart_program():
    python = sys.executable
    fspeak('System Rebooted','user')
    os.execl(python, python, * sys.argv)

#This function is used for subset matching

def check(y,x):
	y=y.split()
	x=x.split()
	c=0
	for i in x:
		if i in y:
			c+=1
	if c==len(x):
		return True
	else:
		return False

####################################################
#######        Playing an Audio File        ########	
####################################################

def playAudio(waf):
	#define stream chunk   
	chunk = 1024  

	#open a wav format music  
	f = wave.open(waf,"rb")  
	#instantiate PyAudio  
	py = pyaudio.PyAudio()  
	#open stream  
	stream = p.open(format = py.get_format_from_width(f.getsampwidth()),  
	                channels = f.getnchannels(),  
	                rate = f.getframerate(),  
	                output = True)  
	#read data  
	data = f.readframes(chunk)  

	#play stream  
	while data:  
	    stream.write(data)  
	    data = f.readframes(chunk)  

	#stop stream  
	stream.stop_stream()  
	stream.close()  

	#close PyAudio  
	py.terminate()

####################################################
#Functions for Recording Audio, and stop on silence#
####################################################

def is_silent(snd_data):
    "Returns 'True' if below the 'silent' threshold"
    return max(snd_data) < THRESHOLD

def normalize(snd_data):
    "Average the volume out"
    MAXIMUM = 16384
    times = float(MAXIMUM)/max(abs(i) for i in snd_data)

    r = array('h')
    for i in snd_data:
        r.append(int(i*times))
    return r

def trim(snd_data):
    "Trim the blank spots at the start and end"
    def _trim(snd_data):
        snd_started = False
        r = array('h')

        for i in snd_data:
            if not snd_started and abs(i)>THRESHOLD:
                snd_started = True
                r.append(i)

            elif snd_started:
                r.append(i)
        return r

    # Trim to the left
    snd_data = _trim(snd_data)

    # Trim to the right
    snd_data.reverse()
    snd_data = _trim(snd_data)
    snd_data.reverse()
    return snd_data

def add_silence(snd_data, seconds):
    "Add silence to the start and end of 'snd_data' of length 'seconds' (float)"
    r = array('h', [0 for i in xrange(int(seconds*RATE))])
    r.extend(snd_data)
    r.extend([0 for i in xrange(int(seconds*RATE))])
    return r

def record():
    """
    Record a word or words from the microphone and 
    return the data as an array of signed shorts.

    Normalizes the audio, trims silence from the 
    start and end, and pads with 0.5 seconds of 
    blank sound to make sure VLC et al can play 
    it without getting chopped off.
    """
    pi = pyaudio.PyAudio()
    stream = pi.open(format=FORMAT, channels=1, rate=RATE,
        input=True, output=True,
        frames_per_buffer=CHUNK_SIZE)

    num_silent = 0
    snd_started = False

    r = array('h')

    while 1:
        # little endian, signed short
        snd_data = array('h', stream.read(CHUNK_SIZE))
        if byteorder == 'big':
            snd_data.byteswap()
        r.extend(snd_data)

        silent = is_silent(snd_data)

        if silent and snd_started:
            num_silent += 1
        elif not silent and not snd_started:
            snd_started = True

        if snd_started and num_silent > 30:
            break

    sample_width = pi.get_sample_size(FORMAT)
    stream.stop_stream()
    stream.close()
    pi.terminate()

    r = normalize(r)
    r = trim(r)
    r = add_silence(r, 0.2)
    return sample_width, r

####################################################
########        Speech to text Synth       #########
####################################################

def recFile():
	sample_width, data = record()
	data = pack('<' + ('h'*len(data)), *data)
	wf = wave.open('rec.wav', 'wb')
	wf.setnchannels(1)
	wf.setsampwidth(sample_width)
	wf.setframerate(RATE)
	wf.writeframes(data)
	wf.close()

def googleSTT():
	# read the rec.wav and send to google for Text response
	AUDIO_FILE = path.join(path.dirname(path.realpath(__file__)), "rec.wav")

	# use the audio file as the audio source
	r = sr.Recognizer()
	with sr.AudioFile(AUDIO_FILE) as source:
		audio = r.record(source) # read the entire audio file

	# Speech recognition using Google Speech Recognition
	try:
		return r.recognize_google(audio,language = 'en-in')
	except sr.UnknownValueError:
		return 'Sorry I Couldnt get it, please speak again.'
	except sr.RequestError as e:
		return 'Sorry I Couldnt get it, please speak again.'

def gSTTDrv(z,que):
	que.put(googleSTT())

####################################################
########           Utility Module          #########
####################################################

def morningMod():
	hm = str(datetime.datetime.now().time())[:5:].split(':')
	hm = hm[0]+" hours and "+hm[1]+" minutes."
	fspeak('Good Morning Sir, The time is '+hm+', Weather at berhampur is clear sky with a temperature of 32 degrees. Playing News, Today your dont have anythng up in schedule.')

def personaCheck(uname):
	fspeak('I will check your personality')

def setReminder(date, time, message):
	fspeak('I will set Reminder for you')

def checkReminder():
	while 1:
		time.sleep(10)
		cdate = str(datetime.date.today())
		ctime = str(datetime.datetime.now().time())[:5:]
		print 'Check Reminder'
		#fspeak('I will check remider')
		# check =0 #set 1 if reminder is there at that time
		# ####
		# #  Your Code here
		# ###
		# if(check==1):
		# 	#Trigger code for Reminder
		
def checkAlarm():
	while 1:
		try:
			time.sleep(10)
			ctime = str(datetime.datetime.now().time())[:5:]
			ctime = datetime.time(int(ctime[:2:]),int(ctime[3::]))
			print 'Check Alarm'
			url = 'http://192.168.0.102/server/?showAlarms'
			day=['mon','tue','wed','thur','fri','sat','sun'][datetime.date.today().weekday()]
			r=requests.get(url)
			res=r.json()
			if(res[day]!='OFF'):
				res = res[day].split(',')[1]
				alarm = datetime.time(int(res[:2:]),int(res[3::]))
				if(ctime==alarm):
					fspeak('Ring Ring')
		except:
			print 'Error Raised : Alarm'

def checkMeds():
	while 1:
		try:
			time.sleep(10)
			ctime = str(datetime.datetime.now().time())[:5:]
			ctime = datetime.time(int(ctime[:2:]),int(ctime[3::]))
			print 'Check Meds'
			url = 'http://192.168.0.102/server/?showmeds'
			r=requests.get(url)
			res=r.json()
			for i in res:
				alarm=i[mtime]
				alarm = datetime.time(int(alarm[:2:]),int(alarm[3::]))
				if(ctime==alarm):
					fspeak('You have to take your '+i[medname]+' pill.')
		except:
			print 'Error Raised : Alarm'

def checkMail():
	while 1:
		time.sleep(600)
		print 'Check Mail'
		#fspeak('I will check Mail')
		# check =0 #set 1 if new Mail is there at that time
		# ####
		# #  Your Code here
		# ###
		# if(check==1):
		# 	#Trigger code for Mail
		# 	fspeak('You Got a new Email')		

def checkSchedules():
	while 1:
		try:
			time.sleep(60)
			print 'Check Schedule'
			url = 'http://192.168.0.102/server/?schedules'
			day=['mon','tue','wed','thur','fri','sat','sun'][datetime.date.today().weekday()]
			r=requests.get(url)
			res=r.json()
			for i in range(5):
				if (res[i]['day'] == day or res[i]['day']=='all'):
					sid = str(res[i]['sid'])
					status = str(res[i]['status'])
					chk = str(res[i]['chk'])
					stime = datetime.time(int(str(res[i]['stime'][:2:])),int(str(res[i]['stime'][3::])))
					etime = datetime.time(int(str(res[i]['etime'][:2:])),int(str(res[i]['etime'][3::])))
					ctime = datetime.datetime.now().time()
					ctime = str(ctime)[:5:]
					ctime = datetime.time(int(ctime[:2:]),int(ctime[3::]))
					stime1= datetime.time(int(str(res[i]['stime'][:2:])),int(str(res[i]['stime'][3::]))+1)
					etime1=datetime.time(int(str(res[i]['etime'][:2:])),int(str(res[i]['etime'][3::]))+1)
					if(chk=='YES'):
						if(ctime==stime or ctime==stime1):
							print 'inside',stime,ctime
							url='http://192.168.0.102/server/?sid='+sid+'&status='+status
							requests.get(url)
						elif (ctime==etime or ctime==etime1):
							if (status=='ON'):
								print 'inside tog on',stime,ctime
								url='http://192.168.0.102/server/?sid='+sid+'&status=OFF'
							else:
								url='http://192.168.0.102/server/?sid='+sid+'&status=ON'
							requests.get(url)
		except:
			print 'Error Raised: Schedules'

	#this thing i will set !

def showIP():
	devs = os.listdir('/sys/class/net/')
	for i in devs:
		if (i[0]=='w' and i[1]=='l'):
			devs = i
			break
	devs = "ip -4 addr show "+devs+" | grep inet | awk '{print $2}' | cut -d/ -f1"
	proc = Popen(devs, shell=True, stdout=PIPE, stderr=PIPE)
	ipNet = proc.communicate()[0]
	ipNet = str(''.join(ipNet.split()))
	textDisp('Hosted IP: '+ipNet,10)
	fspeak('The IP will hide in 5 Seconds')
	time.sleep(5)

####################################################
########        Entertainment Module       #########
####################################################

def fortuneCookie():
	fspeak("Please wait, while i unwrapping your cookie")
	time.sleep(1)
	fortunes = ["Good things come to those who wait.",
	            "Patience is a virtue.",
	            "The early bird gets the worm.",
	            "A wise man once said, everything in its own time and place.",
	            "Fortune cookies rarely share fortunes.",
	            "You will have great fortunes in the near future",
	            "Your close friends will help you along the way", 
	            "The future is good for you" ,
	 			"Work hard and you will find treasure that you never imagined",
				"You are kind and wonderful, hold on to that","There can be some problems in the near future. Be careful"
				"Luck is with you. Carry on with your work"]
	fspeak(random.choice(fortunes))

def inspire():
	fspeak("Please wait, while i pull out some Quotes")
	time.sleep(1)
	list = ["We are what we repeatedly do. Excellence, therefore, is not an act but a habit.","The best way out is always through.","Do not wait to strike till the iron is hot; but make it hot by striking."," Great spirits have always encountered violent opposition from mediocre minds.","Whether you think you can or think you can't, you're right.",
	"I know for sure that what we dwell on is who we become.","	 I've missed more than 9000 shots in my career. I've lost almost 300 games. 26 times, I've been trusted to take the game winning shot and missed. I've failed over and over and over again in my life. And that is why I succeed.","You must be the change you want to see in the world.","What you get by achieving your goals is not as important as what you become by achieving your goals.",
	"You can get everything in life you want if you will just help enough other people get what they want.","Whatever you do will be insignificant, but it is very important that you do it.","Desire is the starting point of all achievement, not a hope, not a wish, but a keen pulsating desire which transcends everything.","Failure is the condiment that gives success its flavor.",
	"Vision without action is daydream. Action without vision is nightmare.","In any situation, the best thing you can do is the right thing; the next best thing you can do is the wrong thing; the worst thing you can do is nothing.","If you keep saying things are going to be bad, you have a chance of being a prophet.","Success consists of doing the common things of life uncommonly well.",
	"Keep on going and the chances are you will stumble on something, perhaps when you are least expecting it. I have never heard of anyone stumbling on something sitting down.","Twenty years from now you will be more disappointed by the things that you didn't do than by the ones you did do. So throw off the bowlines. Sail away from the safe harbor. Catch the trade winds in your sails. Explore. Dream. Discover.",
	"Losers visualize the penalties of failure. Winners visualize the rewards of success.","Some succeed because they are destined. Some succeed because they are determined.","Experience is what you get when you don't get what you want.","Setting an example is not the main means of influencing others; it is the only means.","A happy person is not a person in a certain set of circumstances, but rather a person with a certain set of attitudes.",
	"If you're going to be able to look back on something and laugh about it, you might as well laugh about it now.","Remember that happiness is a way of travel, not a destination.","If you want to test your memory, try to recall what you were worrying about one year ago today.","What lies behind us and what lies before us are tiny matters compared to what lies within us.","We judge of man's wisdom by his hope.","The best way to cheer yourself up is to try to cheer somebody else up.",
	"Many great ideas go unexecuted, and many great executioners are without ideas. One without the other is worthless.","The world is more malleable than you think and it's waiting for you to hammer it into shape.","Sometimes you just got to give yourself what you wish someone else would give you.","Motivation is a fire from within. If someone else tries to light that fire under you, chances are it will burn very briefly.",
	"People become really quite remarkable when they start thinking that they can do things. When they believe in themselves they have the first secret of success.","Whenever you find whole world against you just turn around and lead the world.","Being defeated is only a temporary condition; giving up is what makes it permanent.","I can't understand why people are frightened by new ideas. I'm frightened by old ones.","Fall down seven times, get up eight.",
	"The difference between ordinary and extraordinary is that little extra.","The best way to predict the future is to create it.","Anyone can do something when they WANT to do it. Really successful people do things when they don't want to do it.","There are two primary choices in life: to accept conditions as they exist, or accept the responsibility for changing them.","Success is the ability to go from failure to failure without losing your enthusiasm.",
	"Success seems to be connected with action. Successful people keep moving. They make mistakes but don't quit.","Attitudes are contagious. Make yours worth catching.","Do not let what you cannot do interfere with what you can do.","There are only two rules for being successful. One, figure out exactly what you want to do, and two, do it.","Sooner or later, those who win are those who think they can.",
	"Vision doesn't usually come as a lightening bolt. Rather it comes as a slow crystallization of life challenges that we one day recognize as a beautiful diamond with great value to ourselves and others.","Success is a state of mind. If you want success, start thinking of yourself as a success.","Ever tried. Ever failed. No matter. Try Again. Fail again. Fail better.","Flops are a part of life's menu and I've never been a girl to miss out on any of the courses.",
	"Cause Change & Lead,Accept Change & Survive,Resist Change & Die.","Winners lose much more often than losers. So if you keep losing but you're still trying, keep it up! You're right on track.","An idea can turn to dust or magic, depending on the talent that rubs against it.","An obstacle is often a stepping stone.","Life is trying things to see if they work.","If you worry about yesterday's failures, then today's successes will be few.",
	"We are all inventors, each sailing out on a voyage of discovery, guided each by a private chart, of which there is no duplicate. The world is all gates, all opportunities.","Knowing is not enough; we must apply. Willing is not enough; we must do.","In matters of style, swim with the current; in matters of principle, stand like a rock.","I think and think for months and years. Ninety-nine times, the conclusion is false. The hundredth time I am right.",
	"Where the willingness is great, the difficulties cannot be great.","Strength does not come from physical capacity. It comes from an indomitable will.","Success is not to be measured by the position someone has reached in life, but the obstacles he has overcome while trying to succeed.","There is no education like adversity.","He who has a why to live can bear almost any how.","Adversity introduces a man to himself.","To avoid criticism do nothing, say nothing, be nothing.",
	"Defeat is not bitter unless you swallow it.","I am an optimist. It does not seem too much use being anything else.","Positive anything is better than negative thinking.","People seem not to see that their opinion of the world is also a confession of character.","Those who wish to sing, always find a song.","If you're going through hell, keep going.","By working faithfully eight hours a day you may eventually get to be boss and work twelve hours a day.","I've learned that no matter what happens, or how bad it seems today, life does go on, and it will be better tomorrow.",
	"What you do speaks so loudly that I cannot hear what you say","Don't let life discourage you; everyone who got where he is had to begin where he was.","In three words I can sum up everything I've learned about life: It goes on.","You gain strength, courage and confidence by every experience in which you stop to look fear in the face.","Sometimes even to live is an act of courage.","Do first things first, and second things not at all.","The only people who find what they are looking for in life are the fault finders."]
	a = random.randint(0,95)
	fspeak(list[a])

def sayjoke(uname):
	fspeak('say your joke here!')

def rolladice():
	dice=[1,2,3,4,5,6][random.randint(0,5)]
	st =['Yeah, I Rolled and got ','You got ','It is ','Well the dice shows '][random.randint(0,3)]
	fspeak(st+dice)

def flipcoin():
	coin=['heads','tails'][random.randint(0,1)]
	st =['Yeah, I tossed and got ','You got ','It is ','Tossed and its ','flipping and it\' '][random.randint(0,4)]
	fspeak(st+coin)

def intfact(uname):
	fspeak("Please wait, while i pull out some facts",uname)
	time.sleep(1)
	say=['Unless food is mixed with saliva you cant taste it.','A female dolphin will assist in the birth of anothers baby dolphin.','Human saliva contains a painkiller called opiorphin that is six times more powerful than morphine.','If you Google Zerg Rush Google will eat up the search results.','During pregnancy womans brain shrinks and it takes up to six months to regain its original size.','Putting sugar on a cut or wound reduces pain and speed up the healing process.','Loneliness weakens immunity, having family and friends increases immunity by 60%.','Temperature can affect appetite. A cold person is more likely to eat more food.','Your left lung is smaller than your right lung to make room for your heart.','The smell of freshly cut grass is actually the scent that plants release when in distress.','A lobsters blood is colorless but when exposed to oxygen it turns blue.','Each time you see a full moon you always see the same side','Soldiers from every country salute with their right hand.','All the blinking in one day equates to having your eyes closed for 30 minutes.','Human brain is more active during sleep than during the day.','85% of plant life is found in the ocean.','Sponges hold more cold water than hot','Fire usually moves faster uphill than downhill','Hummingbirds are the only bird that can fly backwards','A duck cant walk without bobbing its head','A rainbow can only be seen in the morning or late afternoon.','A strawberry is the only fruit which seeds grow on the outside.','An elephants ears are used to regulate body temperature.','Reindeer hair is hollow inside like a tube','Your skin is the largest organ making up the human body','Cows dont have upper front teeth','Black on yellow are the 2 colors with the strongest impact.','Apples are more effective at waking you up in the morning than coffee.','Your most sensitive finger is your index finger.','Brazil is named after a tree.','A hard boiled eggs spin.','There is no butter in buttermilk.','Flamingos can bend their knees backwards.','Gold never erodes','Ants stretch when they wake up in the morning','Mars appears red because its covered in rust','Diary cows give more milk when they listen to calming music. It also relaxes the cows and decreases stress levels.','The stomach acids found in a snakes stomach can digest bones and teeth but not fur or hair.','Oak trees dont produce acorns until they are 50 years old','Human thigh bones are stronger than concrete','The Atlantic Ocean is saltier than the Pacific','Not all your taste buds are on our tongue (10% are on the insides of you cheeks)','Sharks are immune to all known diseases','Carrots contain 0% fat','Hot water freezes quicker than cold water','Your most active muscles are in your eye','rain contains vitamin B12','Horses sleep standing up.','Crocodiles are color blind','Dogs sweat through the pads on their feet','Bananas grow pointing upwards.','Crocodiles swallow rocks to help them dive deeper','Bulls can run faster uphill than down','A sharks teeth are literally as hard as steel','Grasshoppers have white blood','Dirty snow melts quicker than clean snow','The water in the Dead Sea is so salty that its easier to float than sink','The most sung song is happy birthday']
	say=say[random.randint(0,len(say)-1)]
	fspeak(say)

def luckgame(uname):
	fspeak("Umm, Welcome to try your luck, in this game, I will be asking you 5 questions, Lets see how many of these you will make correct.",uname)

def crystalball(uname):
	fspeak("Umm, So want to see your fortune ? Come closer. A bit closer, a little, yes now, ask your, yes or no question. I will look into the crystal and predict your answer.",uname)
	os.system("omxplayer start.wav")
	recFile()
	os.system("omxplayer stop.wav")
	ans=['Yes, I think so','Woops, It seems uncertain to me','definitely','No, I can see it.','absolutely, you can'][random.randint(0,4)]
	fspeak(ans)


def rockpaper(uname):
	fspeak("Umm, So you want to play rock paper scissors, cool, let see who wins, After beep say either rock, paper or scissors")
	myopt = ['rock','paper','scissors'][random.randint(0,2)]
	textDisp('Listening...',15)
	os.system("omxplayer start.wav")
	#playAudio('start.wav')
	recFile()
	os.system("omxplayer stop.wav")
	textDisp('Processing..',15)
	rep=googleSTT()
	if(check(rep,'rock')):
		ursopt='rock'
	elif(check(rep,'paper')):
		ursopt='paper'
	elif(check(rep,'scissors')):
		ursopt='scissors'
	else:
		fspeak('Sorry couldnt get that, please try again',uname)
		rockpaper(uname)

	#Checking the matching
	if(ursopt==myopt):
		fspeak("Woops, I too said "+myopt+", guess it is a draw.",uname)
	elif(ursopt=='rock'):
		if(myopt=='paper'):
			fspeak("Paper and, Weee, I won !",uname)
		else:
			fspeak("scissors and i lost !",uname)
	elif(ursopt=='paper'):
		if(myopt=='Scissors'):
			fspeak("Scissors and, Weee, I won !",uname)
		else:
			fspeak("rock and i lost !",uname)
	elif(ursopt=='scissors'):
		if(myopt=='rock'):
			fspeak("rock and, Weee, I won !",uname)
		else:
			fspeak("scissors and i lost !",uname)

def playgame(uname,rep):
	#The Luck Game
	if(check(rep,'luck') or check(rep,'play luck')):
		luckgame(uname)
	
	#The Crystall Ball Game	
	elif(check(rep,'crystal') or check(rep,'play crystal ball') or check(rep,'crystal ball') or check(rep,'ball')):
		crystalball(uname)
	
	#Rock Paper Scissors Game
	elif(check(rep,'play rock') or check(rep,'rock paper') or check(rep,'rock paper scissors') or check(rep,'rock') or check(rep,'paper') or check(rep,'scissors')):
		rockpaper(uname)

def dialogEngine():
	B = 'Hey Buddy !'
	while True:
		# output bot's message
		fspeak(B)
		time.sleep(1)
		# ask for user input; if blank line, exit the loop
		os.system("aplay start.wav")
		#playAudio('start.wav')
		recFile()
		os.system("aplay stop.wav")
		H =googleSTT()
		print 'user',H
		if (check(H,'bye') or check(H,'later') ):
			fspeak('Ok, bye !')
			break
		# store the association between the bot's message words and the user's response
		words = get_words(B)
		words_length = sum([n * len(word) for word, n in words])
		sentence_id = get_id('sentence', H)
		for word, n in words:
			word_id = get_id('word', word)
			weight = sqrt(n / float(words_length))
			cursor.execute('INSERT INTO associations VALUES (?, ?, ?)', (word_id, sentence_id, weight))
		connection.commit()
		# retrieve the most likely answer from the database
		cursor.execute('CREATE TEMPORARY TABLE results(sentence_id INT, sentence TEXT, weight REAL)')
		words = get_words(H)
		words_length = sum([n * len(word) for word, n in words])
		for word, n in words:
			weight = sqrt(n / float(words_length))
			cursor.execute('INSERT INTO results SELECT associations.sentence_id, sentences.sentence, ?*associations.weight/(4+sentences.used) FROM words INNER JOIN associations ON associations.word_id=words.rowid INNER JOIN sentences ON sentences.rowid=associations.sentence_id WHERE words.word=?', (weight, word,))
		# if matches were found, give the best one
		cursor.execute('SELECT sentence_id, sentence, SUM(weight) AS sum_weight FROM results GROUP BY sentence_id ORDER BY sum_weight DESC LIMIT 1')
		row = cursor.fetchone()
		cursor.execute('DROP TABLE results')
		# otherwise, just randomly pick one of the least used sentences
		if row is None:
			cursor.execute('SELECT rowid, sentence FROM sentences WHERE used = (SELECT MIN(used) FROM sentences) ORDER BY RANDOM() LIMIT 1')
			row = cursor.fetchone()
		# tell the database the sentence has been used once more, and prepare the sentence
		B = row[1]
		cursor.execute('UPDATE sentences SET used=used+1 WHERE rowid=?', (row[0],))

####################################################
########            Brain Module           #########
####################################################

def mod():
	textDisp('Listening...',15)
	os.system("omxplayer start.wav")
	#playAudio('start.wav')
	recFile()
	os.system("omxplayer stop.wav")
	textDisp('Processing...',15)
	#playAudio('stop.wav')
	# Multiprocessing the functions.
	q1 = Queue()
	q2 = Queue()
	p1 = Process(target = gSTTDrv, args = (1,q1))
	p1.start()
	p2 = Process(target = chkFaceDrv, args = (1,q2))
	p2.start()

	usr = q1.get().lower()
	uname = q2.get()
	#uname = 'Sid'
	print uname,usr

	if (check(usr,'restart') or check(usr,'restart yourself')):
		textDisp('Restarting...',15)
		fspeak('Restarting System, Please wait',uname)
		restart_program()
	
	# Intent Parsing [English]
	elif (check(usr,'who are you') or check(usr,"natasha what are you") or check(usr,"who natasha") or check(usr,"what your name") or check(usr,"yourself")):
		textDisp('About Me ...',15)
		fspeak(['I am natasha, your smart home assistant','I am natasha, the consience of your home','Hi there, I am natasha, I can make your day easy by helping you in many ways.'][random.randint(0,2)],uname)
	# Intent Parsing [Hindi]
	elif (check(usr,'kaun ho') or check(usr,'tumhara naam kya hai')):
		textDisp('About me ...',15)
		fspeak('Hi main natasha hoon, tumhare apne home assistant.')

	# Intent Parsing [English]
	elif (check(usr,'you help') or check(usr,'can you do')):
		textDisp('Well I can do all these things',5)
		fspeak('I can set reminders, alarms, fetch news, weather information, answer your what is and who is questions, can control your mail. I can remember things for you. Not only that, i can control your electronic devices, identify your presence by face recognition, monitor your home by my surveillance. I learn intents from you and recommend you actions like wise, and there are lots of other functions. Have fun time exploring me.',uname)
	# Intent Parsing [English]
	elif (check(usr,'kya kar sakti ho') or check(usr,'madat karo')):
		textDisp('Well I can do all these things',5)
		fspeak('main apke liye reminders, alarms, mausam ke baare main jaankaaree, samaachaar daena, apke what is and who is prashn ka uttar, email Suchna de sakti hoon. Itna he nahin, main apke liye cheeje yaad rakh sakti hoon, apke electronic upakarano ko niyantran kar sakti hoon, apko face recognition se pahechan sakti hoon, ghar kee nigaraanee mere home surveillance se, main aapse seekhti hoon aur apke anushar kam karti hoon. Aur be bahut hei jo main kar sakti hoon, maaze lo app, mere saath.')

	# Intent Parsing [English]
	elif(check(usr,'weather at') or check(usr,'temperature at')):
		textDisp('Weather Information',10)
		fo=open("pipe.ali","w")
		city = {
		    'place':usr.split()[usr.split().index('at')+1],
		    'bot':'natasha'
		}
		json.dump(city,fo)
		fo.close()
		os.system("python2 ../weather/wea.py")
		fo = open("pipe.ali","r")
		pipe = json.load(fo)
		fspeak(pipe['data'],uname)

	elif(check(usr,'weather in') or check(usr,'temperature in')):
		textDisp('Weather Information',10)
		fo=open("pipe.ali","w")
		city = {
		    'place':usr.split()[usr.split().index('in')+1],
		    'bot':'natasha'
		}
		json.dump(city,fo)
		fo.close()
		os.system("python2 ../weather/wea.py")
		fo = open("pipe.ali","r")
		pipe = json.load(fo)
		fspeak(pipe['data'],uname)

	elif(check(usr,'weather') or check(usr,'rain') or check(usr,'sunny')  or check(usr,'rainy')):
		textDisp('Weather Information',10)
		os.system("python2 ../weather/weaDef.py")
		fo = open("pipe.ali","r")
		pipe = json.load(fo)
		fspeak(pipe['data'],uname)

	# Intent Parsing [Hindi]
	elif(check(usr,'ka mausam') or check(usr,'ka jalvayu') or check(usr,'ka jal vayu')):
		textDisp('Weather Information',10)
		fo=open("pipe.ali","w")
		city = {
		    'place':usr.split()[usr.split().index('ka')-1],
		    'bot':'natasha'
		}
		json.dump(city,fo)
		fo.close()
		os.system("python2 ../weather/weaHindi.py")
		fo = open("pipe.ali","r")
		pipe = json.load(fo)
		fspeak(pipe['data'],uname)

	elif(check(usr,'mausam') or check(usr,'barish') or check(usr,'dhoop')):
		textDisp('Weather Information',10)
		os.system("python2 ../weather/weaDefHindi.py")
		fo = open("pipe.ali","r")
		pipe = json.load(fo)
		fspeak(pipe['data'],uname)

	#Dialog Engine Calls

	elif(check(usr,'we chat') or check(usr,'we talk') or check(usr,'talk to') or check(usr,'chat with') or check(usr,'communicate') or check(usr,'dialog engine') or check(usr,'chatting mode') or check(usr,'Be my friend')):
		dialogEngine()

	#vision API Calls

	elif(check(usr,'analyse text') or check(usr,'analyse') or check(usr,'read text') or check(usr,'read') or check(usr,'reading text') or check(usr,'analysing text')):
		snp = Process (target = takeShot)
		snp.start()
		snp.join()
		os.system("python2 ../vision/text_analysis.py")
		fo = open("pipe.ali","r")
		pipe = json.load(fo)
		fspeak(pipe['data'],uname)

	elif(check(usr,'analyse environment') or check(usr,'environment')):
		snp = Process (target = takeShot)
		snp.start()
		snp.join()
		os.system("python2 ../vision/scene_analysis.py")
		fo = open("pipe.ali","r")
		pipe = json.load(fo)
		fspeak(pipe['data'],uname)

	elif(check(usr,'analyse landmark') or check(usr,'landmark')):
		snp = Process (target = takeShot)
		snp.start()
		snp.join()
		os.system("python2 ../vision/landmark_analysis.py")
		fo = open("pipe.ali","r")
		pipe = json.load(fo)
		fspeak(pipe['data'],uname)

	elif(check(usr,'analyse mood') or check(usr,'what mood') or check(usr,'mood')):
		snp = Process (target = takeShot)
		snp.start()
		snp.join()
		os.system("python2 ../vision/mood_analysis.py")
		fo = open("pipe.ali","r")
		pipe = json.load(fo)
		fspeak(pipe['data'],uname)

	# Intent Parsing [English]
	elif(check(usr,'remember')):
		textDisp('Yes I will remember! ',5)
		fo = open("../memory/mem.ali",'r')
		data = json.load(fo)
		fo.close()
		temp = []
		for i in usr.split():
			if i not in ['remember','please','can','you']:
				temp.append(i)
		data["data"+str(len(data)+1)]=' '.join(temp)
		fo = open("../memory/mem.ali",'w')
		json.dump(data,fo)
		fo.close()
		fspeak('I will remember it.',uname)		

	elif(check(usr,'where')):
		textDisp('There it is...',15)
		fo=open("pipe.ali","w")
		pipe = {
		    'query':usr
		}
		json.dump(pipe,fo)
		fo.close()
		os.system("python2 ../memory/memory.py")
		fo = open("pipe.ali","r")
		pipe = json.load(fo)
		fspeak(pipe['data'],uname)

	# Intent Parsing [Hindi]
	elif(check(usr,'yaad rakh sakti')):
		textDisp('Yes I will remember! ',5)
		fo = open("../memory/mem.ali",'r')
		data = json.load(fo)
		fo.close()
		temp = []
		for i in usr.split():
			if i not in ['remember','please','can','you']:
				temp.append(i)
		data["data"+str(len(data)+1)]=' '.join(temp)
		fo = open("../memory/mem.ali",'w')
		json.dump(data,fo)
		fo.close()
		fspeak('han main yaad rakhi hoon.',uname)		

	elif(check(usr,'kahan hai') or check(usr,'kaha hai')):
		textDisp('There it is...',15)
		fo=open("pipe.ali","w")
		pipe = {
		    'query':usr
		}
		json.dump(pipe,fo)
		fo.close()
		os.system("python2 ../memory/memory.py")
		fo = open("pipe.ali","r")
		pipe = json.load(fo)
		fspeak(pipe['data'],uname)

	elif (check(usr,'events') or check(usr,'event')):
		textDisp('Fetching Events ...',15)
		os.system("python2 ../remAlert/event.py")
		fo = open("pipe.ali","r")
		news = json.load(fo)
		temp = news['data']
		for i in temp:
			fspeak(i,uname)

	elif(check(usr,'happening around') or check(usr,'news') or check(usr,'headlines') or check(usr,'happening')):
		textDisp('Playing News...',15)
		os.system("python2 ../news/news.py")
		fo = open("pipe.ali","r")
		news = json.load(fo)
		fspeak(news['data'],uname)
		#continue

	elif(check(usr,'fortune') or check(usr,'future') or check(usr,'open fortune') or check(usr,'open cookie')):
		textDisp('Seeking your fortune...',10)
		fortuneCookie()

	#luck Game
	elif(check(usr,'luck') or check(usr,'play luck')):
		textDisp('The Luck Game...',15)
		luckgame(uname)
	
	#The Crystall Ball Game	
	elif(check(usr,'crystal') or check(usr,'play crystal ball') or check(usr,'crystal ball') or check(usr,'ball')):
		textDisp('I\'m looking in the ball',5)
		crystalball(uname)
	
	#Rock Paper Scissors Game
	elif(check(usr,'play rock') or check(usr,'rock paper') or check(usr,'rock paper scissors') or check(usr,'rock') or check(usr,'paper') or check(usr,'scissors')):
		textDisp('Lets Play Rock, Paper and Scissors',5)
		rockpaper(uname)

	elif(check(usr,'game') or check(usr,'play')):
		textDisp('Game Mode...',15)
		fspeak("So interested in playing games, Well we can play, try your luck, the crystal ball and rock paper scissors",uname)
		textDisp('Listening...',15)
		os.system("omxplayer start.wav")
		#playAudio('start.wav')
		recFile()
		os.system("omxplayer stop.wav")
		textDisp('Processing...',15)
		rep=googleSTT()
		print rep
		textDisp('Let\'s Play...',15)
		playgame(uname,rep)

	elif(check(usr,'Interesting') or check(usr,'fun fact') or check(usr,'fact') or check(usr,'hear fact') or check(usr,'listen fact') or check(usr,'facts')):
		textDisp('Pulling a Fact...',10)
		intfact(uname)

	#I am bored [Entertainment Section]
	elif (check(usr,'I am bored') or check(usr,'bored') or check(usr,'entertain')):
		dia = ['Well, I can kill it.','Boredom busters, comming right up !','I have got plenty of boredom remedies.'][random.randint(0,2)]
		body = ['We can play a game, I can give you an interesting fact, or you can go for some random fun.','You can play a game, I can tell you a joke, or we can choose to be surprised with some random fun.','I can sing a poem for you, we can play something, or you want to listen a fun fact.'][random.randint(0,2)]
		textDisp('Natasha is here, dont be bored!',5)
		fspeak(dia+body,uname)
		os.system("omxplayer start.wav")
		#playAudio('start.wav')
		recFile()
		os.system("omxplayer stop.wav")
		rep=googleSTT()
		print rep

		#for playing game
		if(check(rep,'game') or check(rep,'play')):
			textDisp('Game Mode...',15)
			fspeak("So interested in playing games, Well we can play, try your luck, the crystal ball and rock paper scissors",uname)
			textDisp('Listening...',15)
			os.system("omxplayer start.wav")
			#playAudio('start.wav')
			recFile()
			os.system("omxplayer stop.wav")
			textDisp('Processing...',15)
			rep=googleSTT()
			print rep
			textDisp('Let\'s Play...',15)
			playgame(uname,rep)

		#Interesting Facts		
		elif(check(rep,'Interesting') or check(rep,'fact') or check(rep,'hear fact') or check(rep,'listen fact') or check(rep,'facts')):
			textDisp('Pulling a Fact...',10)
			intfact(uname)



	elif(check(usr,'fan') or check(usr,'light') or check(usr,'life') or check(usr,'time') or check(usr,'flight') or check(usr,'hand') or check(usr,'pump')):
		textDisp('Automation Mode',15)
		fo=open("pipe.ali","w")
		st=""
		dev=""
		num=""
		z=usr.split()

		if(check(usr,'switch')):
		    st=z[z.index('switch')+1]
		elif(check(usr,'turn')):
		    st=z[z.index('turn')+1]

		if(check(usr,'fan')):
		    dev='fan'
		    if(z[z.index('fan')-1] == 'pehla' or z[z.index('fan')-1] == 'pehle'):
		    	num = 'first'
		    elif(z[z.index('fan')-1] == 'doosra'):
		    	num = 'second'	
		    else:
		    	num=z[z.index('fan')-1]
		elif(check(usr,'time')):
		    dev='fan'
		    if(z[z.index('time')-1] == 'pehla' or z[z.index('time')-1] == 'pehle'):
		    	num = 'first'
		    elif(z[z.index('time')-1] == 'doosra'):
		    	num = 'second'	
		    else:
		    	num=z[z.index('time')-1]

		elif(check(usr,'hand')):
		    dev='fan'
		    if(z[z.index('hand')-1] == 'pehla' or z[z.index('hand')-1] == 'pehle'):
		    	num = 'first'
		    elif(z[z.index('hand')-1] == 'doosra'):
		    	num = 'second'	
		    else:
		    	num=z[z.index('hand')-1]

		elif(check(usr,'life')):
		    dev='light'
		    if(z[z.index('life')-1] == 'pehla' or z[z.index('life')-1] == 'pehle'):
		    	num = 'first'
		    elif(z[z.index('life')-1] == 'doosra'):
		    	num = 'second'	
		    else:
		    	num=z[z.index('life')-1]

		elif(check(usr,'lag')):
		    dev='light'
		    if(z[z.index('lag')-1] == 'pehla' or z[z.index('lag')-1] == 'pehle'):
		    	num = 'first'
		    elif(z[z.index('lag')-1] == 'doosra'):
		    	num = 'second'	
		    else:
		    	num=z[z.index('lag')-1]

		elif(check(usr,'leg')):
		    dev='light'
		    if(z[z.index('leg')-1] == 'pehla' or z[z.index('leg')-1] == 'pehle'):
		    	num = 'first'
		    elif(z[z.index('leg')-1] == 'doosra'):
		    	num = 'second'	
		    else:
		    	num=z[z.index('leg')-1]

		elif(check(usr,'lap')):
		    dev='light'
		    if(z[z.index('lap')-1] == 'pehla' or z[z.index('lap')-1] == 'pehle'):
		    	num = 'first'
		    elif(z[z.index('lap')-1] == 'doosra'):
		    	num = 'second'	
		    else:
		    	num=z[z.index('lap')-1]

		elif(check(usr,'night')):
		    dev='light'
		    if(z[z.index('night')-1] == 'pehla' or z[z.index('night')-1] == 'pehle'):
		    	num = 'first'
		    elif(z[z.index('night')-1] == 'doosra'):
		    	num = 'second'	
		    else:
		    	num=z[z.index('night')-1]

		elif(check(usr,'flag')):
		    dev='light'
		    if(z[z.index('flag')-1] == 'pehla' or z[z.index('flag')-1] == 'pehle'):
		    	num = 'first'
		    elif(z[z.index('flag')-1] == 'doosra'):
		    	num = 'second'	
		    else:
		    	num=z[z.index('flag')-1]

		elif(check(usr,'flight')):
		    dev='light'
		    if(z[z.index('flight')-1] == 'pehla' or z[z.index('flight')-1] == 'pehle'):
		    	num = 'first'
		    elif(z[z.index('flight')-1] == 'doosra'):
		    	num = 'second'	
		    else:
		    	num=z[z.index('flight')-1]

		elif(check(usr,'lite')):
		    dev='light'
		    if(z[z.index('lite')-1] == 'pehla' or z[z.index('lite')-1] == 'pehle'):
		    	num = 'first'
		    elif(z[z.index('lite')-1] == 'doosra'):
		    	num = 'second'	
		    else:
		    	num=z[z.index('lite')-1]

		else:
		    dev='light'
		    if(z[z.index('light')-1] == 'pehla' or z[z.index('light')-1] == 'pehla'):
		    	num = 'first'
		    elif(z[z.index('light')-1] == 'doosra'):
		    	num = 'second'	
		    else:
		    	num=z[z.index('light')-1]
		print dev,num,st
		textDisp('Turning '+num+' '+dev+' '+st+'!',5)
		swi = {
		    'device':dev,
		    'number':num,
		    'status':st
		}
		json.dump(swi,fo)
		fo.close()
		os.system("python2 ../control/get.py")
		fo = open("pipe.ali","r")
		pipe = json.load(fo)
		fspeak(pipe['data'],uname)
		#continue

	elif (check(usr,'what is') or check(usr,'what is meant') or check(usr,'what mean') or check(usr,'who is') or check(usr,'who was') or check(usr,'say me') or check(usr,'say') or check(usr,'something') or check(usr,'define')):
		textDisp('I\'m Searching...',10)
		fo=open("pipe.ali","w")
		temp = []
		for i in usr.split():
			if i not in ['is','was','what','do','please','buddy','hey','for','you','mean','think','it','tell','define','the','?',',','.',',','natasha','something','related','about','can','me','say','meaning','of','means','by','meant','who','well']:
				temp.append(i)
		wiki = {
		'data':' '.join(temp),
		'bot':'NATASHA'
		}
		json.dump(wiki,fo)
		fo.close()
		os.system("python2 ../wiki/wiki.py")
		fo = open("pipe.ali","r")
		wiki = json.load(fo)
		fspeak(wiki['data'],uname)
		#continue 
	else:
		fspeak('Sorry I was not able to hear it, please say again')

####################################################
#######      Initializing Prerequisites      #######
####################################################
'''
try:
    #openin file and reading data from it
    fo = open("data.ali",'r')
    data = json.load(fo)
    fo.close()
except:
	#Getting the network IP
	from subprocess import Popen,PIPE
	#Getting the network hosted IP
	devs = os.listdir('/sys/class/net/')
	for i in devs:
		if (i[0]=='w' and i[1]=='l'):
			devs = i
			break
	devs = "ip -4 addr show "+devs+" | grep inet | awk '{print $2}' | cut -d/ -f1"
	proc = Popen(devs, shell=True, stdout=PIPE, stderr=PIPE)
	ipNet = proc.communicate()[0]
	ipNet = str(''.join(ipNet.split()))
	
	fspeak('Hello User, I am natasha, for initial setup ')
    #Getting data from the user and storing in the data.ali file
    print "Initial Setup, Please Enter your details: "
    fspeak("Initial Setup, Please Enter your details: ")
    data={
    'name':raw_input("Your Name Please: ").lower(),
    'age':input("Your Age please: "),
    'sex':raw_input("Your gender (Male/Female): ").lower(),
    'dob':raw_input("DOB (dd:mm:yyyy): "),
    'home':raw_input("Home Town: "),
    'bot':raw_input("What shall you call me? ")
    }
    #Loading the initial brain into the bot
    fo= open("data.ali","w")
    json.dump(data,fo)
    fo.close()'''



#Running Parallel Processes
chkMail = Process(target = checkMail)
chkMail.start()
chkAlarm = Process(target = checkAlarm)
chkAlarm.start()
chkRem = Process(target = checkReminder)
chkRem.start()
chkSch = Process(target = checkSchedules)
chkSch.start()

#Hot Word Detector Section
p = pyaudio.PyAudio()
stream = p.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True, frames_per_buffer=1024)
stream.start_stream()

in_speech_bf = False
decoder.start_utt()
while 1:
    textDisp('Natasha IDLE',15)
    buf = stream.read(1024)
    if buf:
        decoder.process_raw(buf, False, False)
        if decoder.get_in_speech() != in_speech_bf:
            in_speech_bf = decoder.get_in_speech()
            if not in_speech_bf:
                decoder.end_utt()
                x = decoder.hyp().hypstr 
                print x
                if(x=='HEY NATASHA' or x=='NATASHA'):
                	print 'Speak !!'
                	stream.stop_stream()
                	mod()
                	stream.start_stream()
                elif(x=='GOOD MORNING NATASHA' or x=="HEY NATASHA GOOD MORNING"):
                	print 'Greet Module'
                	fspeak('Greetings Sir, Today is bla bal, you have 2 remiders, latest news and have a nice day')
                elif(x=='GOOD NIGHT NATASHA'):
                	print 'Good Night sir'
                	fspeak('Good night sir, setting the alarm at 3am. Night mode turning on.')
                elif(x=='HEY NATASHA REBOOT'):
                	fspeak('System is rebooting')
                	restart_program()
                decoder.start_utt()
    else:
        break
decoder.end_utt()
chkRem.stop()
chkMail.stop()
chkAlarm.stop()
chkSch.stop()