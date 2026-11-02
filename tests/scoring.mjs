import assert from 'node:assert/strict';
import {scoreHand,totalScores} from '../frontend/js/anotador-rules.js';
const base={bidder:0,cardsA:100,last:0,capote:null,canteTeam:'none',counts:[0,0,0,0,0],bolot:[0,0]};
const cases=[
 ['normal',{},[110,52]],
 ['last B',{last:1},[100,62]],
 ['placed',{cardsA:60},[0,162]],
 ['tie placed',{cardsA:81,last:1,canteTeam:'0',counts:[0,0,0,0,0],bolot:[0,0]},[0,162]],
 ['cante rescue',{cardsA:70,canteTeam:'0',counts:[1,0,0,0,0]},[100,82]],
 ['lost bidder cantes',{cardsA:40,canteTeam:'0',counts:[1,0,0,0,0]},[0,162]],
 ['opponent cantes',{cardsA:40,canteTeam:'1',counts:[0,1,0,0,0]},[0,212]],
 ['bolot',{bolot:[1,0]},[130,52]],
 ['capote bidder',{cardsA:152,capote:0},[252,0]],
 ['capote rival',{cardsA:0,last:1,capote:1},[0,252]],
 ['capote with cante',{cardsA:152,capote:0,canteTeam:'0',counts:[1,0,0,0,0]},[272,0]],
 ['capote loses via cantes',{cardsA:152,capote:0,canteTeam:'1',counts:[0,0,0,0,1]},[0,362]],
];
for(const [label,mods,expected] of cases)assert.deepEqual(scoreHand({...base,...mods}).awarded,expected,label);
for(const cardsA of [-1,153,3.5,NaN])assert.throws(()=>scoreHand({...base,cardsA}));
assert.throws(()=>scoreHand({...base,capote:0}));assert.throws(()=>scoreHand({...base,bolot:[2,1]}));
assert.deepEqual(totalScores([base,base]),[220,104]);
console.log(`${cases.length} scoring cases + 6 validation/total checks passed`);

