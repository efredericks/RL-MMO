from globals import *
from pathfinding import *
import random

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

        # pathfinding
        self.pathfinding_map = GridWithWeights(game.gameMap[pos['level']], game.NUM_COLS, game.NUM_ROWS)

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
                    enemy_grid_id = (self.pos['c'], self.pos['r'])
                    player_grid_id = (player.pos['c'], player.pos['r'])
                    came_from, cost_so_far = a_star_search(self.pathfinding_map, enemy_grid_id, player_grid_id)
                    path = reconstruct_path(came_from, enemy_grid_id, player_grid_id)

                    # grab the 2nd option as the first is the entity itself
                    if len(path) > 1:
                        next_c = path[1][0]
                        next_r = path[1][1] 


                        # distance to player is the last entry
                        last_id = path[-1]

                        # walkable AND the distance is farther away
                        if last_id in cost_so_far and cost_so_far[last_id] > 1 and self.game.isWalkable(next_c, next_r, player.pos['level']):
                            self.pos['r'] = next_r
                            self.pos['c'] = next_c


                #     next_r = self.pos['r']
                #     next_c = self.pos['c']

                #     if next_r < player.pos['r']: next_r += 1
                #     if next_r > player.pos['r']: next_r -= 1
                #     if self.game.isWalkable(next_c, next_r, player.pos['level']):
                #         self.pos['r'] = next_r
                #         self.pos['c'] = next_c

                #     if next_c < player.pos['c']: next_c += 1
                #     if next_c > player.pos['c']: next_c -= 1
                #     if self.game.isWalkable(next_c, next_r, player.pos['level']) and not (player.pos['c'] == next_c and player.pos['r'] == next_r):
                #         self.pos['r'] = next_r
                #         self.pos['c'] = next_c
        else: # no target
            min_dist, min_id = self.game.CAM_NUM_COLS, "none"

            # for pk, pv in players_by_level[self.pos['level']].items():
            for pk, pv in players_by_level.items():
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

# A blob that just replicates and doesn't move
class SlimeMold(Monster):
    def __init__(self, _type, pos, entity_id=None, game=None):
        super().__init__(_type, pos, entity_id, game)

    def update(self, players_by_level):
        if random.random() > 0.96: # replicate
            neighbors = [{'level': self.pos['level'], 'c': d['c']+self.pos['c'], 'r': d['r']+self.pos['r']} for d in ENEMY_DIRS]
            n = random.choice(neighbors)

            if self.game.isWalkable(n['c'], n['r'], n['level']):
                e = self.game.addEnemy("slimeMold", n)
                if e is not None:
                    self.game.enemies[n['level']].append(e)