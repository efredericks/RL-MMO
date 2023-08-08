let KEYS = {
    'up': ['KeyK', 'ArrowUp', 'Numpad8'],
    'down': ['KeyJ', 'ArrowDown', 'Numpad2'],
    'left': ['KeyH', 'ArrowLeft', 'Numpad4'],
    'right': ['KeyL', 'ArrowRight', 'Numpad6'],

    'upleft': ['KeyY', 'Numpad7'],
    'upright': ['KeyU', 'Numpad9'],
    'downleft': ['KeyB', 'Numpad1'],
    'downright': ['KeyN', 'Numpad3'],
};

let canvas, ctx;
let gameMap, gamePlayers, gameEnemies, gameItems, gameEffects;
let myID;
let players;
let NUM_ROWS, NUM_COLS;
let tileSize = 24;
let halfTile = tileSize / 2;

let uiX, uiY;
let sounds;
let audioPlaying = false;

let MSG_TIME = 5; // duplicate from main.py

let TEXT_BG = "rgb(220,220,220)";

let MAP_OVERLAY_ACTIVE = false;

// spritesheet
let SPRITESHEET = {
    // env
    wall1: { sprite: '#', color: '#cc00cc' },
    wall2: { sprite: '#', color: '#999' },
    floor1: { sprite: '.', color: '#333' },
    floor2: { sprite: '.', color: '#666' },
    water1: { sprite: '~', color: '#008080' },
    // water2: { sprite: '☵', color: '#0011ee' },
    water2: { sprite: '~', color: '#0011ee' },
    empty: { sprite: ' ', color: '#000' },
    stairsDown: { sprite: '>', color: '#00ffff' },
    stairsUp: { sprite: '<', color: '#00ffff' },
    // tree1: { sprite: '🌲', color: '#003300' },
    // tree2: { sprite: '🌳', color: '#003300' },
    tree1: { sprite: '🛆', color: '#003300' },
    tree2: { sprite: '🛆', color: '#006600' },
    // tree: { sprite: '🛆', color: '#003300' },
    // shade1: { sprite: '░', color: '#eee' },
    // shade2: { sprite: '▒', color: '#666' },
    // shade3: { sprite: '▓', color: '#333' },

    // players
    player: { 'sprite': '@', 'color': '#ff00ffff' },
    player_meditate: { 'sprite': '@', 'color': '#ff00ffaa' },
    other_player: { 'sprite': '@', 'color': '#00ff00ff' },
    other_player_meditate: { 'sprite': '@', 'color': '#00ff00aa' },

    // monsters
    rat: { sprite: 'r', color: '#ffff00' },
    snek: { sprite: 's', color: '#ffff00' },
    gobbo: { sprite: 'g', color: '#ffff00' },

    // items
    apple: { sprite: 'a', color: '#00ff00' },

    // effects
    fire: { sprite: 'f', color: '#ff0000', max_time: 10 },
    heal: { sprite: '+', color: '#00ff00', max_time: 5 },

    // chat
    enemy_chat: { color: '#666666' },
    player_chat: { color: '#aa00aa' },
    other_player_chat: { color: '#00aa00' },
};

// pick a random index for each sound on [1,len]
let soundMaps = {
    monHit: 2,
    playerHit: 15,
    pickup: 4,
    stairs: 7,
    spawn: 1,
};
