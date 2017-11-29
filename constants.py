DEBUG = False

CURL_TIMEOUT = 10
SLEEP_TIME = 5

NP_CURL = "curl -X GET -H 'Content-type: application/json' 'https://jjdev.io/npbot/data.php?game_id=%s&v=%s'"
WEBHOOK_CURL = "curl -X POST -H 'Content-type: application/json' --data '%s' %s"
