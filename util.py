import subprocess, json, datetime
import constants

def getJsonFromCurl(curl):
	ret = {}
	try:
		process = subprocess.check_output(('timeout %d {}' % (constants.CURL_TIMEOUT)).format(curl), shell=True, stderr=subprocess.PIPE)
		ret = json.loads(process)
	except subprocess.CalledProcessError as exc:
		if exc.returncode == 124:
			log("Reached timeout of %d seconds on curl. (%s)" % (constants.CURL_TIMEOUT, curl), "error")
			return None
	except Exception as e:
		log("Failed to decode json from curl. (%s)" % (curl), "error")
		log(e)
		return None

	return ret

def convertTime(timestamp):
	dt = datetime.datetime.fromtimestamp(timestamp)
	local_dt = dt - datetime.timedelta(hours=5)
	return local_dt

def log(str, logFile = "log"):
	logFile = logFile if not constants.DEBUG else "%s_debug" % (logFile)
	p = "%s : %s" % (datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f'), str)
	print(p)
	with open(logFile, "a") as l:
		l.write("%s\n" % p)

def replaceArray(string, array):
	for key in array:
		string = string.replace(key, str(array[key]))

	return string
