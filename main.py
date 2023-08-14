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
from flask_apscheduler import APScheduler

import tcod, opensimplex

import logging

import json
import random
import uuid

from copy import deepcopy

# lookup table for special tiles that are walkable but can't have things placed on them
DONT_PLACE = [
#   "<", ">", 
    'stairsDown', 'stairsUp',
    'water1',
    'tree1','tree2',
]

WALKABLE = [
#   ".", " ", "<", ">", 
    'floor1', 'floor2', 'water1', 'empty',
    'stairsDown', 'stairsUp',
    'tree1','tree2',
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

MIN_ITEMS_PER_LEVEL = 5#100#5 
MAX_ITEMS_PER_LEVEL = 50#500#10 

ENEMY_FLAVOR_PHRASES_RANDOM = [
    "!~@#!",
    "!!",
    "~!@",
    "rawr",
    "HI",
]

DRUNK_ITERATIONS = 25#50

MSG_TIME = 5
PLAYER_EFFECT_TIMEOUT = 10 # how many ticks before AOE is ready

DROP_TYPE_ID = 0
DROP_NUM_ID = 1
DROP_CHANCE_ID = 2
LOOKUP_STATS = {
    'maxHP': {
        'player': 10,
        'gobbo': 5,
        'snek': 4,
        'rat': 3,
    },
    'xp': {
        'gobbo': 3,
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

        # effects
        'fire': 'f',
        'heal': '+',
    },
    # name: list[(tuple(type, max, chance))] - random() > chance
    'drops': {
        'rat': [('apple', 1, 0.25)],
        'gobbo': [('apple', 3, 0.35)],
        'snek': [('apple', 5, 0.5)],
    },
    # effects
    # key: {attr:impact, timeout: upper}
    'effects': {
        'fire': {'hp': -3, 'timer': 10},
        'heal': {'hp': 1, 'timer': 5},
    }


}

# this is probably redundant and can be removed - just check for one of the other globals
ENTITY_NAMES = [
    # moveable
    'player',
    'gobbo', 'snek', 'rat',

    # static
    'apple',

    # effects
    'fire', 'heal'
]

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

socketio = SocketIO(app)

opensimplex.seed(1)

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

# Effects are special entities
class Effect(Entity):
    def __init__(self, _type, pos, entity_id=None, count=None):
        super().__init__(_type, pos, entity_id)

        # TBD - HANDLE THIS
        self.timer = LOOKUP_STATS['effects'][_type]['timer']

        # self.entity_id = entity_id
        # self._type = _type
        # self.pos = pos
        # self.count = count
        # self.sprite = LOOKUP_STATS['sprite'][_type]

    def getTransmissable(self):
        return {
            'type': self._type,
            'pos': self.pos,
            'count': self.count,
            'sprite': self.sprite,
            'timer': self.timer,
        }

# Entity that can move around the screen
class MoveableEntity(Entity):
    def __init__(self, _type, pos, entity_id=None, player_class=None):
        super().__init__(_type, pos, entity_id)

        # particulars
        # self._type = _type
        # self.pos = pos
        self.last_pos = pos # used to store "prior" position when going up and down stairs
        # self.entity_id = entity_id # only used for logged in players

        # stats
        self.hp = LOOKUP_STATS['maxHP'][_type]
        self.maxHP = LOOKUP_STATS['maxHP'][_type]
        self.active = True
        self.inventory = {}

        self.effect_timeout = 0
        self.atk = 1
        self.ac = 1

        # interaction - ['msg', ticksRemaining]
        self.chatlog = []

        


    # update health
    def updateHealth(self, amt):
        # print(amt,self.hp)
        self.hp += amt

        # constrain - still valid
        if self.hp > self.maxHP: 
            self.hp = self.maxHP
            return True
        # dead - return invalid
        if self.hp <= 0:
            return False
        return True


    # chat related - only 1 can be active per entity
    def addChat(self, msg):
        self.chatlog = [msg, MSG_TIME]

    def hasChat(self):
        if len(self.chatlog) > 0:
            return True
        return False

    # generic update function per entity
    def update(self):
        # next time entity can cast effect
        if self.effect_timeout > 0:
            self.effect_timeout -= 1
            # print(self.effect_timeout)

        self.updateChats()

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
            'effect_timeout': self.effect_timeout,
        }
        return retval

class Player(MoveableEntity):
    def __init__(self, _type, pos, entity_id=None, player_class=None, game=None):
        super().__init__(_type, pos, entity_id)

        # class info
        assert player_class is not None, "Error: missing reference to player class"
        self.player_class = player_class

        # reference to game map info
        assert game is not None, "Error: missing reference to game object"
        self.game = game

    def update(self):
        super().update()

