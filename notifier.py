import subprocess, time, json, datetime, os, sys, re
import constants, auth, notifier, gameUtil
from database import Database
from util import *

def sendTurn(db, turnData, notification_settings, gameOver):
	log("Posting game new turn %d. (%s, %s)" % (turnData['turn_num'], turnData['name'], notification_settings['game_id']))
	# sort players by rank
	players = sorted(turnData['players'], key=lambda k: k['rank'])
	attachments = []

	isSlack = 'hooks.slack.com/services' in notification_settings['webhook_url']
	isDiscord = 'discord.com/api/webhooks' in notification_settings['webhook_url']

	if notification_settings['print_leaderboard']:
		for player in players:
			status = "AI: " if player['status'] is not 0 else ""
			nickname = gameUtil.getNickName(db, player['id'], notification_settings['game_id'])
			player['nickname'] = nickname

			# player is still alive
			if player['total_stars'] is not 0 or player['total_ships'] is not 0:
				hasDiscordNickname = re.match(r"<@[0-9!]{12,}>", nickname)

				rankDif = gameUtil.getRankDif(player['rank'], player['rank_last']) if 'rank_last' in player else ""
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

				if isSlack:
					attachments.append({
						'color': player['color'],
						'title': title,
						'text': text,
						"mrkdwn_in": ["text"]
					})
				elif isDiscord:
					attachments.append({
						'description': text,
						'title': title,
						'color': long(player['color'][1:], 16)
					})
			# player is dead
			else:
				title = '%d. %s%s' % (player['rank'], status, player['name'])

				if isSlack:
					attachments.append({
						'color': '#999999',
						'title': title
					})
				elif isDiscord:
					attachments.append({
						'color': long('999999', 16),
						'title': title
					})

	turnStartTime = convertTime(int(turnData['turn_start']))
	turnEndTime = convertTime(int(turnData['turn_end']))
	starttime = turnStartTime.strftime('%a, %b %-d at %-I:%M:%S %p')
	endtime = turnEndTime.strftime('%a, %b %-d at %-I:%M:%S %p')

	namelink = "[%s](https://np.ironhelmet.com/game/%s)" % (turnData['name'], turnData['game_id'])
	if isSlack:
		namelink = "<https://np.ironhelmet.com/game/%s|%s>" % (turnData['game_id'], turnData['name'])

	variables = {
		'%TURN%': turnData['turn_num'],
		'%NAME%': turnData['name'],
		'%NAMELINK%': namelink,
		'%TURNSTART%': starttime,
		'%TURNEND%': endtime,
		'\\n': '\n'
	}

	if gameOver:
		variables['%WINNER%'] = "%s%s" % (players[0]['name'], ' (%s)' % players[0]['nickname'] if players[0]['nickname'] is not '' else '')

	# replace variables in text
	textFormat = notification_settings['print_turn_start_format'] if not gameOver else notification_settings['print_game_over_format']
	text = replaceArray(textFormat, variables)

	posts = []
	if isSlack:
		posts.append({
			'username': notification_settings['webhook_name'],
			'channel': notification_settings['webhook_channel'],
			'icon_url': notification_settings['webhook_image'],
			'attachments': attachments,
			'link_names': 1,
			'text': text
		})

	elif isDiscord:
		if len(attachments) > 10:
			groupSize = 8
			attachmentGroups = zip(*(iter(attachments),) * groupSize)

			first = True
			for group in attachmentGroups:
				posts.append({
					'username': notification_settings['webhook_name'],
					'avatar_url': notification_settings['webhook_image'],
					'content': text if first else '',
					'embeds': group
				})
				first = False
		else:
			posts.append({
				'username': notification_settings['webhook_name'],
				'avatar_url': notification_settings['webhook_image'],
				'content': text,
				'embeds': attachments
			})

	for post in posts:
		command = constants.WEBHOOK_CURL % (json.dumps(post), notification_settings['webhook_url'])
		process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
		if (len(posts)):
			time.sleep(5)

def sendPlayerTurn(db, playerData, turnData, notification_settings, lastPlayer = False):
	log("Posting %s's turn %d. (%s, %s)" % (playerData['name'], turnData['turn_num'] - (1 if lastPlayer else 0), turnData['name'], notification_settings['game_id']))
	nickname = gameUtil.getNickName(db, playerData['id'], notification_settings['game_id'])

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

	elif 'discord.com/api/webhooks' in notification_settings['webhook_url']:
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
	playersLeft = gameUtil.getPlayersLeft(turnData['players'])
	playersFormatted = []

	for player in playersLeft:
		nickname = gameUtil.getNickName(db, player['id'], notification_settings['game_id'])
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
	elif 'discord.com/api/webhooks' in notification_settings['webhook_url']:
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
	playersLeft = gameUtil.getPlayersLeft(turnData['players'])
	playersFormatted = []

	for player in playersLeft:
		nickname = gameUtil.getNickName(db, player['id'], notification_settings['game_id'])
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
	elif 'discord.com/api/webhooks' in notification_settings['webhook_url']:
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
