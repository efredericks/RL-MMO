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

RESPAWN_TIME_CHECK = 200

DROP_TYPE_ID = 0
DROP_NUM_ID = 1
DROP_CHANCE_ID = 2
LOOKUP_STATS = {
    'maxHP': {
        'player': 10,
        'gobbo': 5,
        'snek': 4,
        'rat': 3,
        'slimeMold': 2,
        'NPC': 999,
    },
    'xp': {
        'gobbo': 3,
        'snek': 2,
        'rat': 1,
        'slimeMold': 1,
        'NPC': 0,
    },
    # probably removeable as rendering is offloaded to the client now
    'sprite': {
        # moveables
        'player': '@',
        'gobbo': 'g',
        'snek': 's',
        'rat': 'r',
        'slimeMold': 'm',

        'NPC': 'P',
        'questNPC': 'P',

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
    'slimeMold',
    'NPC',
    'questNPC',

    # static
    'apple',

    # effects
    'fire', 'heal'
]