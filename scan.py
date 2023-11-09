import subprocess, time, json, datetime, os, sys, re
import constants, auth, notifier, gameUtil
from database import Database
from util import *

def main():
	global lastPlayerNotified
	lastPlayerNotified = False

	while(1):
		try:
			db = Database()
			db.query("SELECT * FROM notification_settings")

			for row in db.fetch():
				processGame(row)
		except Exception as e:
			log(e)
			pass

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

		log("New game found! (%s, %s)" % (settings['name'], settings['id']))
		query = "INSERT INTO game (id, name, description, start_time, settings) VALUES ('%s', '%s', '%s', FROM_UNIXTIME('%s'), '%s')" % (gameId, settings['name'], settings['description'], settings['start_time'] / 1000, json.dumps(settings))
		db.query(query)
	else:
		if rows[0]['game_over'] is 1:
			return

		settings = json.loads(rows[0]['settings'])

	# get latest turn data
	curl = constants.NP_CURL % (gameId, 'latest')
	turnData = getJsonFromCurl(curl)
	if turnData is None:
		return

	# check if game over
	if 'game_over' in turnData and turnData['game_over'] is 1:
		notifier.sendTurn(db, turnData, notification_settings, True)
		log("%s just ended!" % (turnData['name']))
		query = "UPDATE game SET game_over = 1 WHERE id = %s" % (gameId)
		db.query(query)
		return

	if 'turn_num' not in turnData or turnData['turn_num'] is 0:
		return

	# check if new turn
	db.query("SELECT * FROM game_turn WHERE game_id = '%s' AND id = '%s'" % (gameId, turnData['turn_num']))
	rows = db.fetch()

	if len(rows) is 0:
		log("Turn %d started! (%s, %s)" % (turnData['turn_num'], settings['name'], settings['id']))

		# the notified players column is a hack for now. for some reason the db isn't defaulting
		if 'stars' in turnData and 'carriers' in turnData:
			query = """
			INSERT INTO game_turn (id, game_id, turn_start, turn_end, stars, carriers, tick, productions, production_counter, notified_players)
			VALUES ('%s', '%s', FROM_UNIXTIME('%s'), FROM_UNIXTIME('%s'), '%s', '%s', %s, %s, %s, 64)
			""" % (turnData['turn_num'], gameId, turnData['turn_start'] / 1000, turnData['turn_end'] / 1000, json.dumps(turnData['stars']), json.dumps(turnData['carriers']), turnData['tick'], turnData['productions'], turnData['production_counter'])
			db.query(query)
		else:
			query = """
			INSERT INTO game_turn (id, game_id, turn_start, turn_end, tick, productions, production_counter, notified_players)
			VALUES ('%s', '%s', FROM_UNIXTIME('%s'), FROM_UNIXTIME('%s'), %s, %s, %s, 64)
			""" % (turnData['turn_num'], gameId, turnData['turn_start'] / 1000, turnData['turn_end'] / 1000, turnData['tick'], turnData['productions'], turnData['production_counter'])
			db.query(query)

		# insert a player turn for each, but don't set time taken
		for player in turnData['players']:
			query = """
			INSERT INTO player_turn (turn_id, player_id, game_id, status, `rank`, tech, total_carriers, total_economy, total_industry, total_science, total_ships, total_stars)
			VALUES (%s, %s, '%s', %s, %s, '%s', %s, %s, %s, %s, %s, %s)
			""" % (turnData['turn_num'], player['id'], gameId, player['status'], player['rank'], json.dumps(player['tech']), player['total_carriers'], player['total_economy'], player['total_industry'], player['total_science'], player['total_ships'], player['total_stars'])
			db.query(query)

			# check for any missing turns and send notification if needed
			if turnData['turn_num'] is not 1:
				db.query("SELECT * FROM player_turn WHERE taken_at IS NOT NULL AND player_id = %s AND turn_id = %s AND game_id = '%s'" % (player['id'], turnData['turn_num'] - 1, gameId))
				rows = db.fetch()

				if len(rows) is 0 and notification_settings['print_turns_taken']:
					notifier.sendPlayerTurn(db, player, turnData, notification_settings, True)
					# hack to force this to print first
					time.sleep(.2)

		# update players last turn who just took their turn last minute
		if turnData['turn_num'] is not 1:
			db.query("UPDATE player_turn SET taken_at = FROM_UNIXTIME('%s') WHERE taken_at IS NULL AND turn_id = %s AND game_id = '%s'" % (int(time.time()), turnData['turn_num'] - 1, gameId))
			rows = db.fetch()

		notifier.sendTurn(db, turnData, notification_settings, False)

	for player in turnData['players']:
		# check if new player
		db.query("SELECT * FROM player WHERE id = '%s' AND game_id = '%s'" % (player['id'], gameId))
		rows = db.fetch()

		if len(rows) is 0:
			log("Found new player %s! (%s, %s)" % (player['name'], settings['name'], settings['id']))
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
			log("%s took their turn %d. (%s, %s)" % (player['name'], turnData['turn_num'], settings['name'], settings['id']))
			query = "UPDATE player_turn SET taken_at = FROM_UNIXTIME('%s') WHERE player_id = %s AND turn_id = %s AND game_id = '%s'" % (int(time.time()), player['id'], turnData['turn_num'], gameId)
			db.query(query)

			if notification_settings['print_turns_taken']:
				notifier.sendPlayerTurn(db, player, turnData, notification_settings)

	if notification_settings['print_warning']:
		warningTime = turnData['turn_end'] - (60 * 60 * notification_settings['print_warning_n'])
		if time.time() >= warningTime:
			db.query("SELECT * FROM game_turn WHERE notified = 1 AND id = %s AND game_id = '%s'" % (turnData['turn_num'], gameId))
			rows = db.fetch()

			# not notified yet
			if len(rows) is 0:
				db.query("UPDATE game_turn SET notified = 1 WHERE id = %s AND game_id = '%s'" % (turnData['turn_num'], gameId))
				notifier.sendTurnWarning(db, turnData, notification_settings)

	if notification_settings['print_last_players']:
		playersLeft = gameUtil.getPlayersLeft(turnData['players'])
		if len(playersLeft) <= notification_settings['print_last_players_n'] and len(playersLeft) is not 0:
			db.query("SELECT * FROM game_turn WHERE notified_players <= %d AND id = %s AND game_id = '%s'" % (len(playersLeft), turnData['turn_num'], gameId))
			rows = db.fetch()

			# hasn't been notified of this number of players
			if len(rows) is 0:
				db.query("UPDATE game_turn SET notified_players = %d WHERE id = %s AND game_id = '%s'" % (len(playersLeft), turnData['turn_num'], gameId))

				# hack to get this to print after turn taking
				time.sleep(.2)
				notifier.sendPlayerWarning(db, turnData, notification_settings)

	db.close()

if __name__ == "__main__":
	main()
