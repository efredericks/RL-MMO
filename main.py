from flask import Flask, request, render_template
from flask_socketio import SocketIO, emit
from flask_apscheduler import APScheduler

import tcod

import logging

import json
import random
import uuid

# lookup table for special tiles that are walkable but can't have things placed on them
DONT_PLACE = [
#   "<", ">", 
    'stairsDown', 'stairsUp',
    'water1',
]

WALKABLE = [
#   ".", " ", "<", ">", 
    'floor1', 'floor2', 'water1', 'empty',
    'stairsDown', 'stairsUp',
]

ENEMY_DIRS = [
    {'r':-1, 'c': -1},
    {'r':-1, 'c': 0},
    {'r':-1, 'c': 1},
    {'r':0, 'c': -1},
    {'r':0, 'c': 0},
    {'r':0, 'c': 1},
    {'r':1, 'c': -1},
    {'r':1, 'c': 0},
    {'r':1, 'c': 1},
]
MAX_ENEMIES_PER_LEVEL = 20
MIN_ENEMIES_PER_LEVEL = 5

MIN_ITEMS_PER_LEVEL = 5 
MAX_ITEMS_PER_LEVEL = 10 

MSG_TIME = 5

DROP_TYPE_ID = 0
DROP_NUM_ID = 1
DROP_CHANCE_ID = 2
LOOKUP_STATS = {
    'maxHP': {
        'player': 10,
        'gobbo': 2,
        'snek': 2,
        'rat': 1,
    },
    # probably removeable as rendering is offloaded to the client now
    'sprite': {
        # moveables
        'player': '@',
        'gobbo': 'g',
        'snek': 's',
        'rat': 'r',

        # static
        'apple': 'a',
    },
    # name: list[(tuple(type, max, chance))] - random() > chance
    'drops': {
        'rat': [('apple', 1, 0.25)],
        'gobbo': [('apple', 3, 0.35)],
        'snek': [('apple', 5, 0.5)],
    }
}

# this is probably redundant and can be removed - just check for one of the other globals
ENTITY_NAMES = [
    # moveable
    'player',
    'gobbo', 'snek', 'rat',

    # static
    'apple',
]


app = Flask(__name__)
app.config['SECRET_KEY'] = 's3cr3t'

scheduler = APScheduler()
scheduler.api_enabled = True
scheduler.init_app(app)
scheduler.start()

socketio = SocketIO(app)

# Base entity class
class Entity:
    def __init__(self, _type, pos, entity_id=None, count=None):
        assert _type in ENTITY_NAMES, "Error: ${0} not found in lookup table.".format(_type)

        self.entity_id = entity_id
        self._type = _type
        self.pos = pos
        self.count = count
        self.sprite = LOOKUP_STATS['sprite'][_type]

    def getTransmissable(self):
        return {
            'type': self._type,
            'pos': self.pos,
            'count': self.count,
            'sprite': self.sprite,
        }

# Entity that can move around the screen
class MoveableEntity(Entity):
    def __init__(self, _type, pos, entity_id=None):
        super().__init__(_type, pos, entity_id)

        # particulars
        self._type = _type
        self.pos = pos
        self.last_pos = pos # used to store "prior" position when going up and down stairs
        self.entity_id = entity_id # only used for logged in players

        # stats
        self.hp = LOOKUP_STATS['maxHP'][_type]
        self.maxHP = LOOKUP_STATS['maxHP'][_type]
        self.active = True
        self.inventory = {}

        # interaction - ['msg', ticksRemaining]
        self.chatlog = []

    # chat related - only 1 can be active per entity
    def addChat(self, msg):
        self.chatlog = [msg, MSG_TIME]

    def hasChat(self):
        if len(self.chatlog) > 0:
            return True
        return False

    def updateChats(self):
        if self.hasChat():
            self.chatlog[1] -= 1
            if self.chatlog[1] <= 0:
                self.chatlog = []

    def getTransmissable(self):
        retval = {
            'type': self._type,
            'pos': self.pos,
            'hp': self.hp,
            'maxHP': self.maxHP,
            'active': self.active,
            'inventory': self.inventory,
            'sprite': self.sprite,
            'chatlog' : self.chatlog,
        }

        return retval


