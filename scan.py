import subprocess, time, json, datetime, os, sys, re
import constants, auth
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
		except:
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
		query = "INSERT INTO game (id, name, description, start_time, settings) VALUES ('%s', '%s', '%s', FROM_UNIXTIME('%s'), '%s')" % (gameId, settings['name'], settings['description'], settings['start_time'], json.dumps(settings))
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
		sendTurn(db, turnData, notification_settings, True)
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
			""" % (turnData['turn_num'], gameId, turnData['turn_start'], turnData['turn_end'], json.dumps(turnData['stars']), json.dumps(turnData['carriers']), turnData['tick'], turnData['productions'], turnData['production_counter'])
			db.query(query)
		else:
			query = """
			INSERT INTO game_turn (id, game_id, turn_start, turn_end, tick, productions, production_counter, notified_players)
			VALUES ('%s', '%s', FROM_UNIXTIME('%s'), FROM_UNIXTIME('%s'), %s, %s, %s, 64)
			""" % (turnData['turn_num'], gameId, turnData['turn_start'], turnData['turn_end'], turnData['tick'], turnData['productions'], turnData['production_counter'])
			db.query(query)

		# insert a player turn for each, but don't set time taken
		for player in turnData['players']:
			query = """
			INSERT INTO player_turn (turn_id, player_id, game_id, status, rank, tech, total_carriers, total_economy, total_industry, total_science, total_ships, total_stars)
			VALUES (%s, %s, '%s', %s, %s, '%s', %s, %s, %s, %s, %s, %s)
			""" % (turnData['turn_num'], player['id'], gameId, player['status'], player['rank'], json.dumps(player['tech']), player['total_carriers'], player['total_economy'], player['total_industry'], player['total_science'], player['total_ships'], player['total_stars'])
			db.query(query)

			# check for any missing turns and send notification if needed
			if turnData['turn_num'] is not 1:
				db.query("SELECT * FROM player_turn WHERE taken_at IS NOT NULL AND player_id = %s AND turn_id = %s AND game_id = '%s'" % (player['id'], turnData['turn_num'] - 1, gameId))
				rows = db.fetch()

				if len(rows) is 0 and notification_settings['print_turns_taken']:
					sendPlayerTurn(db, player, turnData, notification_settings, True)
					# hack to force this to print first
					time.sleep(.2)

		# update players last turn who just took their turn last minute
		if turnData['turn_num'] is not 1:
			db.query("UPDATE player_turn SET taken_at = FROM_UNIXTIME('%s') WHERE taken_at IS NULL AND turn_id = %s AND game_id = '%s'" % (int(time.time()), turnData['turn_num'] - 1, gameId))
			rows = db.fetch()

		sendTurn(db, turnData, notification_settings, False)

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
				sendPlayerTurn(db, player, turnData, notification_settings)

	if notification_settings['print_warning']:
		warningTime = turnData['turn_end'] - (60 * 60 * notification_settings['print_warning_n'])
		if time.time() >= warningTime:
			db.query("SELECT * FROM game_turn WHERE notified = 1 AND id = %s AND game_id = '%s'" % (turnData['turn_num'], gameId))
			rows = db.fetch()

			# not notified yet
			if len(rows) is 0:
				db.query("UPDATE game_turn SET notified = 1 WHERE id = %s AND game_id = '%s'" % (turnData['turn_num'], gameId))
				sendTurnWarning(db, turnData, notification_settings)

	if notification_settings['print_last_players']:
		playersLeft = getPlayersLeft(turnData['players'])
		if len(playersLeft) <= notification_settings['print_last_players_n'] and len(playersLeft) is not 0:
			db.query("SELECT * FROM game_turn WHERE notified_players <= %d AND id = %s AND game_id = '%s'" % (len(playersLeft), turnData['turn_num'], gameId))
			rows = db.fetch()

			# hasn't been notified of this number of players
			if len(rows) is 0:
				db.query("UPDATE game_turn SET notified_players = %d WHERE id = %s AND game_id = '%s'" % (len(playersLeft), turnData['turn_num'], gameId))

				# hack to get this to print after turn taking
				time.sleep(.2)
				sendPlayerWarning(db, turnData, notification_settings)

	db.close()

def sendTurn(db, turnData, notification_settings, gameOver):
	log("Posting game new turn %d. (%s, %s)" % (turnData['turn_num'], turnData['name'], notification_settings['game_id']))
	# sort players by rank
	players = sorted(turnData['players'], key=lambda k: k['rank'])
	attachments = []

	if notification_settings['print_leaderboard']:
		for player in players:
			status = "AI: " if player['status'] is not 0 else ""
			nickname = getNickName(db, player['id'], notification_settings['game_id'])
			player['nickname'] = nickname

			# player is still alive
			if player['total_stars'] is not 0:
				hasDiscordNickname = re.match(r"<@[0-9]{12,}>", nickname)

				rankDif = getRankDif(player['rank'], player['rank_last']) if 'rank_last' in player else ""
				printNickname = ' (%s)' % nickname if nickname is not '' and not hasDiscordNickname and player['status'] is 0 else ''
				title = '%d. %s%s%s %s' % (player['rank'], status, player['name'], printNickname, rankDif)

				# get total tech
				tech = 0
				for techName in player['tech']:
					tech += int(player['tech'][techName]['level'])

				variables = {
					'%STARS%': player['total_stars'],
					'%SHIPS%': player['total_ships'],
					'%TECH%': tech,
					'%ECON%': player['total_economy'],
					'%INDUSTRY%': player['total_industry'],
					'%SCIENCE%': player['total_science'],
					'\\n': '\n'
				}

				# replace variables in text
				text = replaceArray(notification_settings['print_leaderboard_format'], variables)

				if hasDiscordNickname and player['status'] is 0:
					text = "%s\n%s" % (nickname, text)

				if 'hooks.slack.com/services' in notification_settings['webhook_url']:
					attachments.append({
						'color': player['color'],
						'title': title,
						'text': text,
						"mrkdwn_in": ["text"]
					})
				elif 'discordapp.com/api/webhooks' in notification_settings['webhook_url']:
					attachments.append({
						'description': text,
						'title': title,
						'color': long(player['color'][1:], 16)
					})
			# player is dead
			else:
				title = '%d. %s%s' % (player['rank'], status, player['name'])

				if 'hooks.slack.com/services' in notification_settings['webhook_url']:
					attachments.append({
						'color': '#999999',
						'title': title
					})
				elif 'discordapp.com/api/webhooks' in notification_settings['webhook_url']:
					attachments.append({
						'color': long('999999', 16),
						'title': title
					})

	turnStartTime = convertTime(int(turnData['turn_start']))
	turnEndTime = convertTime(int(turnData['turn_end']))
	starttime = turnStartTime.strftime('%a, %b %-d at %-I:%M:%S %p')
	endtime = turnEndTime.strftime('%a, %b %-d at %-I:%M:%S %p')

	variables = {
		'%TURN%': turnData['turn_num'],
		'%NAME%': turnData['name'],
		'%TURNSTART%': starttime,
		'%TURNEND%': endtime,
		'\\n': '\n'
	}

	if gameOver:
		variables['%WINNER%'] = "%s%s" % (players[0]['name'], ' (%s)' % players[0]['nickname'] if players[0]['nickname'] is not '' else '')

	# replace variables in text
	textFormat = notification_settings['print_turn_start_format'] if not gameOver else notification_settings['print_game_over_format']
	text = replaceArray(textFormat, variables)

	if 'hooks.slack.com/services' in notification_settings['webhook_url']:
		post = {
	        'username': notification_settings['webhook_name'],
	        'channel': notification_settings['webhook_channel'],
	        'icon_url': notification_settings['webhook_image'],
	        'attachments': attachments,
			'link_names': 1,
			'text': text
	    }

	elif 'discordapp.com/api/webhooks' in notification_settings['webhook_url']:
		post = {
			'username': notification_settings['webhook_name'],
			'avatar_url': notification_settings['webhook_image'],
			'content': text,
			'embeds': attachments
		}

	command = constants.WEBHOOK_CURL % (json.dumps(post), notification_settings['webhook_url'])
	process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

def sendPlayerTurn(db, playerData, turnData, notification_settings, lastPlayer = False):
	log("Posting %s's turn %d. (%s, %s)" % (playerData['name'], turnData['turn_num'] - (1 if lastPlayer else 0), turnData['name'], notification_settings['game_id']))
	nickname = getNickName(db, playerData['id'], notification_settings['game_id'])

	turnStartTime = convertTime(int(turnData['turn_start']))
	turnEndTime = convertTime(int(turnData['turn_end']))
	starttime = turnStartTime.strftime('%a, %b %-d at %-I:%M:%S %p')
	endtime = turnEndTime.strftime('%a, %b %-d at %-I:%M:%S %p')

	variables = {
		'%TURN%': turnData['turn_num'] - (1 if lastPlayer else 0),
		'%NAME%': turnData['name'],
		'%TURNSTART%': starttime,
		'%TURNEND%': endtime,
		'%PLAYER%': playerData['name'] + (' (%s)' % nickname if nickname is not '' else ''),
		'\\n': '\n'
	}

	# replace variables in text
	text = replaceArray(notification_settings['print_turns_taken_format'], variables)

	if 'hooks.slack.com/services' in notification_settings['webhook_url']:
		post = {
			'username': notification_settings['webhook_name'],
			'channel': notification_settings['webhook_channel'],
			'icon_url': notification_settings['webhook_image'],
			'attachments': [{
				'color': playerData['color'],
				'text': text,
				"mrkdwn_in": ["text"]
			}],
			'link_names': 1
		}

	elif 'discordapp.com/api/webhooks' in notification_settings['webhook_url']:
		post = {
			'username': notification_settings['webhook_name'],
			'avatar_url': notification_settings['webhook_image'],
			'embeds': [
				{
					'description': text,
					'color': long(playerData['color'][1:], 16)
				}
			]
		}

	command = constants.WEBHOOK_CURL % (json.dumps(post), notification_settings['webhook_url'])
	process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

def sendTurnWarning(db, turnData, notification_settings):
	turnStartTime = convertTime(int(turnData['turn_start']))
	turnEndTime = convertTime(int(turnData['turn_end']))
	starttime = turnStartTime.strftime('%a, %b %-d at %-I:%M:%S %p')
	endtime = turnEndTime.strftime('%a, %b %-d at %-I:%M:%S %p')
	playersLeft = getPlayersLeft(turnData['players'])
	playersFormatted = []

	for player in playersLeft:
		nickname = getNickName(db, player['id'], notification_settings['game_id'])
		playersFormatted.append(player['name'] + (' (%s)' % nickname if nickname is not '' else ''))

	players = ', '.join(playersFormatted)

	hoursLeft = int((turnData['turn_end'] - time.time()) / 60 / 60 + .5)
	log("Posting warning of %d hour(s). (%s, %s)" % (hoursLeft, turnData['name'], notification_settings['game_id']))

	variables = {
		'%TURN%': turnData['turn_num'],
		'%NAME%': turnData['name'],
		'%TURNSTART%': starttime,
		'%TURNEND%': endtime,
		'%HOURS%': hoursLeft,
		'%PLAYERS%': players,
		'\\n': '\n'
	}

	# replace variables in text
	text = replaceArray(notification_settings['print_warning_format'], variables)

	if 'hooks.slack.com/services' in notification_settings['webhook_url']:
		post = {
			'username': notification_settings['webhook_name'],
			'channel': notification_settings['webhook_channel'],
			'icon_url': notification_settings['webhook_image'],
			'attachments': [{
				'color': '#FFFFFF',
				'text': text,
				"mrkdwn_in": ["text"]
			}],
			'link_names': 1
		}
	elif 'discordapp.com/api/webhooks' in notification_settings['webhook_url']:
		post = {
			'username': notification_settings['webhook_name'],
			'avatar_url': notification_settings['webhook_image'],
			'embeds': [
				{
					'description': text,
					'color': long('FFFFFF', 16)
				}
			]
		}

	command = constants.WEBHOOK_CURL % (json.dumps(post), notification_settings['webhook_url'])
	process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

def sendPlayerWarning(db, turnData, notification_settings):
	log("Posting player warning. (%s, %s)" % (turnData['name'], notification_settings['game_id']))

	turnStartTime = convertTime(int(turnData['turn_start']))
	turnEndTime = convertTime(int(turnData['turn_end']))
	starttime = turnStartTime.strftime('%a, %b %-d at %-I:%M:%S %p')
	endtime = turnEndTime.strftime('%a, %b %-d at %-I:%M:%S %p')
	playersLeft = getPlayersLeft(turnData['players'])
	playersFormatted = []

	for player in playersLeft:
		nickname = getNickName(db, player['id'], notification_settings['game_id'])
		playersFormatted.append(player['name'] + (' (%s)' % nickname if nickname is not '' else ''))

	players = ', '.join(playersFormatted)

	variables = {
		'%TURN%': turnData['turn_num'],
		'%NAME%': turnData['name'],
		'%TURNSTART%': starttime,
		'%TURNEND%': endtime,
		'%COUNT%': len(playersLeft),
		'%PLAYERS%': players,
		'\\n': '\n'
	}

	# replace variables in text
	text = replaceArray(notification_settings['print_last_players_format'], variables)
	printColor = playersLeft[0]['color'] if len(playersLeft) is 1 else '#FFFFFF'

	if 'hooks.slack.com/services' in notification_settings['webhook_url']:
		post = {
			'username': notification_settings['webhook_name'],
			'channel': notification_settings['webhook_channel'],
			'icon_url': notification_settings['webhook_image'],
			'attachments': [{
				'color': printColor,
				'text': text,
				"mrkdwn_in": ["text"]
			}],
			'link_names': 1
		}
	elif 'discordapp.com/api/webhooks' in notification_settings['webhook_url']:
		post = {
			'username': notification_settings['webhook_name'],
			'avatar_url': notification_settings['webhook_image'],
			'embeds': [
				{
					'description': text,
					'color': long(printColor[1:], 16)
				}
			]
		}

	command = constants.WEBHOOK_CURL % (json.dumps(post), notification_settings['webhook_url'])
	process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

def getPlayersLeft(players):
	left = []
	for player in players:
		if not player['ready'] and player['status'] is 0:
			left.append(player)
	return left

def getRankDif(thisTurn, lastTurn):
	# determine rank change
	if thisTurn > lastTurn:
		return ("[-%d]" % (thisTurn - lastTurn)).encode('utf-8').strip()
	elif thisTurn < lastTurn:
		return ("[+%d]" % (lastTurn - thisTurn)).encode('utf-8').strip()
	else:
		return ""

def getNickName(db, playerId, gameId):
	db.query("SELECT * FROM player WHERE nickname IS NOT NULL AND id = %s AND game_id = '%s'" % (playerId, gameId))
	rows = db.fetch()

	if len(rows) is not 0:
		return rows[0]['nickname']
	else:
		return ''

def convertTime(timestamp):
	dt = datetime.datetime.fromtimestamp(timestamp)
	local_dt = dt - datetime.timedelta(hours=5)
	return local_dt

if __name__ == "__main__":
	main()
