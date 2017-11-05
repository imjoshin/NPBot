import subprocess, time, json, datetime, os, sys
import constants, auth
from database import Database
from util import *

def main():
	global lastPlayerNotified
	lastPlayerNotified = False

	while(1):
		db = Database()
		db.query("SELECT * FROM notification_settings")

		for row in db.fetch():
			processGame(row)

		# sleep after all fetches have been made
		time.sleep(constants.SLEEP_TIME)

def processGame(notification_settings):
	gameId = notification_settings['game_id']
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
		query = "INSERT INTO game (id, name, description, start_time, settings) VALUES ('%s', '%s', '%s', FROM_UNIXTIME('%s'), '%s')" % (gameId, settings['name'], settings['description'], settings['start_time'], json.dumps(settings))
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
		INSERT INTO game_turn (id, game_id, time_end, time_end, tick, productions, production_counter)
		VALUES ('%s', '%s', FROM_UNIXTIME('%s'), FROM_UNIXTIME('%s'), %s, %s, %s)
		""" % (turnData['turn_num'], gameId, turnData['turn_start'], turnData['turn_end'], turnData['tick'], turnData['productions'], turnData['production_counter'])
		db.query(query)
		sendTurn(turnData, notification_settings)

		# update players last turn who just took their turn last minute
		if turnData['turn_num'] is not 1:
			db.query("UPDATE player_turn SET taken_at = FROM_UNIXTIME('%s') WHERE taken_at IS NULL AND turn_id = %s AND game_id = '%s'" % (int(time.time()), turnData['turn_num'] - 1, gameId))
			rows = db.fetch()

		# insert a player turn for each, but don't set time taken
		for player in turnData['players']:
			query = """
			INSERT INTO player_turn (turn_id, player_id, game_id, status, rank, tech, total_carriers, total_economy, total_industry, total_science, total_ships, total_stars)
			VALUES (%s, %s, '%s', %s, %s, '%s', %s, %s, %s, %s, %s, %s)
			""" % (turnData['turn_num'], player['id'], gameId, player['status'], player['rank'], json.dumps(player['tech']), player['total_carriers'], player['total_economy'], player['total_industry'], player['total_science'], player['total_ships'], player['total_stars'])
			db.query(query)

	for player in turnData['players']:
		# check if new player
		db.query("SELECT * FROM player WHERE id = '%s' AND game_id = '%s'" % (player['id'], gameId))
		rows = db.fetch()

		if len(rows) is 0:
			log("Found new player %s! ('%s', %s)" % (player['name'], settings['name'], settings['id']))
			query = """
			INSERT INTO player (id, game_id, name, color, avatar, shape)
			VALUES ('%s', '%s', '%s', '%s', %s, %s)
			""" % (player['id'], gameId, player['name'], player['color'], player['avatar'], player['shape'])
			db.query(query)

		db.query("SELECT * FROM player_turn WHERE player_id = %s AND turn_id = %s AND game_id = '%s'" % (player['id'], turnData['turn_num'], gameId))
		rows = db.fetch()

		# check if player just submitted turn
		db.query("SELECT * FROM player_turn WHERE taken_at IS NOT NULL AND player_id = %s AND turn_id = %s AND game_id = '%s'" % (player['id'], turnData['turn_num'], gameId))
		rows = db.fetch()

		# just submitted and not AI
		if len(rows) is 0 and player['ready'] and player['status'] is 0:
			log("%s took their turn %d. ('%s', %s)" % (player['name'], turnData['turn_num'], settings['name'], settings['id']))
			query = "UPDATE player_turn SET taken_at = FROM_UNIXTIME('%s') WHERE player_id = %s AND turn_id = %s AND game_id = '%s'" % (int(time.time()), player['id'], turnData['turn_num'], gameId)
			db.query(query)

			if notification_settings['print_turns_taken']:
				sendPlayerTurn(player, turnData['turn_num'], notification_settings)

	if notification_settings['print_warning']:
		warningTime = turnData['turn_end'] - (60 * 60 * notification_settings['print_warning_n'])
		if time.time() >= warningTime:
			db.query("SELECT * FROM game_turn WHERE notified = 1 AND id = %s AND game_id = '%s'" % (turnData['turn_num'], gameId))
			rows = db.fetch()

			# not notified yet
			if len(rows) is 0:
				db.query("UPDATE game_turn SET notified = 1 WHERE id = %s AND game_id = '%s'" % (turnData['turn_num'], gameId))
				sendTurnWarning(turnData, notification_settings)

	if notification_settings['print_last_players']:
		playersLeft = getPlayersLeft(turnData['players'])
		if len(playersLeft) <= notification_settings['print_last_players_n']:
			db.query("SELECT * FROM game_turn WHERE notified_players <= %d AND id = %s AND game_id = '%s'" % (len(playersLeft), turnData['turn_num'], gameId))
			rows = db.fetch()

			# hasn't been notified of this number of players
			if len(rows) is 0:
				db.query("UPDATE game_turn SET notified_players = %d WHERE id = %s AND game_id = '%s'" % (len(playersLeft), turnData['turn_num'], gameId))
				sendPlayerWarning(turnData, notification_settings)

	db.close()

def sendTurn(turnData, notification_settings):
	print "Sending turn..."

def sendPlayerTurn(playerData, turnNum, notification_settings):
	print "Sending player..."

def sendTurnWarning(turnData, notification_settings):
	print "Sending turn warning..."

def sendPlayerWarning(turnData, notification_settings):
	print "Sending player warning..."

def getPlayersLeft(players):
	left = []
	for player in players:
		if player['ready'] and player['status'] is 0:
			left.append(player)
	return left

if __name__ == "__main__":
	main()