class Game:
    def __init__(self):
        self.NUM_ROWS = 50
        self.NUM_COLS = 50
        # self.NUM_ROWS = 1000
        # self.NUM_COLS = 1000

        self.CAM_NUM_ROWS = 20
        self.CAM_NUM_COLS = 27
        self.CAM_HALF_ROWS = self.CAM_NUM_ROWS // 2
        self.CAM_HALF_COLS = self.CAM_NUM_COLS // 2


        self.NUM_LEVELS = 3



        self.world = {}
        self.gameMap = self.initMap()
        self.world['gameMap'] = self.gameMap
        self.world['NUM_ROWS'] = self.NUM_ROWS
        self.world['NUM_COLS'] = self.NUM_COLS
        self.world['CAM_ROWS'] = self.CAM_NUM_ROWS
        self.world['CAM_COLS'] = self.CAM_NUM_COLS
        self.world['CAM_HALF_ROWS'] = self.CAM_HALF_ROWS
        self.world['CAM_HALF_COLS'] = self.CAM_HALF_COLS

        self.players = {}
        self.enemies = self.initEnemies()
        self.items = self.initItems()

        # place stairs
        self.placeStairs()

    def addPlayer(self, player_id):
        self.players[player_id] = MoveableEntity("player", self.getRandomPos(), player_id)
        # pos = self.getRandomPos()
        # self.players[player_id] = {
        #     'r': pos['r'],
        #     'c': pos['c'],
        #     'active': True,
        # }

    def removePlayer(self, player_id):
        del self.players[player_id]

    # update the game state
    def tick(self):
        # update the enemies
        for e in self.enemies:

            # random follow
            if random.random() > 0.15:
                # get closest player
                min_dist, min_id = 999, "none"

                # give the enemy some flavor
                if random.random() > 0.95 and not e.hasChat():
                    e.addChat("!~@#!")

                # filter players on current level
                # players_on_level = filter(lambda l: l.pos['level'] == e.pos['level'], self.players)
                # print(list(players_on_level))
                players_on_level = {}
                for pk,pv in self.players.items():
                    if pv.pos['level'] == e.pos['level']:
                        players_on_level[pv.entity_id] = pv

                for pid, player in players_on_level.items():#self.players.items():
                    if player.active:
                        d = abs(e.pos['c'] - player.pos['c']) + abs(e.pos['r'] - player.pos['r'])
                        if d < min_dist:
                            min_dist = d
                            min_id = pid

                if min_id in self.players:
                    player = self.players[min_id]
                    next_r = e.pos['r']
                    next_c = e.pos['c']

                    if next_r < player.pos['r']: next_r += 1
                    if next_r > player.pos['r']: next_r -= 1
                    if self.isWalkable(next_c, next_r, player.pos['level']):
                        e.pos['r'] = next_r
                        e.pos['c'] = next_c

                    if next_c < player.pos['c']: next_c += 1
                    if next_c > player.pos['c']: next_c -= 1
                    if self.isWalkable(next_c, next_r, player.pos['level']):
                        e.pos['r'] = next_r
                        e.pos['c'] = next_c

            # random movement
            elif random.random() > 0.5:
                new_dir = random.choice(ENEMY_DIRS)
                new_pos = {'r': e.pos['r'] + new_dir['r'], 'c': e.pos['c'] + new_dir['c']}

                if self.isWalkable(new_pos['c'], new_pos['r'], e.pos['level']):
                    e.pos['r'] = new_pos['r']
                    e.pos['c'] = new_pos['c']

            e.updateChats()
        # repopulate
        # TBD - this needs to be on a per-level basis
        # need to filter based on level
        # if len(self.enemies) < MIN_ENEMIES_PER_LEVEL:
        #     if random.random() > 0.5:
        #         self.enemies.append(self.addEnemy("snek"))
                # out of program scope -- need to figure out how to incorporate the socket
                # in the scheduler
                # emit('serverResponse', {'resp': 'monsterSpawn'})

        # update loop for all players
        for k, p in self.players.items():
            p.updateChats()


    def placeStairs(self):
        # down
        for z in range(self.NUM_LEVELS-1):
            stair_pos = self.getRandomPos(z)
            self.gameMap[z][stair_pos['r']][stair_pos['c']] = "stairsDown"

        # up
        for z in range(1, self.NUM_LEVELS):
            stair_pos = self.getRandomPos(z)
            self.gameMap[z][stair_pos['r']][stair_pos['c']] = "stairsUp"

    def initMap(self):
        _map = []
        for z in range(self.NUM_LEVELS):
            _map.append([])

            for r in range(self.NUM_ROWS):
                _map[z].append([])
                for c in range(self.NUM_COLS):
                    if r == 0 or c == 0 or r == self.NUM_ROWS-1 or c == self.NUM_COLS-1:
                        _map[z][r].append("water2")
                    elif r == 1 or c == 1 or r == self.NUM_ROWS-2 or c == self.NUM_COLS-2:
                        # _map[z][r].append(random.choice(['floor1', 'floor2']))
                        _map[z][r].append('water1')
                    else:
                        # random placement
                        if random.random() > 0.9:
                            _map[z][r].append("wall2")
                        else:
                            _map[z][r].append("empty")
        return _map

    def initEnemies(self):
        _enemies = []

        for z in range(self.NUM_LEVELS):
            if z == 0:
                for _ in range(random.randint(MIN_ENEMIES_PER_LEVEL, MAX_ENEMIES_PER_LEVEL)):
                    _enemies.append(self.addEnemy("rat", self.getRandomPos(z)))
            elif z == 1:
                for _ in range(random.randint(MIN_ENEMIES_PER_LEVEL, MAX_ENEMIES_PER_LEVEL)):
                    _enemies.append(self.addEnemy("gobbo", self.getRandomPos(z)))
            else:
                for _ in range(random.randint(MIN_ENEMIES_PER_LEVEL, MAX_ENEMIES_PER_LEVEL)):
                    _enemies.append(self.addEnemy("snek", self.getRandomPos(z)))
        
        return _enemies

    def initItems(self):
        _items = []
        for _ in range(random.randint(MIN_ITEMS_PER_LEVEL, MAX_ITEMS_PER_LEVEL)): # TBD - relate to level
            _items.append(self.addItem())
        return _items

    def addItem(self, _type="apple", pos=None):
        if pos == None:
            pos = self.getRandomPos()
        return Entity(_type, pos, str(uuid.uuid4()))

    def addEnemy(self, _type, pos):
        return MoveableEntity(_type, pos, str(uuid.uuid4()))

        # pos = self.getRandomPos()
        # return pos

    # can walk
    def isWalkable(self, c, r, z):
        if c >= 0 and c <= self.NUM_COLS-1 and r >= 0 and r <= self.NUM_ROWS-1 and self.gameMap[z][r][c] in WALKABLE:#!= "#":
            return True
        return False

    # can place things
    def isPlaceable(self, c, r, z):
        if self.gameMap[z][r][c] not in DONT_PLACE:
            return True
        return False

    # in bounds and walkable
    def isValid(self, pid, c, r, z):
        # in bounds / walkable
        if self.isWalkable(c, r, z):
            # check for other players that are active 
            for other_pid, other_player in self.players.items():
                if other_pid != pid and other_player.active and other_player.pos['c'] == c and other_player.pos['r'] == r:
                    return False

            return True

        return False

    def getRandomPos(self, level=0):
        r = random.randint(0,self.NUM_ROWS-1)
        c = random.randint(0,self.NUM_COLS-1)
        while not self.isWalkable(c, r, level) or not self.isPlaceable(c, r, level):
            r = random.randint(0,self.NUM_ROWS-1)
            c = random.randint(0,self.NUM_COLS-1)
        return {'r': r, 'c': c, 'level': level}

    # if player is meditating then they still view updates but are not impacted by what they see
    # this should probably be on a cooldown to avoid abuse
    def meditatePlayer(self, pid):
        self.players[pid].active = not self.players[pid].active

    # handle a new chat message
    def playerAddChat(self, pid, msg):
        self.players[pid].addChat(msg)

    # go up a level
    def ascendPlayer(self, pid):
        pos = self.players[pid].pos

        if self.gameMap[pos['level']][pos['r']][pos['c']] == 'stairsUp':
            nextZ = pos['level'] - 1
            new_pos = self.getRandomPos(nextZ)

            self.players[pid].last_pos = pos
            self.players[pid].pos = new_pos
            self.players[pid].pos['level'] = nextZ

            return True
        return False

    # go down a level
    def descendPlayer(self, pid):
        pos = self.players[pid].pos

        if self.gameMap[pos['level']][pos['r']][pos['c']] == 'stairsDown':
            nextZ = pos['level'] + 1
            new_pos = self.getRandomPos(nextZ)

            self.players[pid].last_pos = pos
            self.players[pid].pos = new_pos
            self.players[pid].pos['level'] = nextZ
            return True
        return False

    def pickupItem(self, pid):
        pos = self.players[pid].pos
        idx = -1
        valid = False
        for i in range(len(self.items)):
            item = self.items[i]
            if item.pos['c'] == pos['c'] and item.pos['r'] == pos['r']:
                idx = i

                if item._type in self.players[pid].inventory:
                    self.players[pid].inventory[item._type] += 1
                else:
                    self.players[pid].inventory[item._type] = 1

                valid = True

                break


        if idx != -1:
            del self.items[idx]
        return valid

    def hasEnemy(self, pid, c, r, l):
        idx = -1
        for i in range(len(self.enemies)):
            e = self.enemies[i]
            if e.pos['c'] == c and e.pos['r'] == r and e.pos['level'] == l:
                idx = i

        if idx != -1:
            epos = self.enemies[idx].pos
            drop = random.choice(LOOKUP_STATS['drops'][self.enemies[idx]._type])
            if random.random() > drop[DROP_CHANCE_ID]:
                self.items.append(self.addItem(drop[DROP_TYPE_ID], epos))

            del self.enemies[idx]
            return True
        return False


    def tryMove(self, pid, c, r):
        next_c = self.players[pid].pos['c'] + c
        next_r = self.players[pid].pos['r'] + r

        # wake up on move attempt
        self.players[pid].active = True 

        attackVal = self.hasEnemy(pid, next_c, next_r, self.players[pid].pos['level'])
        if attackVal:
            # no movement, attack handled elsewhere
            # but send to client for sound
            emit('serverResponse', {'resp': 'playerHitMonster'})

        elif self.isValid(pid, next_c, next_r, self.players[pid].pos['level']):
            self.players[pid].pos['c'] = next_c
            self.players[pid].pos['r'] = next_r

    # getters/setters
    def getJSONWorld(self):
        return json.dumps(self.world)#gameMap)

    def getJSONPlayers(self, level):
        op = {}
        for k,v in self.players.items():
            if v.pos['level'] == level:
                op[v.entity_id] = v.getTransmissable()

        return json.dumps(op)

    def getJSONEnemies(self, level):
        op = {}
        for v in self.enemies:
            if v.pos['level'] == level:
                op[v.entity_id] = v.getTransmissable()
        return json.dumps(op)
    
    def getJSONItems(self, level):
        op = {}
        for v in self.items:
            if v.pos['level'] == level:
                op[v.entity_id] = v.getTransmissable()
        return json.dumps(op)

