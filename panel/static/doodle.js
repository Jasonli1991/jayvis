// JAYVIS 後台塗鴉頭像：依「長期認識」觀察，程式化畫一張 owner 的醜塗鴉（滑鼠手抖風；零繪圖 token）。
// jayvisDoodle(spec, seed)：spec＝後端模型依「這回觀察」挑的臉部特徵；seed 只決定手抖亂度
// （同 spec＋同 seed 必同圖；同 spec＋不同 seed＝同一張臉、抖法不同；不同 spec＝五官明顯不同）。
// 回傳 <svg viewBox="0 0 100 100"> 的內層 markup。JAYVIS 不擅長繪畫——醜是故意的。
function jayvisDoodle(spec, seed) {
  function _norm(s) {
    s = (s && typeof s === 'object') ? s : {};
    function pick(v, allowed, def) {
      for (var i = 0; i < allowed.length; i++) if (allowed[i] === v) return v;
      return def;
    }
    return {
      mood: pick(s.mood, ['tired','stressed','focused','cheerful','calm','overwhelmed','meh'], 'tired'),
      headShape: pick(s.headShape, ['round','square','egg','potato'], 'round'),
      eyes: pick(s.eyes, ['dots','wide','tired','uneven','sparkle','dead'], 'tired'),
      eyeBags: (s.eyeBags === 1 || s.eyeBags === '1' || s.eyeBags === true) ? 1 : 0,
      brows: pick(s.brows, ['flat','raised','furrowed','uneven'], 'flat'),
      mouth: pick(s.mouth, ['smile','flat','frown','squiggle','open','smirk'], 'frown'),
      hair: pick(s.hair, ['none','tuft','messy','side','spiky','bald'], 'tuft'),
      accessory: pick(s.accessory, ['none','glasses','coffee','cap','headphones','phone'], 'none'),
      gender: pick(s.gender, ['masc','femme','neutral'], 'neutral')
    };
  }

  function xmur3(str) {
    var h = 1779033703 ^ str.length;
    for (var i = 0; i < str.length; i++) {
      h = Math.imul(h ^ str.charCodeAt(i), 3432918353);
      h = (h << 13) | (h >>> 19);
    }
    return function () {
      h = Math.imul(h ^ (h >>> 16), 2246822507);
      h = Math.imul(h ^ (h >>> 13), 3266489909);
      h ^= h >>> 16;
      return h >>> 0;
    };
  }
  function mulberry32(a) {
    return function () {
      a |= 0; a = (a + 0x6D2B79F5) | 0;
      var t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  var S = _norm(spec);
  if (!seed) seed = JSON.stringify(S);
  seed = String(seed);
  var seedFn = xmur3(seed);
  var rand = mulberry32(seedFn());

  var INK = '#2b2b2b';
  var ACC = '#c45b3c';

  function j(amt) { return (rand() * 2 - 1) * amt; }
  function n(x) { return Math.round(x * 100) / 100; }

  var out = [];
  out.push("<rect x='0' y='0' width='100' height='100' fill='#fffdf7'/>");

  function wob(pts, amt) {
    var s = '';
    for (var i = 0; i < pts.length; i++) {
      var x = n(pts[i][0] + j(amt));
      var y = n(pts[i][1] + j(amt));
      s += (i ? ' ' : '') + x + ',' + y;
    }
    return s;
  }
  function pl(pts, amt, w, fill) {
    return "<polyline points='" + wob(pts, amt) + "' fill='" + (fill || 'none') +
      "' stroke='" + INK + "' stroke-width='" + (w || 1.4) + "' stroke-linecap='round' stroke-linejoin='round'/>";
  }
  function plC(pts, amt, w, col) {
    return "<polyline points='" + wob(pts, amt) + "' fill='none' stroke='" + col +
      "' stroke-width='" + (w || 1.4) + "' stroke-linecap='round' stroke-linejoin='round'/>";
  }
  function arcPts(cx, cy, rx, ry, a0, a1, steps) {
    var p = [];
    for (var i = 0; i <= steps; i++) {
      var t = a0 + (a1 - a0) * (i / steps);
      p.push([cx + Math.cos(t) * rx, cy + Math.sin(t) * ry]);
    }
    return p;
  }

  var cx = 50, cy = 52;
  (function () {
    var hp;
    if (S.headShape === 'square') {
      hp = [[28,28],[72,27],[74,74],[70,78],[30,78],[26,73],[27,30],[33,26]];
    } else if (S.headShape === 'egg') {
      hp = arcPts(cx, cy + 2, 21, 27, -Math.PI/2 - 0.2, Math.PI*1.5 - 0.7, 16);
    } else if (S.headShape === 'potato') {
      hp = [[30,30],[42,25],[58,27],[70,33],[75,48],[72,64],[64,75],[48,78],[34,73],[26,60],[25,44],[33,31]];
    } else {
      hp = arcPts(cx, cy, 24, 25, -Math.PI/2, Math.PI*1.5 - 0.55, 18);
    }
    out.push(pl(hp, 1.1, 1.6));
    var last = hp[hp.length - 1];
    out.push(pl([[last[0], last[1]], [last[0] + 5 + j(1.5), last[1] - 4 + j(1.5)]], 1.0, 1.2));
  })();

  var eyeY = cy - 6;
  var eyeLx = cx - 9, eyeRx = cx + 9;
  var droop = (S.mood === 'tired' || S.mood === 'overwhelmed') ? 2.2 : 0;
  eyeY += droop;

  function drawEye(ex, ey, kind, big) {
    var r = big ? 4.6 : 3.4;
    if (kind === 'dots') {
      out.push("<circle cx='" + n(ex + j(0.6)) + "' cy='" + n(ey + j(0.6)) + "' r='1.3' fill='" + INK + "'/>");
    } else if (kind === 'wide') {
      out.push(pl(arcPts(ex, ey, r, r, 0, Math.PI*2, 12), 0.7, 1.3));
      out.push("<circle cx='" + n(ex + j(0.7)) + "' cy='" + n(ey + j(0.7)) + "' r='1.1' fill='" + INK + "'/>");
    } else if (kind === 'tired') {
      out.push(pl(arcPts(ex, ey, 4, 2.6, Math.PI + 0.2, Math.PI*2 - 0.2, 8), 0.6, 1.3));
      out.push(pl([[ex - 2.4, ey + 0.6], [ex + 2.4, ey + 0.4]], 0.6, 1.2));
    } else if (kind === 'sparkle') {
      out.push(pl(arcPts(ex, ey, r, r, 0, Math.PI*2, 12), 0.7, 1.3));
      out.push(plC([[ex, ey - 2.4], [ex, ey + 2.4]], 0.4, 0.9, ACC));
      out.push(plC([[ex - 2.4, ey], [ex + 2.4, ey]], 0.4, 0.9, ACC));
      out.push(plC([[ex - 1.6, ey - 1.6], [ex + 1.6, ey + 1.6]], 0.4, 0.7, ACC));
    } else if (kind === 'dead') {
      out.push(pl([[ex - 2.6, ey - 2.6], [ex + 2.6, ey + 2.6]], 0.6, 1.3));
      out.push(pl([[ex + 2.6, ey - 2.6], [ex - 2.6, ey + 2.6]], 0.6, 1.3));
    } else {
      out.push(pl(arcPts(ex, ey, 2.6, 2.6, 0, Math.PI*2, 10), 0.7, 1.3));
      out.push("<circle cx='" + n(ex) + "' cy='" + n(ey) + "' r='0.9' fill='" + INK + "'/>");
    }
  }

  if (S.eyes === 'uneven') {
    drawEye(eyeLx, eyeY - 1.5, 'wide', false);
    out.push("<circle cx='" + n(eyeRx + j(0.6)) + "' cy='" + n(eyeY + 2.2 + j(0.6)) + "' r='1.2' fill='" + INK + "'/>");
  } else {
    drawEye(eyeLx, eyeY, S.eyes, S.eyes === 'wide');
    drawEye(eyeRx, eyeY, S.eyes, S.eyes === 'wide');
  }

  if (S.eyeBags === 1) {
    out.push(pl(arcPts(eyeLx, eyeY + 4, 3.4, 1.8, 0.25, Math.PI - 0.25, 7), 0.5, 1.0));
    out.push(pl(arcPts(eyeRx, eyeY + 4, 3.4, 1.8, 0.25, Math.PI - 0.25, 7), 0.5, 1.0));
  }

  var bY = eyeY - 6;
  function brow(bx, kind, side) {
    if (kind === 'raised') {
      out.push(pl(arcPts(bx, bY - 1.5, 4, 2.2, Math.PI + 0.3, Math.PI*2 - 0.3, 6), 0.5, 1.2));
    } else if (kind === 'furrowed') {
      var inner = bx + side * 2.5;
      var outer = bx - side * 3;
      out.push(pl([[outer, bY - 1.6], [inner, bY + 1.8]], 0.6, 1.3));
    } else if (kind === 'uneven') {
      if (side < 0) out.push(pl([[bx - 3.5, bY + 1.5], [bx + 3.5, bY - 1.5]], 0.6, 1.2));
      else out.push(pl([[bx - 3.5, bY - 2.5], [bx + 3.5, bY - 2.2]], 0.6, 1.2));
    } else {
      out.push(pl([[bx - 3.5, bY], [bx + 3.5, bY + 0.2]], 0.6, 1.2));
    }
  }
  brow(eyeLx, S.brows, -1);
  brow(eyeRx, S.brows, 1);

  out.push(pl([[cx - 1, cy + 1], [cx - 1.5, cy + 3.5], [cx + 1.2, cy + 3.6]], 0.6, 1.1));

  var mY = cy + 11;
  (function () {
    var m = S.mouth;
    if (m === 'smile') {
      out.push(pl(arcPts(cx, mY - 2, 8, 5, 0.25, Math.PI - 0.25, 9), 0.7, 1.4));
    } else if (m === 'frown') {
      out.push(pl(arcPts(cx, mY + 3, 8, 5, Math.PI + 0.25, Math.PI*2 - 0.25, 9), 0.7, 1.4));
    } else if (m === 'flat') {
      out.push(pl([[cx - 7, mY], [cx - 2, mY + 0.4], [cx + 3, mY - 0.3], [cx + 7, mY]], 0.8, 1.4));
    } else if (m === 'squiggle') {
      out.push(pl([[cx - 8, mY], [cx - 4, mY - 2.5], [cx - 1, mY + 2.5], [cx + 2, mY - 2.5], [cx + 5, mY + 2.5], [cx + 8, mY]], 0.7, 1.3));
    } else if (m === 'open') {
      out.push(pl(arcPts(cx, mY, 5, 4, 0, Math.PI*2, 12), 0.8, 1.4));
    } else if (m === 'smirk') {
      out.push(pl([[cx - 7, mY + 2], [cx - 1, mY + 1], [cx + 5, mY - 1.5], [cx + 8, mY - 3.5]], 0.8, 1.4));
    }
  })();

  (function () {
    var m = S.mood;
    if (m === 'stressed') {
      out.push(pl([[cx - 1.5, bY - 2], [cx - 1.5, bY + 1]], 0.4, 0.8));
      out.push(pl([[cx + 1.5, bY - 2], [cx + 1.5, bY + 1]], 0.4, 0.8));
      out.push(plC([[cx + 18, cy - 10], [cx + 19.5, cy - 6.5], [cx + 17, cy - 5.5], [cx + 16.5, cy - 8]], 0.4, 1.0, ACC));
    } else if (m === 'overwhelmed') {
      var sp = [];
      for (var i = 0; i <= 16; i++) {
        var t = i / 16 * Math.PI * 3;
        var rr = 0.6 + i * 0.28;
        sp.push([cx + 18 + Math.cos(t) * rr, cy - 12 + Math.sin(t) * rr]);
      }
      out.push(plC(sp, 0.4, 0.9, ACC));
    } else if (m === 'tired') {
      out.push(plC([[cx + 14, cy + 2], [cx + 15.5, cy + 5], [cx + 13, cy + 6], [cx + 12.5, cy + 3.5]], 0.4, 0.9, ACC));
    } else if (m === 'cheerful') {
      out.push(pl([[cx - 14, cy + 4], [cx - 12, cy + 3]], 0.4, 1.0));
      out.push(pl([[cx + 12, cy + 3], [cx + 14, cy + 4]], 0.4, 1.0));
    } else if (m === 'focused') {
      out.push(pl([[eyeLx - 3, eyeY + 0.5], [eyeLx + 3, eyeY + 0.5]], 0.3, 0.8));
      out.push(pl([[eyeRx - 3, eyeY + 0.5], [eyeRx + 3, eyeY + 0.5]], 0.3, 0.8));
    }
  })();

  var topY = (S.headShape === 'square') ? 27 : cy - 25;
  (function () {
    var h = S.hair;
    if (h === 'none') return;
    if (h === 'tuft') {
      out.push(pl([[cx - 3, topY + 1], [cx - 2, topY - 5], [cx, topY], [cx + 1, topY - 6], [cx + 3, topY + 1]], 0.6, 1.2));
    } else if (h === 'messy') {
      var mp = [];
      for (var i = 0; i <= 18; i++) {
        var px = cx - 18 + i * 2;
        mp.push([px, topY + ((i % 2) ? -3 : 2)]);
      }
      out.push(pl(mp, 1.3, 1.0));
    } else if (h === 'side') {
      out.push(pl([[cx - 20, topY + 3], [cx - 8, topY - 3], [cx + 6, topY - 1], [cx + 18, topY + 5]], 0.8, 1.3));
      out.push(pl([[cx - 14, topY - 1], [cx + 2, topY - 4]], 0.6, 1.0));
    } else if (h === 'spiky') {
      var sp = [];
      for (var i = 0; i <= 8; i++) {
        var px = cx - 18 + i * 4.5;
        sp.push([px, (i % 2) ? topY - 7 : topY + 2]);
      }
      out.push(pl(sp, 0.8, 1.2));
    } else if (h === 'bald') {
      out.push(pl([[cx - 4, topY + 4], [cx - 1, topY + 2]], 0.3, 0.8));
      out.push(pl([[cx - 22, cy - 4], [cx - 24, cy - 8]], 0.6, 1.0));
      out.push(pl([[cx + 22, cy - 4], [cx + 24, cy - 8]], 0.6, 1.0));
    }
  })();

  (function () {
    var a = S.accessory;
    if (a === 'none') return;
    if (a === 'glasses') {
      out.push(pl(arcPts(eyeLx, eyeY, 5, 4.5, 0, Math.PI*2, 11), 0.6, 1.2));
      out.push(pl(arcPts(eyeRx, eyeY, 5, 4.5, 0, Math.PI*2, 11), 0.6, 1.2));
      out.push(pl([[eyeLx + 5, eyeY], [eyeRx - 5, eyeY]], 0.5, 1.1));
    } else if (a === 'coffee') {
      var cupX = 84, cupY = 60;
      out.push(plC([[cupX - 6, cupY - 6], [cupX - 7, cupY + 7], [cupX + 6, cupY + 8], [cupX + 6, cupY - 5], [cupX - 5, cupY - 6.5]], 0.7, 1.3, ACC));
      out.push(plC(arcPts(cupX + 7, cupY + 1, 3, 3.5, -1.1, 1.3, 6), 0.5, 1.1, ACC));
      out.push(plC([[cupX - 3, cupY - 9], [cupX - 2.5, cupY - 11]], 0.4, 0.8, ACC));
      out.push(plC([[cupX + 1, cupY - 9], [cupX + 1.5, cupY - 11]], 0.4, 0.8, ACC));
    } else if (a === 'cap') {
      out.push(pl([[cx - 18, topY + 2], [cx - 16, topY - 6], [cx + 2, topY - 9], [cx + 16, topY - 4], [cx + 18, topY + 2]], 0.7, 1.4));
      out.push(pl([[cx + 16, topY - 1], [cx + 27, topY + 1], [cx + 26, topY + 3], [cx + 15, topY + 3]], 0.7, 1.2));
    } else if (a === 'headphones') {
      out.push(pl(arcPts(cx, cy - 2, 26, 27, Math.PI + 0.35, Math.PI*2 - 0.35, 12), 0.6, 1.5));
      out.push(pl([[cx - 26, cy - 4], [cx - 23, cy - 4], [cx - 22, cy + 4], [cx - 25, cy + 4], [cx - 26, cy - 3]], 0.5, 1.4));
      out.push(pl([[cx + 26, cy - 4], [cx + 23, cy - 4], [cx + 22, cy + 4], [cx + 25, cy + 4], [cx + 26, cy - 3]], 0.5, 1.4));
    } else if (a === 'phone') {
      out.push(pl([[cx + 14, cy + 14], [cx + 24, cy + 12], [cx + 27, cy + 27], [cx + 17, cy + 29], [cx + 14, cy + 15]], 0.6, 1.3));
      out.push(pl(arcPts(cx + 20.5, cy + 25, 1, 1, 0, Math.PI*2, 6), 0.3, 0.8));
    }
  })();

  // 性別線索（JAYVIS 先用 owner 名字粗判；neutral 不加）：femme＝側邊長髮框臉＋睫毛，masc＝下巴鬍渣。
  (function () {
    var g = S.gender;
    if (g === 'femme') {
      out.push(pl([[cx - 19, topY + 7], [cx - 23, cy + 2], [cx - 19, cy + 18]], 1.0, 1.3));
      out.push(pl([[cx + 19, topY + 7], [cx + 23, cy + 2], [cx + 19, cy + 18]], 1.0, 1.3));
      out.push(pl([[eyeLx - 4, eyeY - 1], [eyeLx - 6.5, eyeY - 2.6]], 0.4, 0.9));
      out.push(pl([[eyeRx + 4, eyeY - 1], [eyeRx + 6.5, eyeY - 2.6]], 0.4, 0.9));
    } else if (g === 'masc') {
      for (var i = 0; i < 7; i++) {
        out.push("<circle cx='" + n(cx - 9 + i * 3 + j(1)) + "' cy='" + n(cy + 20 + j(1.5)) +
                 "' r='0.5' fill='" + INK + "'/>");
      }
    }
  })();

  return out.join('');
}
