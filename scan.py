import subprocess, time, json, datetime, os, sys
import constants, auth
from database import Database
from util import getJsonFromCurl
from util import log

def main():
	global lastPlayerNotified
	lastPlayerNotified = False

	while(1):
		db = Database()
		db.query("SELECT * FROM notification_settings")

		for row in db.fetch():
			processGame(row['game_id'])

		# sleep after all fetches have been made
		time.sleep(constants.SLEEP_TIME)

def processGame(gameId):
	db = Database()
	db.query("SELECT * FROM game WHERE id = '%s'" % (gameId))
	rows = db.fetch()

	# get game settings
	if len(rows) is 0:
		curl = constants.NP_CURL % (gameId, 'settings')
		settings = getJsonFromCurl(curl)
		if settings is None:
			return

		log("New game found! ('%s', %s)" % (settings['name'], settings['id']))
		query = "INSERT INTO game (id, name, description, start_time, settings) VALUES ('%s', ''%s'', ''%s'', FROM_UNIXTIME('%s'), '%s')" % (gameId, settings['name'], settings['description'], settings['start_time'] / 1000, process)
		db.query(query)
	else:
		settings = json.loads(rows[0]['settings'])

	# get latest turn data
	curl = constants.NP_CURL % (gameId, 'latest')
	turnData = getJsonFromCurl(curl)
	if turnData is None:
		return

	# check if new turn
	db.query("SELECT * FROM game_turn WHERE game_id = '%s' AND id = '%s'" % (gameId, turnData['turn_num']))
	rows = db.fetch()

	if len(rows) is 0:
		log("Turn %d started! ('%s', %s)" % (turnData['turn_num'], settings['name'], settings['id']))
		query = """
		INSERT INTO game_turn (id, game_id, timeout, tick, productions, production_counter)
		VALUES ('%s', '%s', FROM_UNIXTIME('%s'), %d, %d, %d)
		""" % (turnData['turn_num'], gameId, turnData['time_out'] / 1000, turnData['tick'], turnData['productions'], turnData['production_counter'])
		db.query(query)
		sendTurn(gameId, turnData)

	for player in turnData['players']:
		# check if new player
		db.query("SELECT * FROM player WHERE id = '%s' AND game_id = '%s'" % (player['id'], gameId))
		rows = db.fetch()

		if len(rows) is 0:
			log("Found new player %s! ('%s', %s)" % (player['name'], settings['name'], settings['id']))
			query = """
			INSERT INTO player (id, game_id, name, color, avatar, shape)
			VALUES ('%s', '%s', '%s', '%s', %d, %d)
			""" % (player['id'], gameId, player['name'], player['color'], player['avatar'], player['shape'])
			db.query(query)

		# check if player just submitted turn
		db.query("SELECT * FROM player_turn WHERE player_id = %d AND turn_id = %d AND game_id = '%s'" % (player['id'], turnData['turn_num'], gameId))
		rows = db.fetch()

		# just submitted
		if len(rows) is 0 and player['ready']:
			log("%s took their turn %d. ('%s', %s)" % (player['name'], turnData['turn_num'], settings['name'], settings['id']))
			query = """
			INSERT INTO player_turn (turn_id, player_id, game_id, status, taken_at, rank, tech, total_carriers, total_economy, total_industry, total_science, total_ships, total_stars)
			VALUES (%d, %d, '%s', %d, FROM_UNIXTIME('%s'), %d, '%s', %d, %d, %d, %d, %d, %d)
			""" % (turnData['turn_num'], player['id'], gameId, player['status'], int(time.time()), player['rank'], json.dumps(player['tech']), player['total_carriers'], player['total_economy'], player['total_industry'], player['total_science'], player['total_ships'], player['total_stars'])
			db.query(query)
			sendPlayerTurn(player)

	db.close()

def sendTurn(gameId, turnData):
	print "Sending turn..."

def sendPlayerTurn(gameId, playerData):
	print "Sending player..."

if __name__ == "__main__":
	main()
