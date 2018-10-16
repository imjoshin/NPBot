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
