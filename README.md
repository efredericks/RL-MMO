# Run instructions

# Content addition

## Enemies

## Items

## Sounds

* Add file to `assets/sounds/`
* Add number to randomly select from in `soundMaps` -- this object lists the total number of sounds that can be chosen between 1 and the max defined.
* Load in `initSounds()`
* Call via `loadSounds()` when appropriate - if waiting for a server notification then send a socket message using the `serverResponse` ID - e.g., `emit('serverResponse', {'resp': 'playerHitMonster'})`