# TBD - turn into a db of some sort to avoid process issues
game = Game()
scheduler.add_job(func=game.tick, id='gametick', trigger='interval', seconds=1, misfire_grace_time=200, )

@app.route("/")
def index():
    return render_template('index.html')

@socketio.on('my event')
def test_message(msg):
    print(msg)
    emit('my response', {'data': msg['data']})

@socketio.on('my broadcast event')
def test_message(msg):
    emit('my response', {'data': msg['data']}, broadcast=True)

@socketio.on('connect')
def test_connect():
    global game
    game.addPlayer(request.sid) # replace with session id
    print('User connected, sending map.')
    emit('mapload', {
        'playerID': request.sid,
        'players': game.getJSONPlayers(level=0), 
        'world': game.getJSONWorld(),
        'enemies': game.getJSONEnemies(level=0),
        'items': game.getJSONItems(level=0),
    })

# put them to "sleep"
@socketio.on('meditateplayer')
def meditate_player(msg):
    global game
    if msg['playerID'] in game.players:
        game.meditatePlayer(msg['playerID'])

# pickup item under the player
@socketio.on('pickupitem')
def meditate_player(msg):
    global game
    if msg['playerID'] in game.players:
        resp = game.pickupItem(msg['playerID'])
        if resp:
            emit('serverResponse', {'resp': 'pickupSuccess'})

    # emit('my response', {'data': msg['data']})

