from flask import Flask, request, render_template
from flask_socketio import SocketIO, emit
from flask_apscheduler import APScheduler

import json
import random
import uuid

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

LOOKUP_STATS = {
    'maxHP': {
        'player': 10,
        'gobbo': 2,
        'snek': 2,
        'rat': 1,
    }
}
ENTITY_NAMES = [
    'player',
    'gobbo', 'snek', 'rat',
]

app = Flask(__name__)
app.config['SECRET_KEY'] = 's3cr3t'

scheduler = APScheduler()
scheduler.api_enabled = True
scheduler.init_app(app)
scheduler.start()

socketio = SocketIO(app)

# Entity that can move around the screen
class MoveableEntity:
    def __init__(self, _type, pos, entity_id=None):
        assert _type in ENTITY_NAMES, "Error: ${0} not found in lookup table.".format(_type)

        # particulars
        self._type = _type
        self.pos = pos
        self.entity_id = entity_id # only used for logged in players

        # stats
        self.hp = LOOKUP_STATS['maxHP'][_type]
        self.maxHP = LOOKUP_STATS['maxHP'][_type]
        self.active = True
        self.inventory = {}

    def getTransmissable(self):
        return {
            'type': self._type,
            'pos': self.pos,
            'hp': self.hp,
            'maxHP': self.maxHP,
            'active': self.active
        }


class Game:
    def __init__(self):
        self.NUM_ROWS = 20
        self.NUM_COLS = 27
        self.gameMap = self.initMap()
        self.players = {}
        self.enemies = self.initEnemies()
        self.items = {}


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
                for pid, player in self.players.items():
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
                    if self.isWalkable(next_c, next_r):
                        e.pos['r'] = next_r
                        e.pos['c'] = next_c

                    if next_c < player.pos['c']: next_c += 1
                    if next_c > player.pos['c']: next_c -= 1
                    if self.isWalkable(next_c, next_r):
                        e.pos['r'] = next_r
                        e.pos['c'] = next_c

            # random movement
            elif random.random() > 0.5:
                new_dir = random.choice(ENEMY_DIRS)
                new_pos = {'r': e.pos['r'] + new_dir['r'], 'c': e.pos['c'] + new_dir['c']}

                if self.isWalkable(new_pos['c'], new_pos['r']):
                    e.pos['r'] = new_pos['r']
                    e.pos['c'] = new_pos['c']

        # repopulate
        if len(self.enemies) < MIN_ENEMIES_PER_LEVEL:
            if random.random() > 0.5:
                self.enemies.append(self.addEnemy())



    def initMap(self):
        _map = []
        for r in range(self.NUM_ROWS):
            _map.append([])
            for c in range(self.NUM_COLS):
                if r == 0 or c == 0 or r == self.NUM_ROWS-1 or c == self.NUM_COLS-1:
                    _map[r].append("#")
                else:
                    if random.random() > 0.9:
                        _map[r].append("#")
                    else:
                        _map[r].append(".")
        return _map

    def initEnemies(self):
        _enemies = []
        for _ in range(random.randint(MIN_ENEMIES_PER_LEVEL, MAX_ENEMIES_PER_LEVEL)): # TBD - relate to level
            _enemies.append(self.addEnemy())
        return _enemies

    def addEnemy(self):
        return MoveableEntity("snek", self.getRandomPos(), str(uuid.uuid4()))

        # pos = self.getRandomPos()
        # return pos

    def isWalkable(self, c, r):
        if c >= 0 and c <= self.NUM_COLS-1 and r >= 0 and c <= self.NUM_ROWS-1 and self.gameMap[r][c] != "#":
            return True
        return False

    # in bounds and walkable
    def isValid(self, pid, c, r):
        # in bounds / walkable
        if self.isWalkable(c, r):
            # check for other players that are active 
            for other_pid, other_player in self.players.items():
                if other_pid != pid and other_player.active and other_player.pos['c'] == c and other_player.pos['r'] == r:
                    return False

            return True

        return False

    def getRandomPos(self):
        r = random.randint(0,self.NUM_ROWS-1)
        c = random.randint(0,self.NUM_COLS-1)
        while not self.isWalkable(c, r):
            r = random.randint(0,self.NUM_ROWS-1)
            c = random.randint(0,self.NUM_COLS-1)
        return {'r': r, 'c': c}

    # if player is meditating then they still view updates but are not impacted by what they see
    # this should probably be on a cooldown to avoid abuse
    def meditatePlayer(self, pid):
        self.players[pid].active = not self.players[pid].active

    def hasEnemy(self, pid, c, r):
        idx = -1
        for i in range(len(self.enemies)):
            e = self.enemies[i]
            if e.pos['c'] == c and e.pos['r'] == r:
                idx = i

        if idx != -1:
            del self.enemies[idx]
            return True
        return False


    def tryMove(self, pid, c, r):
        next_c = self.players[pid].pos['c'] + c
        next_r = self.players[pid].pos['r'] + r

        # wake up on move attempt
        self.players[pid].active = True 

        if self.hasEnemy(pid, next_c, next_r):
            pass  # no movement, attack handled elsewhere

        elif self.isValid(pid, next_c, next_r):
            self.players[pid].pos['c'] = next_c
            self.players[pid].pos['r'] = next_r

    # getters/setters
    def getJSONMap(self):
        return json.dumps(self.gameMap)
    def getJSONPlayers(self):
        op = {}
        for k,v in self.players.items():
            op[v.entity_id] = v.getTransmissable()
        return json.dumps(op)
        # return json.dumps(self.players)
    def getJSONEnemies(self):
        op = {}
        for v in self.enemies:
            op[v.entity_id] = v.getTransmissable()
        return json.dumps(op)
        # return json.dumps(self.enemies)

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
        'players': game.getJSONPlayers(), 
        'map': game.getJSONMap(),
        'enemies': game.getJSONEnemies(),
    })

# put them to "sleep"
@socketio.on('meditateplayer')
def meditate_player(msg):
    global game
    if msg['playerID'] in game.players:
        game.meditatePlayer(msg['playerID'])

@socketio.on('moveplayer')
def move_player(msg):
    global game
    if msg['playerID'] in game.players:
        game.tryMove(msg['playerID'], msg['c'], msg['r'])

@socketio.on('tickRequest')
def sendTick():
    global game
    # game.tick()

    emit('tick', {
        # 'playerID': request.sid,
        'players': game.getJSONPlayers(), 
        'enemies': game.getJSONEnemies(),
        # 'map': game.getJSONMap()
    })

@socketio.on('disconnect')
def test_disconnect():
    global game

    print('Client disconnected.')
    game.removePlayer(request.sid)

if __name__ == '__main__':
    app.debug = True
    socketio.run(app)