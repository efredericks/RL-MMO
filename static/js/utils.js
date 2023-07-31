// random integer [min, max) -- https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Math/random
getRandomInt = (min, max) => {
    min = Math.ceil(min);
    max = Math.floor(max);
    return Math.floor(Math.random() * (max - min) + min);
}

// map function similar to p5.js
p5map = (n, start1, stop1, start2, stop2) => {
    return ((n - start1) / (stop1 - start1)) * (stop2 - start2) + start2
}

// https://stackoverflow.com/questions/21597644/speech-buble-html5-canvas-js
// move to bottom and recalculate a bit
// also give text a bit of padding
drawBubble = (ctx, x, y, w, h, radius) => {
    y -= halfTile;

    var r = x + w;
    var b = y + h;

    ctx.beginPath();
    ctx.strokeStyle = "black";
    ctx.lineWidth = "2";
    ctx.moveTo(x + radius, y);
    // ctx.lineTo(x + radius / 2, y - 10);
    // ctx.lineTo(x + radius * 2, y);
    ctx.lineTo(r - radius, y);
    ctx.quadraticCurveTo(r, y, r, y + radius);
    ctx.lineTo(r, y + h - radius);
    ctx.quadraticCurveTo(r, b, r - radius, b);
    ctx.lineTo(x + radius, b);
    ctx.quadraticCurveTo(x, b, x, b - radius);
    ctx.lineTo(x, y + radius);
    ctx.quadraticCurveTo(x, y, x + radius, y);
    // ctx.stroke();

    ctx.closePath();
    ctx.fillStyle = '#fff';
    ctx.strokeStyle = '#fff';
    ctx.lineJoin = "bevel";
    ctx.lineWidth = 1;
    ctx.stroke();
    ctx.fill();
}