# player is sending a chat message
@socketio.on('chatRequest')
def handle_chat(msg):
    global game
    if msg['playerID'] in game.players:
        game.playerAddChat(msg['playerID'], msg['chatMessage'])

@socketio.on('ascendplayer')
def ascend_player(msg):
    global game
    if msg['playerID'] in game.players:
        resp = game.ascendPlayer(msg['playerID'])
        if resp:
            emit('serverResponse', {'resp': 'stairUpSuccess'})

@socketio.on('descendplayer')
def descend_player(msg):
    global game
    if msg['playerID'] in game.players:
        resp = game.descendPlayer(msg['playerID'])
        if resp:
            emit('serverResponse', {'resp': 'stairDownSuccess'})

@socketio.on('moveplayer')
def move_player(msg):
    global game
    if msg['playerID'] in game.players:
        game.tryMove(msg['playerID'], msg['c'], msg['r'])

@socketio.on('tickRequest')
def sendTick(msg):
    global game
    # game.tick()

    # only send updates for those players on the current level
    if msg['playerID'] in game.players:
        level = game.players[msg['playerID']].pos['level']
        emit('tick', {
            'players': game.getJSONPlayers(level), 
            'enemies': game.getJSONEnemies(level),
            'items': game.getJSONItems(level),
        })

@socketio.on('disconnect')
def test_disconnect():
    global game

    print('Client disconnected.')
    game.removePlayer(request.sid)

if __name__ == '__main__':
    app.debug = True

    # disable get/post messages for python debugging
    log = logging.getLogger("werkzeug")
    log.disabled = True

    socketio.run(app)
