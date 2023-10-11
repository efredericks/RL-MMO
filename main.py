"""
THINGS TO BE DONE
* loot (armor, weapons, etc)
* NPCs with lines of dialogue
* sub-levels
* having the player's position be remembered
* experience points


TODAY: 
- enemy moving in x's (perhaps subclass out enemies)
- mana bar
- hp bars on entities
- xp for mana/hp
- xp per enemy
- elemental resists (color drop shadow on player for pickups?)

"""


from flask import Flask, request, render_template
from flask_socketio import SocketIO, emit
from engineio.payload import Payload
from flask_apscheduler import APScheduler

from pathfinding import *

import tcod, opensimplex

import logging

import json
import random
import uuid

from copy import deepcopy

from globals import *
from entities import *


# utility functions
# map function similar to p5.js
def p5map(n, start1, stop1, start2, stop2): 
    return ((n - start1) / (stop1 - start1)) * (stop2 - start2) + start2

app = Flask(__name__)
app.config['SECRET_KEY'] = 's3cr3t'

scheduler = APScheduler()
scheduler.api_enabled = True
scheduler.init_app(app)
scheduler.start()

Payload.max_decode_packets = 2048
socketio = SocketIO(app)

opensimplex.seed(1)

class Game:
    def __init__(self, scheduler):


        self.NUM_ROWS = 100#50
        self.NUM_COLS = 100#50
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

        self.enemies = {}
        for z in range(self.NUM_LEVELS): self.enemies[z] = []
        self.initEnemies()

        self.items = self.initItems()
        self.effects = []

        # place stairs
        self.placeStairs()

        # repopulation tick
        self.RESPAWN_TIMER = 0

        # schedule jobs
        ### DOES THIS SLOW THINGS DOWN TOO MUCH?!?!?!
        self.scheduler = scheduler
        self.scheduler.add_job(func=self.tick, id='gametick', trigger='interval', seconds=1, misfire_grace_time=200, )
        for z in range(self.NUM_LEVELS):
            self.scheduler.add_job(func=self.enemyTick, args=[z], id='enemytick-{0}'.format(z), trigger='interval', seconds=1, misfire_grace_time=200, )



    def addPlayer(self, player_id):
        self.players[player_id] = Player("player", self.getRandomPos(), player_id, "mage", self)
        # self.players[player_id] = MoveableEntity("player", self.getRandomPos(), player_id, "mage")
        # self.players[player_id].hp = 2
        # pos = self.getRandomPos()
        # self.players[player_id] = {
        #     'r': pos['r'],
        #     'c': pos['c'],
        #     'active': True,
        # }

    def removePlayer(self, player_id):
        del self.players[player_id]

    def enemyTick(self, lvl):
        # update where players are by level
        players_by_level = {}
        # for z in range(self.NUM_LEVELS):
        #     players_by_level[z] = {}

        for pk, pv in self.players.items():
            if pv.pos['level'] == lvl:
                players_by_level[pv.entity_id] = pv

        for e in self.enemies[lvl]:
            e.update(players_by_level)

    # update the game state
    def tick(self):
        # update where players are by level
        # players_by_level = {}
        # for z in range(self.NUM_LEVELS):
        #     players_by_level[z] = {}

        # for pk, pv in self.players.items():
        #     players_by_level[pv.pos['level']][pv.entity_id] = pv


        # update effects
        effect_ids = []
        for i in range(len(self.effects)):
            e = self.effects[i]
            if e.timer is not None and e.timer > 0:
                e.timer -= 1

            # delete this effect afterwards
            if e.timer <= 0:
                effect_ids.append(i)

            else: # impact enemies/players
                for _ in self.enemies[e.pos['level']]:
                    attackVal = self.hasEnemy(None, e.pos['c'], e.pos['r'], e.pos['level'], LOOKUP_STATS['effects'][e._type]['hp'])
                    # if attackVal:
                        # send to client for sound
                        # emit('serverResponse', {'resp': 'playerHitMonster'})

        # iterate backwards over list
        if len(effect_ids) > 0:
            for i in range(len(effect_ids)-1, -1, -1):
                del self.effects[effect_ids[i]]


        # players_by_level = {}
        # for pk,pv in self.players.items():
        #     players_by_level[pv.pos['level']][pv.entity_id] = pv

        # update the enemies
        # this should be offloaded to the particular classes!!
        # for ek, ev in self.enemies.items():
        #     for e in ev:
        #         e.update(players_by_level)

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
            p.update()

        # check for blood moon respawn event
        self.RESPAWN_TIMER += 1
        print(self.RESPAWN_TIMER)
        if self.RESPAWN_TIMER >= RESPAWN_TIME_CHECK:
            self.RESPAWN_TIMER = 0
            print("RESPAWNING!")
            self.initEnemies()



    def placeStairs(self):
        # down
        for z in range(self.NUM_LEVELS-1):
            stair_pos = self.getRandomPos(z)
            self.gameMap[z][stair_pos['r']][stair_pos['c']] = "stairsDown"

        # up
        for z in range(1, self.NUM_LEVELS):
            stair_pos = self.getRandomPos(z)
            self.gameMap[z][stair_pos['r']][stair_pos['c']] = "stairsUp"

    def simplexMap(self, z):
        _map = []
        zoom = p5map(z, 0, self.NUM_LEVELS, 0.1, 0.001)
        for r in range(self.NUM_ROWS):
            _map.append([])
            for c in range(self.NUM_COLS):
                if r == 0 or c == 0 or r == self.NUM_ROWS-1 or c == self.NUM_COLS-1:
                    _map[r].append("water2")
                elif r == 1 or c == 1 or r == self.NUM_ROWS-2 or c == self.NUM_COLS-2:
                    # _map[z][r].append(random.choice(['floor1', 'floor2']))
                    _map[r].append('water1')
                else:
                    n = opensimplex.noise2(c*zoom, r*zoom)#c*0.1, r*0.1)
                    newtile = "empty"
                    if n < -0.8 or n > 0.8:
                        newtile = "water2"
                    elif n < -0.6 or n > 0.6:
                        newtile = "water1"
                    elif n < -0.4 or n > 0.4:
                        newtile = "floor2"
                    elif n < -0.2 or n > 0.2:
                        newtile = "floor1"
                    else:#if n < -0.2 or n > 0.2:
                        newtile = random.choice(['tree1','tree2'])#"tree"

                    _map[r].append(newtile)
                    # random placement
                    # if random.random() > 0.9:
                    #     _map[z][r].append("wall2")
                    # else:
                    #     _map[z][r].append("empty")
        return _map

    # https://abitawake.com/news/articles/procedural-generation-with-godot-creating-caves-with-cellular-automata
    ## cellular automata functions
    def fillWalls(self):
        return [['wall1'] * self.NUM_COLS for _ in range(self.NUM_ROWS)]

    def checkNearby(self, x, y, _map):
        count = 0
        if _map[y-1][x] == 'empty': count += 1
        if _map[y+1][x] == 'empty': count += 1
        if _map[y][x-1] == 'empty': count += 1
        if _map[y][x+1] == 'empty': count += 1
        if _map[y-1][x+1] == 'empty': count += 1
        if _map[y-1][x+1] == 'empty': count += 1
        if _map[y+1][x-1] == 'empty': count += 1
        if _map[y+1][x-1] == 'empty': count += 1
        return count

    def digCaves(self, _map, iterations, neighbors):
        for _ in range(iterations):
            x = random.randint(1, self.NUM_COLS-2)
            y = random.randint(1, self.NUM_ROWS-2)

            if self.checkNearby(x, y, _map) > neighbors:
                _map[y][x] = 'wall2'
            elif self.checkNearby(x, y, _map) < neighbors:
                _map[y][x] = 'empty'

    def randomGround(self, _map):
        for y in range(1, self.NUM_COLS-2):
            for x in range(1, self.NUM_ROWS-2):
                if random.random() > 0.4:
                    _map[y][x] = 'empty'


    def floodFill(self, _map, caves, x, y):
        min_cave_size = 80
        cave = []
        to_fill = [{'x': x, 'y': y}]

        while to_fill:
            tile = to_fill.pop()

            if not tile in cave:
                cave.append(tile)
                _map[tile['y']][tile['x']] = 'wall2'

                north = {'x': tile['x'], 'y': tile['y']-1}
                south = {'x': tile['x'], 'y': tile['y']+1}
                east = {'x': tile['x']+1, 'y': tile['y']}
                west = {'x': tile['x']-1, 'y': tile['y']}

                for dir in [north, south, east, west]:
                    if _map[dir['y']][dir['x']] == 'empty':
                        if not dir in to_fill and not dir in cave:
                            to_fill.append(dir)

        if len(cave) >= min_cave_size:
            caves.append(cave)

    def getCaves(self, _map):
        caves = []

        for y in range(self.NUM_ROWS):
            for x in range(self.NUM_COLS):
                if _map[y][x] == 'empty':
                    self.floodFill(_map, caves, x, y)

        for cave in caves:
            for c in cave:
                _map[c['y']][c['x']] = 'empty'

        return caves
        
    def createTunnel(self, _map, point1, point2, cave):
        max_steps = 500
        steps = 0
        drunk_x = point2['x']
        drunk_y = point2['y']

        while steps < max_steps and not {'x':drunk_x, 'y':drunk_y} in cave:
            steps += 1
            n = 1.0
            s = 1.0
            e = 1.0
            w = 1.0
            weight = 1

            if drunk_x < point1['x']:
                e += weight
            elif drunk_x > point1['x']:
                w += weight

            if drunk_y < point1['y']:
                s += weight
            elif drunk_y > point1['y']:
                n += weight
            tot = n + s + e + w
            n /= tot
            s /= tot
            e /= tot
            w /= tot

            dx = 0
            dy = 0
            choice = random.random()
            if 0 <= choice and choice < n:
                dx = 0
                dy = -1
            elif n <= choice and choice < (n+s):
                dx = 0
                dy = 1
            elif (n+s) <= choice and choice < (n+s+e):
                dx = 1
                dy = 0
            else:
                dx = -1
                dy = 0

            if (2 < drunk_x + dx and drunk_x + dx < self.NUM_COLS-2) and (2 < drunk_y + dy and drunk_y + dy < self.NUM_ROWS-2):
                drunk_x += dx
                drunk_y += dy

                if _map[drunk_y][drunk_x] == 'wall2':
                    _map[drunk_y][drunk_x] = 'empty'

                    _map[drunk_y+1][drunk_x+1] = 'empty'
                    _map[drunk_y][drunk_x+1] = 'empty'





    def connectCaves(self, _map, caves):
        prev_cave = None
        tunnel_caves = deepcopy(caves)

        for cave in tunnel_caves:
            if prev_cave:
                new_point = random.choice(cave)
                prev_point = random.choice(prev_cave)

                if new_point != prev_point:
                    self.createTunnel(_map, new_point, prev_point, cave)
            prev_cave = cave

    def cellularAutomata(self, z):
        _map = [['wall2'] * self.NUM_COLS for _ in range(self.NUM_ROWS)]

        iterations = 20000
        neighbors = 4
        center_c = self.NUM_COLS//2
        center_r = self.NUM_ROWS//2
        ground_chance = 48
        min_cave_size = 80

        self.randomGround(_map)
        self.digCaves(_map, iterations, neighbors)
        caves = self.getCaves(_map)
        self.connectCaves(_map, caves)

        return _map

    ######


    def drunkardsMap(self, z):
        _map = self.fillWalls()#[['wall2'] * self.NUM_COLS for _ in range(self.NUM_ROWS)]

        center_c = self.NUM_COLS//2
        center_r = self.NUM_ROWS//2

        for _ in range(DRUNK_ITERATIONS):
            curr_c = center_c
            curr_r = center_r
            DRUNK_LIFETIME = self.NUM_COLS * self.NUM_ROWS
            # DRUNK_LIFETIME = max(self.NUM_COLS, self.NUM_ROWS)

            for i in range(DRUNK_LIFETIME):
                _map[curr_r][curr_c] = random.choice(['empty', 'empty', 'floor1', 'floor1', 'floor2'])

                new_dir = random.choice(ENEMY_DIRS)
                curr_r += new_dir['r']
                curr_c += new_dir['c']

                # out of bounds
                if curr_c == 0 or curr_r == 1 or curr_c == self.NUM_COLS-1 or curr_r == self.NUM_ROWS-1:
                    break

        return _map

    def initMap(self):
        _map = []

        for z in range(self.NUM_LEVELS):
            if z == 0:
                # _map.append(self.cellularAutomata(z))
                _map.append(self.simplexMap(z))
            else:
                _map.append(self.drunkardsMap(z))

        return _map

    def initEnemies(self):
        # _enemies = {}

        for z in range(self.NUM_LEVELS):
            self.enemies[z] = []
            if z == 0:

                e = self.addEnemy("slimeMold", self.getRandomPos(z))
                print(e.pos)
                if e is not None:
                    self.enemies[z].append(e)

                #e = self.addEnemy("slimeMold", self.getRandomPos(z))
                #print(e.pos)
                #_enemies.append(e)

                for _ in range(random.randint(MIN_ENEMIES_PER_LEVEL, MAX_ENEMIES_PER_LEVEL)):
                    e = self.addEnemy("rat", self.getRandomPos(z))
                    if e is not None:
                        self.enemies[z].append(e)
            elif z == 1:
                for _ in range(random.randint(MIN_ENEMIES_PER_LEVEL, MAX_ENEMIES_PER_LEVEL)):
                    e =self.addEnemy("gobbo", self.getRandomPos(z))
                    if e is not None:
                        self.enemies[z].append(e)
            else:
                for _ in range(random.randint(MIN_ENEMIES_PER_LEVEL, MAX_ENEMIES_PER_LEVEL)):
                    e = self.addEnemy("snek", self.getRandomPos(z))
                    if e is not None:
                        self.enemies[z].append(e)

        # debug
        op = ""
        for z in range(len(self.enemies)):
            op += "[{0}:{1}] ".format(z, len(self.enemies[z]))
        print(op)
        # return _enemies

    def initItems(self):
        _items = []
        for _ in range(random.randint(MIN_ITEMS_PER_LEVEL, MAX_ITEMS_PER_LEVEL)): # TBD - relate to level
            _items.append(self.addItem())
        return _items

    def addItem(self, _type="apple", pos=None):
        if pos == None:
            pos = self.getRandomPos()
        return Entity(_type, pos, str(uuid.uuid4()))

    def addEffect(self, _type, pos=None):
        if pos == None:
            pos = self.getRandomPos()
        return Effect(_type, pos, str(uuid.uuid4()))

    def addEnemy(self, _type, pos):
        if len(self.enemies[pos['level']]) < MAX_ENEMIES_PER_LEVEL:
            if _type == "slimeMold":
                return SlimeMold(_type, pos, str(uuid.uuid4()), self)
            else:
                return Monster(_type, pos, str(uuid.uuid4()), self)
        else:
            return None

    # lookup function for players on level
    def getPlayersOnLevel(self, z):
        players_by_level = {}
        for pk, pv in self.players.items():
            if pv.pos['level'] == z:
                players_by_level[pv.entity_id] = pv
        return players_by_level


    # can walk
    def isWalkable(self, c, r, z):
        if c >= 0 and c <= self.NUM_COLS-1 and r >= 0 and r <= self.NUM_ROWS-1 and self.gameMap[z][r][c] in WALKABLE:#!= "#":
            return True
        return False

    # ensure there is nothing on the cell aside from items
    def isEmpty(self, c, r, z):
        if self.isWalkable(c, r, z) and self.isPlaceable(c, r, z):
            # no players
            players_by_level = self.getPlayersOnLevel(z)
            for pk, pv in players_by_level.items():
                if pv.pos['c'] == c and pv.pos['r'] == r and pv.pos['level'] == z:
                    return False

            # no enemies
            for i in range(len(self.enemies[z])):
                e = self.enemies[z][i]
                if e.pos['c'] == c and e.pos['r'] == r and e.pos['level'] == z:
                    return False

        return True

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

    # general spell handler
    def castSpell(self, pid, spellID):
        if spellID == "teleport":
            # newpos = self.getRandomPos(self.players[pid].pos['level'])
            self.players[pid].pos = self.getRandomPos(self.players[pid].pos['level'])

    # performs a character-special effect (assuming we add classes...)
    # default currently is a blast radius or healing effect
    def playerEffect(self, pid):
        p = self.players[pid]

        if p.effect_timeout == 0:
            p.effect_timeout = PLAYER_EFFECT_TIMEOUT

            # spawn fireballs around the player
            ## TBD - this needs to not use the items array
            if p.player_class == "mage":
                for d in ENEMY_DIRS:
                    new_d = {'level': p.pos['level'], 'r':p.pos['r'] + d['r'], 'c': p.pos['c'] + d['c']}

                    # no fire on self please
                    if d['c'] != 0 or d['r'] != 0:

                        if self.isWalkable(new_d['c'], new_d['r'], p.pos['level']):

                            self.effects.append(self.addEffect('fire', new_d))

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

    # all we have right now are apples so all we need
    # to worry about is one - if we complexify things
    # this will be trickier to manage
    def useItem(self, pid):
        if 'apple' in self.players[pid].inventory:
            apples = self.players[pid].inventory['apple']
            if apples > 0:
                apples -= 1
                return self.players[pid].updateHealth(2)
            # return True
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

    def hasEnemy(self, pid, c, r, l, atk=1):
        idx = -1
        for i in range(len(self.enemies[l])):
            e = self.enemies[l][i]
            if e.pos['c'] == c and e.pos['r'] == r and e.pos['level'] == l:
                idx = i

        if idx != -1:
            epos = self.enemies[l][idx].pos

            # update health, drop and delete if dead
            retval = self.enemies[l][idx].updateHealth(atk)
            if not retval:

                if self.enemies[l][idx]._type in LOOKUP_STATS['drops']:
                    drop = random.choice(LOOKUP_STATS['drops'][self.enemies[l][idx]._type])
                    if random.random() > drop[DROP_CHANCE_ID]:
                        self.items.append(self.addItem(drop[DROP_TYPE_ID], epos))

                del self.enemies[l][idx]
            return True
        return False


    def tryMove(self, pid, c, r):
        next_c = self.players[pid].pos['c'] + c
        next_r = self.players[pid].pos['r'] + r

        # wake up on move attempt
        self.players[pid].active = True 

        attackVal = self.hasEnemy(pid, next_c, next_r, self.players[pid].pos['level'], -self.players[pid].atk)
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
        for ek, ev in self.enemies.items():
            for v in ev:
                if v.pos['level'] == level:
                    op[v.entity_id] = v.getTransmissable()
        return json.dumps(op)
    
    def getJSONItems(self, level):
        op = {}
        for v in self.items:
            if v.pos['level'] == level:
                op[v.entity_id] = v.getTransmissable()
        return json.dumps(op)
    def getJSONEffects(self, level):
        op = {}
        for v in self.effects:
            if v.pos['level'] == level:
                op[v.entity_id] = v.getTransmissable()
        return json.dumps(op)

# TBD - turn into a db of some sort to avoid process issues
game = Game(scheduler)

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
        'effects': game.getJSONEffects(level=0),
    })

# handle player effect
@socketio.on('playereffect')
def player_effect(msg):
    global game
    if msg['playerID'] in game.players:
        game.playerEffect(msg['playerID'])

# put them to "sleep"
@socketio.on('meditateplayer')
def meditate_player(msg):
    global game
    if msg['playerID'] in game.players:
        game.meditatePlayer(msg['playerID'])

# cast a spell
@socketio.on("castspell")
def cast_spell(msg):
    global game
    if msg['playerID'] in game.players:
        game.castSpell(msg['playerID'], msg['spellID'])

# use active item
@socketio.on('useitem')
def meditate_player(msg):
    global game
    if msg['playerID'] in game.players:
        resp = game.useItem(msg['playerID'])
        if resp:
            emit('serverResponse', {'resp': 'useItemSuccess'})
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
            'effects': game.getJSONEffects(level),
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
