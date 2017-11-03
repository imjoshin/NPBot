import subprocess, json, datetime
import constants

def getJsonFromCurl(curl):
	try:
		process = subprocess.check_output(('timeout %d {}' % (constants.CURL_TIMEOUT)).format(curl), shell=True, stderr=subprocess.PIPE)
	except subprocess.CalledProcessError as exc:
		if exc.returncode == 124:
			log("Reached timeout of %d seconds on curl. (%s)" % (constants.CURL_TIMEOUT), curl)
			return None

	return json.loads(process)

def log(str):
	logFile = "log" if not constants.DEBUG else "log_debug"
	p = "%s : %s" % (datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f'), str)
	print(p)
	with open(logFile, "a") as l:
		l.write("%s\n" % p)