class Monster(MoveableEntity):
    def __init__(self, _type, pos, entity_id=None, game=None):
        super().__init__(_type, pos, entity_id)

        # reference to game map info
        assert game is not None, "Error: missing reference to game object"
        self.game = game

        # targeting info
        self.target = None

    def setTarget(self, other_id):
        self.target = other_id

    # returns ID of target
    def getTarget(self):
        return self.target

    def removeTarget(self):
        self.target = None

    def update(self, players_by_level):
        super().update() # update generic entity things

        # TBD (follower):
        # 1 if no target, set target
        # 2 if target, follow
        # 3 if target out of range, forget
        # add a check to see what type of e this is as well
        # make follow dist a function of the lookup table!!

        tgt = self.getTarget()
        if tgt is not None and tgt in self.game.players: # we have a target
            # same level test / meditating test
            if self.game.players[tgt].pos['level'] != self.pos['level'] or not self.game.players[tgt].active:
                self.removeTarget()
            else:
                # if in range, follow
                player = self.game.players[tgt]
                d = abs(self.pos['c'] - player.pos['c']) + abs(self.pos['r'] - player.pos['r'])
                if d > self.game.CAM_NUM_COLS: # forget!
                    self.removeTarget()
                else: # follow!
                    next_r = self.pos['r']
                    next_c = self.pos['c']

                    if next_r < player.pos['r']: next_r += 1
                    if next_r > player.pos['r']: next_r -= 1
                    if self.game.isWalkable(next_c, next_r, player.pos['level']):
                        self.pos['r'] = next_r
                        self.pos['c'] = next_c

                    if next_c < player.pos['c']: next_c += 1
                    if next_c > player.pos['c']: next_c -= 1
                    if self.game.isWalkable(next_c, next_r, player.pos['level']) and not (player.pos['c'] == next_c and player.pos['r'] == next_r):
                        self.pos['r'] = next_r
                        self.pos['c'] = next_c
        else: # no target
            min_dist, min_id = self.game.CAM_NUM_COLS, "none"

            for pk, pv in players_by_level[self.pos['level']].items():
                if pv.active:
                    d = abs(self.pos['c'] - pv.pos['c']) + abs(self.pos['r'] - pv.pos['r'])
                    if d < min_dist:
                        min_dist = d
                        min_id = pv.entity_id

            # we found a target
            if min_id in self.game.players:
                self.setTarget(min_id)

                # add random flavor text if following
                if random.random() > 0.5 and not self.hasChat():
                    self.addChat(random.choice(ENEMY_FLAVOR_PHRASES_RANDOM))
            else:
                new_dir = random.choice(ENEMY_DIRS)
                new_pos = {'r': self.pos['r'] + new_dir['r'], 'c': self.pos['c'] + new_dir['c']}

                if self.game.isWalkable(new_pos['c'], new_pos['r'], self.pos['level']):
                    self.pos['r'] = new_pos['r']
                    self.pos['c'] = new_pos['c']




        # random follow
        # if random.random() > 0.0:#0.15:
        #     # get closest player
        #     # min_dist, min_id = 999, "none"
        #     min_dist, min_id = self.CAM_NUM_COLS, "none"

        #     # give the enemy some flavor
        #     if random.random() > 0.95 and not e.hasChat():
        #         e.addChat(random.choice(ENEMY_FLAVOR_PHRASES_RANDOM))

        #     # filter players on current level
        #     # players_on_level = filter(lambda l: l.pos['level'] == e.pos['level'], self.players)
        #     # print(list(players_on_level))
        #     players_on_level = {}
        #     for pk,pv in self.players.items():
        #         if pv.pos['level'] == e.pos['level']:
        #             players_on_level[pv.entity_id] = pv

        #     for pid, player in players_on_level.items():#self.players.items():
        #         if player.active:
        #             d = abs(e.pos['c'] - player.pos['c']) + abs(e.pos['r'] - player.pos['r'])
        #             print(d)
        #             if d < min_dist:
        #                 min_dist = d
        #                 min_id = pid

        #     if min_id in self.players:
        #         player = self.players[min_id]
        #         next_r = e.pos['r']
        #         next_c = e.pos['c']

        #         if next_r < player.pos['r']: next_r += 1
        #         if next_r > player.pos['r']: next_r -= 1
        #         if self.isWalkable(next_c, next_r, player.pos['level']):
        #             e.pos['r'] = next_r
        #             e.pos['c'] = next_c

        #         if next_c < player.pos['c']: next_c += 1
        #         if next_c > player.pos['c']: next_c -= 1
        #         if self.isWalkable(next_c, next_r, player.pos['level']) and not (player.pos['c'] == next_c and player.pos['r'] == next_r):
        #             e.pos['r'] = next_r
        #             e.pos['c'] = next_c

        # # random movement
        # elif random.random() > 0.5:
        #     new_dir = random.choice(ENEMY_DIRS)
        #     new_pos = {'r': e.pos['r'] + new_dir['r'], 'c': e.pos['c'] + new_dir['c']}

        #     if self.isWalkable(new_pos['c'], new_pos['r'], e.pos['level']):
        #         e.pos['r'] = new_pos['r']
        #         e.pos['c'] = new_pos['c']

        # e.update()


class Game:
    def __init__(self):


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
        self.enemies = self.initEnemies()
        self.items = self.initItems()
        self.effects = []

        # place stairs
        self.placeStairs()

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

    # update the game state
    def tick(self):
        # update where players are by level
        players_by_level = {}
        for z in range(self.NUM_LEVELS):
            players_by_level[z] = {}

        for pk, pv in self.players.items():
            players_by_level[pv.pos['level']][pv.entity_id] = pv


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
                for _ in self.enemies:
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
        for e in self.enemies:
            e.update(players_by_level)

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

    def addEffect(self, _type, pos=None):
        if pos == None:
            pos = self.getRandomPos()
        return Effect(_type, pos, str(uuid.uuid4()))

    def addEnemy(self, _type, pos):
        return Monster(_type, pos, str(uuid.uuid4()), self)
        # return MoveableEntity(_type, pos, str(uuid.uuid4()))

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
        for i in range(len(self.enemies)):
            e = self.enemies[i]
            if e.pos['c'] == c and e.pos['r'] == r and e.pos['level'] == l:
                idx = i

        if idx != -1:
            epos = self.enemies[idx].pos

            # update health, drop and delete if dead
            retval = self.enemies[idx].updateHealth(atk)
            if not retval:
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
    def getJSONEffects(self, level):
        op = {}
        for v in self.effects:
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
